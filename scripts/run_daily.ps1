# Daily İhale Gözlemevi job. Run by Task Scheduler (register with:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "<repo>\scripts\run_daily.ps1")
# Runs `python -m ihale run` (or the arguments given to this script instead) with the repo's venv python,
# appends everything to <data dir>\logs\scheduler-YYYY-MM-DD.log and exits with the run's exit code.
# Exit codes: 0 ok, 1 error, 3 BLOCKED by EKAP (or BLOCKED marker present), 5 backfill hit the request cap.
# Saved as UTF-8 with BOM so Windows PowerShell 5.1 reads the non-ASCII repo path correctly.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

# Absolute paths derived from this script's own location (no hard-coded Masaüstü path).
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo '.venv\Scripts\python.exe'

if ($env:IHALE_DATA_DIR) { $dataDir = $env:IHALE_DATA_DIR } else { $dataDir = Join-Path $env:USERPROFILE 'ihaleGozlemevi-data' }
$logDir = Join-Path $dataDir 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
# Separate from the Python job's own YYYY-MM-DD.log so the two writers never contend for one file.
$log = Join-Path $logDir ("scheduler-{0}.log" -f (Get-Date -Format 'yyyy-MM-dd'))
$utf8 = New-Object System.Text.UTF8Encoding($false)

function Write-Log([string]$text) {
    [System.IO.File]::AppendAllText($log, $text + [Environment]::NewLine, $utf8)
}

if ($args.Count -gt 0) { $ihaleArgs = @($args) } else { $ihaleArgs = @('run') }

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
