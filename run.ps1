# Convenience runner for the BROOD DataOps lab (Windows).
# Usage:  .\run.ps1          -> full pipeline run on data/raw
#         .\run.ps1 tests    -> pytest suite instead
param(
    [ValidateSet("run", "tests")]
    [string]$What = "run"
)

$lab = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $lab ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "First-time setup: creating .venv and installing requirements..." -ForegroundColor Cyan
    python -m venv (Join-Path $lab ".venv")
    & $py -m pip install --quiet --disable-pip-version-check -r (Join-Path $lab "requirements.txt")
}

if ($What -eq "tests") {
    & $py -m pytest -q
}
else {
    & $py -m etl run
}
