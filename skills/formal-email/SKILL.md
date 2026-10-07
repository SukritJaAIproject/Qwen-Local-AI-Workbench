---
name: formal-email
title_th: เขียนอีเมลทางการ
title_en: Formal email
description: ร่างอีเมลทางการ มีหัวเรื่อง คำขึ้นต้น เนื้อหา และคำลงท้ายครบ (ร่างเท่านั้น ไม่ส่งเอง)
description_en: Draft a formal email with subject, greeting, body and closing (draft only, never sent)
order: 70
arguments:
  - name: to
    description: ผู้รับ (ชื่อ ตำแหน่ง หน่วยงาน)
    description_en: Recipient (name, position, organization)
    required: true
  - name: purpose
    description: จุดประสงค์ของอีเมล
    description_en: Purpose of the email
    required: true
  - name: details
    description: รายละเอียดที่ต้องใส่ เช่น วันที่ ตัวเลข เอกสารแนบ
    description_en: Details to include, e.g. dates, figures, attachments
    required: false
  - name: language
    description: ภาษาของอีเมล th หรือ en
    description_en: Email language, th or en
    required: false
    default: th
    default_en: en
---
ร่างอีเมลทางการ
- ถึง: {{to}}
- จุดประสงค์: {{purpose}}
{{#details}}
- รายละเอียดที่ต้องมี: {{details}}
{{/details}}
- ภาษาของอีเมล: {{language}} (th = ไทย, en = อังกฤษ)

โครงสร้าง
1. หัวเรื่อง (Subject) สั้น ชัด บอกเรื่องและสิ่งที่ต้องการ
2. คำขึ้นต้น (ภาษาไทย: เรียน ... / ภาษาอังกฤษ: Dear ...)
3. ย่อหน้าเปิด: บริบทหรือที่มาในประโยคเดียว
4. เนื้อหา: สิ่งที่แจ้งหรือขอให้ชัดเจน มีกำหนดเวลาถ้าเกี่ยวข้อง
5. ย่อหน้าปิด: ขอบคุณ และช่องทางติดต่อกลับ
6. คำลงท้าย (ขอแสดงความนับถือ / Best regards) และลายเซ็น [ชื่อ-นามสกุล] [ตำแหน่ง] [หน่วยงาน] [โทรศัพท์]

สุภาพ กระชับ ไม่เกิน 200 คำถ้าไม่จำเป็น ห้ามแต่งข้อมูลที่ไม่ได้ให้มา ใช้ [ ] แทนส่วนที่ต้องเติม
ร่างอย่างเดียว ไม่ต้องส่งอีเมลหรือสร้างไฟล์ เว้นแต่ผู้ใช้ขอ
