$ErrorActionPreference = 'Stop'
$port = 9223
$netflix = 'https://www.netflix.com/'
$version = Invoke-RestMethod "http://127.0.0.1:$port/json/version" -TimeoutSec 3
if (-not $version.webSocketDebuggerUrl) {
    throw "Chrome CDP is not available on port $port."
}
# Open Netflix as a NEW tab in Lucy's existing controlled Chrome instance.
$targetUrl = "http://127.0.0.1:$port/json/new?$([uri]::EscapeDataString($netflix))"
try {
    $target = Invoke-RestMethod -Uri $targetUrl -Method Put -TimeoutSec 5
} catch {
    $target = Invoke-RestMethod -Uri $targetUrl -Method Get -TimeoutSec 5
}
Start-Sleep -Seconds 3
$targets = Invoke-RestMethod "http://127.0.0.1:$port/json/list" -TimeoutSec 5
$opened = $targets | Where-Object {
    $_.type -eq 'page' -and $_.url -match '^https://(www\.)?netflix\.com/'
} | Select-Object -First 1
if (-not $opened) {
    throw "Netflix tab could not be verified."
}
"NETFLIX_OPENED=True"
"TITLE=$($opened.title)"
"URL=$($opened.url)"
"TARGET_ID=$($opened.id)"
