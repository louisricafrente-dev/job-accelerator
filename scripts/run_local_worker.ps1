$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$tokenFile = Join-Path $root '.vercel/local-worker.token'
if (-not (Test-Path -LiteralPath $tokenFile)) {
    throw "Missing local worker pairing token: $tokenFile"
}
$dataDir = Join-Path $env:LOCALAPPDATA 'JobAccelerator'
New-Item -ItemType Directory -Path $dataDir -Force | Out-Null
Set-Location -LiteralPath $root
$python = (Get-Command python.exe -ErrorAction Stop).Source
$process = Start-Process -FilePath $python -ArgumentList @('-u', ('"' + (Join-Path $PSScriptRoot 'local_worker.py') + '"')) -WindowStyle Hidden -Wait -PassThru
exit $process.ExitCode
