$cdpPort = 9223

# Get Chrome tabs
$tabs = Invoke-RestMethod "http://127.0.0.1:$cdpPort/json"

$youtubeTab = $tabs | Where-Object {
    $_.url -like "https://www.youtube.com/watch*"
} | Select-Object -First 1

if (-not $youtubeTab) {
    Write-Host "No YouTube video tab found."
    exit 1
}

$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$ct = [Threading.CancellationToken]::None

$ws.ConnectAsync(
    [Uri]$youtubeTab.webSocketDebuggerUrl,
    $ct
).Wait()

function Send-CDP {
    param(
        [int]$Id,
        [string]$Method,
        [hashtable]$Params = @{}
    )

    $payload = @{
        id     = $Id
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 20 -Compress

    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)

    $ws.SendAsync(
        [ArraySegment[byte]]::new($bytes),
        [System.Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        $ct
    ).Wait()

    while ($true) {

        $stream = [System.IO.MemoryStream]::new()

        do {
            $buffer = New-Object byte[] 16384

            $result = $ws.ReceiveAsync(
                [ArraySegment[byte]]::new($buffer),
                $ct
            ).Result

            $stream.Write(
                $buffer,
                0,
                $result.Count
            )

        } while (-not $result.EndOfMessage)

        $json = [Text.Encoding]::UTF8.GetString(
            $stream.ToArray()
        )

        $stream.Dispose()

        try {
            $response = $json | ConvertFrom-Json
        }
        catch {
            Write-Host "Failed to parse complete CDP message."
            continue
        }

        if ($response.id -eq $Id) {
            return $response
        }
    }
}

# --------------------------------------------------
# 1. Click "Show transcript"
# --------------------------------------------------

$clickJs = @'
(() => {

    const button = document.querySelector(
        'button[aria-label="Show transcript"]'
    );

    if (!button) {
        return JSON.stringify({
            ok: false,
            error: "No transcript available for this video [transcript button not found on DOM]."
        });
    }

    button.click();

    return JSON.stringify({
        ok: true
    });

})();
'@

$clickResponse = Send-CDP `
    -Id 1 `
    -Method "Runtime.evaluate" `
    -Params @{
        expression    = $clickJs
        returnByValue = $true
    }

$clickValue = $clickResponse.result.result.value

if ($clickValue) {
    $clickData = $clickValue | ConvertFrom-Json

    if (-not $clickData.ok) {
        Write-Host "Error: $($clickData.error)"
        $ws.Dispose()
        exit 1
    }
}

# Wait for transcript panel to render
# --------------------------------------------------
# Wait until transcript finishes loading
# --------------------------------------------------

$lastCount = -1
$stableChecks = 0
$maxChecks = 30

for ($i = 0; $i -lt $maxChecks; $i++) {

    $checkJs = @'
(() => {
    const segments = document.querySelectorAll(
        "transcript-segment-view-model"
    );

    return segments.length;
})();
'@

    $checkResponse = Send-CDP `
        -Id (100 + $i) `
        -Method "Runtime.evaluate" `
        -Params @{
            expression    = $checkJs
            returnByValue = $true
        }

    $count = $checkResponse.result.result.value

    Write-Host "Transcript segments loaded: $count"

    # Has the number stopped changing?
    if ($count -eq $lastCount -and $count -gt 0) {
        $stableChecks++
    }
    else {
        $stableChecks = 0
    }

    # Require it to be unchanged for 3 checks
    if ($stableChecks -ge 3) {
        Write-Host "Transcript finished loading."
        break
    }

    $lastCount = $count

    Start-Sleep -Milliseconds 250
}

if ($lastCount -le 0) {
    Write-Host "Error: Transcript never loaded."
    $ws.Dispose()
    exit 1
}

# LLLEND

# --------------------------------------------------
# 2. Fetch transcript
# --------------------------------------------------

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

    const segments = [
        ...transcriptPanel.querySelectorAll(
            "transcript-segment-view-model"
        )
    ];

    if (!segments.length) {
        return JSON.stringify({
            ok: false,
            error: "No transcript segments found."
        });
    }

    const lines = segments.map(segment => {

        const timestamp = segment.querySelector(
            ".ytwTranscriptSegmentViewModelTimestamp"
        )?.textContent?.trim() || "";

        const text = segment.querySelector(
            'span[role="text"]'
        )?.textContent?.trim() || "";

        return {
            timestamp,
            text
        };

    }).filter(x => x.text);

    return JSON.stringify({
        ok: true,
        title: document.title.replace(" - YouTube", ""),
        count: lines.length,
        lines
    });

})();
'@

$response = Send-CDP `
    -Id 2 `
    -Method "Runtime.evaluate" `
    -Params @{
        expression    = $transcriptJs
        returnByValue = $true
    }

$value = $response.result.result.value

if (-not $value) {
    Write-Host "No result returned from Chrome."
    $ws.Dispose()
    exit 1
}

$data = $value | ConvertFrom-Json

if (-not $data.ok) {
    Write-Host "Error: $($data.error)"
    $ws.Dispose()
    exit 1
}

Write-Host ""
Write-Host "Title: $($data.title)"
Write-Host "Segments: $($data.count)"
Write-Host "----------------------------------------"

foreach ($line in $data.lines) {
    Write-Host "[$($line.timestamp)] $($line.text)"
}

$ws.Dispose()

# LLLEND