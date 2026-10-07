<#
  ตัวเปิด Qwen3.8-27B แบบครบชุด — เรียกจาก shortcut บน Desktop

  ทำอะไรบ้าง
    0. ตรวจว่ามีโทเคนของบริการในเครื่อง C:\LLM\secrets\local-services.token (ไม่มี = สร้างใหม่ ผ่าน
       C:\LLM\secrets_util.py --ensure หรือสร้างเองถ้า helper ยังไม่มี) — MCP 8791/8792 รับเฉพาะคำขอที่มีโทเคนนี้
       hub ส่งให้หน้าแชตเอง  ตัวเปิดไม่พิมพ์ค่าโทเคนที่ไหนเลย
    1. เปิด MCP ค้นอินเทอร์เน็ต (8791) และ MCP เครื่องมือในเครื่อง (8792)
    2. ตรวจ GPU ที่ต่ออยู่ตอนนี้ (ในเครื่อง + eGPU ทาง Thunderbolt) ด้วย C:\LLM\gpu_profile.py
       แล้วเขียน C:\LLM\models-preset.ini ว่าโมเดลไหนใช้ GPU ไหน ctx เท่าไร เปิดดูรูปหรือไม่
       จากนั้นเปิด llama-server แบบ router (พอร์ต 8099) พร้อม
         --models-dir       สแกนโมเดลในโฟลเดอร์ ให้เลือกได้จากหน้าเว็บ
         --models-preset    ค่าต่อโมเดลจาก gpu_profile.py (ctx, KV cache, threads, GPU, mmproj)
         (ไม่ใช้ --tools all แล้ว เครื่องมือย้ายไป MCP 8792 ที่มีชั้นป้องกัน)
         --ui-config-file   ธีมมืด + ลงทะเบียน MCP ให้อัตโนมัติ
         --cors-origins     เฉพาะหน้าของเรา (+ --no-cors-credentials) — ค่าเดิม (*) สะท้อนทุก origin พร้อม credentials
         --api-key-file     โทเคนของบริการในเครื่อง (ข้อ 0) — ทุกคำขอยกเว้น /health ต้องมี (hub แนบให้หน้าแชตเอง)
         (ไม่ใช้ --ui-mcp-proxy แล้ว: WebUI ต่อ MCP ตรงด้วย CORS + โทเคนของ MCP เอง ดู "ความปลอดภัย" ด้านล่าง)
       โดยตั้ง working directory ไว้ที่ C:\ เพื่อให้ path สัมพัทธ์กวาดได้ทั้งไดรฟ์
       router ที่รันอยู่แต่ยังเปิดด้วยค่าความปลอดภัยแบบเก่า (--ui-mcp-proxy / CORS เปิดกว้าง / ไม่มี API key /
       โทเคนชุดเก่า) ถูกรีสตาร์ตเมื่อแชตว่าง
       ถ้า router เปิดอยู่แล้ว: เทียบ GPU และค่าตั้งกับตอนที่มันเริ่ม ต่างเมื่อไหร่รอแชตที่ค้างอยู่ให้เสร็จ
       แล้วรีสตาร์ตเฉพาะ router (เสียบ/ถอด eGPU แล้วดับเบิลคลิก shortcut เดิมได้เลย)
       สร้าง preset ไม่สำเร็จ หรือ router ปิดตัวทันทีเมื่อใช้ preset → เปิดด้วยค่าแบบเดิมทุกอย่าง
    3. เปิด project hub (พอร์ต 8100) แล้วเปิดเบราว์เซอร์ไปที่หน้าเลือกโปรเจกต์
    1d. (batch 2a, สัญญา B2) บริการ embedding พอร์ต 8093 — llama-server --embeddings อีกตัว (CPU ล้วน) ให้ MCP
        ค้นเอกสารของโปรเจกต์ตามความหมาย โมเดล D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf, log ที่
        C:\LLM\logs\embed.out.log / embed.err.log  ไม่มีโมเดล / ไม่มีไฟล์โทเคน / เปิดไม่ขึ้น = MCP ค้นด้วยคำอย่างเดียว
        (ไม่ใช่ข้อผิดพลาดของตัวเปิด)  -NoEmbed = ไม่แตะบริการนี้  -EmbedPort N = พอร์ตอื่น (รอบทดสอบ)
        -EmbedOnly = ทำข้อ 1d อย่างเดียวแล้วจบ (ไม่แตะ MCP/hub/router) exit 0 = พร้อม, 1 = ไม่พร้อม
        -RestartEmbed = เหมือน -EmbedOnly แต่ปิดตัวที่รันอยู่แล้วเปิดใหม่แม้มันปกติดี (ใช้แทน restart_svc ที่ไม่มีเป้า embed:
                        หลังอัปเดต llama.cpp/โมเดล หรือบริการค้าง) — ระหว่างเปิดใหม่ ~10-30 วินาที kb ค้นด้วยคำอย่างเดียว
                        ไม่มีแชตให้รอ (บริการนี้ไม่ได้ตอบแชต) โปรแกรมอื่นที่ถือพอร์ตอยู่ยังไม่ถูกแตะเหมือนเดิม
        ตัวที่รันอยู่แต่ค่าความปลอดภัยแบบเก่า (ไม่มีคีย์ / CORS กว้าง / เปิด /slots) หรือโทเคนชุดเก่า ถูกเปิดใหม่ทันที
        รอบทดสอบ (-Port อื่นที่ไม่ใช่ 8099) ข้ามบริการนี้ถ้าไม่ได้ใส่ -EmbedPort เอง — ไม่ไปเปิด/เปิดใหม่ตัวจริงที่ 8093
    1e. (batch 2b, สัญญา C1/C3) บริการแปลงเสียงเป็นข้อความ (STT) พอร์ต 8795 — C:\LLM\stt\stt_server.py ของ owner voice
        รันด้วย python ของ conda env flexxfast (มี faster-whisper ที่นั่นที่เดียว) ผ่าน WMI env สะอาด + HF_HUB_OFFLINE=1
        hub ส่งเสียงจากปุ่มไมค์ (POST /_qwen/stt) ต่อมาที่ /v1/transcribe พร้อมโทเคน  log C:\LLM\logs\stt.out.log / stt.err.log
        ไม่มีสคริปต์ / ไม่มี flexxfast / ไม่มีโทเคน / เปิดไม่ขึ้น = ปุ่มไมค์ใช้ไม่ได้อย่างเดียว (ไม่กระทบแชตและ exit code)
        -NoStt = ไม่แตะ  -SttPort N = พอร์ตอื่น (รอบทดสอบ)  -SttOnly = ทำข้อ 1e อย่างเดียวแล้วจบ (exit 0 = พร้อม, 1 = ไม่พร้อม)
        -RestartStt = เหมือน -SttOnly แต่ปิดตัวที่รันอยู่แล้วเปิดใหม่ (หลังอัปเดต stt_server.py — restart_svc ไม่มีเป้า stt)
        ไม่ทำในโหมด -NonInteractive (hub สั่งใช้ GPU ชุดใหม่ ไม่ใช่เรื่องของบริการนี้)  รอบทดสอบ (-Port อื่น) ข้ามถ้าไม่ใส่ -SttPort

  พารามิเตอร์เรื่อง GPU
    -Ctx N         บังคับ context ของทุกโมเดล (ไม่ใส่ = เลือกให้: 27B ได้ 65536 เมื่ออยู่บน 4090 ทั้งตัว)
    -Threads N     จำนวนเธรด CPU (ปกติ 6)
    -Vision        บังคับเปิดดูรูปของโมเดลหลัก   -NoVision  บังคับปิด   (มีผลเฉพาะรอบที่สั่ง)
    -Primary ID    เลือกโมเดลหลักเอง (ชื่อไฟล์ไม่มี .gguf)  ปกติ = Qwen3.8-27B-UD-Q4_K_M
  แก้ค่าเองแบบถาวร: C:\LLM\models-preset.user.ini (รูปแบบเดียวกับ models-preset.ini) เช่น
    [Qwen3.8-27B-UD-Q4_K_M]
    mmproj = C:\LLM\models\mmproj-Qwen3.8-27B-F16.gguf        ← ดูรูปได้ทุกครั้งแม้ไม่ได้ต่อ 4090
    [Qwen3-Coder-30B-A3B-Instruct-UD-Q4_K_XL]
    device = CUDA1,CUDA0                                       ← ให้ Coder ใช้ 4090 ด้วยตอนต่ออยู่
  วัดความเร็วจริงหลังเสียบ eGPU: C:\Python313\python.exe C:\LLM\gpu_bench.py
  เลือก GPU ต่อโมเดลเองได้ในหน้าแชต (เมนูบัญชี → เลือก GPU…) — hub เขียน C:\LLM\gpu-choice.json แล้วเรียก
  ตัวเปิดนี้ด้วย -NoBrowser -NonInteractive ให้ (ลำดับ: แผนอัตโนมัติ < gpu-choice.json < models-preset.user.ini)

  พารามิเตอร์สำหรับโปรแกรมอื่นเรียก (hub)
    -NonInteractive  ไม่ถาม (Read-Host) ไม่หน่วงตอนจบ ไม่เปิดเบราว์เซอร์ ไม่แตะ MCP/ตัวตั้งเวลา/Gateway/hub
                     (บริการ embedding ข้อ 1d ยังเปิดให้ถ้าไม่ทำงาน: ไม่ขึ้นกับ GPU ไม่มีแชตให้รอ และไม่มีผลกับ exit code)
                     พิมพ์ความคืบหน้าเป็น UTF-8 ทาง stdout แล้วจบด้วย exit code:
                       0 = เสร็จ (รีสตาร์ตแล้ว หรือไม่มีอะไรต้องเปลี่ยน)
                       3 = ยังมีแชตกำลังตอบอยู่เมื่อรอครบเวลา — ไม่ได้รีสตาร์ต
                       1 = ผิดพลาด (สร้างแผนไม่ได้ / router เปิดไม่ขึ้น / preset ใช้ไม่ได้ / ตรวจสถานะแชตไม่ได้ /
                           ตัวเปิดอีกตัวทำงานอยู่นานเกิน 10 นาที ฯลฯ)
                     ปิดการสืบทอด stdout/stderr ของตัวเองก่อนเปิดลูก — llama-server ไม่ถือ log ของ hub ค้างไว้
    -Unattended      (fix-stack 2026-10-06) เปิด "ครบชุด" แบบเดียวกับเปิดจากไอคอน (MCP ×2, ตัวตั้งเวลา, Gateway, embedding,
                     STT, router, hub) แต่ไม่มีคนนั่งดู: ไม่ถาม Read-Host (จุดที่เคยรอ Enter ตอนล้มเหลวพิมพ์ "ผลลัพธ์: failed"
                     แล้วจบ) ไม่เปิดเบราว์เซอร์ ไม่หน่วงตอนจบ stdout เป็น UTF-8 และจบด้วย exit code แบบ -NonInteractive (0/3/1)
                     ใช้กับการเปิดใหม่หลังรีบูต/สคริปต์ผ่าน WMI — อย่าใช้ -NonInteractive แทน: โหมดนั้นข้าม MCP/ตัวตั้งเวลา/
                     Gateway/hub/STT โดยตั้งใจ (เป็นของปุ่ม "บันทึกและรีสตาร์ตโมเดล" ของ hub เท่านั้น) — หลังรีบูต stack จะขึ้นไม่ครบ
                     ตัวอย่าง (WMI env สะอาด):
                       powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\start-qwen38.ps1 -Unattended
  ตัวเปิดสองตัวบนพอร์ตเดียวกันไม่ทำงานซ้อนกัน (named mutex Local\Qwen38Launcher-<port>): ตัวที่มาทีหลัง
  (จากไอคอนหรือจาก hub) รอสูงสุด 10 นาที แล้วตรวจ/เทียบใหม่เอง — ไม่รีสตาร์ต router ซ้ำซ้อน
    -ChoiceFile P    อ่านการเลือก GPU จากไฟล์นี้แทน C:\LLM\gpu-choice.json (none = ไม่ใช้)
    -IdleTimeoutSec  รอแชตที่กำลังตอบนานสุดกี่วินาทีก่อนยอมแพ้ (ปกติ 180 — ลดไว้ใช้ตอนทดสอบเท่านั้น)

  ไฟล์แผน GPU: C:\LLM\models-preset.ini + gpu-profile.json เป็นของ router พอร์ตหลัก 8099 เท่านั้น
  (hub และ gpu_bench อ่านไฟล์นี้)  รันทดสอบด้วย -Port อื่นจะเก็บแยกที่ C:\LLM\logs\gpu-<port>\

  ความปลอดภัย (2026-09-30)
    * บริการที่รันค้าง (MCP ×2, ตัวตั้งเวลา, Gateway, hub, llama-server) เปิดผ่าน WMI Win32_Process.Create
      ได้ environment มาตรฐานของผู้ใช้ ไม่ใช่ของโปรแกรมที่เรียกตัวเปิด (เชลล์ของเครื่องมือ/เอเจนต์เคยมีโทเคนติดมา
      แล้วส่งต่อถึง MCP ที่รันคำสั่งให้โมเดลได้) WMI ใช้ไม่ได้ = ถอยไป Start-Process หลังตัดตัวแปรลับออกจาก env
    * --ui-mcp-proxy ("do not enable in untrusted environments") เปิด /cors-proxy ให้หน้าเว็บใดก็ได้ใช้ llama-server
      ยิงคำขอไปที่ไหนก็ได้ รวมถึง hub/MCP ในเครื่อง — WebUI ของเราไม่ได้ใช้ (useProxy=false) จึงถอดออก
      ผลข้างเคียง: MCP ภายนอกที่ผู้ใช้เพิ่มเองแล้วติ๊ก "use proxy" จะต่อไม่ได้ (ต้องเป็นเซิร์ฟเวอร์ที่เปิด CORS เอง)
    * --api-key-file = ไฟล์โทเคนเดียวกับ MCP (C:\LLM\secrets\local-services.token): llama-server ไม่ตรวจ Host
      และ CORS กันได้แค่ "การอ่านคำตอบ" — เดิมเว็บไหนก็ส่ง POST แบบ text/plain (ไม่มี preflight) สั่งโหลด/ปลดโมเดล
      หรือแชตได้ และหน้าที่ใช้ DNS rebinding อ่าน /props /slots ได้  ตอนนี้ทุกเส้นทางยกเว้น /health และไฟล์หน้าเว็บ
      ต้องมีโทเคน (วัดบน b10984: /models /v1/models /slots /props ก็ต้องใช้ — โมเดลลูกได้ --api-key-file ต่อจาก
      router เป็น path ไม่ใช่ค่า) ผู้ที่แนบให้เอง: hub (proxy ของทุกโปรเจกต์), Gateway, gpu_profile/gpu_bench
      ผลข้างเคียง: หน้าแชตดิบที่ http://127.0.0.1:8099 ถามหา API key — ใช้ http://127.0.0.1:<พอร์ตโปรเจกต์>/?ui=1 แทน
      สคริปต์เก่าที่ยิง 8099 ตรงๆ ต้องแนบโทเคน หรือยิงผ่านพอร์ตโปรเจกต์ของ hub แทน (hub แนบให้)
      ไฟล์โทเคนถูกสร้างใหม่เมื่อไร router ตัวที่รันอยู่ยังจำค่าเก่า — ตัวเปิดตรวจเจอ (/props ตอบ 401) แล้วรีสตาร์ตให้
    * สิทธิ์ของโฟลเดอร์ C:\LLM\secrets: ตัวเปิดแค่ตรวจแล้วเตือน (สืบทอดจาก C:\ ให้ทุกบัญชีในเครื่องอ่านได้) ไม่แก้สิทธิ์เอง
      เพราะเป็นการเปลี่ยนค่าความปลอดภัยของระบบไฟล์ — คำสั่ง icacls ที่ต้องใช้พิมพ์ไว้ในคำเตือน

  ปิดการทำงาน: ปิดหน้าต่าง PowerShell ที่ค้างไว้ หรือรัน stop-qwen38.ps1
#>
[CmdletBinding()]
param(
    [int]$Port     = 8099,
    [int]$McpPort      = 8791,
    [int]$McpLocalPort = 8792,
    [int]$HubPort  = 8100,
    [int]$GatewayPort  = 8780,
    # ส่งต่อเฉพาะตอนพิมพ์ -Ctx เอง (ดู $CtxGiven) ค่าปริยายนี้ใช้แค่ตอนถอยไปค่าแบบเดิม
    # ไม่งั้น 32768 จะไปทับ 65536 ที่ gpu_profile เลือกให้ 27B บน 4090
    [int]$Ctx      = 32768,
    # 6 = เฉพาะ P-core ของ Core Ultra 7 165H (6P+8E+2LPE) — วัดจริง 2026-09-24:
    #   6 เธรด 0.84 | 8 เธรด 0.74 | 10 เธรด 0.75 | 14 เธรด 0.57 tok/s (27B, ctx 32K)
    # ใช้ E-core ด้วยแล้วช้าลง เพราะทุกโทเคนต้องรอเธรดที่ช้าที่สุด
    [int]$Threads  = 6,
    [switch]$NoBrowser,
    [switch]$Vision,
    [switch]$NoVision,
    [string]$Primary = '',
    # hub เรียกตอนผู้ใช้กด "บันทึกและรีสตาร์ตโมเดล" ในหน้าเลือก GPU — ดูหัวไฟล์
    [switch]$NonInteractive,
    [string]$ChoiceFile = '',
    [int]$IdleTimeoutSec = 180,
    # บริการ embedding (ข้อ 1d) — พอร์ตหลัก 8093 ตามสัญญา B2 (tools_kb.py ของ MCP เรียกพอร์ตนี้)
    [int]$EmbedPort = 8093,
    [switch]$NoEmbed,
    # เปิด/ตรวจเฉพาะบริการ embedding แล้วจบ (ไม่แตะ MCP / ตัวตั้งเวลา / Gateway / hub / router) — ดูหัวไฟล์ข้อ 1d
    [switch]$EmbedOnly,
    # batch 2a (fix): -EmbedOnly + เปิดใหม่แม้ตัวที่รันอยู่ปกติดี (restart_svc.ps1 ไม่มีเป้า embed) — ดูหัวไฟล์ข้อ 1d
    [switch]$RestartEmbed,
    # batch 2b (C3): บริการแปลงเสียงเป็นข้อความ พอร์ตหลัก 8795 ตามสัญญา C1 (hub ส่งเสียงจากปุ่มไมค์มาที่นี่) — ดูหัวไฟล์ข้อ 1e
    [int]$SttPort = 8795,
    [switch]$NoStt,
    [switch]$SttOnly,
    [switch]$RestartStt,
    # fix-stack 2026-10-06: เปิดครบชุดแบบไม่มีคนดู (หลังรีบูต/สคริปต์) — ดูหัวไฟล์ "-Unattended"
    [switch]$Unattended
)

$ErrorActionPreference = 'Stop'

# ตัดตัวแปรลับที่ติดมากับโปรแกรมที่เรียกเรา (เชลล์ของเครื่องมือ/เอเจนต์: CLAUDE_*, *_TOKEN, *_API_KEY ...) ออกจาก env
# ของตัวเปิดเองก่อนเปิดลูกตัวไหน — ทางหลักคือเปิดบริการผ่าน WMI (ได้ env สะอาดอยู่แล้ว) ตรงนี้กันทางสำรอง
# (Start-Process) กับโปรแกรมช่วยอายุสั้น (gpu_profile.py) ที่สืบทอด env ของเรา
# ตัวที่ผู้ใช้ตั้งไว้เองถาวร (User/Machine เช่น GATEWAY_API_KEY) ไม่ใช่ของแปลกปลอม — คงไว้ ไม่งั้น Gateway เปลี่ยนคีย์
function Remove-InheritedSecrets {
    $deny = '^(CLAUDE|ANTHROPIC|OTEL_|SENTRY|BAGGAGE|AI_AGENT)|TOKEN|SECRET|PASSW(OR)?D|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY|CREDENTIAL|OAUTH|_KEY$'
    # ชื่อมีคำว่า TOKEN แต่เป็นแค่ path ของไฟล์โทเคนทดสอบ ไม่ใช่ความลับ — ตัดทิ้งแล้วตัวเปิดจะไปสร้าง/ใช้ไฟล์จริงแทน
    $keep = @('LLM_LOCAL_TOKEN_FILE')
    foreach ($item in @(Get-ChildItem Env: -ErrorAction SilentlyContinue)) {
        $n = [string]$item.Name
        if ($n -notmatch $deny -or $keep -contains $n) { continue }
        try {
            if ($null -ne [Environment]::GetEnvironmentVariable($n, 'User')) { continue }
            if ($null -ne [Environment]::GetEnvironmentVariable($n, 'Machine')) { continue }
        } catch { }
        Remove-Item -LiteralPath "Env:\$n" -ErrorAction SilentlyContinue
    }
}
Remove-InheritedSecrets

# -EmbedOnly ไม่มีใครนั่งอ่านหน้าจอ (ผู้ติดตั้ง/สคริปต์เรียก) — ไม่ถาม Read-Host ไม่เปิดเบราว์เซอร์ ไม่หน่วงตอนจบ เหมือน -NonInteractive
# -RestartEmbed ทำเฉพาะข้อ 1d เหมือน -EmbedOnly (สั่งเปิดใหม่ต้องไม่ลามไปรีสตาร์ต router/MCP/hub)
if ($RestartEmbed) { $EmbedOnly = $true }
if ($EmbedOnly) { $NonInteractive = $true }
# batch 2b (C3): -SttOnly / -RestartStt ทำเฉพาะข้อ 1e แบบเดียวกัน (ไม่มีใครนั่งอ่านหน้าจอ ห้ามลามไปแตะ router/MCP/hub)
if ($RestartStt) { $SttOnly = $true }
if ($SttOnly) { $NonInteractive = $true }
# fix-stack 2026-10-06: -Unattended = เปิดครบชุด (ไม่ใช่ -NonInteractive ที่ข้าม MCP/hub/STT) แต่ไม่มีใครกด Enter ให้
# ทำไม: integrator เปิดใหม่หลังรีบูตด้วย "-NoBrowser -NonInteractive" ตามคำแนะนำเดิม แล้ว stack ขึ้นแค่ router + embedding
# ส่วน "-NoBrowser" อย่างเดียวผ่าน WMI ขึ้นครบ แต่ถ้าเจอจุดล้มเหลวที่รอ Read-Host โปรเซสที่ซ่อนอยู่จะค้างรอตลอดไป
if ($Unattended -and -not $NonInteractive) {
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
    $NoBrowser = $true
}

if ($NonInteractive) {
    # hub อ่าน stdout เป็น UTF-8 — ค่าปริยายของ PS 5.1 (code page ของ Windows) ทำให้ภาษาไทยกลายเป็น "?"
    # (ทดสอบแล้ว: ตั้งตรงนี้ Write-Host ทั้งหมดออกเป็น UTF-8 ไม่มี BOM)
    try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false } catch { }
    $NoBrowser = $true
    # hub ส่ง stdout/stderr ของเราลง C:\LLM\logs\gpu-apply.log ด้วย handle ที่สืบทอดได้ และ Start-Process แบบ
    # -RedirectStandard* ของ PS 5.1 เรียก CreateProcess แบบ "สืบทอด handle ทุกตัวที่สืบทอดได้" — llama-server ที่เปิด
    # จากตรงนี้จึงถือ gpu-apply.log ค้างไว้ตลอดอายุ router (ลบ/หมุน log ไม่ได้ ทุก router ที่รีสตาร์ตจากหน้าแชตติดไปด้วย)
    # ปิดการสืบทอดของ stdout/stderr ของเราเองก่อนเปิดลูกตัวไหน — ลูกทุกตัวมี -RedirectStandardOutput/-Error เป็นไฟล์
    # ของตัวเองอยู่แล้ว ไม่ได้ใช้ handle ของเรา (stdin ของเราเป็น NUL จาก hub ปล่อยไว้: ไม่ได้ล็อกไฟล์อะไร)
    # ต้องไล่ทุก handle ไม่ใช่แค่ GetStdHandle: powershell.exe เองทำสำเนา handle ของ stdout (สืบทอดได้) ไว้อีกตัวตั้งแต่
    # ก่อนสคริปต์เริ่ม (ตรวจแล้ว: 3 handle ชี้ไฟล์เดียวกัน) — CompareObjectHandles เทียบว่าเป็น object เดียวกันไหม
    # โดยไม่ทำ I/O (ไม่ค้างแบบ GetFileType/ชื่อไฟล์ของ pipe) ไม่มีฟังก์ชันนี้ (Windows เก่ากว่า 10) = ปิดแค่ std handle
    # ทำเฉพาะโหมดนี้ — ตอนเปิดจากไอคอน stdout เป็นหน้าต่าง console ไม่มีไฟล์ให้ติดค้าง
    try {
        Add-Type -Namespace Qwen38Launcher -Name StdHandles -ErrorAction Stop -MemberDefinition @'
[DllImport("kernel32.dll", SetLastError = true)] static extern IntPtr GetStdHandle(int nStdHandle);
[DllImport("kernel32.dll", SetLastError = true)] static extern bool GetHandleInformation(IntPtr h, out int flags);
[DllImport("kernel32.dll", SetLastError = true)] static extern bool SetHandleInformation(IntPtr h, int mask, int flags);
[DllImport("kernelbase.dll", SetLastError = true)] static extern bool CompareObjectHandles(IntPtr a, IntPtr b);
public static int StopInheritingOutput() {
    IntPtr o = GetStdHandle(-11), e = GetStdHandle(-12);
    int n = 0;
    foreach (IntPtr s in new IntPtr[] { o, e }) {
        if (s != IntPtr.Zero && s != new IntPtr(-1) && SetHandleInformation(s, 1, 0)) n++;
    }
    try {
        for (int i = 4; i < 65536; i += 4) {
            IntPtr h = new IntPtr(i);
            int f;
            if (h == o || h == e || !GetHandleInformation(h, out f) || (f & 1) == 0) continue;
            if (CompareObjectHandles(h, o) || CompareObjectHandles(h, e)) {
                if (SetHandleInformation(h, 1, 0)) n++;
            }
        }
    } catch (EntryPointNotFoundException) { } catch (DllNotFoundException) { }
    return n;
}
'@
        $null = [Qwen38Launcher.StdHandles]::StopInheritingOutput()
    } catch {
        Write-Host "  (ปิดการสืบทอด handle ของ log ไม่ได้: $($_.Exception.Message) — llama-server ใหม่จะถือ gpu-apply.log ค้างไว้ ทำงานต่อได้ตามปกติ)" -ForegroundColor DarkGray
    }
}
# ค่าผิดรูปกลับเป็น 3 นาที — สั้นเกินไปจะตัดแชตที่กำลังตอบ (ต้องว่างต่อเนื่อง ~9 วินาทีอยู่แล้ว)
if ($IdleTimeoutSec -lt 1 -or $IdleTimeoutSec -gt 3600) { $IdleTimeoutSec = 180 }
# ผลลัพธ์ของโหมด -NonInteractive: 'done' | 'busy' | 'failed' + เหตุผล (บรรทัดสุดท้ายของ log ที่ hub แสดง)
$Outcome = 'done'
$OutcomeWhy = ''
$LlamaDir = 'C:\LLM\llama.cpp-b10984'
$Server   = Join-Path $LlamaDir 'llama-server.exe'
# C:\LLM\models เป็น junction ชี้ไป D:\LLM\models (ย้ายเมื่อ 2026-09-16)
# ใช้ path เดิมต่อไปได้ทุกที่ ถ้าจะย้ายกลับให้ลบ junction แล้วคัดลอกไฟล์คืน
$Model    = 'C:\LLM\models\Qwen3.8-27B-UD-Q4_K_M.gguf'
$Mmproj   = 'C:\LLM\models\mmproj-Qwen3.8-27B-F16.gguf'
$ModelsDir = Split-Path $Model -Parent
$UiConfig = 'C:\LLM\ui-config.json'
$McpDir   = 'C:\LLM\mcp-websearch'
$McpLocal = 'C:\LLM\mcp-local'
$LogDir   = 'C:\LLM\logs'
# โทเคนของบริการในเครื่อง (สัญญา C1) — ทั้งโฟลเดอร์ถูกบล็อกจากเครื่องมือทุกตัวของ MCP
# LLM_LOCAL_TOKEN_FILE = ไฟล์โทเคนทดสอบ (ตัวแปรเดียวกับ secrets_util.token_path() และ hub) — ตั้งไว้เมื่อไร
# ตัวเปิดส่งต่อให้บริการที่เปิดด้วย ทุกตัวจึงอ่านไฟล์เดียวกัน  ปกติไม่ได้ตั้ง = ไฟล์จริง
$TokenFile   = 'C:\LLM\secrets\local-services.token'
if ($env:LLM_LOCAL_TOKEN_FILE) { $TokenFile = $env:LLM_LOCAL_TOKEN_FILE }
$SecretsDir  = Split-Path $TokenFile -Parent
$SecretsUtil = 'C:\LLM\secrets_util.py'
# ตัวแปรที่บริการ python ทุกตัวต้องได้ (env สะอาดของ WMI ไม่มี) — ว่าง = ไม่ส่ง
$SvcEnv = @{ LLM_LOCAL_TOKEN_FILE = [string]$env:LLM_LOCAL_TOKEN_FILE }
$PyExe       = 'C:\Python313\python.exe'
$GpuProfile  = 'C:\LLM\gpu_profile.py'
$UserIni     = 'C:\LLM\models-preset.user.ini'
# ไฟล์กลางใน C:\LLM เป็นของ router พอร์ตหลักที่ hub ต่ออยู่ (hub และ gpu_bench อ่าน)
# พอร์ตอื่น (ทดสอบ) ต้องเก็บแยก ไม่งั้นรอบทดสอบ (หรือรอบที่ซ่อน GPU ด้วย CUDA_VISIBLE_DEVICES) จะเขียนทับ
# แผนของตัวจริง แล้ว hub บอกผู้ใช้ว่า "ไม่มี GPU" ทั้งที่ router ตัวจริงใช้ GPU อยู่
# กฎเดียวกับ published_dir() ใน gpu_profile.py — แก้ที่หนึ่งต้องแก้อีกที่ด้วย
$MainPort = 8099
if ($Port -eq $MainPort) { $PubDir = 'C:\LLM' } else { $PubDir = Join-Path $LogDir "gpu-$Port" }
$PresetFile  = Join-Path $PubDir 'models-preset.ini'
$ProfileJson = Join-Path $PubDir 'gpu-profile.json'
# router ตัวทดสอบ (เช่น -Port 8199) ต้องไม่เขียนทับ log ที่ router ตัวจริงเปิดค้างอยู่
if ($Port -eq $MainPort) { $LlamaLogName = 'llama' } else { $LlamaLogName = "llama-$Port" }
$StateFile = Join-Path $LogDir "router-$Port.state.json"
# บริการ embedding (ข้อ 1d): โมเดลแยกโฟลเดอร์จาก C:\LLM\models โดยตั้งใจ — router สแกน --models-dir แล้วจะเอาไปโชว์
# เป็นโมเดลแชตถ้าอยู่ที่เดียวกัน  พอร์ตทดสอบเขียน log แยก ไม่ทับ log ที่ตัวจริงเปิดค้างอยู่ (แบบเดียวกับ llama-<port>)
$EmbedModel     = 'D:\LLM\models-embed\Qwen3-Embedding-0.6B-Q8_0.gguf'
$EmbedMainPort  = 8093
$EmbedPortGiven = $PSBoundParameters.ContainsKey('EmbedPort')
if ($EmbedPort -eq $EmbedMainPort) { $EmbedLogName = 'embed' } else { $EmbedLogName = "embed-$EmbedPort" }
# บริการ STT (ข้อ 1e): สคริปต์ของ owner voice — พอร์ตทดสอบเขียน log แยก ไม่ทับ log ที่ตัวจริงเปิดค้างอยู่
$SttScript    = 'C:\LLM\stt\stt_server.py'
$SttMainPort  = 8795
$SttPortGiven = $PSBoundParameters.ContainsKey('SttPort')
if ($SttPort -eq $SttMainPort) { $SttLogName = 'stt' } else { $SttLogName = "stt-$SttPort" }
# สร้างโปรไฟล์ใหม่ลงที่พักก่อนเสมอ ถ้า router เปิดอยู่จะได้เทียบกับของเดิมก่อนตัดสินใจทับ
$GenDir    = Join-Path $env:TEMP "qwen38-gpu-$Port"
$CtxGiven  = $PSBoundParameters.ContainsKey('Ctx')
$PrimaryId = [System.IO.Path]::GetFileNameWithoutExtension($Model)
if ($Vision -and $NoVision) {
    Write-Host '  ใส่ทั้ง -Vision และ -NoVision — ใช้ -NoVision' -ForegroundColor Yellow
    $Vision = $false
}

# ลำดับ CUDA ปริยายคือ "เร็วสุดก่อน" พอเสียบ 4090 มันจะแย่งชื่อ CUDA0 ไป แล้ว device = CUDA0
# ใน preset จะชี้ผิดตัว  PCI_BUS_ID ทำให้ชื่อคงที่ (eGPU ได้ bus number สูงกว่า GPU ในเครื่องเสมอ)
# ต้องเป็นค่าเดียวกันทั้งตอนตรวจ GPU และตอนเปิด router — ตั้งที่ process นี้ ลูกทุกตัวได้ตาม
$env:CUDA_DEVICE_ORDER = 'PCI_BUS_ID'

function Test-Port([int]$p) {
    $null -ne (Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue)
}

# จดผลของรอบนี้ (ใช้ตอนจบในโหมด -NonInteractive) — 'failed' ชนะเสมอ ผลที่มาทีหลังห้ามกลบข้อผิดพลาด
function Set-Outcome([string]$State, [string]$Why) {
    if ($script:Outcome -eq 'failed') { return }
    $script:Outcome = $State
    $script:OutcomeWhy = $Why
}

# พอร์ตที่ "มีคนฟัง" ไม่ได้แปลว่าเป็นของเรา บนเครื่องนี้ Wondershare เคยยึด 8090 ไปแล้ว
# จึงต้องถาม /health ว่าเป็น llama-server จริงหรือเปล่า
function Test-Llama([int]$p) {
    try { return (Invoke-RestMethod -Uri "http://127.0.0.1:$p/health" -TimeoutSec 3 -ErrorAction Stop).status -eq 'ok' }
    catch { return $false }
}

function Get-PortOwner([int]$p) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $c) { return $null }
    (Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" -ErrorAction SilentlyContinue).Name
}

function Get-PortPid([int]$p) {
    $c = Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return [int]$c.OwningProcess }
    return 0
}

function Format-Arg([string]$a) {
    # Start-Process ของ PS 5.1 เอา ArgumentList มาต่อด้วยช่องว่างเฉยๆ ตัวที่มีช่องว่างต้องครอบ "" เอง
    if ($a -match '\s') { return '"' + $a + '"' }
    return $a
}

# ---- เปิดบริการที่รันค้างด้วย environment สะอาด ----------------------------------------------
# Start-Process ส่ง env ของตัวเปิดต่อให้ลูกทั้งก้อน ถ้าตัวเปิดถูกเรียกจากเชลล์ของเครื่องมือ/เอเจนต์ (หรือ hub ที่ถูก
# เปิดจากเชลล์แบบนั้น) ตัวแปรลับของเชลล์นั้นจะติดไปอยู่ใน MCP ที่รันคำสั่งให้โมเดลได้เป็นวันๆ (เจอจริง 2026-09-29)
# WMI Win32_Process.Create สร้างโปรเซสด้วย environment มาตรฐานของผู้ใช้ (แบบเปิดจาก Explorer) ไม่สืบทอดของเรา
# และไม่สืบทอด handle ใดๆ ของเราด้วย (llama-server จึงไม่ถือ gpu-apply.log ของ hub ค้างไว้)
# ครอบด้วย cmd.exe เพื่อส่ง stdout/stderr ลงไฟล์ log เดิม และตั้งตัวแปรที่ลูกต้องใช้ ($ChildEnv เช่น CUDA_DEVICE_ORDER)
# /d = ไม่รัน AutoRun ของ cmd, /s = ตัด "" คู่นอกสุดออกตรงๆ (path ที่มีช่องว่างข้างในยังครอบ "" ได้)
# คืน @{ Pid; Proc; Wmi } หรือ $null — Pid ของ WMI คือ cmd.exe ที่ครอบ (จบเมื่อโปรแกรมข้างในจบ)
function Start-CleanProcess([string]$Exe, [object[]]$ArgList, [string]$WorkDir, [string]$OutLog,
                            [string]$ErrLog, [hashtable]$ChildEnv) {
    $argLine = ($ArgList | ForEach-Object { Format-Arg ([string]$_) }) -join ' '
    $sets = ''
    if ($ChildEnv) {
        foreach ($k in $ChildEnv.Keys) {
            $v = [string]$ChildEnv[$k]
            if ($v) { $sets += ('set "{0}={1}"&& ' -f $k, $v) }
        }
    }
    $inner = $sets + '"' + $Exe + '" ' + $argLine + ' > "' + $OutLog + '" 2> "' + $ErrLog + '"'
    $cmdLine = 'cmd.exe /d /s /c "' + $inner + '"'
    if ($cmdLine.Length -le 8000) {       # เพดานบรรทัดคำสั่งของ cmd.exe = 8191 ตัวอักษร
        try {
            $si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
            $r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -ErrorAction Stop -Arguments @{
                CommandLine = $cmdLine; CurrentDirectory = $WorkDir; ProcessStartupInformation = $si }
            if ($r.ReturnValue -eq 0 -and $r.ProcessId) {
                return @{ Pid = [int]$r.ProcessId; Proc = $null; Wmi = $true }
            }
            Write-Host ("        (WMI เปิดโปรเซสไม่ได้ รหัส {0} — ใช้ Start-Process แทน)" -f $r.ReturnValue) -ForegroundColor DarkGray
        } catch {
            Write-Host "        (WMI ใช้ไม่ได้: $($_.Exception.Message) — ใช้ Start-Process แทน)" -ForegroundColor DarkGray
        }
    }
    # ทางสำรอง: สืบทอด env ของตัวเปิด (ตัดตัวแปรลับไปแล้วตอนเริ่ม — Remove-InheritedSecrets) + ตัวแปรที่ลูกต้องใช้
    try {
        if ($ChildEnv) { foreach ($k in $ChildEnv.Keys) { if ([string]$ChildEnv[$k]) { Set-Item -LiteralPath "Env:\$k" -Value ([string]$ChildEnv[$k]) } } }
        $p = Start-Process -FilePath $Exe -ArgumentList $argLine -WorkingDirectory $WorkDir -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
        return @{ Pid = [int]$p.Id; Proc = $p; Wmi = $false }
    } catch {
        Write-Host "        เปิด $(Split-Path $Exe -Leaf) ไม่ได้: $($_.Exception.Message)" -ForegroundColor Yellow
        return $null
    }
}

# โปรเซสที่ Start-CleanProcess เปิดยังทำงานอยู่ไหม (WMI: ดูที่ cmd.exe ที่ครอบ ซึ่งรอโปรแกรมข้างในจบ)
function Test-CleanAlive($H) {
    if (-not $H) { return $false }
    if ($H.Proc) { return (-not $H.Proc.HasExited) }
    return ($null -ne (Get-Process -Id $H.Pid -ErrorAction SilentlyContinue))
}

# PID ของโปรแกรมจริง (ไม่ใช่ cmd.exe ที่ครอบ) — 0 = ยังหาไม่เจอ
function Get-CleanChildPid($H, [string]$Name) {
    if (-not $H) { return 0 }
    if ($H.Proc) { return [int]$H.Pid }
    $k = Get-CimInstance Win32_Process -Filter ("ParentProcessId={0} AND Name='{1}'" -f $H.Pid, $Name) `
             -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($k) { return [int]$k.ProcessId }
    return 0
}

# ---- โทเคนของบริการในเครื่อง (สัญญา C1) ------------------------------------------------------
# 64 ตัวอักษร hex บรรทัดเดียว ไม่มี BOM — ตรวจรูปแบบในหน่วยความจำเท่านั้น ห้ามพิมพ์ค่า
function Test-TokenFile {
    try {
        $t = [System.IO.File]::ReadAllText($TokenFile).Trim()
        return ($t -match '^[0-9a-fA-F]{64}$')
    } catch { return $false }
}

# สร้างเองเมื่อ secrets_util.py ยังไม่มี/ใช้ไม่ได้: สุ่มจาก CSPRNG, เขียนไฟล์ชั่วคราวแล้ว Move
# (Move ล้มถ้ามีคนสร้างไฟล์จริงไปก่อน = ไม่ทับโทเคนที่บริการอื่นอ่านไปแล้ว)
function New-TokenFile {
    $tmp = "$TokenFile.tmp$PID"
    try {
        New-Item -ItemType Directory -Force -Path $SecretsDir | Out-Null
        $bytes = New-Object byte[] 32
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
        $hex = -join ($bytes | ForEach-Object { $_.ToString('x2') })
        [System.IO.File]::WriteAllText($tmp, $hex, (New-Object System.Text.UTF8Encoding $false))
        try { [System.IO.File]::Move($tmp, $TokenFile) } catch { }
    } catch {
        Write-Host "        สร้างไฟล์โทเคนไม่ได้: $($_.Exception.Message)" -ForegroundColor Yellow
    } finally {
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
    }
    return (Test-TokenFile)
}

# ให้ secrets_util.py (ของฝั่ง MCP) เป็นคนสร้างก่อน — ทุกบริการใช้ helper ตัวเดียวกัน กฎการสร้างจึงอยู่ที่เดียว
# ตามสัญญาคือ "secrets_util.py --ensure"; helper รุ่นที่ไม่มี CLI (รันแล้วไม่ทำอะไร) → เรียก get_token() ตรงๆ
# stdout/stderr ของ helper ทิ้งไป (ไม่ลงไฟล์ log) กันพลาดพิมพ์ค่าออกมา
function Confirm-LocalToken {
    if (Test-TokenFile) { return $true }
    if ((Test-Path -LiteralPath $SecretsUtil) -and (Test-Path -LiteralPath $PyExe)) {
        $eap = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'      # PS 5.1 + Stop: แค่ python เขียน stderr ก็โยน error
        try { & $PyExe $SecretsUtil --ensure *> $null } catch { }
        if (-not (Test-TokenFile)) {
            try { & $PyExe -c "import sys;sys.path.insert(0,'C:/LLM');import secrets_util;secrets_util.get_token()" *> $null } catch { }
        }
        $ErrorActionPreference = $eap
        if (Test-TokenFile) { return $true }
    }
    return (New-TokenFile)
}

# ใช้ไฟล์โทเคนเป็น --api-key-file ของ llama-server ได้ไหม — เข้มกว่า Test-TokenFile: llama-server อ่านทีละบรรทัด
# แล้วใช้ทั้งบรรทัดเป็นคีย์ ไม่ตัด BOM/ช่องว่าง (ReadAllText ตัด BOM ให้เงียบๆ) ไฟล์ที่มี BOM จะได้คีย์ที่ไม่ตรงกับที่
# hub/Gateway ส่ง = ทุกแชต 401  รับเฉพาะ hex 64 ตัว + ขึ้นบรรทัดใหม่ได้หนึ่งครั้ง (CRLF ถูกแปลงโดยโหมด text ของ C++)
function Test-TokenFileStrict {
    try {
        $b = [System.IO.File]::ReadAllBytes($TokenFile)
        if ($b.Length -lt 64 -or $b.Length -gt 66) { return $false }
        $s = [System.Text.Encoding]::ASCII.GetString($b)
        return ($s -cmatch '^[0-9a-fA-F]{64}(\r?\n)?$')
    } catch { return $false }
}

# router ที่รันอยู่รับโทเคนในไฟล์ตอนนี้ไหม: $true = รับ (200), $false = ปฏิเสธ (401 — ไฟล์ถูกสร้างใหม่หลัง router เริ่ม),
# $null = ตัดสินไม่ได้ (ไม่มีไฟล์ / router ไม่ตอบ / รหัสอื่น) — GET /props ของ router เองไม่โหลดโมเดลใดๆ
# ไม่ผ่าน proxy ของระบบ (คำขอพกโทเคน) และไม่เก็บค่าโทเคนไว้ในตัวแปรของสคริปต์
# $Path: บริการ embedding (ข้อ 1d) ถามที่ /v1/models แทน — ไม่คำนวณอะไร และ /props ของมันไม่จำเป็นต้องมี
function Test-RouterAuth([int]$p, [string]$Path = '/props') {
    if (-not (Test-TokenFileStrict)) { return $null }
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$p$Path")
        $req.Method = 'GET'
        $req.Timeout = 5000
        $req.Proxy = $null
        # batch 2b: คำขอครั้งเดียว — ไม่ค้างสายไว้ (บริการ python อย่าง STT พิมพ์ traceback เมื่อสายค้างถูกตัดตอนตัวเปิดจบ)
        $req.KeepAlive = $false
        $req.Headers.Add('Authorization', 'Bearer ' + ([System.IO.File]::ReadAllText($TokenFile).Trim()))
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        return ($code -eq 200)
    } catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) {
            $code = [int]$r.StatusCode
            $r.Close()
            if ($code -eq 401) { return $false }
        }
        return $null
    } catch { return $null }
}

# บัญชีกลุ่มกว้าง (ทุกคน / ผู้ใช้ทุกบัญชีในเครื่อง) ที่อ่านไฟล์โทเคนหรือโฟลเดอร์ secrets ได้ — ใช้ SID ไม่ใช้ชื่อ
# (ชื่อกลุ่มเปลี่ยนตามภาษาของ Windows)  ตรวจอย่างเดียว ไม่แก้สิทธิ์ (การเปลี่ยน ACL เป็นการตัดสินใจของผู้ใช้)
function Get-SecretsBroadAccess([string]$Dir, [string]$File) {
    $broad = @{
        'S-1-1-0' = 'Everyone'; 'S-1-5-11' = 'Authenticated Users'; 'S-1-5-32-545' = 'Users'
        'S-1-5-4' = 'INTERACTIVE'; 'S-1-5-7' = 'ANONYMOUS LOGON'; 'S-1-5-32-546' = 'Guests'
    }
    $found = New-Object System.Collections.Generic.List[string]
    foreach ($target in @($File, $Dir)) {
        if (-not $target -or -not (Test-Path -LiteralPath $target)) { continue }
        try {
            $rules = (Get-Acl -LiteralPath $target -ErrorAction Stop).GetAccessRules($true, $true,
                        [System.Security.Principal.SecurityIdentifier])
        } catch { continue }
        foreach ($r in $rules) {
            $sid = $r.IdentityReference.Value
            if (-not $broad.ContainsKey($sid)) { continue }
            if ($r.AccessControlType -ne [System.Security.AccessControl.AccessControlType]::Allow) { continue }
            # InheritOnly บนโฟลเดอร์ = มีผลกับไฟล์ข้างใน (ไฟล์ตรวจแยกอยู่แล้ว) — บนโฟลเดอร์เองดูเฉพาะที่มีผลกับตัวมัน
            if ($target -eq $Dir -and ($r.PropagationFlags -band [System.Security.AccessControl.PropagationFlags]::InheritOnly)) { continue }
            if (($r.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::ReadData) -eq 0) { continue }
            if (-not $found.Contains($broad[$sid])) { $found.Add($broad[$sid]) }
        }
    }
    return ,$found.ToArray()
}

# เรียก python แบบรอผล แล้วคืน exit code (-1 = ไม่จบในเวลา, -2 = ไม่มี python, -3 = เรียก python ไม่ได้)
# ใช้ Start-Process + ไฟล์ log แทน "& python ... 2>&1" เพราะใน PS 5.1 ที่ตั้ง ErrorActionPreference=Stop
# แค่ python เขียน stderr ก็ถูกโยนเป็น error และภาษาไทยจาก stdout ถูกถอดรหัสเพี้ยน
# ไม่ฆ่า python ที่ค้าง (python ในเครื่องนี้ห้ามฆ่า) — gpu_profile.py มี timeout ในตัวอยู่แล้ว
function Invoke-Py([object[]]$PyArgs, [int]$TimeoutSec, [string]$LogBase) {
    if (-not (Test-Path -LiteralPath $PyExe)) { return -2 }
    $argLine = ($PyArgs | ForEach-Object { Format-Arg ([string]$_) }) -join ' '
    try {
        $p = Start-Process -FilePath $PyExe -ArgumentList $argLine -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput "$LogBase.out.log" -RedirectStandardError "$LogBase.err.log"
    } catch {
        # เช่นไฟล์ log ถูกล็อก หรือดิสก์เต็ม — ห้ามให้สคริปต์ตายกลางทาง (router เดิมอาจถูกปิดไปแล้ว)
        Write-Host "        เรียก python ไม่ได้: $($_.Exception.Message)" -ForegroundColor Yellow
        return -3
    }
    $null = $p.Handle   # ต้องแตะ Handle ก่อน ไม่งั้น ExitCode ของ Start-Process -PassThru เป็นค่าว่าง
    if (-not $p.WaitForExit($TimeoutSec * 1000)) { return -1 }
    return $p.ExitCode
}

# พิมพ์ไฟล์ข้อความ UTF-8 ที่ python เขียนไว้ทีละบรรทัด
function Show-Lines([string]$Path, [string]$Indent, [string]$Color) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    foreach ($l in @(Get-Content -LiteralPath $Path -Encoding UTF8)) {
        if ($l.Trim()) { Write-Host ($Indent + $l) -ForegroundColor $Color }
    }
}

# บอกเหตุที่ python ล้มให้เห็นบนจอเลย ไม่ใช่แค่ชี้ไปไฟล์ log — python ที่เริ่มไม่ขึ้น (เช่น
# "Fatal Python error") เขียนแต่ .err.log ส่วน .out.log ว่างเปล่า
# -ErrOnly = .out.log พิมพ์ขึ้นจอไปแล้ว (Show-Lines) ไม่ต้องซ้ำ ดูแค่ .err.log
function Show-PyFailure([int]$Rc, [string]$LogBase, [switch]$ErrOnly) {
    if ($Rc -eq -1) { $why = 'ไม่จบภายในเวลาที่กำหนด (llama-server หรือ nvidia-smi ค้าง? eGPU เพิ่งเสียบอาจยังไม่พร้อม)' }
    elseif ($Rc -eq -2) { $why = "ไม่พบ $PyExe" }
    elseif ($Rc -eq -3) { $why = 'เรียก python ไม่ได้' }
    else { $why = "exit $Rc" }
    Write-Host "        สาเหตุ: $why" -ForegroundColor DarkGray
    $files = @("$LogBase.out.log", "$LogBase.err.log")
    if ($ErrOnly) { $files = @("$LogBase.err.log") }
    foreach ($f in $files) {
        if (-not (Test-Path -LiteralPath $f)) { continue }
        $lines = @(Get-Content -LiteralPath $f -Encoding UTF8 | Where-Object { $_.Trim() })
        if ($lines.Count -eq 0) { continue }
        # stderr: บรรทัดแรกมักเป็นสาเหตุ ("Fatal Python error: ...") บรรทัดท้ายเป็นชนิดข้อผิดพลาด — เอาทั้งสองฝั่ง
        if ($f -like '*.err.log' -and $lines.Count -gt 3) { $tail = @($lines[0]) + @($lines[-2..-1]) }
        else { $tail = @($lines | Select-Object -Last 3) }
        Write-Host "        log: $f" -ForegroundColor DarkGray
        foreach ($l in $tail) { Write-Host "          $l" -ForegroundColor DarkGray }
        return
    }
}

# ตรวจ GPU + เขียน preset/json ลง $OutDir — คืน $true ถ้าได้ไฟล์ครบ
function New-GpuProfile([string]$OutDir) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    foreach ($n in @('models-preset.ini', 'gpu-profile.json', 'compare.txt')) {
        Remove-Item -LiteralPath (Join-Path $OutDir $n) -Force -ErrorAction SilentlyContinue
    }
    $a = @($GpuProfile, '--write', '--models-dir', $ModelsDir, '--out-dir', $OutDir,
           '--threads', $Threads, '--llama-server', $Server)
    # ไม่ใส่ = gpu_profile.py อ่าน C:\LLM\gpu-choice.json เอง (ที่ hub เขียนเมื่อผู้ใช้เลือก GPU ในหน้าแชต)
    if ($ChoiceFile) { $a += @('--choice', $ChoiceFile) }
    if ($CtxGiven) { $a += @('--ctx', $Ctx) }
    if ($NoVision) { $a += '--no-vision' } elseif ($Vision) { $a += '--vision' }
    if ($Primary) { $a += @('--primary', $Primary) }
    $log = Join-Path $LogDir "gpu-profile-$Port"
    $rc = Invoke-Py $a 90 $log
    $ok = ($rc -eq 0) -and (Test-Path -LiteralPath (Join-Path $OutDir 'models-preset.ini')) -and
          (Test-Path -LiteralPath (Join-Path $OutDir 'gpu-profile.json'))
    if (-not $ok) {
        Write-Host '  [2/4] ตรวจ GPU / สร้าง preset ไม่สำเร็จ — ใช้ค่าแบบเดิม' -ForegroundColor Yellow
        Show-PyFailure $rc $log
    }
    return $ok
}

# บรรยาย router ที่เปิดด้วยค่าแบบเดิมลงโปรไฟล์ (ทุกโมเดลใช้ทุก GPU ตามลำดับปกติ) ให้ hub แสดงตามจริง
# ไม่ใช่แผน preset ที่ไม่ได้ใช้ — คืนโฟลเดอร์ที่มี gpu-profile.json หรือ '' ถ้าไม่สำเร็จ
function New-LegacyProfile {
    $dir = Join-Path $GenDir 'legacy'
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
    Remove-Item -LiteralPath (Join-Path $dir 'gpu-profile.json') -Force -ErrorAction SilentlyContinue
    # router แบบเดิมไม่อ่าน models-preset.user.ini และไม่รู้เรื่อง GPU ที่เลือกในหน้าแชต — ไม่ส่งทั้งสองอย่าง
    # จะได้ไม่แสดงค่าที่ไม่ได้ใช้จริง
    $a = @($GpuProfile, '--write', '--legacy', '--models-dir', $ModelsDir, '--out-dir', $dir,
           '--threads', $Threads, '--ctx', $Ctx, '--llama-server', $Server,
           '--user-ini', (Join-Path $dir 'no-user.ini'), '--choice', 'none')
    if ($Vision -and (Test-Path -LiteralPath $Mmproj)) { $a += '--vision' } else { $a += '--no-vision' }
    if ($Primary) { $a += @('--primary', $Primary) }
    $rc = Invoke-Py $a 90 (Join-Path $LogDir "gpu-legacy-$Port")
    if (($rc -eq 0) -and (Test-Path -LiteralPath (Join-Path $dir 'gpu-profile.json'))) { return $dir }
    return ''
}

# วางไฟล์ที่เพิ่งสร้างไปที่จริงแบบ "ไฟล์ชั่วคราวแล้วสลับ" — hub อาจกำลังอ่าน gpu-profile.json อยู่พอดี
# และถ้าคัดลอกไม่ครบ (ไฟล์ถูกล็อก / ดิสก์เต็ม) ไฟล์เดิมยังอยู่ครบ  Copy-Item คัดลอกไบต์ตรงๆ ไม่เติม BOM
# (INI ที่มี BOM ทำให้ llama-server ปิดตัวทันที ห้ามใช้ Set-Content -Encoding UTF8 ของ PS 5.1)
# คืน $false แทนการโยน error — ถึงตรงนี้ router เดิมอาจถูกปิดไปแล้ว สคริปต์ห้ามตายกลางทาง
function Publish-File([string]$Src, [string]$Dst) {
    $tmp = "$Dst.tmp$PID"
    try {
        New-Item -ItemType Directory -Force -Path (Split-Path $Dst -Parent) | Out-Null
        Copy-Item -LiteralPath $Src -Destination $tmp -Force -ErrorAction Stop
    } catch {
        Write-Host "        เขียน $Dst ไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Yellow
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        return $false
    }
    # File.Replace สลับทีเดียว (ไม่มีช่วงที่ไฟล์หายไป) แต่ล้มถ้ามีคนเปิดไฟล์อ่านอยู่พอดี — ลองซ้ำสั้นๆ
    for ($i = 0; $i -lt 5; $i++) {
        try {
            if (Test-Path -LiteralPath $Dst) { [System.IO.File]::Replace($tmp, $Dst, [NullString]::Value) }
            else { Move-Item -LiteralPath $tmp -Destination $Dst -Force -ErrorAction Stop }
            return $true
        } catch {
            Start-Sleep -Milliseconds 300
        }
    }
    try {
        Copy-Item -LiteralPath $tmp -Destination $Dst -Force -ErrorAction Stop
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        return $true
    } catch {
        Write-Host "        เขียน $Dst ไม่สำเร็จ: $($_.Exception.Message)" -ForegroundColor Yellow
        Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue
        return $false
    }
}

# origin ที่ llama-server ยอมให้ (สัญญา C4): หน้าแชตดิบของ router เอง + hub + พอร์ตโปรเจกต์ 8100-8179
# ตรงกับ ALLOWED_ORIGIN ของ hub.py (แก้ที่หนึ่งต้องแก้อีกที่)
function Get-CorsOrigins {
    $ports = New-Object System.Collections.Generic.List[int]
    $ports.Add($Port)
    foreach ($p in (@($HubPort) + @(8100..8179))) { if (-not $ports.Contains([int]$p)) { $ports.Add([int]$p) } }
    $list = New-Object System.Collections.Generic.List[string]
    foreach ($h in @('127.0.0.1', 'localhost')) {
        foreach ($p in $ports) { $list.Add(('http://{0}:{1}' -f $h, $p)) }
    }
    return ($list -join ',')
}

# router ที่รันอยู่เปิดด้วยค่าความปลอดภัยแบบเก่าหรือเปล่า — คืนเหตุผล ('' = ค่าปัจจุบันครบ)
# เทียบ GPU/preset (gpu_profile --compare-running) ไม่รู้เรื่อง flag พวกนี้ ถ้าไม่ตรวจเอง router ตัวเดิมที่ยังเปิด
# /cors-proxy + CORS เปิดกว้างจะถูกปล่อยไว้ "เพราะ GPU เหมือนเดิม" ไปจนกว่าจะรีบูตเครื่อง
function Get-RouterInsecureReason([int]$RouterPid) {
    $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$RouterPid" -ErrorAction SilentlyContinue).CommandLine
    if (-not $cl) { return '' }        # อ่าน command line ไม่ได้ — ไม่รีสตาร์ตเพราะเดาเอา
    if ($cl -match '--(ui|webui)-mcp-proxy(\s|$)' -or $cl -match '\s(-ag|--agent)(\s|$)') {
        return 'router เปิด MCP CORS proxy (/cors-proxy) อยู่'
    }
    if ($cl -notmatch '--cors-origins\s' -or $cl -notmatch '--no-cors-credentials') {
        return 'router ยังใช้ CORS แบบเปิดกว้าง (ทุก origin + credentials)'
    }
    # ไม่มีไฟล์โทเคนที่ใช้เป็นคีย์ได้ = รีสตาร์ตไปก็เปิดแบบไม่มีคีย์เหมือนเดิม ไม่ต้องตัดโมเดลที่โหลดไว้ทิ้ง
    if ((Test-TokenFileStrict) -and $cl -notmatch '--api-key-file\s') {
        return 'router ยังไม่ต้องใช้ API key (เว็บไหนก็สั่งโหลดโมเดล/แชตผ่าน llama-server ได้)'
    }
    if ($cl -match '--api-key-file\s' -and (Test-RouterAuth $Port) -eq $false) {
        return 'router ยังใช้โทเคนชุดเก่า (ไฟล์โทเคนถูกสร้างใหม่หลัง router เริ่ม — hub/Gateway คุยกับมันไม่ได้)'
    }
    return ''
}

function Get-RouterArgs([bool]$UsePreset, [string]$PresetPath) {
    # router mode: เลือกโมเดลได้จากในหน้าเว็บโดยไม่ต้องรีสตาร์ท
    # llama-server สแกน --models-dir เอง และคัดไฟล์ที่ไม่ใช่โมเดลเดี่ยว
    # (mmproj, mtp draft) ออกให้อัตโนมัติ
    $argv = @(
        '--models-dir', $ModelsDir
        '--models-max', '2'   # ให้ 27B กับ 4B อยู่ในหน่วยความจำพร้อมกัน
                              # สลับโปรเจกต์แล้วไม่ต้องรอโหลดใหม่ 47 วินาที
        '-fit', 'on'          # ยังจัดจำนวนชั้นบน GPU ที่เลือกให้เองตอนโหลด (ตามที่ว่างจริง เว้นขอบ 1 GB)
        '--host', '127.0.0.1'
        '--port', $Port
        '-fa', 'on'
        '--jinja'
        '--no-warmup'
        # ไม่ใช้ --tools all อีกแล้ว เครื่องมือในตัวของ llama-server ไม่จำกัด path
        # ทดสอบแล้วอ่าน .ssh และไฟล์ credential ได้ และรันคำสั่งทันทีโดยไม่ถาม
        # ความสามารถเดิมย้ายไปที่ MCP "เครื่องนี้" (พอร์ต 8792) ซึ่งผ่านชั้นป้องกัน
        # ไม่ใช้ --ui-mcp-proxy อีกแล้ว (ดู "ความปลอดภัย" หัวไฟล์) — /cors-proxy ตอบ 403 feature_disabled
        '--ui-config-file', $UiConfig
        # CORS: ค่าปริยาย (*) + credentials = สะท้อนทุก origin เว็บไหนก็อ่านคำตอบของ llama-server ได้
        # b10984 ส่งรายการนี้กลับทั้งก้อนเป็น Access-Control-Allow-Origin (ทดสอบบนพอร์ต 8199 แล้ว) ซึ่งเบราว์เซอร์
        # ถือว่าไม่ตรงกับ origin ใดเลย = ไม่มีหน้าเว็บไหนอ่านข้าม origin ได้ — ของเราไม่ต้องใช้: หน้าแชตเรียกผ่าน
        # proxy ของ hub (same-origin) ส่วนหน้าแชตดิบที่ :8099 ก็ same-origin  ถ้ารุ่นหน้าเลือกตามรายการได้ถูกต้อง
        # ก็จะเหลือเฉพาะหน้าของเราตามรายการนี้พอดี  ('localhost' สะท้อนทุกพอร์ตของ 127.0.0.1 รวมเว็บอื่นในเครื่อง)
        '--cors-origins', (Get-CorsOrigins)
        '--no-cors-credentials'
    )
    # API key = ไฟล์โทเคนเดียวกับ MCP (ดู "ความปลอดภัย" หัวไฟล์) ส่งเป็น path เสมอ ห้ามใช้ --api-key <ค่า>:
    # command line ของ process ใครในเครื่องก็อ่านได้ และ router ส่ง argv ต่อให้โมเดลลูกด้วย
    # ไฟล์ใช้ไม่ได้ (ไม่มี / มี BOM) = เปิดแบบไม่มีคีย์ตามเดิม ดีกว่าเปิดแล้วทุกแชต 401
    if (Test-TokenFileStrict) {
        $argv += @('--api-key-file', $TokenFile)
    } else {
        Write-Host "        คำเตือน: ใช้ $TokenFile เป็น API key ของ llama-server ไม่ได้ (ไม่มีไฟล์ หรือไม่ใช่ hex 64 ตัวล้วน) — เปิดแบบไม่มีคีย์" -ForegroundColor Yellow
    }
    if ($UsePreset) {
        # ctx / KV cache (q8_0) / threads / GPU / mmproj อยู่ใน preset ทั้งหมด ห้ามใส่ซ้ำตรงนี้
        # เพราะค่าบน command line ของ router ชนะ preset เสมอ (ทดสอบแล้ว: -c 32768 ทำให้ ctx-size ใน preset ถูกเมิน)
        $argv += @('--models-preset', $PresetPath)
    } else {
        $argv += @(
            '-c', $Ctx
            '-ctk', 'q8_0'    # บีบ KV cache ครึ่งหนึ่ง: 32K ที่ f16 กิน ~8 GB เหลือ ~4 GB
            '-ctv', 'q8_0'    # ต่างจาก f16 น้อยมากเมื่อเปิด flash attention
            '-t', $Threads
        )
        if ($Vision -and (Test-Path -LiteralPath $Mmproj)) { $argv += @('--mmproj', $Mmproj) }
    }
    return ,$argv
}

# เปิด router แล้วรอ /health สั้นๆ — router ไม่โหลดโมเดลตอนเริ่ม จึงตอบภายในไม่กี่วินาที
# ถ้า process ตายก่อน (เช่น preset มี key ที่ llama-server ไม่รู้จัก) คืน $null ให้ถอยไปค่าแบบเดิม
# คืนออบเจกต์ที่มี .Id = PID ของ llama-server ตัวจริง (ไม่ใช่ cmd.exe ที่ครอบ) — Save-RouterState จดค่านี้
# ซึ่งต้องตรงกับเจ้าของพอร์ตที่ --compare-running เทียบรอบหน้า
function Start-Router([bool]$UsePreset, [string]$PresetPath) {
    $argv = Get-RouterArgs $UsePreset $PresetPath
    # CUDA_DEVICE_ORDER ต้องตรงกับตอนตรวจ GPU (ชื่อ CUDAn ใน preset) — env สะอาดของ WMI ไม่มีค่านี้ จึงส่งเอง
    # CUDA_VISIBLE_DEVICES ส่งต่อเฉพาะเมื่อผู้เรียกตั้งไว้ (รอบทดสอบที่ซ่อน GPU)
    $childEnv = @{ CUDA_DEVICE_ORDER = 'PCI_BUS_ID' }
    if ($env:CUDA_VISIBLE_DEVICES) { $childEnv['CUDA_VISIBLE_DEVICES'] = $env:CUDA_VISIBLE_DEVICES }
    # working directory = C:\ เพื่อให้เครื่องมือที่ใช้ path สัมพัทธ์เข้าถึงได้ทั้งไดรฟ์
    $h = Start-CleanProcess $Server $argv 'C:\' "$LogDir\$LlamaLogName.out.log" "$LogDir\$LlamaLogName.err.log" $childEnv
    if (-not $h) {
        Write-Host '        เปิด llama-server ไม่ได้' -ForegroundColor Red
        return $null
    }
    $rid = 0
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        if (-not (Test-CleanAlive $h)) { return $null }
        if ($rid -eq 0) { $rid = Get-CleanChildPid $h 'llama-server.exe' }
        if (Test-Llama $Port) { break }
        Start-Sleep -Milliseconds 500
    }
    if (-not (Test-CleanAlive $h)) { return $null }
    $owner = Get-PortPid $Port
    if ($owner -gt 0) { $rid = $owner }
    if ($rid -eq 0) { $rid = Get-CleanChildPid $h 'llama-server.exe' }
    if ($rid -eq 0) { $rid = $h.Pid }
    return [pscustomobject]@{ Id = [int]$rid }
}

# จดว่า router ตัวนี้ (PID) เริ่มด้วยแผนไหน — $FromDir = โฟลเดอร์ที่มี preset + json ชุดที่ router อ่านจริง
# $FailedPreset = preset ที่ทำให้ router ปิดตัวทันที (รอบหน้าจะได้ไม่รีสตาร์ตวนลองซ้ำทุกครั้ง)
function Save-RouterState([int]$RouterPid, [string]$Mode, [string]$FromDir, [string]$FailedPreset) {
    if ($RouterPid -le 0) { return }
    $a = @($GpuProfile, '--record-state', '--port', $Port, '--router-pid', $RouterPid,
           '--mode', $Mode, '--out-dir', $FromDir, '--state', $StateFile)
    if ($FailedPreset) { $a += @('--failed-preset', $FailedPreset) }
    $null = Invoke-Py $a 30 (Join-Path $LogDir "gpu-state-$Port")
}

function Start-RouterWithFallback {
    # เก็บไว้บอกผู้ใช้ตอนท้ายว่าทำไมถึงถอยไปค่าแบบเดิม ดู log ไหน
    $script:LegacyWhy = "$LogDir\gpu-profile-$Port.out.log"
    $failedPreset = ''
    if ($genOk) {
        $genPreset = Join-Path $GenDir 'models-preset.ini'
        $presetPath = $PresetFile
        if (-not (Publish-File $genPreset $PresetFile)) {
            # เขียนไฟล์กลางไม่ได้ก็ยังเปิดตามแผนได้ด้วยไฟล์ที่เพิ่งสร้าง (router อ่าน preset ครั้งเดียวตอนเริ่ม)
            $presetPath = $genPreset
            Write-Host "        ใช้ preset จาก $genPreset แทน" -ForegroundColor Yellow
        }
        $p = Start-Router $true $presetPath
        if ($p) {
            # ให้ hub เห็นแผนนี้ก็ต่อเมื่อ router เปิดด้วย preset ได้จริงแล้วเท่านั้น
            $null = Publish-File (Join-Path $GenDir 'gpu-profile.json') $ProfileJson
            Save-RouterState $p.Id 'preset' $GenDir ''
            Write-Host "  [2/4] llama-server: เปิดแบบ router พร้อม preset ตาม GPU ที่ต่ออยู่ (พอร์ต $Port)" -ForegroundColor Green
            return 'preset'
        }
        Copy-Item -LiteralPath "$LogDir\$LlamaLogName.err.log" -Destination "$LogDir\$LlamaLogName.preset-fail.err.log" `
            -Force -ErrorAction SilentlyContinue
        $script:LegacyWhy = "$LogDir\$LlamaLogName.preset-fail.err.log"
        $failedPreset = $genPreset
        Write-Host '  [2/4] llama-server ปิดตัวทันทีเมื่อใช้ preset — ลองเปิดด้วยค่าแบบเดิม' -ForegroundColor Yellow
        Write-Host "        สาเหตุดูได้ที่ $LogDir\$LlamaLogName.preset-fail.err.log" -ForegroundColor DarkGray
        if (Test-Path -LiteralPath $UserIni) {
            Write-Host "        ถ้าเพิ่งแก้ $UserIni ให้ตรวจชื่อ key ในไฟล์นั้น (ชื่อยาวของ option ไม่มีขีดนำหน้า)" -ForegroundColor DarkGray
        }
    }
    $p = Start-Router $false ''
    if ($p) {
        $legacyDir = New-LegacyProfile
        if ($legacyDir) {
            $null = Publish-File (Join-Path $legacyDir 'gpu-profile.json') $ProfileJson
            Save-RouterState $p.Id 'legacy' $legacyDir $failedPreset
        } else {
            Save-RouterState $p.Id 'legacy' $PubDir $failedPreset
        }
    }
    Write-Host '  [2/4] llama-server: เปิดแบบ router ด้วยค่าแบบเดิม (ไม่ได้จัด GPU อัตโนมัติ)' -ForegroundColor Yellow
    return 'legacy'
}

# ปิดเฉพาะ router บนพอร์ตนี้และโมเดลลูกของมัน — llama-server ตัวอื่น (เช่น router อีกพอร์ต) ไม่แตะ
# ปิด router ก่อน จะได้ไม่มีลูกเกิดใหม่ระหว่างปิด (คำขอที่เข้ามาช่วงนั้นทำให้ router เปิดโมเดลลูกเพิ่มได้
# ลูกตัวนั้นจะค้างถือ VRAM และแย่งที่ของ router ตัวใหม่) แล้วค่อยตามปิดลูกจนหมด — ลูกที่ค้างหลัง router
# ตายยังจำ ParentProcessId เดิมไว้ จึงหาเจอด้วย PID ของ router + ต้องเริ่มหลัง router (กัน PID ถูกใช้ซ้ำ)
function Stop-Router([int]$p) {
    $rid = Get-PortPid $p
    if ($rid -eq 0) { return $true }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$rid" -ErrorAction SilentlyContinue
    if (-not $proc -or $proc.Name -ne 'llama-server.exe') { return $false }
    $born = $proc.CreationDate
    $kidFilter = "ParentProcessId=$rid AND Name='llama-server.exe'"
    # นับไว้ก่อนแค่เพื่อบอกผู้ใช้ — ลูกบางตัวปิดตัวเองทันทีที่ router ตาย เลยอาจไม่ทันเจอในรอบตามปิด
    $loaded = @(Get-CimInstance Win32_Process -Filter $kidFilter -ErrorAction SilentlyContinue).Count
    Stop-Process -Id $rid -Force -ErrorAction SilentlyContinue
    $killed = @{}
    $deadline = (Get-Date).AddSeconds(20)
    while ((Get-Date) -lt $deadline) {
        $kids = @(Get-CimInstance Win32_Process -Filter $kidFilter -ErrorAction SilentlyContinue |
                  Where-Object { $_.CreationDate -ge $born })
        foreach ($k in $kids) {
            Stop-Process -Id $k.ProcessId -Force -ErrorAction SilentlyContinue
            $killed[[int]$k.ProcessId] = $true
        }
        $routerAlive = $null -ne (Get-Process -Id $rid -ErrorAction SilentlyContinue |
                                  Where-Object { $_.ProcessName -eq 'llama-server' })
        if ((-not (Test-Port $p)) -and (-not $routerAlive) -and $kids.Count -eq 0) { break }
        Start-Sleep -Milliseconds 500
    }
    $n = $loaded
    if ($killed.Count -gt $n) { $n = $killed.Count }
    Write-Host ("        ปิด router PID {0} และโมเดลที่โหลดอยู่ {1} ตัว" -f $rid, $n) -ForegroundColor DarkGray
    return (-not (Test-Port $p))
}

function Test-StateFor([int]$RouterPid) {
    if (-not (Test-Path -LiteralPath $StateFile)) { return $false }
    try { $s = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { return $false }
    return (([int]$s.router_pid -eq $RouterPid) -and ([int]$s.port -eq $Port))
}

function Get-RouterMode([int]$RouterPid) {
    $cl = (Get-CimInstance Win32_Process -Filter "ProcessId=$RouterPid" -ErrorAction SilentlyContinue).CommandLine
    if ($cl -and ($cl -match '--models-preset')) { return 'preset' }
    return 'legacy'
}

function Show-GpuSummary([string]$JsonPath) {
    try { $doc = Get-Content -LiteralPath $JsonPath -Raw -Encoding UTF8 | ConvertFrom-Json }
    catch { return }
    $first = $true
    foreach ($l in @(([string]$doc.summary_th) -split "`n")) {
        if (-not $l.Trim()) { continue }
        if ($first) { Write-Host "  $l" -ForegroundColor Yellow; $first = $false }
        else { Write-Host "    $l" -ForegroundColor Yellow }
    }
    foreach ($w in @($doc.warnings)) {
        if ($w) { Write-Host "    คำเตือน: $w" -ForegroundColor DarkYellow }
    }
}

# ---- บริการ embedding (ข้อ 1d, สัญญา B2) ----------------------------------------------------------
# tools_kb.py ของ MCP ส่งข้อความเอกสารมาที่ /v1/embeddings (Bearer = โทเคนไฟล์เดียวกับ router) เก็บเวกเตอร์ต่อช่วงเอกสาร
# แล้วค้นแบบผสม (คำ + ความหมาย)  บริการนี้ล่ม/ช้า = kb ถอยไปค้นด้วยคำเอง จึงเปิดใหม่ได้ทันทีโดยไม่ต้องรอแชตใด (ต่างจาก router)
# ค่าที่เลือก (วัดบนพอร์ตทดสอบ 8893, 2026-10-01):
#   --embeddings --pooling last   Qwen3-Embedding ใช้เวกเตอร์ของโทเคนสุดท้าย (ตามการ์ดของโมเดล) เวกเตอร์ 1024 มิติ
#   -ngl 0 --device none          CPU ล้วน ไม่แย่ง VRAM ของโมเดลแชต — --device none ทำให้ไม่โหลด CUDA เลย (log ไม่มีบรรทัด CUDA)
#   -c 8192 -t 4                  ตามสัญญา: ~1.8 GB (private) / 4 ข้อความสั้น ~1.2 วินาที / ข้อความ ~2,400 โทเคน ~30 วินาที
#                                 ไม่ตั้ง -ub: 2048 ไม่ได้เร็วขึ้นแต่กินหน่วยความจำเพิ่มเป็น 3.6 GB (ข้อความยาวกว่า 512 ใช้ได้อยู่แล้ว)
#   --api-key-file                ไฟล์โทเคนเดียวกับ router (path ไม่ใช่ค่า) — ไม่มีไฟล์ที่ใช้เป็นคีย์ได้ = ไม่เปิดเลย ไม่เปิดแบบ
#                                 ไม่มีคีย์: เว็บไหนก็ส่ง POST แบบ text/plain (ไม่มี preflight) สั่งให้คำนวณจนเครื่องช้าได้
#   --no-webui --no-slots         ไม่มีหน้าเว็บ และปิด /slots (มีข้อความเอกสารที่ส่งมาล่าสุด) — ผู้เรียกเป็นโปรแกรม ไม่ต้องใช้
#   --offline                     ไม่ออกเน็ต (ไม่ดาวน์โหลดอะไรเอง)
#   --cors-origins <ตัวเอง> --no-cors-credentials   ค่าปริยาย (*) สะท้อนทุก origin — ไม่มีหน้าเว็บใดต้องอ่านคำตอบข้าม origin
function Get-EmbedArgs {
    $argv = @(
        '--embeddings', '--pooling', 'last'
        '-m', $EmbedModel
        '-ngl', '0', '--device', 'none'
        '-c', '8192', '-t', '4'
        '--host', '127.0.0.1', '--port', $EmbedPort
        '--no-webui', '--no-slots', '--offline'
        '--cors-origins', ('http://127.0.0.1:{0}' -f $EmbedPort), '--no-cors-credentials'
        '--api-key-file', $TokenFile
    )
    return ,$argv
}

# 'ok' = โหลดโมเดลเสร็จ, 'loading' = ฟังพอร์ตแล้วแต่ยังโหลด (/health ตอบ 503), 'down' = ไม่ตอบ
# /health ไม่ต้องใช้คีย์ — ไม่ส่งโทเคน ไม่ผ่าน proxy ของระบบ
function Get-EmbedHealth([int]$p) {
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$p/health")
        $req.Method = 'GET'
        $req.Timeout = 3000
        $req.Proxy = $null
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $resp.Close()
        if ($code -eq 200) { return 'ok' }
        return 'down'
    } catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) {
            $code = [int]$r.StatusCode
            $r.Close()
            if ($code -eq 503) { return 'loading' }
        }
        return 'down'
    } catch { return 'down' }
}

# ใครฟังพอร์ต embedding อยู่ และต้องเปิดใหม่ไหม — คืน @{ Ours; Pid; Name; Why }
#   Ours = $false  โปรแกรมอื่น (หรือ llama-server ที่ไม่ใช่โหมด embedding เช่นผู้ใช้เปิดเอง) — ไม่แตะเด็ดขาด
#   Why  = ''      ใช้ต่อได้  / ข้อความ = เหตุที่ต้องเปิดใหม่ (ค่าความปลอดภัยแบบเก่า / โทเคนชุดเก่า)
function Get-EmbedState([int]$p) {
    $opid = Get-PortPid $p
    $out = @{ Ours = $false; Pid = $opid; Name = ''; Why = '' }
    if ($opid -le 0) { return $out }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$opid" -ErrorAction SilentlyContinue
    if (-not $proc) { return $out }
    $out.Name = [string]$proc.Name
    $cl = [string]$proc.CommandLine
    # อ่าน command line ไม่ได้ = ตัดสินไม่ได้ว่าเป็นของเรา — ไม่ปิดเพราะเดาเอา
    if ($out.Name -ne 'llama-server.exe' -or $cl -notmatch '\s--embeddings?(\s|$)') { return $out }
    $out.Ours = $true
    if ($cl -notmatch '--api-key-file\s') {
        $out.Why = 'ยังไม่ต้องใช้ API key'
    } elseif ($cl -notmatch '--cors-origins\s' -or $cl -notmatch '--no-cors-credentials') {
        $out.Why = 'ยังใช้ CORS แบบเปิดกว้าง'
    } elseif ($cl -notmatch '--no-slots') {
        $out.Why = 'ยังเปิด /slots (ข้อความเอกสารล่าสุด) อยู่'
    } elseif ((Test-RouterAuth $p '/v1/models') -eq $false) {
        $out.Why = 'ใช้โทเคนชุดเก่า (MCP ส่งเอกสารให้ไม่ได้)'
    }
    return $out
}

# ปิดเฉพาะโปรเซสที่ Get-EmbedState ยืนยันแล้วว่าเป็นบริการ embedding ของเรา
function Stop-Embed([int]$OwnerPid) {
    if ($OwnerPid -le 0) { return $true }
    Stop-Process -Id $OwnerPid -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Test-Port $EmbedPort)) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return (-not (Test-Port $EmbedPort))
}

# เปิดผ่าน WMI (env สะอาด เหมือนบริการอื่น) — ไม่รอโหลดเสร็จตรงนี้ (ตรวจอีกทีก่อนจบด้วย Wait-EmbedReady)
# ระหว่างนั้นตัวเปิดไปทำขั้น GPU/router ต่อ โมเดล 0.6B จึงโหลดเสร็จก่อนถูกถามเกือบทุกครั้ง
function Start-Embed {
    $h = Start-CleanProcess $Server (Get-EmbedArgs) 'C:\LLM' "$LogDir\$EmbedLogName.out.log" "$LogDir\$EmbedLogName.err.log" $null
    return $h
}

# รอให้บริการที่เพิ่งเปิดโหลดโมเดลเสร็จ — คืน 'ok' | 'loading' | 'down' (โปรเซสตายไปแล้ว = 'down' ทันที ไม่รอเปล่า)
function Wait-EmbedReady($H, [int]$Sec) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ($true) {
        $s = Get-EmbedHealth $EmbedPort
        if ($s -eq 'ok') { return 'ok' }
        if ($H -and -not (Test-CleanAlive $H)) { return 'down' }
        if ((Get-Date) -ge $deadline) { return $s }
        Start-Sleep -Milliseconds 500
    }
}

# บรรทัดท้ายของ log ของบริการ embedding ที่เปิดไม่ขึ้น — llama-server เขียนสาเหตุลง stderr
function Show-EmbedLogTail {
    $f = "$LogDir\$EmbedLogName.err.log"
    if (-not (Test-Path -LiteralPath $f)) { return }
    $lines = @(Get-Content -LiteralPath $f -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_.Trim() } |
               Select-Object -Last 3)
    foreach ($l in $lines) { Write-Host "          $l" -ForegroundColor DarkGray }
}

# ขั้น 1d ทั้งหมด: ตัดสินว่าจะข้าม / ใช้ตัวที่รันอยู่ / เปิดใหม่ / เปิด — คืน @{ H = handle ของตัวที่เพิ่งเปิด (หรือ $null);
# State = started | running (ใช้ตัวเดิม) | skipped | foreign (พอร์ตเป็นของโปรแกรมอื่น) | failed }
# เป็นฟังก์ชันเพราะใช้สองที่: ขั้นปกติของตัวเปิด และโหมด -EmbedOnly (เปิดเฉพาะบริการนี้ ไม่แตะอย่างอื่น)
function Invoke-EmbedStep {
    if ($NoEmbed) {
        Write-Host '  [1/4] บริการ embedding: ข้าม (-NoEmbed)' -ForegroundColor DarkGray
        return @{ H = $null; State = 'skipped' }
    }
    if ($Port -ne $MainPort -and -not $EmbedPortGiven) {
        Write-Host "  [1/4] บริการ embedding: ข้ามในรอบทดสอบพอร์ต $Port (ใส่ -EmbedPort เพื่อทดสอบบนพอร์ตอื่น)" -ForegroundColor DarkGray
        return @{ H = $null; State = 'skipped' }
    }
    if (-not (Test-Path -LiteralPath $EmbedModel)) {
        Write-Host "  [1/4] บริการ embedding: ไม่พบโมเดล $EmbedModel — ค้นเอกสารด้วยคำอย่างเดียว" -ForegroundColor Yellow
        return @{ H = $null; State = 'failed' }
    }
    if (-not (Test-TokenFileStrict)) {
        Write-Host "  [1/4] บริการ embedding: ไม่เปิด — ใช้ $TokenFile เป็น API key ไม่ได้ (ไม่เปิดแบบไม่มีคีย์) ค้นเอกสารด้วยคำอย่างเดียว" -ForegroundColor Yellow
        return @{ H = $null; State = 'failed' }
    }
    if (Test-Port $EmbedPort) {
        $es = Get-EmbedState $EmbedPort
        if (-not $es.Ours) {
            Write-Host ("  [1/4] พอร์ต {0} ถูก {1} ใช้อยู่ ไม่ใช่บริการ embedding ของเรา — ไม่แตะ ค้นเอกสารด้วยคำอย่างเดียว" -f $EmbedPort, $es.Name) -ForegroundColor Yellow
            return @{ H = $null; State = 'foreign' }
        }
        # -RestartEmbed: ผู้ใช้/ผู้ดูแลสั่งเปิดใหม่เอง — ใช้ทางเดียวกับ "ค่าความปลอดภัยแบบเก่า" (ปิดแล้วเปิดผ่าน WMI)
        # อยู่หลังการตรวจ Ours เสมอ: โปรแกรมอื่นหรือ llama-server ที่ไม่ใช่โหมด embedding ไม่มีทางถูกปิดด้วยสวิตช์นี้
        if ($RestartEmbed -and -not $es.Why) { $es.Why = 'สั่งเปิดใหม่ (-RestartEmbed)' }
        if (-not $es.Why) {
            Write-Host "  [1/4] บริการ embedding: เปิดอยู่แล้ว (พอร์ต $EmbedPort)" -ForegroundColor DarkGray
            return @{ H = $null; State = 'running' }
        }
        Write-Host ("  [1/4] บริการ embedding (พอร์ต {0}) {1} — เปิดใหม่ (ระหว่างนี้ค้นเอกสารด้วยคำ)" -f $EmbedPort, $es.Why) -ForegroundColor Yellow
        if (-not (Stop-Embed $es.Pid)) {
            Write-Host '        ปิดตัวเดิมไม่สำเร็จ — ปล่อยไว้ตามเดิม' -ForegroundColor Red
            return @{ H = $null; State = 'failed' }
        }
        $h = Start-Embed
        if (-not $h) {
            Write-Host '        เปิดใหม่ไม่ได้ — ค้นเอกสารด้วยคำอย่างเดียวจนกว่าจะเปิดตัวเปิดนี้อีกครั้ง' -ForegroundColor Yellow
            return @{ H = $null; State = 'failed' }
        }
        return @{ H = $h; State = 'started' }
    }
    $h = Start-Embed
    if ($h) {
        Write-Host "  [1/4] บริการ embedding: กำลังเปิด (พอร์ต $EmbedPort, CPU ล้วน)" -ForegroundColor Green
        return @{ H = $h; State = 'started' }
    }
    Write-Host '  [1/4] บริการ embedding: เปิดไม่ได้ — ค้นเอกสารด้วยคำอย่างเดียว' -ForegroundColor Yellow
    return @{ H = $null; State = 'failed' }
}

# รอตัวที่เพิ่งเปิดให้พร้อม (สูงสุด $Sec วินาที) แล้วบอกผลหนึ่งบรรทัด — คืน 'ok' | 'loading' | 'down'
function Show-EmbedReady($H, [int]$Sec) {
    $s = Wait-EmbedReady $H $Sec
    if ($s -eq 'ok') {
        Write-Host "  [4/4] บริการ embedding พร้อม (พอร์ต $EmbedPort)" -ForegroundColor Green
    } elseif ($s -eq 'loading') {
        Write-Host "  [4/4] บริการ embedding ยังโหลดโมเดลอยู่ (พอร์ต $EmbedPort) — ระหว่างนี้ค้นเอกสารด้วยคำ" -ForegroundColor Yellow
    } else {
        Write-Host "  [4/4] บริการ embedding ไม่ขึ้น — ค้นเอกสารด้วยคำอย่างเดียว ดูสาเหตุที่ $LogDir\$EmbedLogName.err.log" -ForegroundColor Yellow
        Show-EmbedLogTail
    }
    return $s
}

# ---- บริการแปลงเสียงเป็นข้อความ (ข้อ 1e, batch 2b สัญญา C1/C3) -------------------------------------
# hub (POST /_qwen/stt บนพอร์ตโปรเจกต์) ส่งเสียงจากปุ่มไมค์ต่อมาที่ POST /v1/transcribe ของบริการนี้พร้อม Bearer
# (โทเคนไฟล์เดียวกับ MCP) — ตัวบริการเป็นของ owner voice (ตรวจโทเคน/Host/ขนาด/ความยาวเอง ไม่ออกเน็ต)
# faster-whisper มีเฉพาะใน conda env flexxfast — หา python ของ env นั้น ไม่เจอ = ข้าม (ไม่ติดตั้งอะไรเอง)
# บริการล่ม = แค่ปุ่มไมค์ใช้ไม่ได้ ไม่กระทบแชตและ exit code (แบบเดียวกับ embedding)
function Get-SttPython {
    $cands = @("$env:USERPROFILE\anaconda3\envs\flexxfast\python.exe",
               "$env:ProgramData\anaconda3\envs\flexxfast\python.exe")
    foreach ($c in $cands) { if ($c -and (Test-Path -LiteralPath $c)) { return $c } }
    return ''
}

# คำสั่งเปิดตามที่ owner voice กำหนด (หัวไฟล์ stt_server.py):
#   <python ของ flexxfast> -X utf8 C:\LLM\stt\stt_server.py --port <พอร์ต>
# -X utf8 = โหมด UTF-8 ของ python ทั้งโปรเซส (log/ไฟล์ภาษาไทย)  บริการผูก 127.0.0.1 เองเสมอ ไม่มีตัวเลือก host ให้ส่ง
# โหลดโมเดลตั้งแต่เริ่ม (ค่าปริยายของบริการ) แล้วเลือก GPU/CPU ตาม VRAM ที่ว่างตอนนั้น (สัญญา C1) — ปลดโมเดลเองเมื่อว่าง 15 นาที
function Get-SttArgs {
    $argv = @('-X', 'utf8', $SttScript, '--port', [string]$SttPort)
    return ,$argv
}

# ตัวแปรที่ส่งให้บริการ STT (env สะอาดของ WMI ไม่มี):
#   HF_HUB_OFFLINE=1   ใช้โมเดล faster-whisper ที่แคชไว้เท่านั้น ห้ามดาวน์โหลด (สัญญา: ไม่มีเครือข่าย) — ชั้นกันซ้อนกับตัวบริการ
#   CUDA_DEVICE_ORDER  ลำดับ GPU เดียวกับ router (ชื่อ/เลข GPU ตรงกันเมื่อมี eGPU)
#   PYTHONIOENCODING   print ภาษาไทยลง log ที่ redirect แล้วไม่ตาย (บทเรียนเดียวกับ hub safe_print)
function Get-SttEnv {
    return @{ LLM_LOCAL_TOKEN_FILE = [string]$env:LLM_LOCAL_TOKEN_FILE; HF_HUB_OFFLINE = '1'
              CUDA_DEVICE_ORDER = 'PCI_BUS_ID'; PYTHONIOENCODING = 'utf-8' }
}

# 'ok' (ready/idle) | 'loading' | 'nomodel' (ไม่พบโมเดล faster-whisper — ดิสก์ E: ถอดอยู่?) | 'auth' | 'down'
# /health ของ stt_server.py ไม่ต้องใช้โทเคน และตอบ 200 เสมอพร้อม state (ready | idle | loading | no_model | error)
# จึงอ่านจาก JSON ไม่ใช่รหัส HTTP — ไม่ส่งโทเคน (ไม่จำเป็น) ไม่ผ่าน proxy ของระบบ
function Get-SttHealth([int]$p) {
    try {
        $req = [System.Net.HttpWebRequest]::Create("http://127.0.0.1:$p/health")
        $req.Method = 'GET'
        $req.Timeout = 3000
        $req.Proxy = $null
        # ไม่เก็บสายไว้ใช้ซ้ำ: สายที่ค้างถูกตัดตอนตัวเปิดจบ แล้ว stt_server.py พิมพ์ traceback ConnectionReset ลง log ทุกครั้ง
        $req.KeepAlive = $false
        $resp = $req.GetResponse()
        $code = [int]$resp.StatusCode
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $body = $sr.ReadToEnd()
        $sr.Close()
        $resp.Close()
        if ($code -ne 200) { return 'down' }
        try { $st = [string](ConvertFrom-Json $body).state } catch { $st = '' }
        if ($st -eq 'loading') { return 'loading' }
        if ($st -eq 'no_model') { return 'nomodel' }
        if ($st -eq 'error') { return 'down' }
        return 'ok'
    } catch [System.Net.WebException] {
        $r = $_.Exception.Response
        if ($r) {
            $code = [int]$r.StatusCode
            $r.Close()
            if ($code -eq 503) { return 'loading' }
            if ($code -eq 401 -or $code -eq 403) { return 'auth' }
        }
        return 'down'
    } catch { return 'down' }
}

# ใครฟังพอร์ต STT อยู่ และต้องเปิดใหม่ไหม — คืน @{ Ours; Pid; Name; Why } (แบบเดียวกับ Get-EmbedState)
#   Ours = python ที่ command line มี stt_server.py เท่านั้น — โปรแกรมอื่นที่ถือพอร์ตไม่แตะเด็ดขาด
#   Why  = ไม่รับโทเคนในไฟล์ (ไฟล์ถูกสร้างใหม่หลังบริการเริ่ม = hub ส่งเสียงให้ไม่ได้) — "ไม่ตอบ" ไม่นับ:
#          อาจกำลังแปลงเสียงยาวอยู่ ปิดทิ้งจะตัดงานของผู้ใช้
function Get-SttState([int]$p) {
    $opid = Get-PortPid $p
    $out = @{ Ours = $false; Pid = $opid; Name = ''; Why = '' }
    if ($opid -le 0) { return $out }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$opid" -ErrorAction SilentlyContinue
    if (-not $proc) { return $out }
    $out.Name = [string]$proc.Name
    $cl = [string]$proc.CommandLine
    if ($out.Name -notmatch '^pythonw?\.exe$' -or $cl -notmatch 'stt_server\.py') { return $out }
    $out.Ours = $true
    # /health ไม่ตรวจโทเคน — ถามที่ /v1/status (ต้องใช้โทเคน) แทน: 401 = บริการจำโทเคนชุดเก่า
    if ((Test-RouterAuth $p '/v1/status') -eq $false) { $out.Why = 'ไม่รับโทเคนในไฟล์ (โทเคนชุดเก่า — hub ส่งเสียงให้ไม่ได้)' }
    return $out
}

# ปิดเฉพาะโปรเซสที่ Get-SttState ยืนยันแล้วว่าเป็นบริการ STT ของเรา
function Stop-Stt([int]$OwnerPid) {
    if ($OwnerPid -le 0) { return $true }
    Stop-Process -Id $OwnerPid -Force -ErrorAction SilentlyContinue
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Test-Port $SttPort)) { return $true }
        Start-Sleep -Milliseconds 250
    }
    return (-not (Test-Port $SttPort))
}

# เปิดผ่าน WMI (env สะอาด) — ไม่รอโหลดโมเดลเสร็จตรงนี้ (ตรวจอีกทีก่อนจบด้วย Show-SttReady)
function Start-Stt([string]$Py) {
    return (Start-CleanProcess $Py (Get-SttArgs) (Split-Path $SttScript -Parent) "$LogDir\$SttLogName.out.log" `
                "$LogDir\$SttLogName.err.log" (Get-SttEnv))
}

# รอให้บริการที่เพิ่งเปิดพร้อม — คืน 'ok' | 'loading' | 'auth' | 'down' (โปรเซสตายไปแล้ว = 'down' ทันที ไม่รอเปล่า)
function Wait-SttReady($H, [int]$Sec) {
    $deadline = (Get-Date).AddSeconds($Sec)
    while ($true) {
        $s = Get-SttHealth $SttPort
        # nomodel ไม่หายเองระหว่างรอ (ไม่มีไฟล์โมเดล) — ตอบเลย ไม่ต้องรอจนหมดเวลา
        if ($s -eq 'ok' -or $s -eq 'auth' -or $s -eq 'nomodel') { return $s }
        if ($H -and -not (Test-CleanAlive $H)) { return 'down' }
        if ((Get-Date) -ge $deadline) { return $s }
        Start-Sleep -Milliseconds 500
    }
}

function Show-SttReady($H, [int]$Sec) {
    $s = Wait-SttReady $H $Sec
    if ($s -eq 'ok') {
        Write-Host "  [4/4] บริการแปลงเสียงเป็นข้อความพร้อม (พอร์ต $SttPort)" -ForegroundColor Green
    } elseif ($s -eq 'loading') {
        Write-Host "  [4/4] บริการแปลงเสียงเป็นข้อความยังโหลดโมเดลอยู่ (พอร์ต $SttPort) — ปุ่มไมค์ใช้ได้เมื่อโหลดเสร็จ" -ForegroundColor Yellow
    } elseif ($s -eq 'auth') {
        Write-Host "  [4/4] บริการแปลงเสียงเป็นข้อความไม่รับโทเคนในไฟล์ — เปิดตัวเปิดด้วย -RestartStt" -ForegroundColor Yellow
    } elseif ($s -eq 'nomodel') {
        Write-Host "  [4/4] บริการแปลงเสียงเป็นข้อความเปิดแล้วแต่ไม่พบโมเดล faster-whisper (แคชบนดิสก์ E: — ถอดอยู่?) — ปุ่มไมค์ใช้ไม่ได้" -ForegroundColor Yellow
    } else {
        Write-Host "  [4/4] บริการแปลงเสียงเป็นข้อความไม่ขึ้น — ปุ่มไมค์ใช้ไม่ได้ ดูสาเหตุที่ $LogDir\$SttLogName.err.log" -ForegroundColor Yellow
        $f = "$LogDir\$SttLogName.err.log"
        if (Test-Path -LiteralPath $f) {
            $lines = @(Get-Content -LiteralPath $f -Encoding UTF8 -ErrorAction SilentlyContinue | Where-Object { $_.Trim() } |
                       Select-Object -Last 3)
            foreach ($l in $lines) { Write-Host "          $l" -ForegroundColor DarkGray }
        }
    }
    return $s
}

# ขั้น 1e ทั้งหมด — คืน @{ H = handle ของตัวที่เพิ่งเปิด (หรือ $null); State = started | running | skipped | foreign | failed }
# ใช้สองที่: ขั้นปกติของตัวเปิด (เปิดจากไอคอน) และโหมด -SttOnly / -RestartStt
function Invoke-SttStep {
    if ($NoStt) {
        Write-Host '  [1/4] บริการแปลงเสียงเป็นข้อความ: ข้าม (-NoStt)' -ForegroundColor DarkGray
        return @{ H = $null; State = 'skipped' }
    }
    if ($Port -ne $MainPort -and -not $SttPortGiven) {
        Write-Host "  [1/4] บริการแปลงเสียงเป็นข้อความ: ข้ามในรอบทดสอบพอร์ต $Port (ใส่ -SttPort เพื่อทดสอบบนพอร์ตอื่น)" -ForegroundColor DarkGray
        return @{ H = $null; State = 'skipped' }
    }
    if (-not (Test-Path -LiteralPath $SttScript)) {
        Write-Host "  [1/4] บริการแปลงเสียงเป็นข้อความ: ยังไม่มี $SttScript — ข้าม (ปุ่มไมค์ใช้ไม่ได้)" -ForegroundColor DarkGray
        return @{ H = $null; State = 'skipped' }
    }
    $py = Get-SttPython
    if (-not $py) {
        Write-Host '  [1/4] บริการแปลงเสียงเป็นข้อความ: ไม่พบ python ของ conda env flexxfast (ที่มี faster-whisper) — ข้าม' -ForegroundColor Yellow
        return @{ H = $null; State = 'failed' }
    }
    if (-not (Test-TokenFileStrict)) {
        Write-Host "  [1/4] บริการแปลงเสียงเป็นข้อความ: ไม่เปิด — ใช้ $TokenFile ไม่ได้ (บริการรับเฉพาะคำขอที่มีโทเคน)" -ForegroundColor Yellow
        return @{ H = $null; State = 'failed' }
    }
    if (Test-Port $SttPort) {
        $ss = Get-SttState $SttPort
        if (-not $ss.Ours) {
            Write-Host ("  [1/4] พอร์ต {0} ถูก {1} ใช้อยู่ ไม่ใช่บริการแปลงเสียงของเรา — ไม่แตะ (ปุ่มไมค์ใช้ไม่ได้)" -f $SttPort, $ss.Name) -ForegroundColor Yellow
            return @{ H = $null; State = 'foreign' }
        }
        # -RestartStt อยู่หลังการตรวจ Ours เสมอ: โปรแกรมอื่นไม่มีทางถูกปิดด้วยสวิตช์นี้
        if ($RestartStt -and -not $ss.Why) { $ss.Why = 'สั่งเปิดใหม่ (-RestartStt)' }
        if (-not $ss.Why) {
            Write-Host "  [1/4] บริการแปลงเสียงเป็นข้อความ: เปิดอยู่แล้ว (พอร์ต $SttPort)" -ForegroundColor DarkGray
            return @{ H = $null; State = 'running' }
        }
        Write-Host ("  [1/4] บริการแปลงเสียงเป็นข้อความ (พอร์ต {0}) {1} — เปิดใหม่" -f $SttPort, $ss.Why) -ForegroundColor Yellow
        if (-not (Stop-Stt $ss.Pid)) {
            Write-Host '        ปิดตัวเดิมไม่สำเร็จ — ปล่อยไว้ตามเดิม' -ForegroundColor Red
            return @{ H = $null; State = 'failed' }
        }
    }
    $h = Start-Stt $py
    if ($h) {
        Write-Host "  [1/4] บริการแปลงเสียงเป็นข้อความ: กำลังเปิด (พอร์ต $SttPort, python ของ flexxfast)" -ForegroundColor Green
        return @{ H = $h; State = 'started' }
    }
    Write-Host '  [1/4] บริการแปลงเสียงเป็นข้อความ: เปิดไม่ได้ — ปุ่มไมค์ใช้ไม่ได้' -ForegroundColor Yellow
    return @{ H = $null; State = 'failed' }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host ''
Write-Host '  Qwen3.8-27B' -ForegroundColor Cyan
Write-Host '  ===========' -ForegroundColor Cyan
Write-Host ''

foreach ($f in @($Server, $Model, $UiConfig)) {
    if (-not (Test-Path -LiteralPath $f)) {
        Write-Host "  ไม่พบไฟล์ที่จำเป็น: $f" -ForegroundColor Red
        if ($NonInteractive -or $Unattended) { Write-Host "  ผลลัพธ์: failed — ไม่พบไฟล์ที่จำเป็น $(Split-Path $f -Leaf) (exit 1)" -ForegroundColor Red }
        else { Read-Host '  กด Enter เพื่อปิด' }
        exit 1
    }
}

# ---- กันตัวเปิดสองตัวทำงานซ้อนกันบนพอร์ตเดียวกัน ------------------------------
# hub สั่งรัน (-NonInteractive) ระหว่างที่ผู้ใช้ดับเบิลคลิกไอคอน (หรือกลับกัน) = สองตัวรอแชตว่างพร้อมกันแล้วต่างคนต่าง
# ปิด/เปิด router ซ้อนกัน: ปิด router (และโมเดลที่กำลังโหลด) ที่อีกตัวเพิ่งเปิด, ลบไฟล์ใน $GenDir ที่อีกตัวกำลังเทียบ,
# ตัวที่แย่งพอร์ตไม่ทันถอยไปค่าแบบเดิมแล้วเผยแพร่โปรไฟล์ legacy ทับ (hub แสดงแผนที่ไม่ได้ใช้)
# named mutex ต่อพอร์ต: ตัวที่มาทีหลังรอ พอตัวแรกจบค่อยตรวจ/เทียบใหม่ (ปกติจะเจอว่า "เหมือนเดิม" ไม่ต้องรีสตาร์ตซ้ำ)
# Local\ = เฉพาะ session ของผู้ใช้นี้ (hub ที่สั่งรันก็อยู่ session เดียวกัน)  process ตายกลางทาง Windows ปล่อยให้เอง
# (ตัวถัดไปได้ AbandonedMutexException = ได้ lock แล้ว)  พอร์ตทดสอบ (-Port 8199) ใช้ lock ของตัวเอง ไม่รอตัวจริง
$LockName = "Local\Qwen38Launcher-$Port"
$LockWaitSec = 600      # ตัวแรกใช้ได้ถึง ~9 นาทีในกรณีแย่สุด (สร้างแผน + รอแชต 3 นาที + รีสตาร์ต + ถอยไปค่าแบบเดิม)
$LockWaitMin = [int][math]::Ceiling($LockWaitSec / 60)
$LauncherLock = $null

# WaitOne ที่ได้ mutex ของ process ที่ตายไปแล้ว โยน AbandonedMutexException (ห่อมาใน MethodInvocationException ของ PS)
# แต่ lock เป็นของเราแล้ว — ถือว่าได้  ข้อผิดพลาดอื่น (ไม่ควรเกิด) คืน $null ให้ทำต่อแบบไม่มี lock
function Wait-LauncherLock($M, [int]$Ms) {
    try { return $M.WaitOne($Ms) }
    catch {
        $e = $_.Exception
        while ($e) {
            if ($e -is [System.Threading.AbandonedMutexException]) { return $true }
            $e = $e.InnerException
        }
        return $null
    }
}

function Lock-Launcher {
    try { $m = New-Object System.Threading.Mutex($false, $LockName) }
    catch {
        Write-Host "  (สร้าง lock ของตัวเปิดไม่ได้: $($_.Exception.Message) — ทำต่อโดยไม่กันตัวเปิดซ้อน)" -ForegroundColor DarkGray
        return $true
    }
    $got = Wait-LauncherLock $m 0
    if ($got -eq $false) {
        Write-Host ("  มีตัวเปิดอีกตัวกำลังทำงานกับพอร์ต {0} อยู่ (หน้าแชตกำลังใช้ GPU ชุดใหม่ หรือเปิดจากไอคอนซ้ำ) — รอให้เสร็จก่อน สูงสุด {1} นาที..." -f $Port, $LockWaitMin) -ForegroundColor Yellow
        $deadline = (Get-Date).AddSeconds($LockWaitSec)
        while (($got -eq $false) -and ((Get-Date) -lt $deadline)) { $got = Wait-LauncherLock $m 5000 }
        if ($got -eq $true) { Write-Host '  ตัวเปิดอีกตัวทำงานเสร็จแล้ว — ตรวจ GPU และเทียบค่าใหม่อีกรอบ' -ForegroundColor DarkGray }
    }
    if ($null -eq $got) {
        Write-Host '  (รอ lock ของตัวเปิดไม่ได้ — ทำต่อโดยไม่กันตัวเปิดซ้อน)' -ForegroundColor DarkGray
        try { $m.Dispose() } catch { }
        return $true
    }
    if ($got) { $script:LauncherLock = $m; return $true }
    try { $m.Dispose() } catch { }
    return $false
}

# ปล่อยก่อนทุกจุดที่จบ/รอผู้ใช้ (Read-Host, หน่วงท้าย) — ไม่งั้น hub ที่สั่งรันต้องรอผู้ใช้กด Enter
# ต้องเรียกจากเธรดเดียวกับที่ WaitOne (สคริปต์ทั้งไฟล์รันบนเธรดเดียว) พลาดก็ไม่เป็นไร: process จบแล้ว Windows ปล่อยให้
function Unlock-Launcher {
    if ($script:LauncherLock) {
        try { $script:LauncherLock.ReleaseMutex() } catch { }
        try { $script:LauncherLock.Dispose() } catch { }
        $script:LauncherLock = $null
    }
}

if (-not (Lock-Launcher)) {
    Write-Host ("  ตัวเปิดอีกตัวยังทำงานอยู่หลังรอครบ {0} นาที — ไม่ทำอะไรรอบนี้ (ไม่แตะ router)" -f $LockWaitMin) -ForegroundColor Red
    if ($NonInteractive -or $Unattended) {
        Write-Host ("  ผลลัพธ์: failed — มีตัวเปิดอีกตัวกำลังทำงานกับพอร์ต {0} อยู่นานเกิน {1} นาที ไม่ได้รีสตาร์ต ลองใหม่ภายหลัง (exit 1)" -f $Port, $LockWaitMin) -ForegroundColor Red
    } else { Read-Host '  กด Enter เพื่อปิด' }
    exit 1
}

# ---- 0. โทเคนของบริการในเครื่อง ---------------------------------------------
# ต้องมีก่อนเปิด MCP / hub: MCP ปฏิเสธทุกคำขอที่ไม่มีโทเคน (fail closed) และ hub ส่งโทเคนให้หน้าแชต
# สร้างไม่ได้ก็ทำต่อ — แชตยังใช้ได้ แค่เครื่องมือ MCP จะตอบ 401 จนกว่าจะมีไฟล์
if (Confirm-LocalToken) {
    Write-Host "  [0/4] โทเคนของบริการในเครื่อง: พร้อม ($TokenFile)" -ForegroundColor DarkGray
} else {
    Write-Host "  [0/4] สร้างโทเคนของบริการในเครื่องไม่ได้ ($TokenFile) — เครื่องมือ MCP จะใช้ไม่ได้จนกว่าจะแก้" -ForegroundColor Yellow
}
# C:\LLM\secrets สืบทอดสิทธิ์จาก C:\ (Authenticated Users: Modify) = บัญชีอื่นในเครื่องอ่าน/เปลี่ยนโทเคนได้
# ตัวเปิดไม่แก้ ACL เอง (ค่าความปลอดภัยของระบบไฟล์ = ผู้ใช้ตัดสินใจ) แค่เตือนพร้อมคำสั่งที่ต้องใช้ — ใช้ SID
# (*S-1-5-18 = SYSTEM, *S-1-5-32-544 = Administrators) คำสั่งจึงใช้ได้ทุกภาษาของ Windows
# โหมด -NonInteractive ไม่เตือน: log ของ hub แสดงแค่ไม่กี่บรรทัดท้ายเรื่อง GPU
if (-not $NonInteractive) {
    # ห้ามครอบ @(...): ฟังก์ชันคืน array ก้อนเดียว (return ,array) — @() จะห่ออีกชั้นแล้ว Count = 1 เสมอ
    $broadAcc = Get-SecretsBroadAccess $SecretsDir $TokenFile
    if ($broadAcc -and $broadAcc.Count -gt 0) {
        Write-Host ("        คำเตือน: {0} อ่านได้โดย {1} (สืบทอดจาก C:\) — บัญชีอื่นในเครื่องอ่าน/เปลี่ยนโทเคนได้" -f $SecretsDir, ($broadAcc -join ', ')) -ForegroundColor DarkYellow
        Write-Host '        ถ้าต้องการปิด ให้รันเอง (ตัวเปิดไม่เปลี่ยนสิทธิ์ให้):' -ForegroundColor DarkYellow
        Write-Host ('          icacls "{0}" /inheritance:r /grant:r "{1}:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "*S-1-5-32-544:(OI)(CI)F"' -f $SecretsDir, $env:USERNAME) -ForegroundColor DarkYellow
    }
}

# -EmbedOnly: ขั้น 1d อย่างเดียวแล้วจบ — ใช้เปิดบริการ embedding ครั้งแรกหลังติดตั้ง หรือตอนมันล่ม โดยไม่เสี่ยงไปเทียบ/รีสตาร์ต
# router ที่มีแชตค้างอยู่  exit 0 = พร้อม (เพิ่งเปิดหรือเปิดอยู่แล้ว), 1 = ไม่ได้เปิด/ไม่พร้อม (ข้อความบอกเหตุผลอยู่บรรทัดก่อนหน้า)
if ($EmbedOnly) {
    $eo = Invoke-EmbedStep
    $eoOk = ($eo.State -eq 'running')
    if ($eo.H) { $eoOk = ((Show-EmbedReady $eo.H 60) -eq 'ok') }
    Unlock-Launcher
    if ($eoOk) { exit 0 }
    exit 1
}

# -SttOnly / -RestartStt (batch 2b C3): ขั้น 1e อย่างเดียวแล้วจบ — เปิด/เปิดใหม่บริการ STT หลังอัปเดต stt_server.py โดยไม่เทียบ/
# รีสตาร์ต router ที่มีแชตค้างอยู่  exit 0 = พร้อม (เพิ่งเปิดหรือเปิดอยู่แล้ว), 1 = ไม่ได้เปิด/ไม่พร้อม
if ($SttOnly) {
    $so = Invoke-SttStep
    $soOk = ($so.State -eq 'running')
    if ($so.H) { $soOk = ((Show-SttReady $so.H 90) -eq 'ok') }
    Unlock-Launcher
    if ($soOk) { exit 0 }
    exit 1
}

# -NonInteractive (hub สั่งใช้ GPU ชุดใหม่) ทำเฉพาะขั้นที่ 2: MCP / ตัวตั้งเวลา / Gateway / hub เป็นของรอบเปิดจากไอคอน
# hub ที่เรียกเรามาก็รันอยู่แล้ว ไม่ต้องไปเปิดหรือตรวจอะไรที่ไม่เกี่ยวกับ GPU
if ($NonInteractive) {
    Write-Host '  [1/4] โหมด -NonInteractive: ข้าม MCP / ตัวตั้งเวลา / Gateway (ทำเฉพาะ GPU + llama-server)' -ForegroundColor DarkGray
}

# ---- 1. MCP server สำหรับค้นอินเทอร์เน็ต -----------------------------------
# บริการที่รันค้างทุกตัวเปิดด้วย Start-CleanProcess (WMI → env สะอาดของผู้ใช้) ดูเหตุผลที่ฟังก์ชันนั้น
if ($NonInteractive) {
    # ข้าม (ดูด้านบน)
} elseif (Test-Port $McpPort) {
    Write-Host "  [1/4] MCP ค้นอินเทอร์เน็ต: เปิดอยู่แล้ว (พอร์ต $McpPort)" -ForegroundColor DarkGray
} else {
    $py = @('C:\Python313\python.exe',
            "$env:USERPROFILE\anaconda3\python.exe",
            "$env:USERPROFILE\anaconda3\envs\flexxfast\python.exe") |
          Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($py) {
        $null = Start-CleanProcess $py @("$McpDir\server.py", $McpPort) $McpDir `
            "$LogDir\mcp.out.log" "$LogDir\mcp.err.log" $SvcEnv
        Start-Sleep -Milliseconds 1200
        Write-Host "  [1/4] MCP ค้นอินเทอร์เน็ต: เปิดแล้ว (พอร์ต $McpPort)" -ForegroundColor Green
    } else {
        Write-Host '  [1/4] ไม่พบ python — ข้ามส่วนค้นอินเทอร์เน็ต' -ForegroundColor Yellow
    }
}

# ---- 1b. MCP เครื่องมือในเครื่อง (มีชั้นป้องกัน) ---------------------------
# มาแทน --tools all ของ llama-server ซึ่งเข้าถึงทุก path ได้โดยไม่ตรวจสอบอะไรเลย
if ($NonInteractive) {
    # ข้าม (ดูด้านบน)
} elseif (Test-Port $McpLocalPort) {
    Write-Host "  [1/4] MCP เครื่องมือในเครื่อง: เปิดอยู่แล้ว (พอร์ต $McpLocalPort)" -ForegroundColor DarkGray
} else {
    $py3 = @('C:\Python313\python.exe',
             "$env:USERPROFILE\anaconda3\python.exe") |
           Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($py3 -and (Test-Path -LiteralPath "$McpLocal\server.py")) {
        $null = Start-CleanProcess $py3 @("$McpLocal\server.py", $McpLocalPort) $McpLocal `
            "$LogDir\mcp-local.out.log" "$LogDir\mcp-local.err.log" $SvcEnv
        Start-Sleep -Milliseconds 1000
        Write-Host "  [1/4] MCP เครื่องมือในเครื่อง: เปิดแล้ว (พอร์ต $McpLocalPort)" -ForegroundColor Green
    } else {
        Write-Host '  [1/4] ข้าม MCP เครื่องมือในเครื่อง' -ForegroundColor Yellow
    }
}

# ---- 1c. ตัวตั้งเวลา + Remote Prompt Gateway -------------------------------
# ตัวตั้งเวลา: heartbeat ทุก 30 นาที และจัดระเบียบความจำของโปรเจกต์ทุกวัน 03:00
# Gateway: รับ prompt จากภายนอกแอป ผูกกับ 127.0.0.1 เท่านั้นและต้องมี API key
#          ไม่มี tunnel ใดๆ การเปิดออกอินเทอร์เน็ตเป็นการตัดสินใจของผู้ใช้
$pyx = @('C:\Python313\python.exe', "$env:USERPROFILE\anaconda3\python.exe") |
       Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if ($pyx -and -not $NonInteractive) {
    if (-not (Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
              Where-Object { $_.CommandLine -like '*scheduler.py*' })) {
        $null = Start-CleanProcess $pyx @("$McpLocal\scheduler.py") $McpLocal `
            "$LogDir\scheduler.out.log" "$LogDir\scheduler.err.log" $SvcEnv
    }
    if (-not (Test-Port $GatewayPort)) {
        # GATEWAY_API_KEY (ถ้าผู้ใช้ตั้งไว้ถาวรใน User/Machine) มากับ env สะอาดของ WMI เองอยู่แล้ว
        $null = Start-CleanProcess $pyx @("$McpLocal\gateway.py", $GatewayPort) $McpLocal `
            "$LogDir\gateway.out.log" "$LogDir\gateway.err.log" $SvcEnv
    }
    Start-Sleep -Milliseconds 800
    Write-Host "  [1/4] ตัวตั้งเวลา + Gateway (พอร์ต $GatewayPort): พร้อม" -ForegroundColor Green
}

# ---- 1d. บริการ embedding (ค้นเอกสารตามความหมาย, สัญญา B2) --------------------
# ทำทั้งตอนเปิดจากไอคอนและโหมด -NonInteractive (hub สั่งใช้ GPU ชุดใหม่): CPU ล้วน ไม่ขึ้นกับ GPU ไม่มีแชตให้รอ
# ผลของขั้นนี้ไม่เปลี่ยน exit code — ไม่มี embedding แค่ทำให้ kb ค้นด้วยคำอย่างเดียว (MCP บอกผู้ใช้เองหนึ่งบรรทัด)
# รอบทดสอบ (-Port อื่น) ต้องใส่ -EmbedPort เอง ไม่งั้นข้าม: ห้ามรอบทดสอบไปเปิด/ปิดตัวจริงที่ 8093
# (ตัวขั้นตอนอยู่ใน Invoke-EmbedStep — ใช้ร่วมกับโหมด -EmbedOnly ที่จบก่อนถึงตรงนี้)
$EmbedH = (Invoke-EmbedStep).H

# ---- 1e. บริการแปลงเสียงเป็นข้อความ (พูดแทนพิมพ์, batch 2b สัญญา C1/C3) --------
# ไม่ทำในโหมด -NonInteractive: hub สั่งใช้ GPU ชุดใหม่ = เรื่องของ router เท่านั้น (บริการนี้เลือก GPU/CPU เองตอนเริ่ม)
# ผลของขั้นนี้ไม่เปลี่ยน exit code — ไม่มี STT แค่ทำให้ปุ่มไมค์ใช้ไม่ได้ (hub บอกสถานะในเมนู "บริการ")
$SttH = $null
if (-not $NonInteractive) { $SttH = (Invoke-SttStep).H }

# ---- 2. ตรวจ GPU + llama-server ---------------------------------------------
# $Mode: 'preset' | 'legacy' = เราเพิ่งเปิด router, '' = ไม่ได้แตะ router ที่เปิดอยู่
$Mode = ''
$LegacyWhy = ''
$ShowSummary = $false
$EndNote = ''
if ($Port -ne $MainPort) {
    Write-Host "  [2/4] พอร์ตทดสอบ $Port — แผน GPU เก็บที่ $PubDir (ไม่แตะไฟล์ของ router พอร์ต $MainPort)" -ForegroundColor DarkGray
}
$genOk = New-GpuProfile $GenDir
if (-not $genOk) { Set-Outcome 'failed' 'สร้างแผน GPU ไม่สำเร็จ (ดู C:\LLM\logs\gpu-profile-*.log)' }

# router เปิดแบบถอยไปค่าแบบเดิม = การจัด GPU (รวมถึงที่ผู้ใช้เลือกในหน้าแชต) ไม่ได้ถูกใช้ — ต้องรายงานว่าล้ม
function Set-ModeOutcome([string]$M) {
    if ($M -eq 'preset') { Set-Outcome 'done' 'เปิด llama-server ด้วยแผน GPU ใหม่แล้ว' }
    else { Set-Outcome 'failed' 'llama-server เปิดด้วย preset ไม่ขึ้น — ถอยไปค่าแบบเดิม (แผน GPU ไม่ถูกใช้)' }
}

# รอแชตว่าง → ปิด router → เปิดใหม่ (preset ก่อน ถอยไปค่าแบบเดิม) — ใช้ทั้งตอน GPU/preset เปลี่ยน และตอน router
# ยังเปิดด้วยค่าความปลอดภัยแบบเก่า  ตั้ง $script:Mode / $script:EndNote + ผลลัพธ์ของรอบนี้
function Restart-RouterWhenIdle {
    # ไม่ตัดแชตที่กำลังตอบกลางคัน: รอให้ว่างต่อเนื่องก่อน (สูงสุด 3 นาที) ไม่ว่างก็ไม่รีสตาร์ต
    # ต้องบอกบนจอว่ากำลังรอ ไม่งั้นหน้าต่างเงียบไปถึง 3 นาทีเหมือนค้าง
    Write-Host ("        กำลังรอให้แชตที่ตอบอยู่เสร็จ (ต้องว่างต่อเนื่อง ~10 วินาที สูงสุด {0} วินาที)..." -f $IdleTimeoutSec) -ForegroundColor DarkGray
    $idleLog = Join-Path $LogDir "gpu-idle-$Port"
    $idleRc = Invoke-Py @($GpuProfile, '--wait-idle', '--port', $Port, '--timeout', $IdleTimeoutSec) `
                        ($IdleTimeoutSec + 60) $idleLog
    Show-Lines "$idleLog.out.log" '        ' 'DarkGray'
    # 13 = EXIT_AUTH: router ปฏิเสธโทเคนในไฟล์ตอนนี้ — hub/Gateway ที่ถือโทเคนนี้ส่งแชตถึงมันไม่ได้อยู่แล้ว
    # รอให้ว่างก็อ่านสถานะไม่ได้ตลอดไป (ไม่งั้นต้องปิดทั้งชุดด้วยมือ) จึงถือว่าไม่มีแชตของเราให้รอ
    if ($idleRc -eq 13) {
        Write-Host '        router ใช้โทเคนชุดเก่า — ไม่มีแชตจากหน้าเว็บ/Gateway ที่ส่งถึงมันได้ รีสตาร์ตเลย' -ForegroundColor Yellow
        $idleRc = 0
    }
    if ($idleRc -eq 0) {
        Write-Host "        รีสตาร์ตเฉพาะ llama-server พอร์ต $Port (hub / MCP ทำงานต่อ)" -ForegroundColor Yellow
        if (Stop-Router $Port) {
            $script:Mode = Start-RouterWithFallback
            Set-ModeOutcome $script:Mode
        } else {
            Write-Host "        ปิด router เดิมไม่สำเร็จ — ปล่อยไว้ตามเดิม" -ForegroundColor Red
            $script:EndNote = 'หมายเหตุ: router ที่รันอยู่ยังใช้ค่าชุดเดิม (ปิดไม่สำเร็จ)'
            Set-Outcome 'failed' 'ปิด llama-server ตัวเดิมไม่สำเร็จ — ยังใช้ค่าชุดเดิม'
        }
    } elseif ($idleRc -eq 11) {
        # 11 = EXIT_BUSY ของ gpu_profile.wait_idle: ถามได้จริงและยังมีแชตตอบอยู่เมื่อครบเวลา
        Write-Host '        ยังมีแชตกำลังตอบอยู่ — ยังไม่รีสตาร์ต เปิดตัวเปิดนี้อีกครั้งเมื่อแชตตอบเสร็จ' -ForegroundColor Yellow
        $script:EndNote = 'หมายเหตุ: router ที่รันอยู่ยังใช้ค่าชุดเดิม — เปิดตัวเปิดอีกครั้งเมื่อแชตตอบเสร็จ เพื่อใช้ค่าชุดใหม่'
        Set-Outcome 'busy' ('ยังมีแชตกำลังตอบอยู่เมื่อรอครบ {0} วินาที — ไม่ได้รีสตาร์ต ลองใหม่เมื่อแชตตอบเสร็จ' -f $IdleTimeoutSec)
    } else {
        # ตัวรอแชตล้มเอง (python ค้างเกินเวลา -1 / เรียก python ไม่ได้ -2,-3 / python ผิดพลาด 2) — ไม่ใช่ "มีแชต
        # ตอบอยู่" ถ้ารายงานเป็น busy หน้าแชตจะบอกผู้ใช้ให้รอแชตแล้วลองใหม่ ทั้งที่ลองกี่ครั้งก็ล้มแบบเดิม
        Write-Host '        ตรวจไม่ได้ว่ายังมีแชตกำลังตอบอยู่หรือเปล่า — ยังไม่รีสตาร์ต (ไม่ตัดแชตที่อาจกำลังตอบ)' -ForegroundColor Red
        Show-PyFailure $idleRc $idleLog -ErrOnly
        $script:EndNote = 'หมายเหตุ: router ที่รันอยู่ยังใช้ค่าชุดเดิม — ตรวจสถานะแชตไม่ได้ จึงไม่รีสตาร์ต (ดู gpu-idle-*.log)'
        Set-Outcome 'failed' ('ตรวจสถานะแชตไม่ได้ (exit {0}) — ไม่ได้รีสตาร์ต ค่าชุดใหม่ยังไม่ถูกใช้ (ดู gpu-idle-{1}.*.log)' -f $idleRc, $Port)
    }
}

if (Test-Llama $Port) {
    $routerPid = Get-PortPid $Port
    # ค่าความปลอดภัยของ router (CORS / MCP proxy) ไม่เกี่ยวกับ GPU — ตรวจแยก และชนะผลเทียบ GPU เสมอ
    $insecureWhy = Get-RouterInsecureReason $routerPid
    if (-not $genOk) {
        if ($insecureWhy) {
            Write-Host "  [2/4] llama-server เปิดอยู่แล้ว (พอร์ต $Port) แต่ $insecureWhy — ต้องรีสตาร์ต (ใช้ค่า GPU แบบเดิม)" -ForegroundColor Yellow
            Restart-RouterWhenIdle
        } else {
            Write-Host "  [2/4] llama-server: เปิดอยู่แล้ว (พอร์ต $Port) — ปล่อยไว้ตามเดิม" -ForegroundColor DarkGray
        }
    } else {
        # เทียบ GPU + ค่าตั้งของ router ที่รันอยู่กับโปรไฟล์ใหม่
        # exit 0 = เหมือนเดิม, 10 = ต่าง, 12 = router ใช้ค่าแบบเดิมเพราะ preset นี้เคยล้ม, อื่นๆ = ตัดสินไม่ได้
        $report = Join-Path $GenDir 'compare.txt'
        $cmpRc = Invoke-Py @($GpuProfile, '--compare-running', '--port', $Port, '--router-pid', $routerPid,
                             '--state', $StateFile, '--out-dir', $GenDir, '--report', $report) `
                           60 (Join-Path $LogDir "gpu-compare-$Port")
        if ($cmpRc -eq 10) {
            Write-Host "  [2/4] llama-server เปิดอยู่แล้ว (พอร์ต $Port) แต่ GPU/ค่าตั้งต่างจากตอนที่มันเริ่ม:" -ForegroundColor Yellow
            Show-Lines $report '        ' 'Yellow'
            if ($insecureWhy) { Write-Host "        และ $insecureWhy" -ForegroundColor Yellow }
            Restart-RouterWhenIdle
        } elseif ($insecureWhy) {
            Write-Host "  [2/4] llama-server เปิดอยู่แล้ว (พอร์ต $Port) — $insecureWhy (ค่าความปลอดภัยแบบเก่า) ต้องรีสตาร์ต" -ForegroundColor Yellow
            Restart-RouterWhenIdle
        } elseif ($cmpRc -eq 0) {
            Write-Host "  [2/4] llama-server: เปิดอยู่แล้ว (พอร์ต $Port) — GPU และค่าตั้งเหมือนเดิม" -ForegroundColor DarkGray
            $null = Publish-File (Join-Path $GenDir 'models-preset.ini') $PresetFile
            $null = Publish-File (Join-Path $GenDir 'gpu-profile.json') $ProfileJson
            $routerMode = Get-RouterMode $routerPid
            # router ที่เปิดจากตัวเปิดรุ่นก่อนยังไม่มีบันทึก — จดไว้ตอนนี้ รอบหน้าจะรู้ว่า GPU เปลี่ยนไหม
            if (-not (Test-StateFor $routerPid)) { Save-RouterState $routerPid $routerMode $GenDir '' }
            if ($routerMode -eq 'legacy') {
                # ค่าที่ส่งให้โมเดลเท่ากับ preset ทุกตัว จึงไม่รีสตาร์ต (รีสตาร์ต = ทิ้งโมเดลที่โหลดไว้)
                Write-Host '        router นี้เปิดด้วยค่าแบบเดิม (ตัวเปิดรุ่นก่อน หรือรอบที่ preset ใช้ไม่ได้) แต่ค่าเท่ากับ preset — จะใช้ --models-preset เองเมื่อรีสตาร์ตครั้งถัดไป' -ForegroundColor DarkGray
                Write-Host '        (เช่นหลังเสียบ/ถอด eGPU หรือปิดด้วย stop-qwen38.ps1 แล้วเปิดใหม่)' -ForegroundColor DarkGray
            }
            $ShowSummary = $true
            Set-Outcome 'done' 'GPU และค่าตั้งของทุกโมเดลเหมือนเดิม — ไม่ต้องรีสตาร์ต'
        } elseif ($cmpRc -eq 12) {
            Write-Host "  [2/4] llama-server: เปิดอยู่แล้ว (พอร์ต $Port) — ยังใช้ค่าแบบเดิม ไม่รีสตาร์ต" -ForegroundColor Yellow
            Show-Lines $report '        ' 'Yellow'
            $EndNote = "หมายเหตุ: router ใช้ค่าแบบเดิม (ไม่ได้จัด GPU อัตโนมัติ) เพราะ preset เคยทำให้ llama-server ปิดตัว — ดู $LogDir\$LlamaLogName.preset-fail.err.log"
            Set-Outcome 'failed' "preset ชุดนี้เคยทำให้ llama-server ปิดตัว — router ยังใช้ค่าแบบเดิม (ดู $LlamaLogName.preset-fail.err.log)"
        } else {
            Write-Host "  [2/4] llama-server: เปิดอยู่แล้ว (พอร์ต $Port) — เทียบค่าไม่ได้ ปล่อยไว้ตามเดิม" -ForegroundColor DarkGray
            Show-Lines $report '        ' 'DarkGray'
            if (-not (Test-Path -LiteralPath $report)) { Show-PyFailure $cmpRc (Join-Path $LogDir "gpu-compare-$Port") }
            $EndNote = 'หมายเหตุ: ไม่ได้แตะ router ที่รันอยู่ — แผน GPU ใหม่ยังไม่ถูกใช้'
            Set-Outcome 'failed' 'เทียบค่ากับ llama-server ที่รันอยู่ไม่ได้ — ไม่ได้แตะ router แผน GPU ใหม่ยังไม่ถูกใช้'
        }
    }
} elseif (Test-Port $Port) {
    $owner = Get-PortOwner $Port
    Write-Host "  [2/4] พอร์ต $Port ถูก $owner ใช้อยู่ ไม่ใช่ llama-server" -ForegroundColor Red
    Write-Host "        เปิดใหม่ด้วยพอร์ตอื่น เช่น: Qwen38.cmd -Port 8111" -ForegroundColor DarkGray
    Unlock-Launcher
    if ($NonInteractive -or $Unattended) { Write-Host "  ผลลัพธ์: failed — พอร์ต $Port ถูกโปรแกรมอื่นใช้อยู่ (exit 1)" -ForegroundColor Red }
    else { Read-Host '  กด Enter เพื่อปิด' }
    exit 1
} else {
    # router โหลดโมเดลตอนมีคำขอแรก ไม่ใช่ตอนสตาร์ท
    $Mode = Start-RouterWithFallback
    Set-ModeOutcome $Mode
}

# ---- 2b. project hub -------------------------------------------------------
if ($NonInteractive) {
    # hub เป็นคนเรียกเรามา — รันอยู่แล้ว
} elseif (Test-Port $HubPort) {
    Write-Host "  [3/4] Project hub: เปิดอยู่แล้ว (พอร์ต $HubPort)" -ForegroundColor DarkGray
} else {
    $py2 = @('C:\Python313\python.exe',
             "$env:USERPROFILE\anaconda3\python.exe") |
           Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if ($py2) {
        # hub เปิดตัวเปิดนี้ซ้ำตอนผู้ใช้เลือก GPU (-NonInteractive) — env สะอาดของ hub จึงส่งต่อถึงรอบนั้นด้วย
        $null = Start-CleanProcess $py2 @('C:\LLM\projects\hub.py', $HubPort, $Port) 'C:\LLM\projects' `
            "$LogDir\hub.out.log" "$LogDir\hub.err.log" $SvcEnv
        Start-Sleep -Milliseconds 1200
        Write-Host "  [3/4] Project hub: เปิดแล้ว (พอร์ต $HubPort)" -ForegroundColor Green
    } else {
        Write-Host '  [3/4] ไม่พบ python — ข้าม project hub' -ForegroundColor Yellow
    }
}

# ---- 3. รอให้พร้อมแล้วเปิดเบราว์เซอร์ --------------------------------------
$url = "http://127.0.0.1:$Port"
# router ไม่โหลดโมเดลตอนเริ่ม ตอบ /health ภายในไม่กี่วินาที — hub ที่รอผลอยู่ไม่ต้องรอถึง 6 นาทีถ้ามันไม่ขึ้นจริง
if ($NonInteractive) { $deadline = (Get-Date).AddSeconds(60) } else { $deadline = (Get-Date).AddMinutes(6) }
$ready = $false
while ((Get-Date) -lt $deadline) {
    try {
        if ((Invoke-RestMethod -Uri "$url/health" -TimeoutSec 4 -ErrorAction Stop).status -eq 'ok') {
            $ready = $true; break
        }
    } catch { Start-Sleep -Seconds 3 }
}

# บริการ embedding ที่เพิ่งเปิดในข้อ 1d — ถึงตรงนี้ปกติโหลดเสร็จนานแล้ว (~2 วินาที) รอเพิ่มได้ไม่เกิน 45 วินาที
# พิมพ์ก่อนบรรทัด "[4/4] llama-server พร้อม": hub แสดงแค่บรรทัดท้ายของ log งานเลือก GPU ให้ท้ายยังเป็นแผน GPU + ผลลัพธ์
if ($EmbedH) { $embedState = Show-EmbedReady $EmbedH 45 }
# บริการ STT ที่เพิ่งเปิดในข้อ 1e — โหลดโมเดล faster-whisper บน CPU ใช้ราว 5-30 วินาที รอได้ไม่เกิน 60 วินาที
if ($SttH) { $null = Show-SttReady $SttH 60 }

if ($ready -and $NonInteractive) {
    # hub แสดงแค่ ~15 บรรทัดท้าย log — ให้ท้ายเป็นแผน GPU ที่ใช้จริงแล้วตามด้วยผลลัพธ์ ไม่ใช่รายการเครื่องมือ
    Write-Host "  [4/4] llama-server พร้อม (พอร์ต $Port)" -ForegroundColor Green
    if ($Mode -eq 'preset' -or $ShowSummary) {
        Show-GpuSummary (Join-Path $GenDir 'gpu-profile.json')
    } elseif ($Mode -eq 'legacy') {
        Write-Host "  หมายเหตุ: เปิดด้วยค่าแบบเดิม (-fit จัด GPU เอง) สาเหตุ: $script:LegacyWhy" -ForegroundColor Yellow
    } elseif ($EndNote) {
        Write-Host "  $EndNote" -ForegroundColor Yellow
    }
} elseif ($ready) {
    # เปิดหน้าแชตเลย ไม่ต้องผ่านหน้าสร้างโปรเจกต์
    # hub สร้างโปรเจกต์ "ทั่วไป" ให้เองถ้ายังไม่มี จึงมีที่ให้พิมพ์ได้ทันทีเสมอ
    $chat = $url
    if (Test-Port $HubPort) {
        try {
            $projects = (Invoke-RestMethod -Uri "http://127.0.0.1:$HubPort/api/projects" -TimeoutSec 5).projects
            if ($projects -and $projects.Count -gt 0) { $chat = "http://127.0.0.1:$($projects[0].port)" }
        } catch { }
    }
    Write-Host "  [4/4] พร้อมใช้งาน" -ForegroundColor Green
    Write-Host "        จัดการโปรเจกต์: http://127.0.0.1:$HubPort" -ForegroundColor DarkGray
    # หน้าแชตดิบที่ :8099 ต้องใส่ API key เอง (router เปิดด้วย --api-key-file) — หน้าเดียวกันผ่าน hub ไม่ต้อง (hub แนบให้)
    if ($chat -ne $url) {
        Write-Host "        แชตดิบไม่มีแถบโปรเจกต์: $chat/?ui=1" -ForegroundColor DarkGray
    } else {
        Write-Host "        แชตดิบไม่มีแถบโปรเจกต์: $url (ต้องใส่ API key = เนื้อหาไฟล์ $TokenFile)" -ForegroundColor DarkGray
    }
    Write-Host ''
    Write-Host '  เครื่องมือที่เปิดให้โมเดล (28 อย่าง ผ่านชั้นป้องกันทั้งหมด):' -ForegroundColor DarkGray
    Write-Host '    ไฟล์   read_file, write_file, edit_file, list_dir, file_glob_search, grep_search, get_info' -ForegroundColor DarkGray
    Write-Host '    คำสั่ง exec_shell_command  (คำสั่งที่เปลี่ยนเครื่องต้องให้คุณยืนยันก่อน)' -ForegroundColor DarkGray
    Write-Host '    สื่อ   media_probe/trim/resize/compress/extract_audio/mute/to_gif/transcode' -ForegroundColor DarkGray
    Write-Host '    งาน    task_start, task_list, task_get, task_stop' -ForegroundColor DarkGray
    Write-Host '    ความจำ memory_remember/recall/forget/export, path_add/list/remove/resolve  (แยกตามโปรเจกต์)' -ForegroundColor DarkGray
    Write-Host '    เน็ต   web_search, fetch_url' -ForegroundColor DarkGray
    Write-Host ''
    Write-Host '  ที่กันไว้ไม่ให้เข้าถึง: .ssh, ไฟล์ credential, ฐานข้อมูลรหัสผ่านของเบราว์เซอร์,' -ForegroundColor DarkGray
    Write-Host '  ไฟล์คีย์ (.pem .key .env), C:\Windows\System32\config — และเขียนทับ C:\Windows ไม่ได้' -ForegroundColor DarkGray
    Write-Host '  MCP รับเฉพาะหน้าแชตของเราที่มีโทเคน (hub ใส่ให้เอง) — เว็บอื่นที่เปิดอยู่เรียกเครื่องมือไม่ได้' -ForegroundColor DarkGray
    Write-Host '  บันทึกการเรียกเครื่องมือ: C:\LLM\mcp-local\audit.log' -ForegroundColor DarkGray
    Write-Host ''
    # โมเดลไหนอยู่บน GPU ไหน + ความเร็วโดยประมาณ (มาแทนข้อความ "1.5 token/วินาที" ตายตัวแบบเดิม
    # ซึ่งผิดทันทีที่เสียบ eGPU) — แสดงเฉพาะเมื่อ router ที่รันอยู่ใช้แผนนี้จริง
    if ($Mode -eq 'preset' -or $ShowSummary) {
        Show-GpuSummary (Join-Path $GenDir 'gpu-profile.json')
    } elseif ($Mode -eq 'legacy') {
        Write-Host "  หมายเหตุ: เปิดด้วยค่าแบบเดิม (-fit จัด GPU เอง ไม่ได้จัดตาม eGPU) สาเหตุ: $script:LegacyWhy" -ForegroundColor Yellow
    } elseif ($EndNote) {
        Write-Host "  $EndNote" -ForegroundColor Yellow
    }
    if ($Vision) {
        # -Vision มีผลเฉพาะรอบนี้: เปิดจากไอคอนครั้งหน้า (ไม่มีพารามิเตอร์) จะกลับเป็นค่าปกติและรีสตาร์ต router
        Write-Host '  -Vision ใช้เฉพาะรอบนี้ — ถ้าอยากดูรูปได้ทุกครั้ง เพิ่ม 2 บรรทัดนี้ใน C:\LLM\models-preset.user.ini:' -ForegroundColor DarkGray
        Write-Host "    [$PrimaryId]" -ForegroundColor DarkGray
        Write-Host "    mmproj = $Mmproj" -ForegroundColor DarkGray
    }
    if (-not $NoBrowser) { Start-Process $chat }
} else {
    if ($NonInteractive) { $waited = '60 วินาที' } else { $waited = '6 นาที' }
    Write-Host "  [4/4] เซิร์ฟเวอร์ยังไม่พร้อมภายใน $waited" -ForegroundColor Red
    Write-Host "  ดู log ได้ที่ $LogDir\$LlamaLogName.err.log" -ForegroundColor DarkGray
    Set-Outcome 'failed' "llama-server ไม่ตอบ /health ภายใน $waited (ดู $LlamaLogName.err.log)"
}

if ($NonInteractive -or $Unattended) {
    # บรรทัดสุดท้ายของ log = ผลที่ hub แสดงให้ผู้ใช้ — exit code: 0 เสร็จ, 3 ยังมีแชตตอบอยู่ (ไม่รีสตาร์ต), 1 ผิดพลาด
    # -Unattended (fix-stack): สคริปต์ที่เปิดครบชุดหลังรีบูตอ่านผลจากบรรทัดนี้/exit code เหมือนกัน
    if ($Outcome -eq 'failed') { $rc = 1; $color = 'Red' }
    elseif ($Outcome -eq 'busy') { $rc = 3; $color = 'Yellow' }
    else { $rc = 0; $color = 'Green' }
    Unlock-Launcher
    Write-Host ("  ผลลัพธ์: {0} — {1} (exit {2})" -f $Outcome, $OutcomeWhy, $rc) -ForegroundColor $color
    exit $rc
}

Unlock-Launcher
Write-Host ''
Write-Host '  ปิดหน้าต่างนี้ได้เลย เซิร์ฟเวอร์ทำงานเบื้องหลังต่อ' -ForegroundColor DarkGray
Write-Host '  หยุดทั้งหมด: powershell -File C:\LLM\stop-qwen38.ps1' -ForegroundColor DarkGray
Write-Host ''
if ($Host.Name -eq 'ConsoleHost' -and -not $NoBrowser) { Start-Sleep -Seconds 8 }
