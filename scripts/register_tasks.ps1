# (Re)register the two İhale Gözlemevi scheduled tasks for the CURRENT user. Idempotent: run it as often as you like.
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\register_tasks.ps1"
#   ihaleGozlemevi-daily-ai     21:30 local, scripts\run_daily.ps1,    time limit 2 h (an existing trigger is left as it is)
#   ihaleGozlemevi-backfill-ai  14:00 local (= 01:00 TRT while this PC is on PST), scripts\run_backfill.ps1, limit 8 h
# The PC clock is US Pacific, Turkey is UTC+3. The backfill command has its own --window-utc guard (22:00-04:30 UTC),
# so a task that fires at the wrong hour (daylight saving) or a manual start cannot send requests by day.
# Interactive logon (S4U is denied without admin), RunLevel Limited. Node (fnm) is put on PATH like the daily task did.
# Neither task is started by this script. Stop the backfill: Disable-ScheduledTask ihaleGozlemevi-backfill-ai (or the BLOCKED marker).
# Saved as UTF-8 with BOM for Windows PowerShell 5.1.

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

# --- daily
$name = 'ihaleGozlemevi-daily-ai'
if (Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue) {
    # keep the existing trigger untouched (no -Trigger)
    Set-ScheduledTask -TaskName $name -Action (New-IhaleAction 'run_daily.ps1') -Settings (New-IhaleSettings (New-TimeSpan -Hours 2)) -Principal $principal | Out-Null
    Write-Host "updated $name (trigger kept)"
} else {
    Register-ScheduledTask -TaskName $name -Action (New-IhaleAction 'run_daily.ps1') -Trigger (New-ScheduledTaskTrigger -Daily -At '21:30') `
        -Settings (New-IhaleSettings (New-TimeSpan -Hours 2)) -Principal $principal | Out-Null
    Write-Host "registered $name"
}

# --- backfill (replaced wholesale, including its trigger)
$name = 'ihaleGozlemevi-backfill-ai'
Register-ScheduledTask -TaskName $name -Action (New-IhaleAction 'run_backfill.ps1') -Trigger (New-ScheduledTaskTrigger -Daily -At '14:00') `
    -Settings (New-IhaleSettings (New-TimeSpan -Hours 8)) -Principal $principal -Force | Out-Null
Write-Host "registered $name"

Get-ScheduledTask | Where-Object TaskName -like 'ihaleGozlemevi-*' | ForEach-Object {
    $i = Get-ScheduledTaskInfo $_
    '{0,-30} {1,-8} next {2}  limit {3}' -f $_.TaskName, $_.State, $i.NextRunTime, $_.Settings.ExecutionTimeLimit
}
