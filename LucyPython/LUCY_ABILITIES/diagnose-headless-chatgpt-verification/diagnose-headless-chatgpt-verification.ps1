$ErrorActionPreference = "Stop"

$live = Invoke-RestMethod "http://127.0.0.1:9223/json/version" -TimeoutSec 3
$headless = Invoke-RestMethod "http://127.0.0.1:9333/json/version" -TimeoutSec 3

Write-Output "LIVE_9223_READY=$([bool]$live.webSocketDebuggerUrl)"
Write-Output "HEADLESS_9333_READY=$([bool]$headless.webSocketDebuggerUrl)"
Write-Output "DIAGNOSIS=Headless 9333 is independently receiving the verification page despite authenticated cookies."
