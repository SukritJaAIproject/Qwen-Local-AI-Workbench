"""Local Docker backend for the project Python kernel.

The immutable image ID is set by the installer. Only a local Linux engine is
used. A failed probe/start never executes code on the Windows host.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import stat
import subprocess
import threading
import time

HERE = Path(__file__).resolve().parent
CONFIG = HERE / 'python-sandbox.json'
CREATE_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0
HOST = 'npipe:////./pipe/docker_engine'
IMAGE_ID = re.compile(r'^sha256:[0-9a-f]{64}$')
CONTAINER_NAME = re.compile(r'^qwen-py-[0-9a-f]{24}$')
_CACHE = None
_CACHE_UNTIL = 0.0
_CACHE_KEY = None
_LOCK = threading.Lock()


def _cli() -> str:
    choices = [
        Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/DockerDesktop/resources/bin/docker.exe',
        Path(r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'),
    ]
    return next((str(p) for p in choices if p.is_file()), '')


def _env(cli: str) -> dict:
    keep = {'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'PATHEXT',
            'TEMP', 'TMP', 'LOCALAPPDATA', 'APPDATA', 'USERPROFILE',
            'PROGRAMDATA', 'USERNAME', 'USERDOMAIN'}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep}
    root = env.get('SYSTEMROOT') or env.get('SystemRoot') or r'C:\Windows'
    env['PATH'] = os.pathsep.join((str(Path(cli).parent), os.path.join(root, 'System32'), root))
    return env


class Backend:
    def __init__(self, cli: str, image: str):
        if not IMAGE_ID.fullmatch(image):
            raise ValueError('Invalid sandbox image ID')
        self.cli, self.image = cli, image

    def run_cli(self, args, timeout=8):
        result = subprocess.run([self.cli, '--host', HOST, *args],
                                capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout, cwd=str(HERE),
                                env=_env(self.cli), creationflags=CREATE_NO_WINDOW)
        if result.returncode:
            raise RuntimeError('The local Docker engine or sandbox image is unavailable')
        return result.stdout.strip()

    def available(self):
        info = json.loads(self.run_cli(['info', '--format', '{{json .}}']))
        if info.get('OSType') != 'linux':
            raise RuntimeError('Python sandbox requires the local Linux container engine')
        image = json.loads(self.run_cli(['image', 'inspect', self.image]))[0]
        if image.get('Id') != self.image or image.get('Config', {}).get('User') != '10001:10001':
            raise RuntimeError('Sandbox image validation failed')
        return self

    @staticmethod
    def _mount(path: str, destination: str, readonly=False):
        # Docker parses --mount as CSV. Reject delimiters rather than allowing
        # a host path to add another mount option.
        if ',' in path or '\n' in path or '\r' in path:
            raise RuntimeError('Unsupported project path for the Docker sandbox')
        source = os.path.abspath(path)
        if os.path.realpath(source) != source:
            raise RuntimeError('Sandbox folders must not be links or junctions')
        for root, dirs, files in os.walk(source, followlinks=False):
            for name in dirs + files:
                item = os.path.join(root, name)
                attrs = getattr(os.lstat(item), 'st_file_attributes', 0)
                if os.path.islink(item) or attrs & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                    raise RuntimeError('Sandbox folders must not contain links or junctions')
        return 'type=bind,src=%s,dst=%s%s' % (source, destination, ',readonly' if readonly else '')

    def command(self, workdir: str, outdir: str, idle: int):
        name = 'qwen-py-' + secrets.token_hex(12)
        args = [self.cli, '--host', HOST, 'run', '--rm', '-i', '--init',
                '--name', name, '--label', 'qwen.owner=python-sandbox',
                '--pull=never', '--network=none', '--read-only',
                '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
                '--user=10001:10001', '--pids-limit=256',
                '--memory=1g', '--memory-swap=1g', '--cpus=2',
                '--ipc=private', '--log-driver=none',
                '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=256m,mode=1777',
                '--tmpfs', '/runtime:rw,nosuid,nodev,noexec,size=32m,mode=700,uid=10001,gid=10001',
                '--mount', self._mount(workdir, '/work'),
                '--mount', self._mount(outdir, '/outputs')]
        attachments = os.path.join(os.path.dirname(workdir), 'attachments')
        if os.path.isdir(attachments):
            args.extend(['--mount', self._mount(attachments, '/attachments', readonly=True)])
        args.extend([self.image, '--workdir', '/work', '--outdir', '/outputs',
                     '--runtime', '/runtime', '--idle', str(idle), '--edge', ''])
        return name, args, _env(self.cli)

    def verify(self, name: str):
        if not CONTAINER_NAME.fullmatch(name):
            raise RuntimeError('Invalid sandbox container name')
        doc = json.loads(self.run_cli(['inspect', name]))[0]
        host = doc['HostConfig']
        mounts = doc.get('Mounts') or []
        allowed = {'/work': True, '/outputs': True, '/attachments': False}
        good_mounts = (len(mounts) in (2, 3)
                       and {m['Destination'] for m in mounts} >= {'/work', '/outputs'}
                       and all(m['Type'] == 'bind' and m['Destination'] in allowed
                               and m['RW'] == allowed[m['Destination']] for m in mounts))
        safe = (doc.get('Image') == self.image and doc['Config']['User'] == '10001:10001'
                and host.get('NetworkMode') == 'none' and host.get('ReadonlyRootfs') is True
                and host.get('Privileged') is False and 'ALL' in (host.get('CapDrop') or [])
                and any(s.startswith('no-new-privileges') for s in host.get('SecurityOpt') or [])
                and host.get('Memory') == 1073741824 and host.get('MemorySwap') == 1073741824
                and host.get('NanoCpus') == 2000000000 and host.get('PidsLimit') == 256
                and host.get('PidMode') in ('', 'private')
                and host.get('IpcMode') == 'private' and not host.get('PortBindings')
                and good_mounts)
        if not safe:
            raise RuntimeError('Sandbox isolation verification failed; no user code was executed')
        return {'backend': 'docker', 'image': self.image, 'container': name,
                'network': 'none', 'memory_mb': 1024, 'cpus': 2,
                'project_paths': ['/work', '/outputs', '/attachments']}

    def remove(self, name: str):
        if CONTAINER_NAME.fullmatch(name):
            try:
                self.run_cli(['rm', '--force', name], timeout=12)
            except Exception:
                pass


def active():
    """Return a verified backend or None. None preserves the host review gate."""
    global _CACHE, _CACHE_KEY, _CACHE_UNTIL
    if os.environ.get('QWEN_PY_SANDBOX', '').lower() in ('off', '0', 'false'):
        return None
    path = Path(os.environ.get('QWEN_PY_SANDBOX_CONFIG') or CONFIG)
    try:
        key = (str(path), path.stat().st_mtime_ns)
        with _LOCK:
            if key == _CACHE_KEY and time.monotonic() < _CACHE_UNTIL:
                return _CACHE
            config = json.loads(path.read_text(encoding='utf-8-sig'))
            cli = _cli()
            backend = Backend(cli, str(config.get('image_id') or '')) if config.get('enabled') is True and cli else None
            if backend is not None:
                backend.available()
            _CACHE, _CACHE_KEY, _CACHE_UNTIL = backend, key, time.monotonic() + 15
            return backend
    except Exception:
        return None
