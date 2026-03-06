Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

$venvPath = Join-Path $scriptDir ".venv"
$activatePath = Join-Path $venvPath "Scripts\Activate.ps1"
$requirementsPath = Join-Path $scriptDir "requirements-dashboard.txt"
$dashboardScript = Join-Path $scriptDir "project_inventory_dashboard.py"

if (-not (Test-Path -LiteralPath $dashboardScript)) {
    throw "Missing dashboard script: $dashboardScript"
}

if (-not (Test-Path -LiteralPath $requirementsPath)) {
    throw "Missing requirements file: $requirementsPath"
}

if (-not (Test-Path -LiteralPath $activatePath)) {
    Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Cyan
    python -m venv $venvPath
}

. $activatePath

python -c "import streamlit, pandas" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dashboard dependencies ..." -ForegroundColor Cyan
    python -m pip install -r $requirementsPath
}

Write-Host "Starting dashboard ..." -ForegroundColor Green
streamlit run $dashboardScript
