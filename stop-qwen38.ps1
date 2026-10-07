<#
  หยุด Qwen3.8 ทั้งชุด: llama-server + project hub + proxy ของทุกโปรเจกต์ + MCP ค้นอินเทอร์เน็ต
  + บริการ embedding (8093) — งานค้นคว้าที่กำลังทำใน MCP ถูกตัดไปด้วย (MCP เปิดใหม่แล้วจะขึ้นว่า interrupted)
  + บริการแปลงเสียงเป็นข้อความ STT (8795, batch 2b) — เฉพาะเมื่อผู้ฟังพอร์ตเป็น python.exe

  จับจาก "พอร์ตที่เราเป็นเจ้าของ" ไม่ใช่จากข้อความใน command line
  เพราะ Start-Process ตั้ง working directory แยก command line จริงจึงเป็นแค่
  "python.exe hub.py 8100 8099" ไม่มีชื่อโฟลเดอร์อยู่ในนั้น การ match ด้วยชื่อโฟลเดอร์จึงพลาด
#>
$ErrorActionPreference = 'SilentlyContinue'

$LlamaPorts   = 8099, 8090
# บริการ embedding (batch 2a สัญญา B2) เป็น llama-server อีกตัว — ปิดตามพอร์ตให้เห็นชื่อชัดๆ ในรายการที่ปิด
# (ถ้าไม่ระบุ ก็ถูกปิดอยู่ดีในรอบกวาด llama-server ที่เหลือท้ายไฟล์ แต่จะขึ้นว่า "ยังไม่ได้ผูกพอร์ต" ซึ่งไม่จริง)
$EmbedPort    = 8093
# บริการ STT (batch 2b สัญญา C1) = python ของ conda env flexxfast รัน C:\LLM\stt\stt_server.py — ไม่ผูกกับ hub จึงต้องปิดแยก
$SttPort      = 8795
$HubPort      = 8100
$McpPort      = 8791
$McpLocalPort = 8792
$GatewayPort  = 8780
$ProjectPorts = 8101..8179
$stopped = @{}

function Stop-ByPort([int]$Port, [string]$Label, [string[]]$OnlyNames) {
    Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | ForEach-Object {
        $procId = $_.OwningProcess
        if ($stopped.ContainsKey($procId)) { return }
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction SilentlyContinue
        if (-not $proc) { return }
        if ($OnlyNames -and $proc.Name -notin $OnlyNames) {
            Write-Host ("  ข้าม พอร์ต {0} เป็นของ {1} ไม่ใช่ของเรา" -f $Port, $proc.Name) -ForegroundColor DarkYellow
            return
        }
        Write-Host ("  ปิด {0} PID {1} (พอร์ต {2})" -f $Label, $procId, $Port) -ForegroundColor DarkGray
        Stop-Process -Id $procId -Force
        $stopped[$procId] = $true
    }
}

foreach ($p in $LlamaPorts)   { Stop-ByPort $p 'llama-server'      @('llama-server.exe') }
Stop-ByPort $EmbedPort        'embedding service'                  @('llama-server.exe')
Stop-ByPort $SttPort          'speech-to-text service'             @('python.exe')
Stop-ByPort $HubPort          'project hub'                        @('python.exe')
Stop-ByPort $McpPort          'MCP search'                         @('python.exe')
Stop-ByPort $McpLocalPort     'MCP local tools'                    @('python.exe')
Stop-ByPort $GatewayPort      'Remote Prompt Gateway'              @('python.exe')
# ตัวตั้งเวลาไม่ได้ผูกพอร์ต จึงต้องหาจาก command line
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
    Where-Object { $_.CommandLine -like '*scheduler.py*' } | ForEach-Object {
        Write-Host ("  ปิด ตัวตั้งเวลา PID {0}" -f $_.ProcessId) -ForegroundColor DarkGray
        Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue
    }
foreach ($p in $ProjectPorts) { Stop-ByPort $p 'project proxy'     @('python.exe') }

Get-Process llama-server -ErrorAction SilentlyContinue | Where-Object { -not $stopped.ContainsKey($_.Id) } | ForEach-Object {
    Write-Host ("  ปิด llama-server PID {0} (ยังไม่ได้ผูกพอร์ต)" -f $_.Id) -ForegroundColor DarkGray
    Stop-Process -Id $_.Id -Force
    $stopped[$_.Id] = $true
}

if ($stopped.Count -eq 0) { Write-Host '  ไม่มีอะไรทำงานอยู่' -ForegroundColor DarkGray }
else { Write-Host ("  หยุดแล้ว {0} process" -f $stopped.Count) -ForegroundColor Green }
