param(
    [switch]$TestMode
)

$cdpPort = 9223
$geminiUrl = "https://gemini.google.com/"
$script:youtubeCdpId = 0
$script:geminiCdpId = 0
$youtubeWs = $null
$youtubeCts = $null
$geminiWs = $null
$geminiCts = $null

function Format-PlayheadTime {
    param([double]$Seconds)

    if ([double]::IsNaN($Seconds) -or $Seconds -lt 0) {
        return "00:00"
    }

    $totalSeconds = [int][math]::Floor($Seconds)
    $hours = [int]([math]::Floor($totalSeconds / 3600))
    $minutes = [int]([math]::Floor(($totalSeconds % 3600) / 60))
    $seconds = [int]($totalSeconds % 60)
    $minutesText = $minutes.ToString().PadLeft(2, '0')
    $secondsText = $seconds.ToString().PadLeft(2, '0')

    if ($hours -gt 0) {
        return "$hours`:$minutesText`:$secondsText"
    }

    return "$minutesText`:$secondsText"
}

function Build-GeminiPrompt {
    param(
        [string]$TranscriptText,
        [string]$PlayheadTime,
        [string]$UserInput
    )

    return @"
Full transcript with playhead times:
$TranscriptText

Current playhead time: $PlayheadTime

User input: $UserInput
"@
}

function Send-CdpCommand {
    param(
        [System.Net.WebSockets.ClientWebSocket]$WebSocket,
        [Threading.CancellationTokenSource]$CancellationSource,
        [int]$Id,
        [string]$Method,
        [hashtable]$Params = @{}
    )

    $payload = @{
        id = $Id
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 30 -Compress

    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
    $WebSocket.SendAsync(
        [ArraySegment[byte]]::new($bytes),
        [System.Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        $CancellationSource.Token
    ).GetAwaiter().GetResult() | Out-Null

    while ($true) {
        $buffer = New-Object byte[] 65536
        $stream = [System.IO.MemoryStream]::new()

        do {
            $result = $WebSocket.ReceiveAsync(
                [ArraySegment[byte]]::new($buffer),
                $CancellationSource.Token
            ).GetAwaiter().GetResult()

            if ($result.MessageType -eq [System.Net.WebSockets.WebSocketMessageType]::Close) {
                throw "Chrome closed the CDP WebSocket connection."
            }

            if ($result.Count -gt 0) {
                $stream.Write($buffer, 0, $result.Count)
            }
        } while (-not $result.EndOfMessage)

        $json = [Text.Encoding]::UTF8.GetString($stream.ToArray())
        $stream.Dispose()

        try {
            $response = $json | ConvertFrom-Json -ErrorAction Stop
        } catch {
            continue
        }

        if ($response.id -ne $Id) {
            continue
        }

        if ($response.error) {
            throw "CDP error $($response.error.code): $($response.error.message)"
        }

        return $response
    }
}

function Invoke-YouTubeCdp {
    param(
        [string]$Method,
        [hashtable]$Params = @{}
    )

    $script:youtubeCdpId++
    return Send-CdpCommand -WebSocket $youtubeWs -CancellationSource $youtubeCts -Id $script:youtubeCdpId -Method $Method -Params $Params
}

function Invoke-GeminiCdp {
    param(
        [string]$Method,
        [hashtable]$Params = @{}
    )

    $script:geminiCdpId++
    return Send-CdpCommand -WebSocket $geminiWs -CancellationSource $geminiCts -Id $script:geminiCdpId -Method $Method -Params $Params
}

function Close-WebSocketSafely {
    param($WebSocket, $CancellationSource)

    try {
        if ($WebSocket -and $WebSocket.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $WebSocket.CloseAsync(
                [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                "Done",
                [Threading.CancellationToken]::None
            ).GetAwaiter().GetResult() | Out-Null
        }
    } catch {}

    try { if ($WebSocket) { $WebSocket.Dispose() } } catch {}
    try { if ($CancellationSource) { $CancellationSource.Dispose() } } catch {}
}

function Get-TranscriptData {
    $clickJs = @'
(() => {
    const button = document.querySelector('button[aria-label="Show transcript"]');
    if (!button) {
        return JSON.stringify({
            ok: false,
            error: "No transcript available for this video [transcript button not found on DOM]."
        });
    }

    button.click();
    return JSON.stringify({ ok: true });
})();
'@

    $clickResponse = Invoke-YouTubeCdp -Method "Runtime.evaluate" -Params @{
        expression = $clickJs
        returnByValue = $true
    }

    $clickValue = $clickResponse.result.result.value
    if ($clickValue) {
        $clickData = $clickValue | ConvertFrom-Json
        if (-not $clickData.ok) {
            throw $clickData.error
        }
    }

    $lastCount = -1
    $stableChecks = 0
    $maxChecks = 30

    for ($i = 0; $i -lt $maxChecks; $i++) {
        $checkJs = @'
(() => {
    const segments = document.querySelectorAll("transcript-segment-view-model");
    return segments.length;
})();
'@

        $checkResponse = Invoke-YouTubeCdp -Method "Runtime.evaluate" -Params @{
            expression = $checkJs
            returnByValue = $true
        }

        $count = [int]$checkResponse.result.result.value
        if ($count -eq $lastCount -and $count -gt 0) {
            $stableChecks++
        } else {
            $stableChecks = 0
        }

        if ($stableChecks -ge 3) {
            break
        }

        $lastCount = $count
        Start-Sleep -Milliseconds 250
    }

    if ($lastCount -le 0) {
        throw "Transcript never loaded."
    }

    $transcriptJs = @'
(() => {
    const searchPlaceholder = [...document.querySelectorAll("div")].find(el =>
        el.classList.contains("ytStandardsTextareaShapePlaceholder") &&
        el.textContent.trim() === "Search transcript"
    );

    if (!searchPlaceholder) {
        return JSON.stringify({
            ok: false,
            error: "Search transcript element not found."
        });
    }

    let transcriptPanel = searchPlaceholder.parentElement;
    while (transcriptPanel && transcriptPanel !== document.body) {
        if (transcriptPanel.querySelector("transcript-segment-view-model")) {
            break;
        }
        transcriptPanel = transcriptPanel.parentElement;
    }

    if (!transcriptPanel || transcriptPanel === document.body) {
        return JSON.stringify({
            ok: false,
            error: "Transcript panel not found."
        });
    }

    const segments = [...transcriptPanel.querySelectorAll("transcript-segment-view-model")];
    if (!segments.length) {
        return JSON.stringify({
            ok: false,
            error: "No transcript segments found."
        });
    }

    const lines = segments.map(segment => {
        const timestamp = segment.querySelector(".ytwTranscriptSegmentViewModelTimestamp")?.textContent?.trim() || "";
        const text = segment.querySelector('span[role="text"]')?.textContent?.trim() || "";
        return { timestamp, text };
    }).filter(x => x.text);

    return JSON.stringify({
        ok: true,
        title: document.title.replace(" - YouTube", ""),
        count: lines.length,
        lines
    });
})();
'@

    $response = Invoke-YouTubeCdp -Method "Runtime.evaluate" -Params @{
        expression = $transcriptJs
        returnByValue = $true
    }

    $value = $response.result.result.value
    if (-not $value) {
        throw "No result returned from Chrome."
    }

    $data = $value | ConvertFrom-Json
    if (-not $data.ok) {
        throw $data.error
    }

    return $data
}

function Get-CurrentPlayheadTime {
    $playheadJs = @'
(() => {
    const video = document.querySelector("video");
    if (!video) {
        return JSON.stringify({
            ok: false,
            error: "YouTube video element not found."
        });
    }

    const currentTime = Number(video.currentTime);
    if (!Number.isFinite(currentTime)) {
        return JSON.stringify({
            ok: false,
            error: "Current playhead time is not available."
        });
    }

    return JSON.stringify({
        ok: true,
        currentTime
    });
})();
'@

    $response = Invoke-YouTubeCdp -Method "Runtime.evaluate" -Params @{
        expression = $playheadJs
        returnByValue = $true
    }

    $value = $response.result.result.value
    if (-not $value) {
        throw "No playhead result returned from Chrome."
    }

    $data = $value | ConvertFrom-Json
    if (-not $data.ok) {
        throw $data.error
    }

    return (Format-PlayheadTime -Seconds ([double]$data.currentTime))
}

function Invoke-GeminiResponse {
    param([string]$Prompt)

    $newTabUrl = "http://127.0.0.1:$cdpPort/json/new?" + [Uri]::EscapeDataString($geminiUrl)
    $tab = Invoke-RestMethod -Uri $newTabUrl -Method Put -ErrorAction Stop

    $script:geminiWs = [System.Net.WebSockets.ClientWebSocket]::new()
    $script:geminiCts = [Threading.CancellationTokenSource]::new()
    $geminiWs.ConnectAsync([Uri]$tab.webSocketDebuggerUrl, $geminiCts.Token).GetAwaiter().GetResult() | Out-Null

    Invoke-GeminiCdp "Page.enable" | Out-Null
    Invoke-GeminiCdp "Page.navigate" @{ url = $geminiUrl } | Out-Null

    for ($i = 0; $i -lt 20; $i++) {
        try {
            Invoke-GeminiCdp "Runtime.enable" | Out-Null
            break
        } catch {
            if ($_.Exception.Message -notmatch "Cannot find default execution context|Execution context was destroyed") {
                throw
            }
            Start-Sleep -Milliseconds 250
        }
    }

    for ($i = 0; $i -lt 80; $i++) {
        try {
            $state = Invoke-GeminiCdp "Runtime.evaluate" @{
                expression = "document.readyState"
                returnByValue = $true
            }
            if ($state.result.result.value -eq "complete") {
                break
            }
        } catch {
            if ($_.Exception.Message -notmatch "Cannot find default execution context|Execution context was destroyed") {
                throw
            }
        }
        Start-Sleep -Milliseconds 250
    }

    $requestJson = $Prompt | ConvertTo-Json -Compress
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

    $result = Invoke-GeminiCdp "Runtime.evaluate" @{
        expression = $js
        returnByValue = $true
        awaitPromise = $true
    }

    if ($result.result.exceptionDetails) {
        $details = $result.result.exceptionDetails
        if ($details.exception.description) {
            throw $details.exception.description
        }
        throw $details.text
    }

    $data = $result.result.result.value
    if (-not $data.success) {
        throw $data.error
    }

    return $data.text
}

function Find-ActiveYoutubeTab {
    param([object[]]$Tabs)

    $youtubeTabs = @($Tabs | Where-Object {
        $_.type -eq "page" -and $_.url -like "https://www.youtube.com/watch*"
    })

    $tab = $youtubeTabs | Where-Object { $_.active } | Select-Object -First 1
    if ($tab) {
        return $tab
    }

    foreach ($candidate in $youtubeTabs) {
        $probeWs = [System.Net.WebSockets.ClientWebSocket]::new()
        $probeCts = [Threading.CancellationTokenSource]::new()
        try {
            $probeWs.ConnectAsync([Uri]$candidate.webSocketDebuggerUrl, $probeCts.Token).GetAwaiter().GetResult() | Out-Null
            $probe = Send-CdpCommand -WebSocket $probeWs -CancellationSource $probeCts -Id 1 -Method "Runtime.evaluate" -Params @{
                expression = "document.hasFocus() && document.visibilityState === 'visible'"
                returnByValue = $true
            }
            if ($probe.result.result.value -eq $true) {
                return $candidate
            }
        } catch {
            continue
        } finally {
            Close-WebSocketSafely -WebSocket $probeWs -CancellationSource $probeCts
        }
    }

    return $youtubeTabs | Select-Object -First 1
}

try {
    if ($TestMode) {
        $sampleTranscript = @(
            "[00:00] Intro",
            "[00:12] Main idea",
            "[00:34] Closing thought"
        ) -join [Environment]::NewLine
        $samplePrompt = Build-GeminiPrompt -TranscriptText $sampleTranscript -PlayheadTime "00:34" -UserInput "Explain the main idea."
        Write-Host $samplePrompt
        exit 0
    }

    $userInput = Read-Host "Enter your request"
    if ([string]::IsNullOrWhiteSpace($userInput)) {
        Write-Host "No request entered."
        exit 1
    }

    $tabs = Invoke-RestMethod "http://127.0.0.1:$cdpPort/json"
    $youtubeTab = Find-ActiveYoutubeTab -Tabs $tabs

    if (-not $youtubeTab) {
        Write-Host "No YouTube video tab found."
        exit 1
    }

    $youtubeWs = [System.Net.WebSockets.ClientWebSocket]::new()
    $youtubeCts = [Threading.CancellationTokenSource]::new()
    $youtubeWs.ConnectAsync([Uri]$youtubeTab.webSocketDebuggerUrl, $youtubeCts.Token).GetAwaiter().GetResult() | Out-Null

    $playheadTime = Get-CurrentPlayheadTime
    $transcriptData = Get-TranscriptData
    $transcriptText = ($transcriptData.lines | ForEach-Object {
        "[$($_.timestamp)] $($_.text)"
    }) -join [Environment]::NewLine

    $prompt = Build-GeminiPrompt -TranscriptText $transcriptText -PlayheadTime $playheadTime -UserInput "$($userInput.Trim()) - summarize in once sentence if needed. Only return the summery."
    $responseText = Invoke-GeminiResponse -Prompt $prompt

    Write-Host ""
    Write-Host "Gemini response:"
    Write-Host ""
    Write-Host $responseText
}
catch {
    Write-Host ""
    Write-Host "ERROR:"
    Write-Host $_.Exception.Message
}
finally {
    Close-WebSocketSafely -WebSocket $youtubeWs -CancellationSource $youtubeCts
    Close-WebSocketSafely -WebSocket $geminiWs -CancellationSource $geminiCts
}
