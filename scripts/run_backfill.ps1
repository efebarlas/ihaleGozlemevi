# Night-time history backfill (fetch only) of İhale Gözlemevi. Run by Task Scheduler (see register_tasks.ps1).
# Runs `python -m ihale backfill-history` (or the arguments given to this script instead) with the repo's venv python,
# appends everything to <data dir>\logs\scheduler-backfill-YYYY-MM-DD.log and exits with the command's exit code.
# Exit codes: 0 done / run budget used / outside the night window, 1 error, 3 BLOCKED by EKAP (or BLOCKED marker present),
# 5 shared daily request cap, 7 data dir missing. The command itself refuses to run outside --window-utc.
# Saved as UTF-8 with BOM so Windows PowerShell 5.1 reads the non-ASCII repo path correctly.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Absolute paths derived from this script's own location (no hard-coded Masaüstü path).
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'

# Same resolution as ihale.config: $env:IHALE_DATA_DIR, else the pointer file, else the old default.
$pointer = Join-Path $env:USERPROFILE '.ihaleGozlemevi-data-dir'
if ($env:IHALE_DATA_DIR) { $dataDir = $env:IHALE_DATA_DIR }
elseif (Test-Path -LiteralPath $pointer) { $dataDir = ([System.IO.File]::ReadAllText($pointer)).Trim() }
else { $dataDir = Join-Path $env:USERPROFILE 'ihaleGozlemevi-data' }
# Missing-data guard (SSD unplugged): never create the data dir here; ihale itself also refuses.
if (-not (Test-Path -LiteralPath (Join-Path $dataDir 'ihale.db'))) {
    $fallback = Join-Path $env:TEMP 'ihaleGozlemevi-missing-data.log'
    [System.IO.File]::AppendAllText($fallback, ("{0} ERROR data dir {1} or its ihale.db is missing (external drive unplugged?). Nothing was run.`r`n" -f (Get-Date -Format 's'), $dataDir))
    exit 7
}
$logDir = Join-Path $dataDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
# Separate from the Python job's own YYYY-MM-DD.log and from the daily job's scheduler log (no shared writers).
$log = Join-Path $logDir ("scheduler-backfill-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$text) {
    [System.IO.File]::AppendAllText($log, $text + [Environment]::NewLine, $utf8)
}

if ($args.Count -gt 0) { $ihaleArgs = @($args) } else { $ihaleArgs = @('backfill-history') }

if (-not (Test-Path -LiteralPath $python)) {
    Write-Log ("{0} ERROR venv python not found: {1}" -f (Get-Date -Format 's'), $python)
    exit 1
}

Write-Log ("{0} start: {1} -m ihale {2}" -f (Get-Date -Format 's'), $python, ($ihaleArgs -join ' '))

$outFile = Join-Path $env:TEMP ("ihale-out-{0}.txt" -f [guid]::NewGuid())
$errFile = Join-Path $env:TEMP ("ihale-err-{0}.txt" -f [guid]::NewGuid())
$exit = 1
try {
    # Start-Process so native stderr is not turned into PowerShell error records (PS 5.1).
    $argLine = '-m ihale ' + (($ihaleArgs | ForEach-Object { if ($_ -match '\s') { '"' + $_ + '"' } else { $_ } }) -join ' ')
    $p = Start-Process -FilePath $python -ArgumentList $argLine -WorkingDirectory $repo -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $outFile -RedirectStandardError $errFile
    $exit = $p.ExitCode
    foreach ($f in @($outFile, $errFile)) {
        if (Test-Path -LiteralPath $f) {
            $t = [System.IO.File]::ReadAllText($f, $utf8)
            if ($t.Length -gt 0) { Write-Log $t.TrimEnd() }
        }
    }
} catch {
    Write-Log ("{0} ERROR {1}" -f (Get-Date -Format 's'), $_.Exception.Message)
    $exit = 1
} finally {
    Remove-Item -LiteralPath $outFile, $errFile -ErrorAction SilentlyContinue
}

Write-Log ("{0} finished with exit code {1}" -f (Get-Date -Format 's'), $exit)
exit $exit
