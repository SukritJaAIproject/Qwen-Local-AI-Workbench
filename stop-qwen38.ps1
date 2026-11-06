<#
  Stop the entire Qwen3.8 suite: llama-server + project hub + proxies for all projects + internet search MCP
  + embedding service (8093) — in-progress research in MCP is also terminated (will show 'interrupted' when MCP reopens)
  + speech-to-text (STT) service (8795, batch 2b) — only when the port listener is python.exe

  Matches by "ports we own", not by text in the command line
  because Start-Process sets the working directory separately; the actual command line is just
  "python.exe hub.py 8100 8099" with no folder name in it, so matching by folder name fails.
#>
$ErrorActionPreference = 'SilentlyContinue'

$LlamaPorts   = 8099, 8090
# Embedding service (batch 2a contract B2) is another llama-server instance — stop by port to display clearly in shutdown list
# (If omitted, it gets swept up in the remaining llama-server cleanup at the end of the script, but would display as "unbound port" which is inaccurate)
$EmbedPort    = 8093
# STT service (batch 2b contract C1) = python in conda env flexxfast running C:\LLM\stt\stt_server.py — not bound to hub, so stopped separately
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
            Write-Host ("  Skipping port {0} (owned by {1}, not ours)" -f $Port, $proc.Name) -ForegroundColor DarkYellow
            return
        }
        Write-Host ("  Stopping {0} PID {1} (port {2})" -f $Label, $procId, $Port) -ForegroundColor DarkGray
        Stop-Process -Id $procId -Force
        $stopped[$procId] = $true
    }
}

foreach ($p in $LlamaPorts)   { Stop-ByPort $p 'llama-server'          @('llama-server.exe') }
Stop-ByPort $EmbedPort        'embedding service'                      @('llama-server.exe')
Stop-ByPort $SttPort          'speech-to-text service'                 @('python.exe')
Stop-ByPort $HubPort          'project hub'                            @('python.exe')
Stop-ByPort $McpPort          'MCP search'                             @('python.exe')
Stop-ByPort $McpLocalPort     'MCP local tools'                        @('python.exe')
Stop-ByPort $GatewayPort      'Remote Prompt Gateway'                  @('python.exe')
# Scheduler is not bound to a port, so locate by command line
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -EA SilentlyContinue |
    Where-Object { $_.CommandLine -like '*scheduler.py*' } | ForEach-Object {
        Write-Host ("  Stopping scheduler PID {0}" -f $_.ProcessId) -ForegroundColor DarkGray
        Stop-Process -Id $_.ProcessId -Force -EA SilentlyContinue
    }
foreach ($p in $ProjectPorts) { Stop-ByPort $p 'project proxy'         @('python.exe') }

Get-Process llama-server -ErrorAction SilentlyContinue | Where-Object { -not $stopped.ContainsKey($_.Id) } | ForEach-Object {
    Write-Host ("  Stopping llama-server PID {0} (unbound port)" -f $_.Id) -ForegroundColor DarkGray
    Stop-Process -Id $_.Id -Force
    $stopped[$_.Id] = $true
}

if ($stopped.Count -eq 0) { Write-Host '  Nothing running' -ForegroundColor DarkGray }
else { Write-Host ("  Stopped {0} process(es)" -f $stopped.Count) -ForegroundColor Green }
