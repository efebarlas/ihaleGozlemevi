# Register the ihaleGozlemevi-history-ai scheduled task for the CURRENT user. Idempotent (replaces the task):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<repo>\scriptsegister_history_task.ps1"
# Daily 10:07 local, scriptsun_history.ps1 (history-parse into research\history.db: offline, no EKAP client), limit 3 h,
# StartWhenAvailable + WakeToRun, Interactive logon (S4U is denied without admin), RunLevel Limited, battery allowed.
# Does not start the task. Saved as UTF-8 with BOM for Windows PowerShell 5.1.

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$fnm = Join-Path $env:USERPROFILE '.fnm\aliases\default'
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

function New-IhaleAction([string]$script) {
    $cmd = "`$env:Path = '$fnm;' + `$env:Path; & '$(Join-Path $repo "scripts\$script")'; exit `$LASTEXITCODE"
    New-ScheduledTaskAction -Execute 'powershell.exe' -WorkingDirectory $repo `
        -Argument ('-NoProfile -ExecutionPolicy Bypass -Command "' + $cmd + '"')
}
function New-IhaleSettings([TimeSpan]$limit) {
    New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -MultipleInstances IgnoreNew -ExecutionTimeLimit $limit -WakeToRun
}
$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited

$name = 'ihaleGozlemevi-history-ai'
Register-ScheduledTask -TaskName $name -Action (New-IhaleAction 'run_history.ps1') -Trigger (New-ScheduledTaskTrigger -Daily -At '10:07') `
    -Settings (New-IhaleSettings (New-TimeSpan -Hours 3)) -Principal $principal -Force | Out-Null
Write-Host "registered $name"
Get-ScheduledTask -TaskName $name | ForEach-Object {
    $i = Get-ScheduledTaskInfo $_
    '{0,-30} {1,-8} next {2}  limit {3} wake {4}' -f $_.TaskName, $_.State, $i.NextRunTime, $_.Settings.ExecutionTimeLimit, $_.Settings.WakeToRun
}
