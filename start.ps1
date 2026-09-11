$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$localPython = Join-Path $PSScriptRoot '.runtime\python\python.exe'
if (Test-Path -LiteralPath $localPython) {
    & $localPython app.py
} elseif (Test-Path -LiteralPath '.venv\Scripts\python.exe') {
    & '.\.venv\Scripts\python.exe' app.py
} else {
    Write-Host 'Chua co Python moi truong du an. Xem README.md de cai dat.'
    exit 1
}
