# -*- coding: utf-8 -*-
"""
เทสต์ส่วนของหน้า shell รอบ 4 (2026-09-30) ใน C:\\LLM\\projects\\hub_i18n_parts.py
  K3 ความจำ · K4 ปรับให้เป็นของคุณ · K5 แจ้งเตือน · K7 แผงแสดงผล · K10 ส่งออกแชต

รัน:  C:\\Python313\\python.exe -m unittest discover -s C:\\LLM\\tests -v
      (QWEN_PARTS_FILE=<path> ใช้ทดสอบสำเนาอื่นของไฟล์ได้ — ค่าเริ่มต้นคือไฟล์จริง)

สิ่งที่ตรวจ
  * ข้อความ th/en ครบคู่ และทุก __T_key__ / t('key') ในหน้า shell มีข้อความจริง (ไม่ขึ้นเป็นชื่อคีย์)
  * สคริปต์ inline ทุกก้อนผ่าน node --check และไม่มี </script> แฝงในสตริงที่ปิดสคริปต์กลางคัน
  * สัญญา qwenShellApi.notify / openArtifact มีอยู่จริง
  * ความปลอดภัยของแผงแสดงผล: iframe sandbox ไม่มี allow-same-origin, CSP default-src 'none', HTML ของโมเดลถูกแยกด้วย
    DOMParser แล้วแทรก CSP ไว้หน้าสุด, ไม่มี innerHTML ในหน้า shell
  * ฟังก์ชันล้วน (_LIB_JS) ใน node: Markdown → HTML ไม่ปล่อยแท็ก/ลิงก์อันตราย, CSV, ตรวจข้อมูลชิ้นงาน,
    ไล่กิ่งบทสนทนา + จับคู่ผลเครื่องมือ, ไฟล์ HTML ที่ส่งออกมี CSP และไม่มีสคริปต์ (ยกเว้นสคริปต์พิมพ์ที่มี nonce)
ไม่เปิดพอร์ต ไม่แตะไฟล์ของผู้ใช้ (ไฟล์ JS ชั่วคราวอยู่ใน %TEMP% และถูกลบ)
"""
import ast
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

PARTS = os.environ.get("QWEN_PARTS_FILE") or r"C:\LLM\projects\hub_i18n_parts.py"
HUB = r"C:\LLM\projects\hub.py"


def load_parts():
    spec = importlib.util.spec_from_file_location("hub_i18n_parts_under_test", PARTS)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


parts = load_parts()


def node_exe():
    for p in (shutil.which("node"), r"C:\Program Files\nodejs\node.exe"):
        if p and os.path.isfile(p):
            return p
    return None


NODE = node_exe()


def hub_strings():
    """STRINGS ของ hub.py (อ่านด้วย ast — ไม่ import hub ซึ่งเริ่มงานเบื้องหลังหลายอย่าง)"""
    with open(HUB, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", None) == "STRINGS":
            return ast.literal_eval(n.value)
    return {"th": {}, "en": {}}


def run_js(body):
    """รัน _LIB_JS + body ใน node แล้วคืนค่า JSON ที่ body พิมพ์ด้วย out(x)"""
    code = parts._LIB_JS + "\nfunction out(x){process.stdout.write(JSON.stringify(x));}\n" + body
    fd, fn = tempfile.mkstemp(suffix=".js", prefix="shelltest-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(code)
        r = subprocess.run([NODE, fn], capture_output=True, text=True, encoding="utf-8", timeout=60)
    finally:
        os.remove(fn)
    if r.returncode:
        raise AssertionError("node error: " + (r.stderr or "")[-1500:])
    return json.loads(r.stdout)


def inline_scripts(tpl):
    return re.findall(r"<script>(.*?)</script>", tpl, re.S)


class StringsTests(unittest.TestCase):
    NEW = ("mem_title", "mem_hint", "mem_add", "mem_sum", "pers_menu", "pers_title", "pers_about", "pers_style",
           "notify", "ntf_off", "ntf_on", "ntf_sound", "ntf_done", "art_preview", "art_code", "art_close",
           "exp_md", "exp_html", "exp_pdf", "exp_meta", "out_title")

    def test_th_en_same_keys(self):
        th, en = parts.STRINGS_UI["th"], parts.STRINGS_UI["en"]
        self.assertEqual(sorted(set(th) ^ set(en)), [])
        for k in self.NEW:
            self.assertIn(k, th)
            self.assertTrue(th[k].strip() and en[k].strip(), k)

    def test_english_has_no_thai(self):
        # หน้าอังกฤษต้องไม่มีอักษรไทย (ยกเว้นป้าย "ไทย" ของสวิตช์ภาษาที่ไม่ได้อยู่ใน STRINGS_UI)
        bad = [k for k, v in parts.STRINGS_UI["en"].items() if re.search(r"[\u0e00-\u0e7f]", v)]
        self.assertEqual(bad, [])

    def test_style_keys_cover_all_styles(self):
        for s in ("normal", "concise", "explanatory", "formal", "learning", "custom"):
            for lang in ("th", "en"):
                for k in ("pers_st_" + s, "pers_st_" + s + "_d", "pers_pv_" + s):
                    self.assertIn(k, parts.STRINGS_UI[lang], (lang, k))
        for kind in ("fact", "decision", "requirement", "progress", "todo"):
            self.assertIn("mem_k_" + kind, parts.STRINGS_UI["en"])
        for kind in ("html", "svg", "mermaid", "markdown", "csv", "image"):
            self.assertIn("art_k_" + kind, parts.STRINGS_UI["en"])

    def test_every_template_key_exists(self):
        known = set(parts.STRINGS_UI["en"]) | set(hub_strings().get("en", {}))
        used = set(re.findall(r"__T_([a-z0-9_]+?)__", parts.SHELL))
        for s in inline_scripts(parts.SHELL):
            used |= set(re.findall(r"\bt(?:Raw)?\('([a-z0-9_]+)'\)", s))
        self.assertEqual(sorted(used - known), [])


class ShellTemplateTests(unittest.TestCase):
    def test_contract_functions(self):
        api = re.search(r"window\.qwenShellApi = \{(.*?)\n\};", parts.SHELL, re.S)
        self.assertIsNotNone(api)
        for name in ("notify", "openArtifact", "closeArtifact", "openProjectPanel", "onRoute"):
            self.assertRegex(api.group(1), r"\n  %s:" % name)

    def test_no_stray_script_close(self):
        # "</script>" ในสตริงของ JavaScript ปิดสคริปต์ inline กลางคัน (ส่วนที่เหลือกลายเป็นข้อความบนหน้า)
        # ตัดเนื้อสคริปต์ออกตามกติกาของตัวแยก HTML (จบที่ </script> ตัวแรก) แล้วแท็กเปิด/ปิดที่เหลือต้องเท่ากัน
        html_only = re.sub(r"(<script\b[^>]*>).*?(</script>)", r"\1\2", parts.SHELL, flags=re.S | re.I)
        self.assertEqual(len(re.findall(r"<script\b", html_only, re.I)), len(re.findall(r"</script>", html_only, re.I)))
        self.assertNotIn("<!--", "".join(inline_scripts(parts.SHELL)))
        # สคริปต์หลักต้องจบที่ })(); ของตัวเอง — ถ้าถูกตัดกลางคัน ท้ายก้อนจะเป็นโค้ดครึ่งๆ
        self.assertTrue(inline_scripts(parts.SHELL)[-1].rstrip().endswith("})();"))

    @unittest.skipUnless(NODE, "ไม่มี node")
    def test_inline_scripts_parse(self):
        tpl = (parts.SHELL.replace("__BOOTCFG__", "{}").replace("__SHELLDATA__", "{}").replace("__T_JSON__", "{}")
               .replace("__ME__", "8101").replace("__HUB__", "http://127.0.0.1:8100").replace("__LANG__", "th")
               .replace("__UI__", "/?ui=1"))
        tpl = re.sub(r"__T_([a-z0-9_]+?)__", "x", tpl)
        for i, code in enumerate(inline_scripts(tpl)):
            fd, fn = tempfile.mkstemp(suffix=".js", prefix="shellsyn-")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(code)
                r = subprocess.run([NODE, "--check", fn], capture_output=True, text=True, encoding="utf-8", timeout=60)
            finally:
                os.remove(fn)
            self.assertEqual(r.returncode, 0, "script %d: %s" % (i, r.stderr[-800:]))

    def test_artifact_sandbox_rules(self):
        s = parts.SHELL
        # ทุกค่าของ sandbox ที่หน้า shell ตั้ง (ใน HTML และใน artSetFrame) — ห้ามมีสิทธิ์ที่พาออกจากกรอบ
        values = re.findall(r'sandbox="([^"]*)"', s) + re.findall(r"artSetFrame\('([^']*)'", s)
        self.assertTrue(values)
        for v in values:
            self.assertEqual(set(v.split()) - {"allow-scripts"}, set(), v)
        self.assertNotIn(".innerHTML", s)
        self.assertNotIn("insertAdjacentHTML", s)
        self.assertRegex(s, r'<iframe id="artFrame" sandbox=""')
        csp = re.search(r"var ART_CSP = \"([^\"]+)\"", s).group(1)
        self.assertIn("default-src 'none'", csp)
        self.assertIn("form-action 'none'", csp)
        self.assertNotRegex(csp, r"https?:|\*")
        # สคริปต์ได้เฉพาะชนิด html และเฉพาะเมื่อผู้ใช้กด "เรียกใช้สคริปต์" (v.run) — ชนิดอื่น sandbox ว่างเสมอ
        # (แก้ 2026-09-30: เดิม HTML รันสคริปต์ทันทีที่เปิด แล้วสคริปต์ location='https://…?d=' พาข้อมูลออกได้)
        self.assertEqual(re.findall(r"artSetFrame\('allow-scripts'", s), [])
        self.assertEqual(re.findall(r"'allow-scripts'", s), ["'allow-scripts'"])
        self.assertIn("artSetFrame(run ? 'allow-scripts' : '', hd.html, tok)", s)
        self.assertIn("var run = v.run === true,", s)
        # v.run = true ถูกตั้งได้จากปุ่มในแถบของแผงเท่านั้น (artRunJs) — ไม่มีทางอื่นเปิดสคริปต์เอง
        self.assertEqual(re.findall(r"\bv\.run = [^;]+;", s), ["v.run = !!on;", "v.run = false;"])
        self.assertEqual(re.findall(r"artRunJs\(true\)", s), ["artRunJs(true)", "artRunJs(true)"])
        # HTML ของโมเดล: แยกด้วย DOMParser แล้วแทรก CSP ไว้หน้าสุดของ <head> ก่อนเนื้อหาทุกส่วน
        # ไม่ได้เปิดสคริปต์ = CSP ไม่มี script-src และไม่มีตัวกัน <script> ของเรา
        self.assertIn("new DOMParser().parseFromString(code, 'text/html')", s)
        self.assertIn("var head = [mk({ charset: 'utf-8' }), mk({ 'http-equiv': 'Content-Security-Policy', content: run ? ART_CSP_JS : ART_CSP }),", s)
        self.assertIn("if (run) { var sc = doc.createElement('script'); sc.textContent = artGuard(tok); head.push(sc); }", s)
        self.assertIn("doc.head.prepend.apply(doc.head, head);", s)
        self.assertNotIn("script-src", csp)
        # DOM ของหน้าถูกเดินผ่านกติกาใน _LIB_JS (ทดสอบใน node ที่ ArtifactHtmlRuleTests)
        for fn in ("qwArtDropEl(ln, n.getAttribute('attributeName'))", "qwArtScriptAttr(nm, a.value)", "qwArtDropAttr(ln, nm, a.value)"):
            self.assertIn(fn, s)
        # ข้อความ "กำลังออก" จากเฟรม: ต้องมาจากเฟรมของแผงเอง และโทเคนตรงกับรอบที่แสดงอยู่
        self.assertIn("if (e.source !== artFrame.contentWindow || !d || typeof d !== 'object' || d.qwArt !== 'leave') return;", s)
        self.assertIn("if (!ART.tok || d.tok !== ART.tok || !artOpen()) return;", s)

    def test_panel_a11y_fixes(self):
        s = parts.SHELL
        # หัวเรื่องของแผง (tabindex=-1 รับโฟกัสจากโค้ด) ไม่มีวงโฟกัสส้มทุกครั้งที่เปิดด้วยเมาส์
        self.assertIn(".art-title:focus{outline:none}", s)
        self.assertNotIn(".art-title:focus-visible{outline", s)
        # ตัวปรับความกว้าง: Home = แคบสุด (valuemin) End = กว้างสุด (valuemax) ตามแบบ window splitter
        self.assertIn("e.key === 'Home' ? 0 : e.key === 'End' ? 1e6 : null", s)
        self.assertIn("max = Math.max(320, innerWidth - sbw - 480)", s)
        # เปิดจาก "ไฟล์ที่ Qwen สร้าง" (แผงโปรเจกต์ปิดไปแล้ว) — ปิดแผงแสดงผลแล้วโฟกัสกลับปุ่มแผงโปรเจกต์
        m = re.search(r"function openOutput\(f, kind\) \{(.*?)\n\}", s, re.S)
        self.assertIsNotNone(m)
        self.assertIn("ART.back = $('#projBtn');", m.group(1))
        self.assertNotRegex(m.group(1), r"(?<![\w.])openArtifact\(\{")    # ทุกทางเปิดผ่าน open() ที่ตั้ง ART.back

    def test_memory_escape_keeps_draft(self):
        s = parts.SHELL
        # Esc ในช่องเพิ่ม/แก้ความจำ: ครั้งแรกเตือน (memEscape) ไม่ทิ้งข้อความทันที
        self.assertIn("if (!memEscape($('#ppMemEsc'), !!memIn.value.trim())) closeMemForm();", s)
        self.assertIn("if (!memEscape(escN, ta.value.trim() !== e.text.trim() || sel.value !== memKindOf(e))) memEndEdit(e.id);", s)
        self.assertNotRegex(s, r"e\.key === 'Escape'\) \{ e\.preventDefault\(\); e\.stopPropagation\(\); closeMemForm\(\); \}")
        self.assertIn('id="ppMemEsc" hidden>__T_mem_esc_again__</p>', s)

    def test_notify_menu_shows_effective_state(self):
        s = parts.SHELL
        # เมนูแสดงค่าที่ใช้ได้จริง (ntfEff) ไม่ใช่ค่าที่เก็บไว้ + คำเตือนใต้แถวเมื่อเบราว์เซอร์ไม่อนุญาต
        self.assertIn("[['off', t('ntf_off')], ['on', t('ntf_on')], ['sound', t('ntf_sound')]], ntfEff(),", s)
        self.assertNotIn("ntf_sound')]], ntfPref(),", s)
        self.assertIn("if (seg) segSet(seg, ntfEff());", s)
        for lang in ("th", "en"):
            for k in ("ntf_blocked", "ntf_ask_again", "ntf_unsupported", "mem_esc_again", "mem_esc_edit",
                      "art_js_off_note", "art_js_on_note", "art_js_left", "art_js_run", "art_js_stop", "art_js_on", "art_js_off"):
                self.assertTrue(parts.STRINGS_UI[lang].get(k, "").strip(), (lang, k))

    def test_panel_and_dialog_markup(self):
        s = parts.SHELL
        for sel in ('id="ppMem"', 'id="ppOut"', 'id="pdWrap"', 'role="radiogroup" aria-labelledby="pdStyleH"',
                    'id="art"', 'role="separator" aria-orientation="vertical"', 'id="artMode" role="radiogroup"'):
            self.assertIn(sel, s)
        # หน้าต่างปรับให้เป็นของคุณเป็น modal ที่มีชื่อ
        self.assertIn('id="pd" role="dialog" aria-modal="true" aria-labelledby="pdTitle"', s)


@unittest.skipUnless(NODE, "ไม่มี node")
class MarkdownTests(unittest.TestCase):
    def test_escapes_html_and_bad_links(self):
        r = run_js(r"""
out([
  qwMd('<script>alert(1)</script> <img src=x onerror=alert(1)>'),
  qwMd('[x](javascript:alert(1)) [y](JaVaScRiPt:alert(1)) [z](data:text/html,<b>) [ok](https://a.example/?q=1&r=2)'),
  qwMd('![a](https://evil.example/p.png) ![b](data:image/svg+xml;base64,PHN2Zz4=) ![c](data:image/png;base64,iVBORw0KGgo=)', {images: true}),
  qwMd('![c](data:image/png;base64,iVBORw0KGgo=)'),
  qwMd('[ok](https://a.example/)', {links: false}),
  qwMd('see <https://a.example/x> and https://b.example/y).'),
  qwMd('a "quote" & <tag> \u0001 0\u0002')
]);""")
        self.assertNotIn("<script", r[0])
        self.assertNotIn("<img", r[0])
        self.assertIn("&lt;script&gt;", r[0])
        self.assertNotIn('href="javascript', r[1].lower())
        self.assertNotIn('href="data', r[1])
        self.assertIn('href="https://a.example/?q=1&amp;r=2"', r[1])
        self.assertNotIn("evil.example/p.png\"", r[2].replace('title="', ''))
        self.assertNotIn("svg+xml", r[2].split("<img")[-1] if "<img" in r[2] else "")
        self.assertEqual(r[2].count("<img"), 1)
        self.assertIn('src="data:image/png;base64,iVBORw0KGgo="', r[2])
        self.assertNotIn("<img", r[3])           # ไม่ได้เปิด images → ไม่มีรูปเลย
        self.assertNotIn("<a ", r[4])            # links:false → ไม่มีลิงก์ที่กดได้
        self.assertIn('href="https://a.example/x"', r[5])
        self.assertIn('href="https://b.example/y"', r[5])
        self.assertIn(").", r[5])
        self.assertNotIn("\u0001", r[6])

    def test_blocks(self):
        r = run_js(r"""
out([
  qwMd('# H\n\n- a\n- b\n  - c\n- d\n\n1. x\n2. y'),
  qwMd('| a | b |\n|---|--:|\n| `p|q` | 2 |'),
  qwMd('```py\nx = "<b>"\n```'),
  qwMd('```code``` inline'),
  qwMd('> q **b**\n> l2\n\n---\n\ntext\nnext line'),
  qwMd('**bold `code` in**, snake_case_name, _it_, ~~s~~')
]);""")
        self.assertIn("<h1>H</h1>", r[0])
        self.assertIn("<ul><li>a</li><li>b<ul><li>c</li></ul></li><li>d</li></ul>", r[0])
        self.assertIn("<ol><li>x</li><li>y</li></ol>", r[0])
        self.assertIn("<table>", r[1])
        self.assertIn('<td class="al-r">2</td>', r[1])
        self.assertIn("<code>p|q</code>", r[1])
        self.assertIn('<pre><code class="language-py">x = &quot;&lt;b&gt;&quot;</code></pre>', r[2])
        self.assertIn("<code>code</code> inline", r[3])
        self.assertIn("<blockquote><p>q <strong>b</strong><br>l2</p></blockquote>", r[4])
        self.assertIn("<hr>", r[4])
        self.assertIn("text<br>next line", r[4])
        self.assertIn("<strong>bold <code>code</code> in</strong>", r[5])
        self.assertIn("snake_case_name", r[5])
        self.assertIn("<em>it</em>", r[5])
        self.assertIn("<del>s</del>", r[5])


@unittest.skipUnless(NODE, "ไม่มี node")
class CsvAndArtifactTests(unittest.TestCase):
    def test_csv(self):
        r = run_js(r"""
var big = 'h1,h2\n'; for (var i = 0; i < 50; i++) big += i + ',x\n';
out([qwCsv('a,b\r\n"x, ""y"" z",2\n\n3,4\n'), qwCsv('a;b;c\n1;2;3'), qwCsv('a\tb\n1\t2'), qwCsv(big, 10), qwCsv('\ufeffa,b\n"multi\nline",2')]);""")
        self.assertEqual(r[0]["rows"], [["a", "b"], ['x, "y" z', "2"], ["3", "4"]])
        self.assertEqual(r[1]["delim"], ";")
        self.assertEqual(r[2]["rows"][1], ["1", "2"])
        self.assertEqual(len(r[3]["rows"]), 10)
        self.assertEqual(r[3]["total"], 51)
        self.assertEqual(r[4]["rows"], [["a", "b"], ["multi\nline", "2"]])

    def test_artifact_normalize(self):
        r = run_js(r"""
function k(o) { var a = qwArtNorm(o, 1000); return a ? (a.tooBig ? 'big' : a.kind + '|' + a.code.slice(0, 40)) : null; }
out([
  k({kind: 'html', code: '<p>x</p>', id: 'a'}), k({kind: 'MD', code: '# x'}), k({kind: 'png', code: '/_qwen/out/chart.png'}),
  k({kind: 'image', code: '/_qwen/out/../x.png'}), k({kind: 'image', code: '/_qwen/out/a/b.png'}),
  k({kind: 'image', code: 'https://evil.example/x.png'}), k({kind: 'image', code: 'data:image/svg+xml;base64,PHN2Zz4='}),
  k({kind: 'image', code: 'data:image/png;base64,iVBORw0KGgo='}), k({kind: 'image', code: 'blob:http://127.0.0.1:8103/0f8e1b2a-3c4d-4e5f-8a9b-0c1d2e3f4a5b'}),
  k({kind: 'image', code: 'blob:https://evil.example/0f8e1b2a-3c4d-4e5f-8a9b-0c1d2e3f4a5b'}),
  k({kind: 'exe', code: 'x'}), k({kind: 'html', code: '   '}), k({kind: 'html', code: new Array(1200).join('x')}), k(null),
  qwArtNorm({kind: 'mermaid', code: 'graph TD', svg: '<svg><g/></svg>'}).svg, qwArtNorm({kind: 'mermaid', code: 'g', svg: '<img src=x>'}).svg,
  qwArtNorm({kind: 'csv', code: 'a', title: '  a \n b  '}).title, qwArtNorm({kind: 'csv', code: 'a', title: 't'}).id
]);""")
        self.assertEqual(r[0], "html|<p>x</p>")
        self.assertEqual(r[1], "markdown|# x")
        self.assertEqual(r[2], "image|/_qwen/out/chart.png")
        self.assertIsNone(r[3])
        self.assertIsNone(r[4])
        self.assertIsNone(r[5])
        self.assertIsNone(r[6])                   # svg ในรูปมีสคริปต์ได้ — ไม่รับ
        self.assertTrue(r[7].startswith("image|data:image/png"))
        self.assertTrue(r[8].startswith("image|blob:http://127.0.0.1:8103/"))
        self.assertIsNone(r[9])
        self.assertIsNone(r[10])
        self.assertIsNone(r[11])
        self.assertEqual(r[12], "big")
        self.assertIsNone(r[13])
        self.assertEqual(r[14], "<svg><g/></svg>")
        self.assertEqual(r[15], "")
        self.assertEqual(r[16], "a b")
        self.assertEqual(r[17], "csv:t")


@unittest.skipUnless(NODE, "ไม่มี node")
class ExportTests(unittest.TestCase):
    FIX = r"""
var C = 'c1';
var msgs = [
  {id: 'r', convId: C, type: 'root', role: 'system', content: '', parent: null, children: ['s']},
  {id: 's', convId: C, type: 'system', role: 'system', content: 'SECRET-SYSTEM C:\\path', parent: 'r', children: ['u1']},
  {id: 'u1', convId: C, type: 'text', role: 'user', content: 'hi <script>alert(1)</script>', parent: 's', children: ['a1', 'a1b'], timestamp: 10,
   extra: [{type: 'IMAGE', name: 'p.png', base64Url: 'data:image/png;base64,iVBORw0KGgo='}, {type: 'TEXT', name: 'n.txt', content: 'x'}]},
  {id: 'a1b', convId: C, type: 'text', role: 'assistant', content: 'OTHER BRANCH', parent: 'u1', children: [], timestamp: 11},
  {id: 'a1', convId: C, type: 'text', role: 'assistant', content: 'reading', reasoningContent: 'think **hard**', model: 'Qwen3.8-27B-UD-Q4_K_M',
   toolCalls: JSON.stringify([{id: 'call_1', type: 'function', function: {name: 'local_read', arguments: '{"action":"read","path":"a.csv"}'}}]),
   parent: 'u1', children: ['t1'], timestamp: 12},
  {id: 't1', convId: C, type: 'text', role: 'tool', toolCallId: 'call_1', content: 'x```y', parent: 'a1', children: ['a2'], timestamp: 13},
  {id: 'a2', convId: C, type: 'text', role: 'assistant', content: '<think>inner</think>done ```', parent: 't1', children: [], timestamp: 14}
];
var conv = {id: C, name: 'T', currNode: 'a2'};
var L = {lang: 'en', you: 'You', reasoning: 'Reasoning', tool: 'Tool', args: 'Arguments', result: 'Result', noResult: '(no result)',
  attach: 'Attachments', cut: '… (trimmed to %1 of %2 characters)', printHint: 'Press Ctrl+P', meta: 'Exported',
  time: function (ms) { return 'T' + ms; }};
var turns = qwTurns(qwConvPath(conv, msgs));
"""

    def test_turns(self):
        r = run_js(self.FIX + "out(turns);")
        self.assertEqual([t["role"] for t in r], ["user", "assistant"])
        parts_ = r[1]["parts"]
        self.assertEqual([p["type"] for p in parts_], ["reasoning", "text", "tool", "reasoning", "text"])
        self.assertEqual(parts_[2]["name"], "local_read")
        self.assertEqual(parts_[2]["result"], "x```y")
        self.assertEqual(parts_[3]["text"], "inner")          # <think> ในเนื้อความย้ายไปเป็นความคิด
        self.assertEqual(r[1]["model"], "Qwen3.8-27B-UD-Q4_K_M")
        self.assertEqual(r[0]["files"][0]["image"], "data:image/png;base64,iVBORw0KGgo=")
        self.assertNotIn("OTHER BRANCH", json.dumps(r))     # กิ่งที่ไม่ได้เปิดไม่ถูกส่งออก
        self.assertNotIn("SECRET-SYSTEM", json.dumps(r))    # ข้อความระบบ (ที่อยู่ไฟล์ในเครื่อง) ไม่ถูกส่งออก

    def test_no_currnode_uses_latest(self):
        r = run_js(self.FIX + "out(qwConvPath({id: C}, msgs).map(function (m) { return m.id; }));")
        self.assertEqual(r[-1], "a2")

    def test_html_export_is_inert(self):
        r = run_js(self.FIX + r"""
out([qwExportHtml('T <b>', turns, L), qwExportHtml('T', turns, L, {print: true, nonce: 'abcdef0123456789abcd'}),
     qwExportHtml('T', turns, L, {print: true, nonce: 'bad nonce"><script>'})]);""")
        plain, printable, bad = r
        self.assertIn("Content-Security-Policy", plain)
        self.assertIn("default-src 'none'", plain)
        self.assertEqual(len(re.findall(r"<script", plain)), 0)
        self.assertIn("&lt;script&gt;alert(1)", plain)
        self.assertIn("<title>T &lt;b&gt;</title>", plain)
        self.assertIn("<details><summary>Reasoning</summary>", plain)
        self.assertIn("Tool: local_read", plain)
        self.assertIn('<img src="data:image/png;base64,iVBORw0KGgo="', plain)
        self.assertNotIn("\u2060", plain)
        self.assertEqual(len(re.findall(r"<script", printable)), 1)
        self.assertIn("script-src 'nonce-abcdef0123456789abcd'", printable)
        self.assertIn('<script nonce="abcdef0123456789abcd">', printable)
        self.assertEqual(len(re.findall(r"<script", bad)), 0)   # nonce ผิดรูป = ไม่มีสคริปต์เลย

    def test_markdown_export(self):
        md = run_js(self.FIX + "out(qwExportMd('T', turns, L));")
        self.assertTrue(md.startswith("# T\n"))
        self.assertIn("<details>\n<summary>Reasoning</summary>", md)
        self.assertIn("````\nx```y\n````", md)          # รั้วยาวกว่า ``` ในผลลัพธ์
        self.assertIn('"path": "a.csv"', md)
        self.assertIn("_Attachments: p.png, n.txt_", md)

    def test_file_names(self):
        r = run_js(r"""out([qwFileName('a/b:c*?"<>|. ', 'md'), qwFileName('CON', 'html'), qwFileName('', 'md'),
          qwFileName(new Array(200).join('ก'), 'md').length, qwFileName('x\u2060y', 'md')]);""")
        self.assertEqual(r[0], "a b c.md")
        self.assertEqual(r[1], "chat.html")
        self.assertEqual(r[2], "chat.md")
        self.assertLessEqual(r[3], 84)
        self.assertEqual(r[4], "x y.md")


@unittest.skipUnless(NODE, "ไม่มี node")
class ExportOutputsTests(unittest.TestCase):
    """รูป/ลิงก์ของไฟล์ที่ Qwen สร้าง (/_qwen/out/…) ในไฟล์ส่งออก (แก้ 2026-09-30)
    เดิม: HTML/PDF แสดง [fig] แทนกราฟ, Markdown เก็บลิงก์สัมพัทธ์ที่เปิดนอกพอร์ตโปรเจกต์แล้วใช้ไม่ได้"""
    FIX = r"""
var PNG = 'data:image/png;base64,iVBORw0KGgo=';
var turns = [
  {role: 'user', at: 1, model: '', files: [], parts: [{type: 'text', text: 'plot please'}]},
  {role: 'assistant', at: 2, model: '', files: [], parts: [
    {type: 'text', text: 'Chart:\n\n![fig](/_qwen/out/fig-1.png)\n\n![กราฟ](/_qwen/out/%E0%B8%81.png) ![x](/_qwen/out/fig-1.png)\n' +
      '[report](/_qwen/out/%E0%B8%A3.docx) ![ev](https://evil.example/a.png) ![bad](/_qwen/out/../secret.png)'},
    {type: 'reasoning', text: '![r](/_qwen/out/r.webp)'},
    {type: 'tool', id: 'c', name: 'local_do', args: '{}', result: '![t](/_qwen/out/tool.png)'}
  ]}
];
var L = {lang: 'en', you: 'You', reasoning: 'Reasoning', tool: 'Tool', args: 'Arguments', result: 'Result', noResult: '-',
  attach: 'Attachments', cut: '%1/%2', printHint: '', meta: 'Exported', time: function (ms) { return 'T' + ms; }};
"""

    def test_collect_out_images(self):
        r = run_js(self.FIX + "out([qwOutImgs(turns, 40), qwOutImgs(turns, 1)]);")
        # ไม่ซ้ำ ตามลำดับ เฉพาะ /_qwen/out ที่ปลอดภัย (ไม่เอา .. และ URL ภายนอก) ไม่เอาผลของเครื่องมือ (แสดงเป็นข้อความดิบ)
        self.assertEqual(r[0], ["/_qwen/out/fig-1.png", "/_qwen/out/%E0%B8%81.png", "/_qwen/out/r.webp"])
        self.assertEqual(r[1], ["/_qwen/out/fig-1.png"])

    def test_html_inlines_images_and_names_missing_ones(self):
        r = run_js(self.FIX + r"""
var imgs = {'/_qwen/out/fig-1.png': PNG, '/_qwen/out/r.webp': 'data:image/svg+xml;base64,PHN2Zz4='};
out([qwExportHtml('T', turns, L, {imgs: imgs, base: 'http://127.0.0.1:8103'}), qwExportHtml('T', turns, L),
     qwExportHtml('T', turns, L, {base: 'https://evil.example'})]);""")
        withimg, plain, badbase = r
        self.assertEqual(withimg.count('<img src="data:image/png;base64,iVBORw0KGgo="'), 2)   # รูปเดียวกันสองที่
        # รูปที่ไม่ได้ฝัง: ชื่อไฟล์ (ถอด %xx) แทน [fig] เปล่า · svg ที่ส่งมาในแผนที่ถูกตีตก (qwSafeImg)
        self.assertIn('<span class="md-img">[กราฟ: ก.png]</span>', withimg)
        self.assertIn('<span class="md-img">[r: r.webp]</span>', withimg)
        self.assertNotIn("svg+xml", withimg)
        self.assertIn('<span class="md-img">[fig: fig-1.png]</span>', plain)
        self.assertNotIn("<img", plain.split("<main>")[1])
        # รูปจากเน็ตไม่ถูกโหลด (ชื่อไฟล์เป็นแค่ข้อความ) · CSP ของไฟล์ยังรับรูปแค่ data:
        self.assertIn("[ev: a.png]", withimg)
        self.assertNotIn('src="https://evil.example', withimg)
        self.assertIn("img-src data:;", withimg)
        # ลิงก์ไฟล์เป็นที่อยู่เต็มของพอร์ตโปรเจกต์ — base อื่นที่ไม่ใช่เครื่องนี้ไม่ใช้
        self.assertIn('href="http://127.0.0.1:8103/_qwen/out/%E0%B8%A3.docx"', withimg)
        self.assertNotIn('href="https://evil.example/_qwen', badbase)
        self.assertNotIn('href="/_qwen', badbase)
        self.assertEqual(len(re.findall(r"<script", withimg)), 0)

    def test_markdown_links_absolute(self):
        r = run_js(self.FIX + r"""
out([qwExportMd('T', turns, L, {base: 'http://127.0.0.1:8103'}), qwExportMd('T', turns, L, {base: 'javascript:alert(1)//'}),
     qwExportMd('T', turns, L)]);""")
        md, bad, rel = r
        self.assertIn("![fig](http://127.0.0.1:8103/_qwen/out/fig-1.png)", md)
        self.assertIn("[report](http://127.0.0.1:8103/_qwen/out/%E0%B8%A3.docx)", md)
        self.assertIn("![r](http://127.0.0.1:8103/_qwen/out/r.webp)", md)
        body, tool = md.split("Tool: local_do")
        self.assertNotIn("](/_qwen/out/fig", body)
        self.assertIn("![bad](/_qwen/out/../secret.png)", body)     # path ที่มี .. ไม่ถูกทำเป็นที่อยู่เต็ม
        self.assertIn("![t](/_qwen/out/tool.png)", tool)           # ผลของเครื่องมืออยู่ในรั้วโค้ด แสดงตามจริง
        self.assertIn("](/_qwen/out/fig-1.png)", bad)            # base ผิดรูป = ไม่เปลี่ยนอะไร
        self.assertNotIn("javascript", bad)
        self.assertIn("](/_qwen/out/fig-1.png)", rel)

    def test_image_names(self):
        r = run_js(r"""out([qwImgName('/_qwen/out/%E0%B8%81%20x.png?download=1'), qwImgName('data:image/png;base64,AAA'),
          qwImgName('/_qwen/out/%E0%B8'), qwImgName('https://a.example/p/q.png#h'), qwImgName('a\u0001b⁠.png'),
          qwImgName(new Array(120).join('x') + '.png').length]);""")
        self.assertEqual(r[0], "ก x.png")
        self.assertEqual(r[1], "")
        self.assertEqual(r[2], "%E0%B8")                       # %xx ที่ถอดไม่ได้ ไม่ทำให้ล้ม
        self.assertEqual(r[3], "q.png")
        self.assertEqual(r[4], "ab.png")
        self.assertLessEqual(r[5], 80)


@unittest.skipUnless(NODE, "ไม่มี node")
class ArtifactHtmlRuleTests(unittest.TestCase):
    """กติกาของหน้า HTML ในแผงเมื่อสคริปต์ปิด (ค่าเริ่มต้น) — สิ่งที่พาเฟรมออกนอกเครื่องได้โดยไม่ใช้สคริปต์ต้องถูกตัด"""

    def test_drop_navigation_attrs(self):
        r = run_js(r"""
function d(ln, nm, v) { return qwArtDropAttr(ln, nm, v); }
out([
  d('a', 'href', 'https://evil.example/?d=secret'), d('A', 'HREF', ' http://x/'), d('area', 'href', '//evil.example/'),
  d('a', 'xlink:href', 'https://evil.example/'), d('a', 'href', 'data:text/html,x'), d('a', 'href', 'javascript:alert(1)'),
  d('a', 'href', 'relative/page.html'), d('a', 'href', '#top'), d('a', 'href', '  #sec'), d('a', 'ping', 'https://evil.example/'),
  d('use', 'href', '#icon'), d('image', 'href', 'data:image/png;base64,AAA'), d('image', 'xlink:href', 'https://evil.example/p.png'),
  d('math', 'href', 'https://evil.example/'), d('div', 'title', 'https://evil.example/'), d('img', 'src', 'https://evil.example/')
]);""")
        self.assertEqual(r, [True, True, True, True, True, True, True, False, False, True,
                             False, False, True, True, False, False])

    def test_drop_href_animation(self):
        r = run_js(r"""out([qwArtDropEl('animate', 'href'), qwArtDropEl('set', 'xlink:href'), qwArtDropEl('animateMotion', 'HREF'),
          qwArtDropEl('animate', 'opacity'), qwArtDropEl('a', 'href'), qwArtDropEl('set', null)]);""")
        self.assertEqual(r, [True, True, True, False, False, False])

    def test_script_detection(self):
        r = run_js(r"""out([qwArtScriptAttr('onclick', 'x()'), qwArtScriptAttr('ONLOAD', ''), qwArtScriptAttr('href', ' JavaScript:void(0)'),
          qwArtScriptAttr('class', 'on'), qwArtScriptAttr('title', 'javascript is fun')]);""")
        self.assertEqual(r, [True, True, True, False, False])


@unittest.skipUnless(NODE, "ไม่มี node")
class SmallFixTests(unittest.TestCase):
    def test_csv_download_has_bom(self):
        # Excel (ดับเบิลคลิก) อ่าน CSV ไม่มี BOM เป็น ANSI → ภาษาไทยเพี้ยน · มี BOM อยู่แล้วไม่ใส่ซ้ำ · ชนิดอื่นไม่แตะ
        r = run_js(r"""out([qwDlText('csv', 'สถานี,kW\nA,50'), qwDlText('csv', '﻿a,b'), qwDlText('html', '<p>x</p>'),
          qwDlText('markdown', '# x'), qwDlText('csv', '')]);""")
        self.assertEqual(r[0], "﻿สถานี,kW\nA,50")
        self.assertEqual(r[1], "﻿a,b")
        self.assertEqual(r[2], "<p>x</p>")
        self.assertEqual(r[3], "# x")
        self.assertEqual(r[4], "﻿")

    def test_notify_effective_state(self):
        r = run_js(r"""out([qwNtfState('on', 'granted'), qwNtfState('sound', 'granted'), qwNtfState('on', 'denied'),
          qwNtfState('sound', 'default'), qwNtfState('on', 'unsupported'), qwNtfState('off', 'denied'), qwNtfState(null, 'granted'),
          qwNtfState('bogus', 'granted')]);""")
        self.assertEqual([x["shown"] for x in r], ["on", "sound", "off", "off", "off", "off", "off", "off"])
        self.assertEqual([x["warn"] for x in r], ["", "", "ntf_blocked", "ntf_ask_again", "ntf_unsupported", "", "", ""])


if __name__ == "__main__":
    unittest.main()
