param(
    [int]$LastCount = 5
)

$cdpHost = "127.0.0.1"
$cdpPort = 9223
$ws = $null
$cts = $null
$browserWs = $null
$browserCts = $null
$script:cdpId = 0
$script:browserCdpId = 0

function Send-CDP {
    param([string]$Method, [hashtable]$Params = @{})

    $script:cdpId++
    $id = $script:cdpId
    $message = @{ id = $id; method = $Method; params = $Params } |
        ConvertTo-Json -Depth 20 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($message)
    $script:ws.SendAsync(
        [ArraySegment[byte]]::new($bytes),
        [Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        $script:cts.Token
    ).GetAwaiter().GetResult() | Out-Null

    while ($true) {
        $buffer = New-Object byte[] 65536
        $memory = New-Object IO.MemoryStream
        do {
            $receive = $script:ws.ReceiveAsync(
                [ArraySegment[byte]]::new($buffer),
                $script:cts.Token
            ).GetAwaiter().GetResult()
            if ($receive.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) {
                throw "Chrome closed the CDP WebSocket connection."
            }
            if ($receive.Count -gt 0) { $memory.Write($buffer, 0, $receive.Count) }
        } while (-not $receive.EndOfMessage)

        $json = [Text.Encoding]::UTF8.GetString($memory.ToArray())
        $memory.Dispose()
        try { $response = $json | ConvertFrom-Json -ErrorAction Stop } catch { continue }
        if ($response.id -ne $id) { continue }
        if ($response.error) { throw "CDP error $($response.error.code): $($response.error.message)" }
        return $response
    }
}

function Close-CDP {
    try {
        if ($script:ws -and $script:ws.State -eq [Net.WebSockets.WebSocketState]::Open) {
            $script:ws.CloseAsync(
                [Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                "Done",
                [Threading.CancellationToken]::None
            ).GetAwaiter().GetResult() | Out-Null
        }
    } catch {}
    try { if ($script:ws) { $script:ws.Dispose() } } catch {}
    try { if ($script:cts) { $script:cts.Dispose() } } catch {}
}

function New-MailWindow {
    $version = Invoke-RestMethod "http://${cdpHost}:${cdpPort}/json/version" -ErrorAction Stop
    $endpoint = [string]$version.webSocketDebuggerUrl
    if ([string]::IsNullOrWhiteSpace($endpoint)) { throw "Chrome browser CDP endpoint was not found." }

    $browserWs = [Net.WebSockets.ClientWebSocket]::new()
    $browserCts = [Threading.CancellationTokenSource]::new()
    $browserWs.ConnectAsync([Uri]::new($endpoint), $browserCts.Token).GetAwaiter().GetResult() | Out-Null
    $script:browserCdpId++
    $id = $script:browserCdpId
    $message = @{ id = $id; method = "Target.createTarget"; params = @{ url = "https://mail.my.bcit.ca/"; newWindow = $true } } |
        ConvertTo-Json -Depth 10 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($message)
    $browserWs.SendAsync([ArraySegment[byte]]::new($bytes), [Net.WebSockets.WebSocketMessageType]::Text, $true, $browserCts.Token).GetAwaiter().GetResult() | Out-Null

    while ($true) {
        $buffer = New-Object byte[] 65536
        $memory = New-Object IO.MemoryStream
        do {
            $receive = $browserWs.ReceiveAsync([ArraySegment[byte]]::new($buffer), $browserCts.Token).GetAwaiter().GetResult()
            if ($receive.Count -gt 0) { $memory.Write($buffer, 0, $receive.Count) }
        } while (-not $receive.EndOfMessage)
        $json = [Text.Encoding]::UTF8.GetString($memory.ToArray())
        $memory.Dispose()
        try { $response = $json | ConvertFrom-Json -ErrorAction Stop } catch { continue }
        if ($response.id -eq $id) {
            if ($response.error) { throw "Browser CDP error $($response.error.code): $($response.error.message)" }
            $targetId = [string]$response.result.targetId
            $browserWs.Dispose()
            $browserCts.Dispose()
            return $targetId
        }
    }
}

try {
    $targetId = New-MailWindow
    $page = $null
    for ($attempt = 0; $attempt -lt 40 -and -not $page; $attempt++) {
        $pageList = Invoke-RestMethod "http://${cdpHost}:${cdpPort}/json/list" -ErrorAction Stop
        $pages = if ($pageList -is [Array]) { $pageList } else { @($pageList) }
        foreach ($candidate in $pages) {
            if ($candidate.type -eq "page" -and $candidate.id -eq $targetId) {
                $page = $candidate
                break
            }
        }
        if (-not $page) { Start-Sleep -Milliseconds 250 }
    }
    if (-not $page) { throw "The new BCIT Mail window did not become available." }

    $wsEndpoint = [string]$page.PSObject.Properties["webSocketDebuggerUrl"].Value
    if ([string]::IsNullOrWhiteSpace($wsEndpoint)) { throw "BCIT Mail WebSocket endpoint was not found." }
    $script:ws = [Net.WebSockets.ClientWebSocket]::new()
    $script:cts = [Threading.CancellationTokenSource]::new()
    $script:ws.ConnectAsync([Uri]::new($wsEndpoint), $script:cts.Token).GetAwaiter().GetResult() | Out-Null
    Send-CDP "Runtime.enable" | Out-Null

    $countJson = [Math]::Max(1, $LastCount) | ConvertTo-Json -Compress
    $mailScript = @'
(async () => {
    const count = __COUNT__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const clean = value => (value || "").replace(/\s+/g, " ").trim();
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;

    function readUnread() {
        return [...document.querySelectorAll("tr.message.unread")]
            .filter(visible)
            .map(row => {
                const sender = row.querySelector(".rcmContactAddress, .fromto [title]");
                const subject = row.querySelector("td.subject a");
                return {
                    sender: clean(sender?.getAttribute("title") || sender?.innerText),
                    subject: clean(subject?.innerText || subject?.textContent)
                };
            })
            .filter(item => item.sender && item.subject)
            .slice(0, count);
    }

    for (let i = 0; i < 60; i++) {
        const emails = readUnread();
        if (emails.length) return { success: true, emails: emails };
        await sleep(500);
    }
    return { success: true, emails: [] };
})()
'@.Replace('__COUNT__', $countJson)

    $result = Send-CDP "Runtime.evaluate" @{
        expression = $mailScript
        returnByValue = $true
        awaitPromise = $true
    }
    if ($result.result.exceptionDetails) {
        $details = $result.result.exceptionDetails
        if ($details.exception.description) { throw $details.exception.description }
        throw $details.text
    }

    $data = $result.result.result.value
    if (-not $data.success) { throw "Could not read BCIT inbox." }
    if (@($data.emails).Count -eq 0) {
        Write-Host "No unread inbox messages found."
    }
    else {
        Write-Host "Latest $LastCount unread inbox message(s):`n"
        $index = 1
        foreach ($email in @($data.emails)) {
            Write-Host "$index. From: $($email.sender)"
            Write-Host "   Subject: $($email.subject)"
            $index++
        }
    }
}
catch {
    Write-Host "`nERROR:"
    Write-Host $_.Exception.Message
}
finally {
    Close-CDP
}
