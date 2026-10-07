# tts_samples.ps1 - synthesize short WAV samples with the Windows OneCore voices (offline, no downloads).
# Used to measure the STT service (latency / accuracy) and to build test fixtures.
#
# Why WinRT and not System.Speech: System.Speech only sees the desktop SAPI voices (David, Zira);
# the Thai voice "Microsoft Pattara" exists only as a OneCore voice, which Windows.Media.SpeechSynthesis can use.
# This file is ASCII on purpose: Windows PowerShell 5.1 misreads UTF-8 without BOM, so the Thai text lives
# in the UTF-8 JSON file passed with -Spec and is read with -Encoding UTF8.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File C:\LLM\stt\tts_samples.ps1 -Spec samples.json -OutDir <dir>
# samples.json = [{"name": "th_short", "voice": "Pattara", "text": "..."}, ...]
param(
    [Parameter(Mandatory = $true)][string]$Spec,
    [Parameter(Mandatory = $true)][string]$OutDir
)
$ErrorActionPreference = 'Stop'

Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.SpeechSynthesis.SpeechSynthesizer, Windows.Media.SpeechSynthesis, ContentType = WindowsRuntime]
$null = [Windows.Storage.Streams.DataReader, Windows.Storage.Streams, ContentType = WindowsRuntime]

# WinRT async -> .NET Task (PowerShell 5.1 has no await)
$asTaskGeneric = [System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
} | Select-Object -First 1

function Wait-Op($op, [Type]$resultType) {
    $task = $asTaskGeneric.MakeGenericMethod($resultType).Invoke($null, @($op))
    $null = $task.Wait(60000)
    return $task.Result
}

if (-not (Test-Path -LiteralPath $OutDir)) { $null = New-Item -ItemType Directory -Path $OutDir }
$items = Get-Content -LiteralPath $Spec -Encoding UTF8 -Raw | ConvertFrom-Json
$all = [Windows.Media.SpeechSynthesis.SpeechSynthesizer]::AllVoices

foreach ($it in $items) {
    $voice = $all | Where-Object { $_.DisplayName -like ('*' + $it.voice + '*') } | Select-Object -First 1
    if (-not $voice) {
        Write-Output ("skip {0}: voice '{1}' is not installed" -f $it.name, $it.voice)
        continue
    }
    $synth = New-Object Windows.Media.SpeechSynthesis.SpeechSynthesizer
    $synth.Voice = $voice
    $stream = Wait-Op ($synth.SynthesizeTextToStreamAsync([string]$it.text)) ([Windows.Media.SpeechSynthesis.SpeechSynthesisStream])
    $size = [uint32]$stream.Size
    $reader = New-Object Windows.Storage.Streams.DataReader($stream.GetInputStreamAt(0))
    $null = Wait-Op ($reader.LoadAsync($size)) ([uint32])
    $bytes = New-Object byte[] $size
    $reader.ReadBytes($bytes)
    $out = Join-Path $OutDir ($it.name + '.wav')
    [System.IO.File]::WriteAllBytes($out, $bytes)
    $reader.Dispose(); $stream.Dispose(); $synth.Dispose()
    Write-Output ("ok {0} voice={1} bytes={2}" -f $it.name, $voice.DisplayName, $size)
}
