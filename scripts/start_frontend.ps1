# Start the CareVista results dashboard on http://localhost:8000
#
#   .\scripts\start_frontend.ps1              # serve the last exported results
#   .\scripts\start_frontend.ps1 -Refresh     # pull the latest results from AWS first
#   .\scripts\start_frontend.ps1 -Port 8080
param(
    [int]$Port = 8000,
    [switch]$Refresh
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$py = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $py) { $py = Get-Command py -ErrorAction Stop }

if ($Refresh) {
    Write-Host 'Exporting the latest results from AWS...'
    & $py.Source (Join-Path $root 'deploy\aws\export_results.py')
    if ($LASTEXITCODE -ne 0) { throw 'Export failed (are you logged in? run: aws login)' }
}

if (-not (Test-Path (Join-Path $root 'frontend\data\results.json'))) {
    Write-Warning 'frontend\data\results.json not found. Run with -Refresh (needs AWS login) to create it.'
}

Write-Host ""
Write-Host "CareVista dashboard: http://localhost:$Port   (Ctrl+C to stop)"
Start-Process "http://localhost:$Port" | Out-Null
& $py.Source -m http.server $Port --bind 127.0.0.1 --directory (Join-Path $root 'frontend')
