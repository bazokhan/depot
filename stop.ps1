Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir

$dashboardScript = Join-Path $scriptDir "project_inventory_dashboard.py"
$dashboardName = Split-Path -Leaf $dashboardScript
$escapedScriptPath = [regex]::Escape($dashboardScript)
$escapedScriptName = [regex]::Escape($dashboardName)

$targets = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -ieq "python.exe" -or $_.Name -ieq "pythonw.exe" -or $_.Name -ieq "streamlit.exe") -and
    $_.CommandLine -and
    $_.CommandLine -match "(?i)\bstreamlit\b" -and
    ($_.CommandLine -match $escapedScriptPath -or $_.CommandLine -match $escapedScriptName)
}

if (-not $targets) {
    Write-Host "No running Streamlit process found for this project." -ForegroundColor Yellow
    exit 0
}

foreach ($proc in $targets) {
    try {
        Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
        Write-Host ("Stopped Streamlit PID {0}" -f $proc.ProcessId) -ForegroundColor Green
    }
    catch {
        Write-Warning ("Failed to stop PID {0}: {1}" -f $proc.ProcessId, $_.Exception.Message)
    }
}
