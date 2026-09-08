$ErrorActionPreference = 'Stop'
$shot = Join-Path $env:TEMP 'lucychromeheadless_9224.png'
$version = Invoke-RestMethod 'http://127.0.0.1:9224/json/version' -TimeoutSec 3
if (-not $version.webSocketDebuggerUrl) { throw "CDP 9224 unavailable." }
Write-Output "CDP_9224_READY=True"
Write-Output "SCREENSHOT=$shot"
