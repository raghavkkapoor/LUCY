
$ErrorActionPreference = 'Stop'
$root = Join-Path (Get-Location) 'LUCY_ABILITIES'
if (Test-Path $root) {
    Get-ChildItem $root -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match 'browser|chrome|image|search' } |
        Select-Object -First 10 | Out-Null
}
$port = 9223
$url = 'https://www.google.com/search?tbm=isch&q=Kawasaki+Ninja+H2+supercharger+engine+close+up'
try {
    $version = Invoke-RestMethod "http://127.0.0.1:$port/json/version" -TimeoutSec 3
    $ws = $version.webSocketDebuggerUrl
    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.WebSockets.ClientWebSocket]::new()
    $uri = [Uri]$ws
    $client.ConnectAsync($uri,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
    function Send-CDP($obj) {
        $json = $obj | ConvertTo-Json -Compress -Depth 10
        $bytes = [Text.Encoding]::UTF8.GetBytes($json)
        $seg = [ArraySegment[byte]]::new($bytes)
        $client.SendAsync($seg,[Net.WebSockets.WebSocketMessageType]::Text,$true,[Threading.CancellationToken]::None).GetAwaiter().GetResult()
    }
    Send-CDP @{
        id = 1
        method = 'Target.createTarget'
        params = @{
            url = $url
            newWindow = $true
        }
    }
    Start-Sleep -Seconds 2
    Add-Type -AssemblyName System.Speech
    $voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $voice.Speak("I opened images of the Kawasaki H2 supercharger in a new browser window.")
    $ability = Join-Path $root 'show-h2-supercharger'
    New-Item -ItemType Directory -Force -Path $ability | Out-Null
    $scriptPath = Join-Path $ability 'show-h2-supercharger.ps1'
    $readmePath = Join-Path $ability 'README.md'
    $MyInvocation.MyCommand.ScriptBlock.ToString() | Set-Content $scriptPath -Encoding UTF8
    @"
# Show Kawasaki H2 Supercharger
Goal: Open clear images of the Kawasaki Ninja H2 supercharger.
Method: Uses the existing Chrome DevTools Protocol instance on port 9223 and creates a new browser window showing Google Images results for the H2 supercharger.
Risk/Stability: Low risk. Read-only browser navigation. Stable as long as the Lucy Chrome CDP instance is running on port 9223.
"@ | Set-Content $readmePath -Encoding UTF8
    Write-Output "H2_SUPERCHARGER_IMAGES_OPENED=True"
    Write-Output "SCRIPT_EXISTS=$([bool](Test-Path $scriptPath))"
    Write-Output "README_EXISTS=$([bool](Test-Path $readmePath))"
    Write-Output "GOAL_COMPLETED=True"
}
catch {
    Write-Output "GOAL_COMPLETED=False"
    Write-Output "ERROR=$($_.Exception.Message)"
}
    
