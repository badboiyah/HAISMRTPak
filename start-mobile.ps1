$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:HOST = '0.0.0.0'
Write-Host 'Mo tren dien thoai cung Wi-Fi: http://IP-LAN-MAY-TINH:5000/driver/'
Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } | ForEach-Object { Write-Host ('http://' + $_.IPAddress + ':5000/driver/') }
& (Join-Path $PSScriptRoot 'start.ps1')
