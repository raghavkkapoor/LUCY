param(
    [Parameter(Mandatory)]
    [string]$Name,
    [string]$Id,
    [string]$Url
)

$ErrorActionPreference = "Stop"

# ------------------------------------------------------------
# GET LUCY CHROME STATE
# ------------------------------------------------------------

$StateFile = "$env:LOCALAPPDATA\Lucy\chrome_state.json"

if (-not (Test-Path $StateFile)) {
    throw "Lucy Chrome state not found. Run Manage-LucyChrome.ps1 first."
}

$state = Get-Content $StateFile -Raw | ConvertFrom-Json
$port  = [int]$state.Port

# ------------------------------------------------------------
# GET ALL CHROME TABS
# ------------------------------------------------------------

$targets = Invoke-RestMethod "http://127.0.0.1:$port/json/list"

$pages = @(
    $targets | Where-Object {
        $_.type -eq "page" -and
        $_.webSocketDebuggerUrl
    }
)

if ($pages.Count -eq 0) {
    throw "No Chrome pages found."
}

# ------------------------------------------------------------
# FIND TARGET
# ------------------------------------------------------------

$target = $null

if ($Id) {

    $target = $pages |
        Where-Object { $_.id -eq $Id } |
        Select-Object -First 1
}
elseif ($Url) {

    $target = $pages |
        Where-Object { $_.url -like "*$Url*" } |
        Select-Object -First 1
}
elseif ($Name) {

    $query = $Name.ToLowerInvariant()

    $matches = foreach ($page in $pages) {

        $title = ([string]$page.title).ToLowerInvariant()
        $pageUrl = ([string]$page.url).ToLowerInvariant()

        $score = 0

        if ($pageUrl.Contains($query)) {
            $score += 100
        }

        if ($title.Contains($query)) {
            $score += 80
        }

        foreach ($word in ($query -split '\s+')) {

            if ($word.Length -lt 2) {
                continue
            }

            if ($pageUrl.Contains($word)) {
                $score += 20
            }

            if ($title.Contains($word)) {
                $score += 15
            }
        }

        [PSCustomObject]@{
            Score  = $score
            Target = $page
        }
    }

    $best = $matches |
        Sort-Object Score -Descending |
        Select-Object -First 1

    if ($best -and $best.Score -gt 0) {
        $target = $best.Target
    }
}
else {
    throw "Use -Name, -Id, or -Url."
}

if (-not $target) {
    throw "Could not find matching Chrome page."
}

# ------------------------------------------------------------
# CONNECT TO TARGET USING CDP
# ------------------------------------------------------------

$wsUrl = [string]$target.webSocketDebuggerUrl

Write-Host ""
Write-Host "TARGET FOUND"
Write-Host "============"
Write-Host "TITLE: $($target.title)"
Write-Host "URL:   $($target.url)"
Write-Host "ID:    $($target.id)"
Write-Host ""

$ws = [System.Net.WebSockets.ClientWebSocket]::new()

$uri = [System.Uri]::new($wsUrl)

$ws.ConnectAsync(
    $uri,
    [Threading.CancellationToken]::None
).GetAwaiter().GetResult()

$script:CDP_ID = 0

function Send-CDP {

    param(
        [string]$Method,
        [hashtable]$Params = @{}
    )

    $script:CDP_ID++
    $requestId = $script:CDP_ID

    $request = @{
        id     = $requestId
        method = $Method
        params = $Params
    } | ConvertTo-Json -Depth 30 -Compress

    $bytes = [Text.Encoding]::UTF8.GetBytes($request)

    $ws.SendAsync(
        [ArraySegment[byte]]::new($bytes),
        [System.Net.WebSockets.WebSocketMessageType]::Text,
        $true,
        [Threading.CancellationToken]::None
    ).GetAwaiter().GetResult() | Out-Null

    while ($true) {

        $stream = [System.IO.MemoryStream]::new()

        do {
            $buffer = New-Object byte[] 65536

            $receive = $ws.ReceiveAsync(
                [ArraySegment[byte]]::new($buffer),
                [Threading.CancellationToken]::None
            ).GetAwaiter().GetResult()

            $stream.Write(
                $buffer,
                0,
                $receive.Count
            )

        } while (-not $receive.EndOfMessage)

        $json = [Text.Encoding]::UTF8.GetString(
            $stream.ToArray()
        )

        try {
            $obj = $json | ConvertFrom-Json
        }
        catch {
            continue
        }

        if ($obj.id -eq $requestId) {
            return $obj
        }
    }
}

# ------------------------------------------------------------
# ENABLE JAVASCRIPT RUNTIME
# ------------------------------------------------------------

Send-CDP "Runtime.enable" | Out-Null

# ------------------------------------------------------------
# READ PAGE
# ------------------------------------------------------------

$result = Send-CDP "Runtime.evaluate" @{
    expression = @'
(() => {

    function visible(el) {

        const rect = el.getBoundingClientRect();
        const style = getComputedStyle(el);

        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.display !== "none" &&
            style.visibility !== "hidden"
        );
    }

    const selector = `
        a,
        button,
        input,
        textarea,
        select,
        [role="button"],
        [role="link"],
        [role="textbox"],
        [role="checkbox"],
        [role="radio"],
        [role="menuitem"],
        [role="tab"],
        [role="option"],
        [contenteditable="true"]
    `;

    const elements =
        [...document.querySelectorAll(selector)]
        .filter(visible)
        .map((el, index) => {

            return {
                index: index,

                tag:
                    el.tagName.toLowerCase(),

                role:
                    el.getAttribute("role") || "",

                text:
                    (
                        el.innerText ||
                        el.value ||
                        ""
                    )
                    .trim()
                    .replace(/\s+/g, " "),

                aria:
                    el.getAttribute("aria-label") || "",

                placeholder:
                    el.getAttribute("placeholder") || "",

                type:
                    el.getAttribute("type") || ""
            };
        });

    return JSON.stringify({
        title: document.title,
        url: location.href,
        text: document.body
            ? document.body.innerText
            : "",
        elements: elements
    });

})()
'@

    returnByValue = $true
}

$data = $result.result.result.value | ConvertFrom-Json

# ------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------

Write-Host ""
Write-Host "PAGE CONTENT"
Write-Host "============"
Write-Host ""

Write-Host $data.text

Write-Host ""
Write-Host ""
Write-Host "INTERACTIVE ELEMENTS"
Write-Host "===================="
Write-Host ""

$data.elements |
    Select-Object `
        index,
        tag,
        role,
        text,
        aria,
        placeholder,
        type |
    Format-Table -Wrap -AutoSize