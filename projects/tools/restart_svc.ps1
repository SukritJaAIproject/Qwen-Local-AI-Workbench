# Restart one long-lived stack service with a clean user environment (WMI Win32_Process.Create).
# ASCII only. Logs are appended (>>), never truncated.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File restart_svc.ps1 -Name mcp-local|websearch|scheduler|hub
param([Parameter(Mandatory = $true)][string]$Name)
$ErrorActionPreference = 'Stop'
$py = 'C:\Python313\python.exe'
switch ($Name) {
    'mcp-local' { $match = 'C:\\LLM\\mcp-local\\server\.py"?\s+8792'; $port = 8792
                  $args1 = '"C:\LLM\mcp-local\server.py" 8792'; $wd = 'C:\LLM\mcp-local'
                  $out = 'C:\LLM\logs\mcp-local.out.log'; $err = 'C:\LLM\logs\mcp-local.err.log' }
    'websearch' { $match = 'C:\\LLM\\mcp-websearch\\server\.py"?\s+8791'; $port = 8791
                  $args1 = '"C:\LLM\mcp-websearch\server.py" 8791'; $wd = 'C:\LLM\mcp-websearch'
                  $out = 'C:\LLM\logs\mcp.out.log'; $err = 'C:\LLM\logs\mcp.err.log' }
    'scheduler' { $match = 'C:\\LLM\\mcp-local\\scheduler\.py'; $port = 0
                  $args1 = '"C:\LLM\mcp-local\scheduler.py"'; $wd = 'C:\LLM\mcp-local'
                  $out = 'C:\LLM\logs\scheduler.out.log'; $err = 'C:\LLM\logs\scheduler.err.log' }
    'hub'       { $match = 'C:\\LLM\\projects\\hub\.py"?\s+8100 8099'; $port = 8100
                  $args1 = '"C:\LLM\projects\hub.py" 8100 8099'; $wd = 'C:\LLM\projects'
                  $out = 'C:\LLM\logs\hub.out.log'; $err = 'C:\LLM\logs\hub.err.log' }
    default { throw "unknown service $Name" }
}
$old = @(Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -match $match })
foreach ($p in $old) {
    Write-Output ("stopping {0} pid {1}" -f $Name, $p.ProcessId)
    Stop-Process -Id $p.ProcessId -Force
}
if ($port) {
    for ($i = 0; $i -lt 40; $i++) {
        if (-not (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 250
    }
}
$cmd = 'cmd.exe /d /s /c ""' + $py + '" ' + $args1 + ' >> "' + $out + '" 2>> "' + $err + '""'
$si = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = $cmd; CurrentDirectory = $wd; ProcessStartupInformation = $si }
Write-Output ("create rc={0} wrapper pid={1}" -f $r.ReturnValue, $r.ProcessId)
if ($port) {
    for ($i = 0; $i -lt 60; $i++) {
        $up = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        if ($up) { Write-Output ("{0} listening on {1}, pid {2}" -f $Name, $port, $up[0].OwningProcess); break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $up) { Write-Output "WARNING: $Name did not start listening" }
} else {
    Start-Sleep -Seconds 2
    $k = Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $r.ProcessId) | Select-Object -First 1
    if ($k) { Write-Output ("{0} running pid {1}" -f $Name, $k.ProcessId) } else { Write-Output "WARNING: $Name not running" }
}
