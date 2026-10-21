$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonw)) { throw "Missing background Python executable: $pythonw" }
$worker = Join-Path $PSScriptRoot 'local_worker.py'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument "-u `"$worker`"" -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'Job Accelerator Local Worker' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Keeps the Job Accelerator cloud dashboard connected to this PC for local job harvesting.' -Force | Out-Null
Start-ScheduledTask -TaskName 'Job Accelerator Local Worker'
Write-Output 'Installed and started the Job Accelerator Local Worker for this Windows account.'
