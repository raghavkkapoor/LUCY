$cdpHost = "127.0.0.1"
$cdpPort = 9223
$geminiUrl = "https://gemini.google.com/"
$userInput = Read-Host "Enter your request"

if ([string]::IsNullOrWhiteSpace($userInput)) {
    Write-Host "No request entered."
    exit
}

$request = "$($userInput.Trim()) - summarize in once sentence if needed."
$ws = $null
$cts = $null
$script:geminiCdpId = 0

function Send-GeminiCDP {
    param([string]$Method, [hashtable]$Params = @{})

    $script:geminiCdpId++
    $id = $script:geminiCdpId
    $message = @{ id = $id; method = $Method; params = $Params } |
        ConvertTo-Json -Depth 30 -Compress
    $bytes = [Text.Encoding]::UTF8.GetBytes($message)
    $ws.SendAsync(
        [ArraySegment[byte]]::new($bytes),
        [Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        $cts.Token
    ).GetAwaiter().GetResult() | Out-Null

    while ($true) {
        $buffer = New-Object byte[] 65536
        $memory = New-Object IO.MemoryStream
        do {
            $result = $ws.ReceiveAsync(
                [ArraySegment[byte]]::new($buffer),
                $cts.Token
            ).GetAwaiter().GetResult()
            if ($result.MessageType -eq [Net.WebSockets.WebSocketMessageType]::Close) {
                throw "Chrome closed the CDP WebSocket connection."
            }
            if ($result.Count -gt 0) { $memory.Write($buffer, 0, $result.Count) }
        } while (-not $result.EndOfMessage)

        $json = [Text.Encoding]::UTF8.GetString($memory.ToArray())
        $memory.Dispose()
        try { $response = $json | ConvertFrom-Json -ErrorAction Stop } catch { continue }
        if ($response.id -ne $id) { continue }
        if ($response.error) {
            throw "CDP error $($response.error.code): $($response.error.message)"
        }
        return $response
    }
}

function Close-GeminiCDP {
    try {
        if ($ws -and $ws.State -eq [Net.WebSockets.WebSocketState]::Open) {
            $ws.CloseAsync(
                [Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                "Done",
                [Threading.CancellationToken]::None
            ).GetAwaiter().GetResult() | Out-Null
        }
    } catch {}
    try { if ($ws) { $ws.Dispose() } } catch {}
    try { if ($cts) { $cts.Dispose() } } catch {}
}

function Invoke-GeminiEvaluate {
    param([string]$Expression, [bool]$AwaitPromise = $false)

    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        try {
            return Send-GeminiCDP "Runtime.evaluate" @{
                expression = $Expression
                returnByValue = $true
                awaitPromise = $AwaitPromise
            }
        }
        catch {
            if ($_.Exception.Message -notmatch "Cannot find default execution context|Execution context was destroyed") {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    }

    throw "Gemini JavaScript execution context did not become available."
}

try {
    $newTabUrl = "http://${cdpHost}:${cdpPort}/json/new?" +
        [Uri]::EscapeDataString($geminiUrl)
    $tab = Invoke-RestMethod -Uri $newTabUrl -Method Put -ErrorAction Stop
    $ws = [Net.WebSockets.ClientWebSocket]::new()
    $cts = [Threading.CancellationTokenSource]::new()
    $ws.ConnectAsync([Uri]$tab.webSocketDebuggerUrl, $cts.Token).GetAwaiter().GetResult() | Out-Null

    Send-GeminiCDP "Page.enable" | Out-Null
    Send-GeminiCDP "Page.navigate" @{ url = $geminiUrl } | Out-Null
    for ($i = 0; $i -lt 20; $i++) {
        try {
            Send-GeminiCDP "Runtime.enable" | Out-Null
            break
        }
        catch {
            if ($_.Exception.Message -notmatch "Cannot find default execution context|Execution context was destroyed") { throw }
            Start-Sleep -Milliseconds 250
        }
    }
    Write-Host "Waiting for Gemini..."

    $loaded = $false
    for ($i = 0; $i -lt 80; $i++) {
        try {
            $state = Invoke-GeminiEvaluate "document.readyState"
            if ($state.result.result.value -eq "complete") { $loaded = $true; break }
        }
        catch {
            # A new Chrome tab can briefly exist before its default JS context is ready.
            if ($_.Exception.Message -notmatch "Cannot find default execution context|Execution context was destroyed") { throw }
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $loaded) { throw "Gemini page load timed out." }

    # Match main.py: fill the rich-text editor, dispatch DOM events, click Send, then read the newest model response.
    $requestJson = $request | ConvertTo-Json -Compress
    $js = @'
(async () => {
    const request = __REQUEST_JSON__;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
    const visible = el => el && getComputedStyle(el).display !== "none" && el.getBoundingClientRect().width > 0;
    const responseText = () => {
        const turns = [...document.querySelectorAll("message-content, model-response, div.model-response, .response-container")].filter(visible);
        const texts = turns.map(turn => (turn.innerText || "").trim()).filter(text => text && text !== request.trim());
        return texts.length ? texts[texts.length - 1] : "";
    };

    try {
        let composer = document.querySelector("rich-textarea .ql-editor");
        for (let i = 0; i < 120 && !visible(composer); i++) {
            await sleep(250);
            composer = document.querySelector("rich-textarea .ql-editor");
        }
        if (!visible(composer)) return { success: false, error: "Gemini composer not found." };

        composer.focus();
        document.execCommand("selectAll", false, null);
        document.execCommand("insertText", false, request);
        composer.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: request }));
        composer.dispatchEvent(new Event("change", { bubbles: true }));

        let button = document.querySelector("button.send-button, button[aria-label*='Send'], button[aria-label*='Submit']");
        for (let i = 0; i < 120 && !visible(button); i++) {
            await sleep(250);
            button = document.querySelector("button.send-button, button[aria-label*='Send'], button[aria-label*='Submit']");
        }
        if (!visible(button)) return { success: false, error: "Gemini send button not found." };

        const before = responseText();
        let sawGeneration = false;
        try { button.click(); } catch { button.dispatchEvent(new MouseEvent("click", { bubbles: true })); }

        for (let i = 0; i < 240; i++) {
            const stop = document.querySelector("button[aria-label*='Stop response']");
            const text = responseText();
            if (stop) sawGeneration = true;
            if (!stop && text && (sawGeneration || text !== before)) return { success: true, text: text };
            await sleep(100);
        }

        const text = responseText();
        return text && (sawGeneration || text !== before)
            ? { success: true, text: text }
            : { success: false, error: "Gemini response timed out." };
    } catch (err) {
        return { success: false, error: err?.message || String(err) };
    }
})()
'@.Replace('__REQUEST_JSON__', $requestJson)

    Write-Host "Sending request to Gemini..."
    $result = Invoke-GeminiEvaluate $js $true
    if ($result.result.exceptionDetails) {
        $details = $result.result.exceptionDetails
        if ($details.exception.description) { throw $details.exception.description }
        throw $details.text
    }

    $data = $result.result.result.value
    if (-not $data.success) { throw $data.error }
    Write-Host "`nGemini response:`n"
    Write-Host $data.text
}
catch {
    Write-Host "`nERROR:"
    Write-Host $_.Exception.Message
}
finally {
    Close-GeminiCDP
}
