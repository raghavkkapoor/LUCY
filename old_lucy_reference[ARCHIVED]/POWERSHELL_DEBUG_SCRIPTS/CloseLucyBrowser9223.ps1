param([int]$Port = 9223)

$connection = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
if ($connection) {
    $connection | ForEach-Object {
        Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
    }
    Write-Host "CDP browser on port $Port has been closed." -ForegroundColor Green
} else {
    Write-Host "No active browser session found on port $Port." -ForegroundColor Yellow
}
