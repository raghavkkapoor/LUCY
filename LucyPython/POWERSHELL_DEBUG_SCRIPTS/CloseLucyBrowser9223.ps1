$connection = Get-NetTCPConnection -LocalPort 9223 -ErrorAction SilentlyContinue
if ($connection) {
    $connection | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    Write-Host "CDP browser on port 9223 has been closed." -ForegroundColor Green
} else {
    Write-Host "No active browser session found on port 9223." -ForegroundColor Yellow
}
