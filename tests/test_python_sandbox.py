"""Real-container tests for automatic Python execution and its host fallback.

All project data, audit logs and credentials are synthetic and temporary.
The image is built separately; this suite never installs software or changes
the production sandbox configuration.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_security_common as C

guard = C.import_local('guard')
tools = C.import_local('tools_python')
fast = C.import_local('tools_fast')
backend_module = C.import_local('python_sandbox')


def _image_id():
    """ID of the locally built sandbox image; skip the Docker suites when the image was never built."""
    path = Path(C.MCP_LOCAL) / 'python-sandbox' / 'image-id.txt'
    try:
        return path.read_text(encoding='utf-8-sig').strip()
    except OSError:
        raise unittest.SkipTest('Docker sandbox image not built (%s missing)' % path)


def _sandbox_ready(config):
    """True when the Docker backend for this config is usable (same check the MCP server does)."""
    keys = ('QWEN_PY_SANDBOX', 'QWEN_PY_SANDBOX_CONFIG')
    saved = {k: os.environ.get(k) for k in keys}
    os.environ['QWEN_PY_SANDBOX'] = 'on'
    os.environ['QWEN_PY_SANDBOX_CONFIG'] = str(config)
    try:
        return backend_module.active() is not None
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class DockerPythonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image = _image_id()                 # may skip: before any state is changed
        cls.saved_env = {k: os.environ.get(k) for k in
                         ('QWEN_PY_SANDBOX', 'QWEN_PY_SANDBOX_CONFIG', 'OPENAI_API_KEY')}
        cls.old_runtime = tools.RUNTIME_BASE
        tools.RUNTIME_BASE = Path(C.TMP) / 'sandbox-runtime-secrets'
        cls.config = Path(C.TMP) / 'python-sandbox.json'
        cls.config.write_text(json.dumps({'enabled': True, 'image_id': cls.image}), encoding='utf-8')
        os.environ['QWEN_PY_SANDBOX'] = 'on'
        os.environ['QWEN_PY_SANDBOX_CONFIG'] = str(cls.config)
        os.environ['OPENAI_API_KEY'] = 'SYNTHETIC-MUST-NOT-REACH-CONTAINER'
        cls.backend = backend_module.active()
        if cls.backend is None:
            # Docker Desktop not running / image missing: skip like the other live suites (the Doctor page
            # reports Docker separately). tearDownClass does not run after a skip, so restore state here.
            cls.tearDownClass()
            raise unittest.SkipTest('Docker sandbox unavailable (Docker engine not running or image missing)')

    @classmethod
    def tearDownClass(cls):
        tools.shutdown_all()
        tools.RUNTIME_BASE = cls.old_runtime
        for key, value in cls.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def setUp(self):
        self.slug = 'sandbox-test-' + os.urandom(4).hex()

    def tearDown(self):
        tools.shutdown_all()

    def execute(self, code, timeout=60, slug=None):
        with guard.project_scope(slug or self.slug):
            result = fast.local_do(action='python', code=code, timeout=timeout)
        self.assertNotIn('confirm_token=', result, result)
        self.assertNotIn('เปิด Docker sandbox ไม่สำเร็จ', result, result)
        return result

    def test_automatic_execution_isolated_environment_and_real_limits(self):
        result = self.execute("import os, json, pathlib\nprint(json.dumps({'uid':os.getuid(),'cwd':os.getcwd(),'key':os.environ.get('OPENAI_API_KEY'),'socket':pathlib.Path('/var/run/docker.sock').exists()}))")
        self.assertIn('"uid": 10001', result)
        self.assertIn('"cwd": "/work"', result)
        self.assertIn('"key": null', result)
        self.assertIn('"socket": false', result)
        kernel = tools._KERNELS[self.slug]
        self.assertEqual(kernel.backend, 'docker')
        verified = self.backend.verify(kernel.container)
        self.assertEqual(verified['memory_mb'], 1024)
        self.assertEqual(verified['cpus'], 2)

    def test_variables_persist_and_other_projects_are_isolated(self):
        self.assertIn('84', self.execute('answer = 84\nprint(answer)'))
        self.assertIn('84', self.execute('print(answer)'))
        other = self.slug + '-other'
        self.assertIn('NO_OTHER_VARIABLE', self.execute("print(globals().get('answer', 'NO_OTHER_VARIABLE'))", slug=other))
        path = Path(guard.project_dir(other)) / 'work' / 'other-project.txt'
        path.write_text('OTHER_PROJECT', encoding='utf-8')
        result = self.execute("from pathlib import Path\nprint('OTHER_PROJECT_VISIBLE', Path('/other-project').exists())\nprint('HOST_PARENT_VISIBLE', Path('/work/../" + other + "').exists())")
        self.assertIn('OTHER_PROJECT_VISIBLE False', result)
        self.assertIn('HOST_PARENT_VISIBLE False', result)

    def test_attachments_readonly_and_project_outputs_writable(self):
        attachments = Path(guard.project_dir(self.slug)) / 'attachments'
        attachments.mkdir(parents=True, exist_ok=True)
        source = attachments / 'input.csv'
        source.write_text('value\n12\n7\n', encoding='utf-8')
        code = """import pandas as pd
from pathlib import Path
print('CSV_SUM', pd.read_csv('/attachments/input.csv')['value'].sum())
try:
    Path('/attachments/input.csv').write_text('CHANGED')
except OSError:
    print('ATTACHMENTS_READONLY')
Path('/outputs/result.txt').write_text('PROJECT_RESULT')
"""
        result = self.execute(code)
        self.assertIn('CSV_SUM 19', result)
        self.assertIn('ATTACHMENTS_READONLY', result)
        self.assertEqual(source.read_text(), 'value\n12\n7\n')
        self.assertEqual((attachments.parent / 'outputs/result.txt').read_text(), 'PROJECT_RESULT')
        self.assertIn('/_qwen/out/result.txt', result)

    def test_network_and_root_filesystem_are_blocked(self):
        code = """import socket
from pathlib import Path
s = socket.socket()
s.settimeout(0.4)
try:
    s.connect(('1.1.1.1', 443))
    print('NETWORK_UNEXPECTEDLY_OPEN')
except OSError:
    print('NETWORK_BLOCKED')
finally:
    s.close()
try:
    Path('/etc/qwen-test-write').write_text('probe')
    print('ROOT_UNEXPECTEDLY_WRITABLE')
except OSError:
    print('ROOT_READONLY')
"""
        result = self.execute(code)
        self.assertIn('NETWORK_BLOCKED', result)
        self.assertIn('ROOT_READONLY', result)
        self.assertNotIn('UNEXPECTEDLY', result)

    def test_matplotlib_and_excel_artifacts(self):
        result = self.execute("import pandas as pd\nimport matplotlib.pyplot as plt\npd.DataFrame({'value':[12,7]}).to_excel('/outputs/example.xlsx', index=False)\nplt.plot([1,2,3], [12,7,84]); plt.title('ทดสอบ Python'); plt.show()")
        outputs = Path(guard.project_dir(self.slug)) / 'outputs'
        images = list(outputs.glob('fig-*.png'))
        self.assertEqual(len(images), 1, result)
        self.assertGreater(images[0].stat().st_size, 1000)
        self.assertEqual(images[0].read_bytes()[:8], b'\x89PNG\r\n\x1a\n')
        self.assertTrue((outputs / 'example.xlsx').is_file())
        self.assertIn('![fig](/_qwen/out/', result)
        self.assertNotIn('Glyph', result, 'Thai font must exist in the container')

    def test_timeout_and_cleanup(self):
        self.assertIn('ก่อน', self.execute("kept = 'ก่อน'\nprint(kept)"))
        result = self.execute('import time\ntime.sleep(30)', timeout=5)
        self.assertIn('หมดเวลา', result)
        self.assertIn('ก่อน', self.execute('print(kept)'))
        kernel = tools._KERNELS[self.slug]
        name = kernel.container
        kernel.stop()
        self.assertFalse(kernel.alive())
        with self.assertRaises(RuntimeError):
            self.backend.run_cli(['inspect', name])

    def test_host_kernel_cannot_receive_automatic_sandbox_code(self):
        with guard.project_scope(self.slug):
            workdir, outdir, runtime = tools._dirs(self.slug)
            first = tools._run(self.slug, 'host_only = True\nprint("HOST_READY")', 60, workdir, outdir, runtime)
        self.assertIn('HOST_READY', first)
        self.assertEqual(tools._KERNELS[self.slug].backend, 'host')
        result = self.execute("print('HOST_STATE_LEAK', globals().get('host_only', False))")
        self.assertIn('HOST_STATE_LEAK False', result)
        self.assertEqual(tools._KERNELS[self.slug].backend, 'docker')

    def test_failed_container_start_never_falls_back_to_host(self):
        with patch.object(backend_module.Backend, 'command', side_effect=RuntimeError('Synthetic Docker failure')):
            with guard.project_scope(self.slug):
                result = tools.python_exec(code="open('unapproved.txt','w').write('must not run')")
        self.assertIn('ยังไม่ได้รันโค้ดบนเครื่องจริง', result)
        self.assertFalse((Path(guard.project_dir(self.slug)) / 'work/unapproved.txt').exists())
        self.assertTrue(tools._KERNELS[self.slug]._log.closed)

    def test_invalid_image_preserves_host_confirmation_and_no_kernel(self):
        unavailable = Path(C.TMP) / 'unavailable-sandbox.json'
        unavailable.write_text(json.dumps({'enabled': True, 'image_id': 'sha256:' + '0'*64}), encoding='utf-8')
        with patch.dict(os.environ, {'QWEN_PY_SANDBOX_CONFIG': str(unavailable)}):
            with guard.project_scope(self.slug):
                result = tools.python_exec(code="print('must wait for human approval')")
        self.assertIn('confirm_token', result)
        self.assertIn('REVIEW', result)
        self.assertNotIn(self.slug, tools.kernel_status())


class DockerHTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = _image_id()
        cls.config = Path(C.TMP) / 'http-python-sandbox.json'
        cls.config.write_text(json.dumps({'enabled': True, 'image_id': image}), encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            cls.port = sock.getsockname()[1]
        env = C.clean_env()
        env.update(QWEN_PY_SANDBOX='on', QWEN_PY_SANDBOX_CONFIG=str(cls.config),
                   QWEN_PY_RUNTIME=str(Path(C.TMP) / 'http-runtime-secrets'))
        cls.log = open(Path(C.TMP) / 'sandbox-http.log', 'wb')
        cls.proc = subprocess.Popen([sys.executable, str(Path(C.MCP_LOCAL) / 'server.py'), str(cls.port)],
                                    env=env, cwd=C.MCP_LOCAL, stdout=cls.log, stderr=cls.log,
                                    stdin=subprocess.DEVNULL, creationflags=0x08000000)
        deadline = time.monotonic() + 30
        while not C.port_in_use(cls.port):
            if cls.proc.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Isolated sandbox HTTP server did not start')
            time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(15)
        cls.log.close()

    def test_automatic_python_over_authenticated_http(self):
        if not _sandbox_ready(self.config):
            self.skipTest('Docker sandbox unavailable (Docker engine not running or image missing)')
        for path, name, args in (
            ('/fast/', 'local_do', {'action': 'python', 'code': "import os\nprint('HTTP_SANDBOX', os.getuid(), 12*7)"}),
            ('/mcp/', 'python_exec', {'code': "print('HTTP_SANDBOX_AGAIN', 84)"}),
        ):
            status, _, raw = C.rpc(self.port, path + C.PROJECT_OF_ALLOWED_ORIGIN, 'tools/call',
                                   {'name': name, 'arguments': args}, origin=C.ALLOWED_ORIGIN)
            self.assertEqual(status, 200)
            result = C.tool_text(raw)
            self.assertIn('HTTP_SANDBOX', result)
            self.assertIn('84', result)
            self.assertIn('Docker sandbox', result)
            self.assertNotIn('confirm_token=', result)

    def test_http_auth_and_project_scope_still_enforced(self):
        path = '/fast/' + C.PROJECT_OF_ALLOWED_ORIGIN
        params = {'name': 'local_do', 'arguments': {'action': 'python', 'code': "print('UNAUTHORIZED')"}}
        for origin, token in ((C.ALLOWED_ORIGIN, None), ('http://evil.example', C.TOKEN),
                              ('http://127.0.0.1:8104', C.TOKEN)):
            status, _, _ = C.rpc(self.port, path, 'tools/call', params, origin=origin, token=token)
            self.assertIn(status, (401, 403))


if __name__ == '__main__':
    unittest.main()
