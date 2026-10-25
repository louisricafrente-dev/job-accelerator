$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$script = Join-Path $PSScriptRoot 'sync_upwork.py'
$python = (Get-Command python.exe -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path -Parent $python) 'pythonw.exe'
$action = New-ScheduledTaskAction -Execute $pythonw -Argument ('"' + $script + '" --background') -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 10)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Minutes 5) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'Job Accelerator Upwork Feed' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description 'Fetches targeted Upwork jobs via flconsole every 10 minutes while this PC is online.' -Force | Out-Null
Start-ScheduledTask -TaskName 'Job Accelerator Upwork Feed'
Write-Output 'Upwork polling installed: every 10 minutes while signed into Windows.'
