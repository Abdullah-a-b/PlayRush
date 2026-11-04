param(
    [string]$Email,
    [switch]$CheckConnection
)
$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$scriptPath = Join-Path $PSScriptRoot 'Backend\scripts\unban_production.py'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Project Python environment not found.' }
if ($CheckConnection) {
    & $pythonPath $scriptPath --check-connection
} else {
    if ([string]::IsNullOrWhiteSpace($Email)) { $Email = Read-Host 'Account email to unban in PRODUCTION' }
    & $pythonPath $scriptPath --email $Email
}
if ($LASTEXITCODE -ne 0) { throw "Production unban exited with code $LASTEXITCODE." }
