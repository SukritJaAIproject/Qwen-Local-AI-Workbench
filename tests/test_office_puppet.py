# -*- coding: utf-8 -*-
"""ตัวเปิดเอกสารทดสอบของ test_office_live.py — ไม่ใช่เทสต์ (ไม่มี TestCase) รันด้วย anaconda python เท่านั้น

ทำไมต้องมีไฟล์นี้
-----------------
เทสต์รันบน C:\\Python313 ที่ไม่มี pywin32 จึงสั่ง Office เองไม่ได้ ไฟล์นี้ถูกเปิดเป็นโปรเซสลูกหนึ่งตัวต่อชุดเทสต์
(anaconda python) แล้วรับคำสั่งทีละบรรทัด JSON ทาง stdin: สร้าง/อ่าน/แก้ "เอกสารทดสอบที่ตัวเองสร้าง" ใน Office
อินสแตนซ์ใหม่ของตัวเอง (DispatchEx — ไม่เกาะ Excel/Word ที่ผู้ใช้เปิดอยู่) และตอนจบปิดเอกสารของตัวเองโดยไม่บันทึก
แล้วปิดอินสแตนซ์ที่ตัวเองเปิด — ไม่เคยแตะเอกสารของผู้ใช้ (ทุกคำสั่งหาเอกสารด้วย path ของไฟล์ทดสอบเท่านั้น)

PowerPoint เปิดได้ทีละอินสแตนซ์ต่อเครื่อง (DispatchEx จะเกาะตัวที่ผู้ใช้เปิดอยู่) — เทสต์จึงข้ามส่วน PowerPoint
ถ้ามี POWERPNT.EXE อยู่ก่อนเริ่ม (ตรวจฝั่งเทสต์) และคำสั่ง quit ของ PowerPoint ปิดโปรแกรมเฉพาะเมื่อไม่เหลืองานนำเสนออื่น
"""
import json
import os
import sys


def main():
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    apps = {}
    docs = {}          # path (normcase) -> (kind, doc)

    def app(kind):
        if kind not in apps:
            progid = {"excel": "Excel.Application", "word": "Word.Application",
                      "powerpoint": "PowerPoint.Application"}[kind]
            a = win32com.client.DispatchEx(progid)
            if kind in ("excel", "word"):
                a.Visible = False
                a.DisplayAlerts = False if kind == "excel" else 0
            apps[kind] = a
        return apps[kind]

    def doc(path):
        return docs[os.path.normcase(path)][1]

    def grid(v):
        if not isinstance(v, tuple):
            return [[v]]
        return [list(r) for r in v]

    def jsonable(v):
        if isinstance(v, (list, tuple)):
            return [jsonable(x) for x in v]
        if v is None or isinstance(v, (bool, int, float, str)):
            return v
        return str(v)

    def handle(c):
        cmd = c["cmd"]
        if cmd == "excel_new":
            a = app("excel")
            wb = a.Workbooks.Add()
            ws = wb.Worksheets(1)
            for name in c.get("extra_sheets") or []:
                s = wb.Worksheets.Add(After=wb.Worksheets(wb.Worksheets.Count))
                s.Name = name
            ws.Activate()
            for addr, value in (c.get("cells") or {}).items():
                ws.Range(addr).Formula = value
            if os.path.exists(c["path"]):
                raise FileExistsError(c["path"])      # ไฟล์ทดสอบใช้ชื่อสุ่มใหม่เสมอ — ไม่ทับอะไรที่มีอยู่
            wb.SaveAs(c["path"], 51)
            if c.get("select"):
                ws.Range(c["select"]).Select()
            docs[os.path.normcase(c["path"])] = ("excel", wb)
            return {"full": wb.FullName}
        if cmd == "excel_get":
            wb = doc(c["path"])
            ws = wb.Worksheets(c.get("sheet") or 1)
            r = ws.Range(c["range"])
            return {"formula": jsonable(grid(r.Formula)), "value": jsonable(grid(r.Value2)),
                    "numfmt": jsonable(grid(r.NumberFormat)) if r.Count == 1 else r.NumberFormat,
                    "prefix": ws.Range(c["range"].split(":")[0]).PrefixCharacter}
        if cmd == "excel_set":
            wb = doc(c["path"])
            wb.Worksheets(c.get("sheet") or 1).Range(c["range"]).Formula = c["value"]
            return {}
        if cmd == "excel_select":
            wb = doc(c["path"])
            ws = wb.Worksheets(c.get("sheet") or 1)
            ws.Activate()
            ws.Range(c["range"]).Select()
            return {}
        if cmd == "excel_rename_sheet":
            doc(c["path"]).Worksheets(c.get("sheet") or 1).Name = c["name"]
            return {}
        if cmd == "excel_merge":
            doc(c["path"]).Worksheets(1).Range(c["range"]).Merge()
            return {}
        if cmd == "excel_protect":
            doc(c["path"]).Worksheets(1).Protect()
            return {}
        if cmd == "doc_saved":
            return {"saved": bool(doc(c["path"]).Saved)}
        # [fix-office b2b] อ่านอย่างเดียว: ลิงก์ไปสมุดงานอื่น (สูตรอ้างไฟล์อื่นที่หลุดไปเป็นสูตรจริงจะโผล่ที่นี่) และสวิตช์มาโครเหตุการณ์
        if cmd == "excel_links":
            links = doc(c["path"]).LinkSources(1)        # 1 = xlExcelLinks; None = ไม่มีลิงก์
            return {"links": jsonable(links) if links else None}
        if cmd == "excel_events":
            return {"events": bool(doc(c["path"]).Application.EnableEvents)}
        if cmd == "word_new":
            a = app("word")
            d = a.Documents.Add()
            d.Content.Text = c.get("text") or ""
            if os.path.exists(c["path"]):
                raise FileExistsError(c["path"])
            d.SaveAs2(c["path"], 16)
            s = int(c.get("start") or 0)
            d.ActiveWindow.Selection.SetRange(s, int(c.get("end") or s))
            docs[os.path.normcase(c["path"])] = ("word", d)
            return {"full": d.FullName}
        if cmd == "word_get":
            d = doc(c["path"])
            sel = d.ActiveWindow.Selection
            return {"text": d.Content.Text, "start": sel.Start, "end": sel.End, "tables": d.Tables.Count,
                    "saved": bool(d.Saved)}
        if cmd == "word_select":
            doc(c["path"]).ActiveWindow.Selection.SetRange(int(c["start"]), int(c["end"]))
            return {}
        if cmd == "word_type":
            doc(c["path"]).Range(int(c["pos"]), int(c["pos"])).InsertAfter(c["text"])
            return {}
        if cmd == "word_undo":
            doc(c["path"]).Undo()
            return {"text": doc(c["path"]).Content.Text}
        if cmd == "ppt_new":
            a = app("powerpoint")
            p = a.Presentations.Add(0)                   # WithWindow = msoFalse: ไม่โผล่หน้าต่างบนจอผู้ใช้
            for i, sl in enumerate(c.get("slides") or [], 1):
                s = p.Slides.Add(i, 2)                   # ppLayoutText: หัวเรื่อง + เนื้อหา
                s.Shapes.Placeholders(1).TextFrame.TextRange.Text = sl.get("title", "")
                s.Shapes.Placeholders(2).TextFrame.TextRange.Text = sl.get("body", "")
                if sl.get("table"):
                    rows = sl["table"]
                    t = s.Shapes.AddTable(len(rows), len(rows[0]), 50, 300, 400, 100)
                    for r, row in enumerate(rows, 1):
                        for k, val in enumerate(row, 1):
                            t.Table.Cell(r, k).Shape.TextFrame.TextRange.Text = val
                if sl.get("notes"):
                    s.NotesPage.Shapes.Placeholders(2).TextFrame.TextRange.Text = sl["notes"]
            if os.path.exists(c["path"]):
                raise FileExistsError(c["path"])
            p.SaveAs(c["path"], 24)
            docs[os.path.normcase(c["path"])] = ("powerpoint", p)
            return {"full": p.FullName}
        if cmd == "quit":
            closed = 0
            for key, (kind, d) in list(docs.items()):
                try:
                    if kind == "excel":
                        d.Close(False)
                    elif kind == "word":
                        d.Close(0)
                    else:
                        d.Close()
                    closed += 1
                except Exception:              # noqa: BLE001
                    pass
                docs.pop(key, None)
            for kind, a in list(apps.items()):
                try:
                    if kind == "powerpoint":
                        if int(a.Presentations.Count) == 0:
                            a.Quit()
                    elif kind == "word":
                        a.Quit(0)
                    else:
                        a.Quit()
                except Exception:              # noqa: BLE001
                    pass
            apps.clear()
            return {"closed": closed}
        raise ValueError("unknown cmd %r" % cmd)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            c = json.loads(line)
            out = {"ok": True, **handle(c)}
        except Exception as exc:                   # noqa: BLE001
            out = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        sys.stdout.write(json.dumps(out, ensure_ascii=True) + "\n")
        sys.stdout.flush()
        if line and json.loads(line).get("cmd") == "quit":
            break
    pythoncom.CoUninitialize()


if __name__ == "__main__":
    main()
