Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

$venvPath = Join-Path $scriptDir ".venv"
$activatePath = Join-Path $venvPath "Scripts\Activate.ps1"
$venvPythonPath = Join-Path $venvPath "Scripts\python.exe"
$venvPipPath = Join-Path $venvPath "Scripts\pip.exe"
$requirementsPath = Join-Path $scriptDir "requirements-dashboard.txt"
$dashboardScript = Join-Path $scriptDir "depot.py"

if (-not (Test-Path -LiteralPath $dashboardScript)) {
    throw "Missing dashboard script: $dashboardScript"
}

if (-not (Test-Path -LiteralPath $requirementsPath)) {
    throw "Missing requirements file: $requirementsPath"
}

function New-CleanVenv {
    param (
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (Test-Path -LiteralPath $Path) {
        Write-Host "Rebuilding virtual environment (detected moved/broken .venv) ..." -ForegroundColor Yellow
        Remove-Item -Recurse -Force -LiteralPath $Path
    }
    else {
        Write-Host "Creating virtual environment in .venv ..." -ForegroundColor Cyan
    }

    python -m venv $Path
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create virtual environment at: $Path"
    }
}

$venvNeedsRebuild = $false
if (-not (Test-Path -LiteralPath $activatePath) -or -not (Test-Path -LiteralPath $venvPythonPath)) {
    $venvNeedsRebuild = $true
}
else {
    & $venvPythonPath -m pip --version *> $null
    if ($LASTEXITCODE -ne 0) {
        $venvNeedsRebuild = $true
    }

    if (-not $venvNeedsRebuild -and (Test-Path -LiteralPath $venvPipPath)) {
        & $venvPipPath --version *> $null
        if ($LASTEXITCODE -ne 0) {
            $venvNeedsRebuild = $true
        }
    }
}

if ($venvNeedsRebuild) {
    New-CleanVenv -Path $venvPath
}

. $activatePath

python -c "import streamlit, pandas" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing dashboard dependencies ..." -ForegroundColor Cyan
    python -m pip install -r $requirementsPath
}

Write-Host "Starting dashboard ..." -ForegroundColor Green
python -m streamlit run $dashboardScript
