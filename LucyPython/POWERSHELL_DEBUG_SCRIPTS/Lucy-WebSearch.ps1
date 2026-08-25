
#############################

$cdpHost = "127.0.0.1"
$cdpPort = 9223

$searchTerm = Read-Host "Enter Google search term"

if ([string]::IsNullOrWhiteSpace($searchTerm)) {
    Write-Host "No search term entered."
    exit
}

$encodedSearch = [System.Uri]::EscapeDataString($searchTerm)
$googleUrl = "https://www.google.com/search?q=$encodedSearch"

Write-Host "`nOpening new Google tab..."

try {
    $newTabUrl =
        "http://${cdpHost}:${cdpPort}/json/new?" +
        [System.Uri]::EscapeDataString($googleUrl)

    $tab = Invoke-RestMethod `
        -Uri $newTabUrl `
        -Method Put `
        -ErrorAction Stop
}
catch {
    Write-Host "Failed to create Chrome tab."
    Write-Host $_.Exception.Message
    exit
}

$wsUrl = $tab.webSocketDebuggerUrl

if (-not $wsUrl) {
    Write-Host "Could not get WebSocket debugger URL."
    exit
}

Write-Host "Connected to:"
Write-Host $tab.url

$ws = [System.Net.WebSockets.ClientWebSocket]::new()
$cts = [System.Threading.CancellationTokenSource]::new()

try {
    $ws.ConnectAsync(
        [Uri]$wsUrl,
        $cts.Token
    ).GetAwaiter().GetResult() | Out-Null
}
catch {
    Write-Host "Failed to connect to CDP WebSocket."
    Write-Host $_.Exception.Message

    $ws.Dispose()
    $cts.Dispose()
    exit
}

if ($ws.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
    Write-Host "WebSocket did not open correctly."
    Write-Host "State: $($ws.State)"

    $ws.Dispose()
    $cts.Dispose()
    exit
}

$script:cdpId = 0

function Send-CDP {
    param (
        [string]$Method,
        [hashtable]$Params = @{}
    )

    if ($ws.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
        throw "CDP WebSocket is not open. Current state: $($ws.State)"
    }

    $script:cdpId++
    $id = $script:cdpId

    $message = @{
        id     = $id
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 50 -Compress

    $bytes = [System.Text.Encoding]::UTF8.GetBytes($message)
    $segment = [System.ArraySegment[byte]]::new($bytes)

    try {
        $ws.SendAsync(
            $segment,
            [System.Net.WebSockets.WebSocketMessageType]::Text,
            $true,
            $cts.Token
        ).GetAwaiter().GetResult() | Out-Null
    }
    catch {
        throw "CDP send failed: $($_.Exception.Message)"
    }

    while ($true) {
        if ($ws.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
            throw "CDP WebSocket closed while waiting for response. State: $($ws.State)"
        }

        $buffer = New-Object byte[] 65536
        $memory = [System.IO.MemoryStream]::new()

        try {
            do {
                if ($ws.State -ne [System.Net.WebSockets.WebSocketState]::Open) {
                    throw "WebSocket became unavailable. State: $($ws.State)"
                }

                $segment = [System.ArraySegment[byte]]::new($buffer)

                try {
                    $result = $ws.ReceiveAsync(
                        $segment,
                        $cts.Token
                    ).GetAwaiter().GetResult()
                }
                catch {
                    throw "CDP receive failed: $($_.Exception.Message)"
                }

                if (
                    $result.MessageType -eq
                    [System.Net.WebSockets.WebSocketMessageType]::Close
                ) {
                    throw "Chrome closed the CDP WebSocket connection."
                }

                if ($result.Count -gt 0) {
                    $memory.Write(
                        $buffer,
                        0,
                        $result.Count
                    )
                }

            } while (-not $result.EndOfMessage)

            $json = [System.Text.Encoding]::UTF8.GetString(
                $memory.ToArray()
            )
        }
        finally {
            if ($memory) {
                $memory.Dispose()
            }
        }

        if ([string]::IsNullOrWhiteSpace($json)) {
            continue
        }

        try {
            $response = $json | ConvertFrom-Json -ErrorAction Stop
        }
        catch {
            continue
        }

        if ($null -eq $response.id) {
            continue
        }

        if ($response.id -ne $id) {
            continue
        }

        if ($response.error) {
            throw "CDP error $($response.error.code): $($response.error.message)"
        }

        return $response
    }
}

function Close-CDP {
    try {
        if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
            $ws.CloseAsync(
                [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                "Done",
                [System.Threading.CancellationToken]::None
            ).GetAwaiter().GetResult() | Out-Null
        }
    }
    catch {}

    try {
        $ws.Dispose()
    }
    catch {}

    try {
        $cts.Dispose()
    }
    catch {}
}

try {

    Send-CDP "Page.enable" | Out-Null
    Send-CDP "Runtime.enable" | Out-Null

    Write-Host "Waiting for Google results..."

    $pageLoaded = $false

    for ($i = 0; $i -lt 80; $i++) {

        $response = Send-CDP "Runtime.evaluate" @{
            expression    = "document.readyState"
            returnByValue = $true
        }

        $state = $response.result.result.value

        if ($state -eq "complete") {
            $pageLoaded = $true
            break
        }

        Start-Sleep -Milliseconds 250
    }

    if (-not $pageLoaded) {
        Write-Host "Page load timeout."
        exit
    }

    # ============================================================
    # WAIT FOR RATING BUTTONS
    # ============================================================

    Write-Host "Waiting for rating buttons..."

    $ratingButtonsReady = $false

    for ($i = 0; $i -lt 10; $i++) {

        $check = Send-CDP "Runtime.evaluate" @{
            expression = @'
(() => {
    const good = document.querySelector(
        '[aria-label="Good response"]'
    );

    const bad = document.querySelector(
        '[aria-label="Bad response"]'
    );

    return {
        good: !!good,
        bad: !!bad
    };
})()
'@
            returnByValue = $true
        }

        $result = $check.result.result.value

        if ($result.good -and $result.bad) {
            $ratingButtonsReady = $true
            break
        }

        Start-Sleep -Milliseconds 500
    }

    if (-not $ratingButtonsReady) {
        Write-Host "Rating buttons not found after waiting."
        exit
    }

    Write-Host "Rating buttons found."
    Write-Host "Extracting AI Overview...`n"

    $js = @'
(() => {

    try {

        const overview = document.querySelector(
            'div[jsname="cUzNTd"][role="heading"]'
        );

        const good = document.querySelector(
            '[aria-label="Good response"]'
        );

        const bad = document.querySelector(
            '[aria-label="Bad response"]'
        );

        if (!overview) {
            return {
                success: false,
                error: "AI Overview not found"
            };
        }

        if (!good || !bad) {
            return {
                success: false,
                error: "Rating buttons not found"
            };
        }

        let section = overview.parentElement;

        while (
            section &&
            (!section.contains(good) || !section.contains(bad))
        ) {
            section = section.parentElement;
        }

        if (!section) {
            return {
                success: false,
                error: "AI Overview section not found"
            };
        }

        const links = [];

        section.querySelectorAll(
            'a[href], button[data-amic="true"]'
        ).forEach(el => {

            if (el.tagName === "A") {

                links.push({
                    text: el.innerText?.trim() || "",
                    href: el.href,
                    ariaLabel: el.getAttribute("aria-label") || null
                });

            } else {

                const innerLink = el.querySelector("a[href]");

                links.push({
                    text: el.innerText?.trim() || "",
                    href: innerLink?.href || null,
                    ariaLabel: el.getAttribute("aria-label") || null
                });
            }
        });

        const uniqueLinks = links.filter(
            (item, index, arr) =>
                index === arr.findIndex(x =>
                    x.href === item.href &&
                    x.text === item.text
                )
        );

        const images = [];

        section.querySelectorAll("img").forEach(img => {

            const src = img.currentSrc || img.src;

            if (
                src &&
                img.naturalWidth >= 100 &&
                img.naturalHeight >= 100 &&
                !images.some(x => x.src === src)
            ) {

                images.push({
                    src: src,
                    width: img.naturalWidth,
                    height: img.naturalHeight,
                    alt: img.alt || ""
                });
            }
        });

        const firstFiveImages = images.slice(0, 5);

        const clone = section.cloneNode(true);

        clone.querySelectorAll(
            'a, button[data-amic="true"]'
        ).forEach(el => el.remove());

        clone.querySelectorAll(
            'img, svg, video, audio, iframe, script, style, noscript, template'
        ).forEach(el => el.remove());

        const garbageText = [
            ". Try again later.",
            "Show less",
            "Show all",
            "Share",
            "Click to copy link",
            "Link copied",
            "Your feedback helps Google improve",
            "See our Privacy Policy",
            "Report a problem",
            "An AI Overview is not available for this search",
            "Can't generate an AI overview right now",
            "AI Overview",
            "MicrophoneStopRetrySendSend",
            "Transcribing...",
            "Share link Your feedback helps Google improve",
            "About this response",
            "Save to Google Drive",
            "When you export, you will allow Google Search to save AI-powered information to your Google Drive.",
            "Got it",
            "Save to Gmail",
            "When you export, you will allow Google Search to save AI-powered information to your Gmail.",
            "Add files, tools, and select a model",
            "feedbackclose",
            "See our .",
            "more Thank you",
            "more feedback",
            "sendsend",
        ];

        const blockTags = new Set([
            "DIV",
            "P",
            "LI",
            "SECTION",
            "ARTICLE",
            "H1",
            "H2",
            "H3",
            "H4",
            "H5",
            "H6",
            "BR"
        ]);

        let text = "";

        function collectText(node) {
            if (node.nodeType === Node.TEXT_NODE) {
                const value = node.textContent
                    .replace(/\s+/g, " ")
                    .trim();

                if (value) {
                    text += value + " ";
                }

                return;
            }

            if (node.nodeType !== Node.ELEMENT_NODE) {
                return;
            }

            const isBlock = blockTags.has(node.tagName);

            if (
                isBlock &&
                text.length > 0 &&
                !text.endsWith("\n")
            ) {
                text += "\n";
            }

            node.childNodes.forEach(collectText);

            if (
                isBlock &&
                text.length > 0 &&
                !text.endsWith("\n")
            ) {
                text += "\n";
            }
        }

        collectText(clone);

        garbageText.forEach(garbage => {
            text = text.replace(new RegExp(garbage.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), "gi"), "");
        });


        // Clean spaces but PRESERVE line boundaries
        text = text
            .split("\n")
            .map(line =>
                line
                    .replace(/[ \t]+/g, " ")
                    .trim()
            )
            .filter(Boolean)
            .join("\n");

        return {
            success: true,
            text: text,
            images: firstFiveImages,
            links: uniqueLinks
        };

    }
    catch (err) {

        return {
            success: false,
            error: "JavaScript extraction error: " +
                (err?.message || String(err))
        };
    }

})()
'@

    $response = Send-CDP "Runtime.evaluate" @{
        expression    = $js
        returnByValue = $true
        awaitPromise  = $true
    }

    if ($response.result.exceptionDetails) {

        Write-Host "JavaScript execution failed."

        if ($response.result.exceptionDetails.exception.description) {
            Write-Host $response.result.exceptionDetails.exception.description
        }
        elseif ($response.result.exceptionDetails.text) {
            Write-Host $response.result.exceptionDetails.text
        }

        exit
    }

    $data = $response.result.result.value

    if (-not $data) {
        Write-Host "No data returned from AI Overview script."
        exit
    }

    if ($data.success -ne $true) {

        Write-Host ""

        switch ($data.error) {

            "AI Overview not found" {
                Write-Host "AI Overview not found"
            }

            "Rating buttons not found" {
                Write-Host "Rating buttons not found"
            }

            "AI Overview section not found" {
                Write-Host "AI Overview section not found"
            }

            default {
                Write-Host $data.error
            }
        }

        exit
    }

    Write-Host "============================================================"
    Write-Host "AI OVERVIEW"
    Write-Host "============================================================"
    Write-Host ""
    Write-Host $data.text

    
    Write-Host ""
    Write-Host "============================================================"
    Write-Host "FIRST 5 IMAGES"
    Write-Host "============================================================"

    if ($data.images -and $data.images.Count -gt 0) {

        $i = 1

        foreach ($img in $data.images) {

            Write-Host ""
            Write-Host "Image $i ($($img.width)x$($img.height))"

            if ($img.alt) {
                Write-Host "Alt: $($img.alt)"
            }

            Write-Host $img.src

            $i++
        }

    }
    else {
        Write-Host "No images found."
    }

    

    Write-Host ""
    Write-Host "============================================================"
    Write-Host "LINKS / SOURCES"
    Write-Host "============================================================"
    Write-Host ""

    if ($data.links -and $data.links.Count -gt 0) {

        $data.links |
            Select-Object text, href, ariaLabel |
            Format-Table -AutoSize -Wrap

    }
    else {
        Write-Host "No links/sources found."
    }

    
}
catch {

    Write-Host ""
    Write-Host "ERROR:"
    Write-Host $_.Exception.Message

    if ($ws) {
        Write-Host "WebSocket state: $($ws.State)"
    }
}
finally {

    Close-CDP
}