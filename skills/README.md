# Skills — แม่แบบพรอมต์ของ Qwen3.8 / prompt templates

แต่ละโฟลเดอร์ `C:\LLM\skills\<name>\SKILL.md` คือหนึ่ง skill เซิร์ฟเวอร์ MCP "เครื่องนี้" (พอร์ต 8792)
เสิร์ฟเป็น MCP prompts ใช้ในหน้าแชตได้โดย **พิมพ์ `/` ในช่องพิมพ์ → เลือก `prompt` → เลือก skill**
→ กรอกช่อง (ถ้ามี) → **Use Prompt** แล้วพิมพ์ข้อความเพิ่ม (ถ้าต้องการ) และส่ง

Each folder is one skill, served as an MCP prompt: type `/` in the composer → `prompt` → pick a skill →
fill the fields → **Use Prompt** → send.

## รูปแบบ / Format

```
---
name: my-skill                 # ต้องตรงกับชื่อโฟลเดอร์ (a-z 0-9 -)
title_th: ชื่อภาษาไทย
title_en: English title
description: คำอธิบายภาษาไทย
description_en: English description        # ไม่บังคับ
order: 10                      # ไม่บังคับ: ลำดับในรายการ (น้อยขึ้นก่อน ค่าเริ่มต้น 100)
arguments:
  - name: file                 # A-Z a-z 0-9 _ (ใช้เป็น id ของช่องกรอกในหน้าเว็บ)
    description: ชื่อไฟล์ในไฟล์แนบ
    description_en: Attachment file name   # ไม่บังคับ
    required: false
    default: ค่าเมื่อเว้นว่าง               # ไม่บังคับ
    default_en: value if left empty (EN UI)  # ไม่บังคับ
    complete: attachments      # ไม่บังคับ: attachments | outputs = เดาชื่อไฟล์ของโปรเจกต์ให้ตอนพิมพ์
                               # ค่าที่ผู้ใช้ใส่ (x.pdf, attachments/x.pdf, path เต็ม) กลายเป็น "x.pdf" เสมอ
                               # แม่แบบจึงเขียน attachments/{{file}} ได้เลย; path นอกโฟลเดอร์ = แจ้งผู้ใช้ตอนกด
---
เนื้อแม่แบบ ใช้ {{file}} แทนค่า
{{#file}}แสดงเมื่อ file ไม่ว่าง{{/file}}{{^file}}แสดงเมื่อ file ว่าง{{/file}}
```

ชื่อสงวน / reserved: `{{_project}}` `{{_date}}` `{{_lang}}` `{{_attachments}}` `{{_outputs}}` (path เต็ม)
และส่วน `{{#_fast}}…{{/_fast}}` (ผิวย่อ local_read/local_do — ค่าเริ่มต้นของหน้าแชต) กับ
`{{^_fast}}…{{/_fast}}` (ผิวเต็ม read_file/doc_extract/…)

ข้อจำกัด: frontmatter เป็น YAML ชุดย่อย (ไม่มีคอมเมนต์ท้ายบรรทัด — ตัวอย่างข้างบนมีไว้อธิบายเท่านั้น),
ไฟล์ไม่เกิน 64 KB, อาร์กิวเมนต์ไม่เกิน 10 ตัว, ส่วนชื่อเดียวกันซ้อนกันไม่ได้, เขียน `{{` ตรงๆ ในเนื้อไม่ได้
skill ที่ผิดรูปจะไม่ขึ้นในรายการ ดูเหตุผลได้ที่ GET `http://127.0.0.1:8792/fast/<project>` (ต้องมี token) หัวข้อ `skills.failed`

## เปิด/ปิดต่อโปรเจกต์ / Per-project list (ไม่บังคับ)

`C:\LLM\skills\enabled.json` — ไม่มีไฟล์ = ทุกโปรเจกต์เห็นทุก skill

```json
{"default": {"disabled": []},
 "projects": {"วินิจฉัยตู้ชาร์จ": {"enabled": ["ocpp-log-analysis", "charger-incident-report"]},
              "project1": {"disabled": ["formal-email"]}}}
```

## ความปลอดภัย / Safety

โฟลเดอร์นี้อยู่ในเขตห้ามเขียนของเครื่องมือ (guard) — โมเดลสร้างหรือแก้ skill เองไม่ได้ แก้ได้เฉพาะผู้ใช้
เพราะ skill คือข้อความที่ผู้ใช้เลือกส่งให้โมเดลเอง ถ้าโมเดลแก้ได้ ข้อความที่หลอกโมเดลจากเว็บหรือไฟล์จะฝังคำสั่งถาวรได้
The folder is write-protected from tools; only you can add or edit skills.
