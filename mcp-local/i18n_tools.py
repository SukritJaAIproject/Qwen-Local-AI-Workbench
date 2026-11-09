# -*- coding: utf-8 -*-
"""Messages of the local tools in the language of the interface — Thai (source), English, Japanese, Chinese.

The tools were written with Thai messages. ``TR("...")`` wraps a message at the place it is produced: when the
interface language (``projects/settings.json`` → ``lang``) is Thai the text is returned as written; for another
language the catalogue in ``i18n_catalog.py`` is consulted (keyed by the Thai text), falling back to English and
then to the Thai source, so an untranslated message is never lost. ``%s``/``%d`` templates are translated before
formatting (``TR("ไม่พบไฟล์ %s") % name``), which keeps every placeholder.

Tool descriptions (``tools/list``) and the server instructions are translated on the way out by
``localize_tools()`` / ``TR`` in server.py — the module constants that define the tools stay Thai.

The language is read from settings.json at most every two seconds (mtime check), so a switch in the UI reaches
the tools without a restart. ``QWEN_SETTINGS_FILE`` overrides the path (tests, demo hub).
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
import threading
import time
from pathlib import Path

LANGS = ("th", "en", "ja", "zh")
DEFAULT_LANG = "th"
FALLBACK_LANG = "en"
SETTINGS_FILE = Path(os.environ.get("QWEN_SETTINGS_FILE") or r"C:\LLM\projects\settings.json")
_CHECK_EVERY_S = 2.0


def load_module_by_path(name, path):
    """Import ``path`` as module ``name`` without touching sys.path (a cached module of that name is reused).

    The hub and the web-search server load this module (and this module loads the catalogue) this way, so no
    folder is pushed in front of sys.path and no module name of mcp-local can shadow their own. Modules of this
    folder that are themselves loaded from outside — netguard (web search), tools_memory (hub), kernel_runner
    (``python -I`` under anaconda) — fall back to the same by-path import of ``i18n_tools`` when the bare import fails.
    """
    path = str(path)
    mod = sys.modules.get(name)
    have = getattr(mod, "__file__", None) if mod is not None else None
    if have and os.path.normcase(os.path.realpath(have)) == os.path.normcase(os.path.realpath(path)):
        return mod
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    register = name not in sys.modules
    if register:
        sys.modules[name] = mod
    try:
        spec.loader.exec_module(mod)
    except BaseException:
        if register:
            sys.modules.pop(name, None)
        raise
    return mod


try:
    CATALOG = load_module_by_path("i18n_catalog", Path(__file__).with_name("i18n_catalog.py")).CATALOG
except Exception:                       # noqa: BLE001 — ไม่มีแคตตาล็อก = ข้อความไทยตามเดิม
    CATALOG = {}

_state = {"lang": DEFAULT_LANG, "mtime": None, "checked": 0.0, "override": None}
_lock = threading.Lock()


def norm_lang(value, default=DEFAULT_LANG):
    if not isinstance(value, str):
        return default
    code = value.strip().lower().replace("_", "-").split("-", 1)[0]
    return code if code in LANGS else default


def set_lang(value):
    """Pin the language for this process (tests, or a server that knows better) — None goes back to settings.json."""
    with _lock:
        _state["override"] = norm_lang(value, None) if value is not None else None
        _state["checked"] = 0.0             # กลับไปอ่าน settings.json ทันที ไม่รอแคช 2 วินาที


def ui_lang():
    """The interface language from settings.json (th/en/ja/zh), re-read when the file changes."""
    with _lock:
        if _state["override"]:
            return _state["override"]
        now = time.monotonic()
        if now - _state["checked"] < _CHECK_EVERY_S:
            return _state["lang"]
        _state["checked"] = now
        try:
            mtime = SETTINGS_FILE.stat().st_mtime
        except OSError:
            _state["lang"], _state["mtime"] = DEFAULT_LANG, None
            return _state["lang"]
        if mtime == _state["mtime"]:
            return _state["lang"]
        _state["mtime"] = mtime
        try:
            doc = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            _state["lang"] = norm_lang(doc.get("lang") if isinstance(doc, dict) else None)
        except (OSError, ValueError):
            _state["lang"] = DEFAULT_LANG
        return _state["lang"]


def tr_for(text, lang):
    """``text`` (Thai source) in ``lang`` — English, then Thai when the catalogue has no entry.

    A text made of two catalogue entries joined by the rules marker (``"<rules> || <description>"`` — the first
    tool of each surface carries the short rules in front of its own description) is translated in two halves.
    """
    if lang == DEFAULT_LANG or not isinstance(text, str) or not text:
        return text
    row = CATALOG.get(text)
    if row:
        return row.get(lang) or row.get(FALLBACK_LANG) or text
    cut = text.find("|| ")
    if cut > 0:
        head, tail = text[:cut + 2], text[cut + 3:]
        if head in CATALOG or tail in CATALOG:
            return tr_for(head, lang) + " " + tr_for(tail, lang)
    return text


def TR(text):
    """The message in the interface language (see module docstring)."""
    return tr_for(text, ui_lang())


def localize_tools(tools, lang=None):
    """A deep copy of a ``tools/list`` result with every description in ``lang`` (Thai → unchanged, same objects)."""
    lang = lang or ui_lang()
    if lang == DEFAULT_LANG:
        return tools
    out = copy.deepcopy(tools)

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("description"), str):
                node["description"] = tr_for(node["description"], lang)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for schema in out:
        if isinstance(schema.get("description"), str):
            schema["description"] = tr_for(schema["description"], lang)
        walk(schema.get("inputSchema"))
    return out


def pick(lang, th, en):
    """A Thai/English pair in ``lang`` — the catalogue row of the Thai text for ja/zh, English otherwise."""
    if lang == DEFAULT_LANG:
        return th
    if lang in LANGS and lang != FALLBACK_LANG:
        row = CATALOG.get(th)
        if row and row.get(lang):
            return row[lang]
    return en


def catalog_coverage(lang):
    """(translated, total) entries of the catalogue for ``lang`` — for the doctor and the tests."""
    total = len(CATALOG)
    done = sum(1 for row in CATALOG.values() if row.get(lang))
    return done, total
