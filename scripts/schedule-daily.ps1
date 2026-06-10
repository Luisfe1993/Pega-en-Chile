# Pega-en-Chile daily runner — scheduled task entrypoint.
#
# Schedules itself in Windows Task Scheduler. Each daily run:
#   1. Discovers fresh jobs.
#   2. Re-ranks using search.yaml.
#   3. Writes a new digest into data/digests/.
#   4. Does NOT run research/tailor (LLM stages) — those cost tokens; trigger
#      them manually after you've reviewed the digest.
#
# Usage (one-time install, from this repo root, in an elevated pwsh):
#   .\scripts\schedule-daily.ps1 -Install
#
# To run once now without scheduling:
#   .\scripts\schedule-daily.ps1
#
# To uninstall the scheduled task:
#   .\scripts\schedule-daily.ps1 -Uninstall

[CmdletBinding()]
param(
    [switch]$Install,
    [switch]$Uninstall,
    [string]$Time = "08:00",
    [string]$TaskName = "Pega-en-Chile Daily Search"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Error "Python venv not found at $Python. Run: python -m venv .venv first."
    exit 1
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "[OK] Removed scheduled task '$TaskName'." -ForegroundColor Green
    } else {
        Write-Host "Task '$TaskName' was not registered." -ForegroundColor Yellow
    }
    exit 0
}

if ($Install) {
    # Register a daily task that calls this same script (without -Install).
    $action = New-ScheduledTaskAction `
        -Execute "pwsh.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" `
        -WorkingDirectory $RepoRoot
    $trigger = New-ScheduledTaskTrigger -Daily -At $Time
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable -DontStopIfGoingOnBatteries `
        -RunOnlyIfNetworkAvailable
    Register-ScheduledTask -TaskName $TaskName -Action $action `
        -Trigger $trigger -Settings $settings -Force | Out-Null
    Write-Host "[OK] Scheduled '$TaskName' daily at $Time." -ForegroundColor Green
    Write-Host "     Edit later: Task Scheduler > Task Scheduler Library > $TaskName" -ForegroundColor Gray
    exit 0
}

# ---- Normal run -----------------------------------------------------------
Push-Location $RepoRoot
try {
    Write-Host "[$(Get-Date -Format s)] Pega daily run starting..." -ForegroundColor Cyan
    & $Python -m pega_agent.cli run --research 0 --tailor 0 --thread daily
    if ($LASTEXITCODE -ne 0) {
        # Pipeline pauses at Quality Gate even with --research 0; that's expected
        # and exits non-zero is not how typer behaves anyway. Re-check below.
        Write-Warning "pega run exited with code $LASTEXITCODE"
    }
    # If the digest landed, write its path to a 'latest.txt' for convenience.
    $digestsDir = Join-Path $RepoRoot "data\digests"
    if (Test-Path $digestsDir) {
        $latest = Get-ChildItem -Path $digestsDir -Filter "*.md" |
            Sort-Object LastWriteTime -Descending | Select-Object -First 1
        if ($latest) {
            $latest.FullName | Out-File -FilePath (Join-Path $digestsDir "latest.txt") -Encoding utf8
            Write-Host "[OK] Latest digest: $($latest.FullName)" -ForegroundColor Green
        }
    }
}
finally {
    Pop-Location
}
