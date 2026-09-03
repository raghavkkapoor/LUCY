#############################

$needsStaRestart = [Threading.Thread]::CurrentThread.ApartmentState -ne 'STA'
if ($needsStaRestart -and -not $env:LUCY_OPEN_GOOGLE_IMAGES_RELAUNCHED) {
    $env:LUCY_OPEN_GOOGLE_IMAGES_RELAUNCHED = '1'
    $hostExe = (Get-Process -Id $PID).Path

    Start-Process -FilePath $hostExe -ArgumentList @(
        '-NoProfile'
        '-Sta'
        '-ExecutionPolicy'
        'Bypass'
        '-File'
        $PSCommandPath
    ) -WindowStyle Hidden | Out-Null

    exit
}

Remove-Item Env:LUCY_OPEN_GOOGLE_IMAGES_RELAUNCHED -ErrorAction SilentlyContinue

$cdpHost = "127.0.0.1"
$cdpPort = 9223
$minimumImages = 3
$maxImagesToOpen = 3

function Test-CDPPort {
    try {
        Invoke-RestMethod `
            -Uri "http://${cdpHost}:${cdpPort}/json/version" `
            -TimeoutSec 2 `
            -ErrorAction Stop |
            Out-Null

        return $true
    }
    catch {
        return $false
    }
}

function Get-ChromePath {
    return @(
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    ) |
        Where-Object { Test-Path $_ } |
        Select-Object -First 1
}

function Ensure-CDPChrome {
    if (Test-CDPPort) {
        return
    }

    $chrome = Get-ChromePath

    if (-not $chrome) {
        throw "Chrome was not found, and CDP port $cdpPort is not already running."
    }

    $profileDir = Join-Path $env:TEMP "lucy-google-images-cdp-profile"
    New-Item -ItemType Directory -Force -Path $profileDir | Out-Null

    Write-Host "CDP port $cdpPort is not running. Starting Chrome..."

    Start-Process -FilePath $chrome -ArgumentList @(
        "--remote-debugging-port=$cdpPort",
        "--user-data-dir=$profileDir",
        "--new-window",
        "about:blank"
    ) | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        if (Test-CDPPort) {
            return
        }

        Start-Sleep -Milliseconds 250
    }

    throw "Chrome started, but CDP port $cdpPort did not become available."
}

$searchTerm = Read-Host "Enter Google image search term"

if ([string]::IsNullOrWhiteSpace($searchTerm)) {
    Write-Host "No search term entered."
    exit
}

$encodedSearch = [System.Uri]::EscapeDataString($searchTerm.Trim())
$googleUrl = "https://www.google.com/search?tbm=isch&safe=active&q=$encodedSearch"

Ensure-CDPChrome

Write-Host "`nOpening Google Images search..."

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
    Write-Host "Failed to create Chrome tab on CDP port $cdpPort."
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

function New-SolidBrush {
    param(
        [byte]$Red,
        [byte]$Green,
        [byte]$Blue
    )

    $brush = New-Object System.Windows.Media.SolidColorBrush (
        [System.Windows.Media.Color]::FromRgb($Red, $Green, $Blue)
    )
    $brush.Freeze()
    return $brush
}

function Show-ImageStripWindow {
    param(
        [Parameter(Mandatory = $true)]
        [array]$Images,

        [int]$DurationSeconds = 8
    )

    Add-Type -AssemblyName PresentationFramework, PresentationCore, WindowsBase

    [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12

    $window = New-Object System.Windows.Window
    $window.Title = "Google Images"
    $window.Width = 1500
    $window.Height = 760
    $window.WindowStartupLocation = 'CenterScreen'
    $window.ResizeMode = 'NoResize'
    $window.Topmost = $true
    $window.Background = [System.Windows.Media.Brushes]::Black

    $root = New-Object System.Windows.Controls.Border
    $root.Margin = New-Object System.Windows.Thickness 16
    $root.Padding = New-Object System.Windows.Thickness 16
    $root.CornerRadius = New-Object System.Windows.CornerRadius 18
    $root.Background = New-SolidBrush 24 24 24
    $root.BorderBrush = New-SolidBrush 60 60 60
    $root.BorderThickness = New-Object System.Windows.Thickness 1

    $layout = New-Object System.Windows.Controls.Grid

    $headerRow = New-Object System.Windows.Controls.RowDefinition
    $headerRow.Height = [System.Windows.GridLength]::Auto
    $contentRow = New-Object System.Windows.Controls.RowDefinition
    $contentRow.Height = [System.Windows.GridLength]::new(1, [System.Windows.GridUnitType]::Star)
    $layout.RowDefinitions.Add($headerRow) | Out-Null
    $layout.RowDefinitions.Add($contentRow) | Out-Null

    $header = New-Object System.Windows.Controls.DockPanel
    $header.Margin = New-Object System.Windows.Thickness 0,0,0,14

    $title = New-Object System.Windows.Controls.TextBlock
    $title.Text = "Google Images"
    $title.Foreground = [System.Windows.Media.Brushes]::White
    $title.FontSize = 22
    $title.FontWeight = 'SemiBold'
    $title.VerticalAlignment = 'Center'
    [System.Windows.Controls.DockPanel]::SetDock($title, 'Left')

    $closeButton = New-Object System.Windows.Controls.Button
    $closeButton.Content = "Close"
    $closeButton.Width = 92
    $closeButton.Height = 34
    $closeButton.FontWeight = 'SemiBold'
    $closeButton.Background = New-SolidBrush 230 230 230
    $closeButton.Foreground = [System.Windows.Media.Brushes]::Black
    $closeButton.HorizontalAlignment = 'Right'
    [System.Windows.Controls.DockPanel]::SetDock($closeButton, 'Right')

    $countdown = New-Object System.Windows.Controls.TextBlock
    $countdown.Text = "Auto-closing in $DurationSeconds seconds"
    $countdown.Foreground = New-SolidBrush 180 180 180
    $countdown.Margin = New-Object System.Windows.Thickness 12,0,0,0
    $countdown.VerticalAlignment = 'Center'

    $header.Children.Add($title) | Out-Null
    $header.Children.Add($closeButton) | Out-Null
    $header.Children.Add($countdown) | Out-Null

    $imageGrid = New-Object System.Windows.Controls.Grid
    $imageGrid.Margin = New-Object System.Windows.Thickness 0

    1..3 | ForEach-Object {
        $null = $imageGrid.ColumnDefinitions.Add((New-Object System.Windows.Controls.ColumnDefinition))
    }

    $displayImages = @($Images | Select-Object -First 3)

    for ($i = 0; $i -lt $displayImages.Count; $i++) {
        $item = $displayImages[$i]

        $frame = New-Object System.Windows.Controls.Border
        $frame.Margin = New-Object System.Windows.Thickness 8
        $frame.CornerRadius = New-Object System.Windows.CornerRadius 16
        $frame.Background = [System.Windows.Media.Brushes]::Black
        $frame.BorderBrush = New-SolidBrush 70 70 70
        $frame.BorderThickness = New-Object System.Windows.Thickness 1
        $frame.ClipToBounds = $true

        $img = New-Object System.Windows.Controls.Image
        $img.Stretch = 'Uniform'
        $img.HorizontalAlignment = 'Center'
        $img.VerticalAlignment = 'Center'
        $img.SnapsToDevicePixels = $true

        try {
            $webClient = New-Object System.Net.WebClient
            $webClient.Headers[[System.Net.HttpRequestHeader]::UserAgent] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36'
            $webClient.Headers[[System.Net.HttpRequestHeader]::Referer] = 'https://www.google.com/'
            $imageBytes = $webClient.DownloadData([string]$item.url)
            $webClient.Dispose()

            $imageStream = New-Object System.IO.MemoryStream(,$imageBytes)
            $bitmap = New-Object System.Windows.Media.Imaging.BitmapImage
            $bitmap.BeginInit()
            $bitmap.CacheOption = [System.Windows.Media.Imaging.BitmapCacheOption]::OnLoad
            $bitmap.StreamSource = $imageStream
            $bitmap.EndInit()
            $bitmap.Freeze()
            $imageStream.Dispose()
            $img.Source = $bitmap
        }
        catch {
            $fallback = New-Object System.Windows.Controls.TextBlock
            $fallback.Text = "Image unavailable"
            $fallback.Foreground = [System.Windows.Media.Brushes]::White
            $fallback.HorizontalAlignment = 'Center'
            $fallback.VerticalAlignment = 'Center'
            $frame.Child = $fallback
            [System.Windows.Controls.Grid]::SetColumn($frame, $i)
            $imageGrid.Children.Add($frame) | Out-Null
            continue
        }

        $frame.Child = $img
        [System.Windows.Controls.Grid]::SetColumn($frame, $i)
        $imageGrid.Children.Add($frame) | Out-Null
    }

    for ($i = $displayImages.Count; $i -lt 3; $i++) {
        $placeholder = New-Object System.Windows.Controls.Border
        $placeholder.Margin = New-Object System.Windows.Thickness 8
        $placeholder.CornerRadius = New-Object System.Windows.CornerRadius 16
        $placeholder.Background = [System.Windows.Media.Brushes]::Black
        $placeholder.BorderBrush = New-SolidBrush 70 70 70
        $placeholder.BorderThickness = New-Object System.Windows.Thickness 1

        $text = New-Object System.Windows.Controls.TextBlock
        $text.Text = "Missing image"
        $text.Foreground = New-SolidBrush 180 180 180
        $text.HorizontalAlignment = 'Center'
        $text.VerticalAlignment = 'Center'

        $placeholder.Child = $text
        [System.Windows.Controls.Grid]::SetColumn($placeholder, $i)
        $imageGrid.Children.Add($placeholder) | Out-Null
    }

    [System.Windows.Controls.Grid]::SetRow($header, 0)
    [System.Windows.Controls.Grid]::SetRow($imageGrid, 1)
    $layout.Children.Add($header) | Out-Null
    $layout.Children.Add($imageGrid) | Out-Null
    $root.Child = $layout
    $window.Content = $root

    $timer = New-Object System.Windows.Threading.DispatcherTimer
    $timer.Interval = [TimeSpan]::FromSeconds($DurationSeconds)
    $timer.Add_Tick({
        $timer.Stop()
        $window.Close()
    })

    $closeButton.Add_Click({
        $timer.Stop()
        $window.Close()
    })

    $window.Add_Closed({
        if ($timer.IsEnabled) {
            $timer.Stop()
        }
    })

    $timer.Start()
    $null = $window.ShowDialog()
}

function Invoke-RuntimeEvaluateWithRetry {
    param (
        [string]$Expression,
        [bool]$AwaitPromise = $false,
        [int]$Retries = 40,
        [int]$DelayMilliseconds = 250
    )

    $lastError = $null

    for ($i = 0; $i -lt $Retries; $i++) {
        try {
            return Send-CDP "Runtime.evaluate" @{
                expression    = $Expression
                returnByValue = $true
                awaitPromise  = $AwaitPromise
            }
        }
        catch {
            $lastError = $_.Exception.Message

            if (
                $lastError -notmatch "Cannot find default execution context" -and
                $lastError -notmatch "Execution context was destroyed" -and
                $lastError -notmatch "Inspected target navigated or closed"
            ) {
                throw
            }

            Start-Sleep -Milliseconds $DelayMilliseconds
        }
    }

    throw "Runtime.evaluate did not become available. Last error: $lastError"
}

try {
    Send-CDP "Page.enable" | Out-Null
    Send-CDP "Runtime.enable" | Out-Null

    Write-Host "Waiting for Google Images..."

    $pageLoaded = $false

    for ($i = 0; $i -lt 80; $i++) {
        try {
            $response = Invoke-RuntimeEvaluateWithRetry `
                -Expression "document.readyState" `
                -Retries 3 `
                -DelayMilliseconds 250
        }
        catch {
            Start-Sleep -Milliseconds 250
            continue
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

    Write-Host "Finding image result URLs..."

    $js = @'
(async () => {
    const needed = 3;
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

    function cleanText(value) {
        return (value || "").replace(/\s+/g, " ").trim();
    }

    function normalizeUrl(value) {
        if (!value) {
            return null;
        }

        try {
            const url = new URL(value, location.href);
            return url.href;
        }
        catch {
            return null;
        }
    }

    function fromGoogleImageResultHref(href) {
        const normalized = normalizeUrl(href);
        if (!normalized) {
            return null;
        }

        try {
            const url = new URL(normalized);
            const imageUrl =
                url.searchParams.get("imgurl") ||
                url.searchParams.get("mediaurl") ||
                url.searchParams.get("url");

            if (imageUrl && /^https?:\/\//i.test(imageUrl)) {
                return imageUrl;
            }
        }
        catch {}

        return null;
    }

    function usableImageUrl(src) {
        const normalized = normalizeUrl(src);
        if (!normalized || !/^https?:\/\//i.test(normalized)) {
            return null;
        }

        if (/google\.com\/logos|gstatic\.com\/images\/branding/i.test(normalized)) {
            return null;
        }

        return normalized;
    }

    function addUnique(results, item) {
        if (!item || !item.url || results.some(existing => existing.url === item.url)) {
            return;
        }

        results.push(item);
    }

    function collectResults() {
        const results = [];

        document.querySelectorAll('a[href*="/imgres"], a[href*="imgurl="]').forEach(anchor => {
            const url = fromGoogleImageResultHref(anchor.href);
            if (!url) {
                return;
            }

            const img = anchor.querySelector("img");
            addUnique(results, {
                url,
                title: cleanText(anchor.getAttribute("aria-label") || img?.alt || anchor.innerText),
                source: "imgres"
            });
        });

        document.querySelectorAll("img").forEach(img => {
            const box = img.getBoundingClientRect();
            const src = usableImageUrl(img.currentSrc || img.src);

            if (!src || box.width < 120 || box.height < 90) {
                return;
            }

            addUnique(results, {
                url: src,
                title: cleanText(img.alt),
                source: "thumbnail"
            });
        });

        return results;
    }

    let results = [];

    for (let attempt = 0; attempt < 6; attempt++) {
        results = collectResults();

        if (results.length >= needed) {
            break;
        }

        window.scrollBy(0, Math.max(window.innerHeight, 900));
        await sleep(900);
    }

    return {
        success: results.length >= needed,
        count: results.length,
        images: results.slice(0, 10),
        error: results.length >= needed
            ? null
            : `Only found ${results.length} usable image URLs.`
    };
})()
'@

    $response = Invoke-RuntimeEvaluateWithRetry `
        -Expression $js `
        -AwaitPromise $true `
        -Retries 40 `
        -DelayMilliseconds 250

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
        Write-Host "No data returned from image extraction script."
        exit
    }

    if ($data.success -ne $true) {
        Write-Host $data.error
        exit
    }

    $imagesToOpen = @($data.images | Select-Object -First $maxImagesToOpen)

    if ($imagesToOpen.Count -lt $minimumImages) {
        Write-Host "Expected at least $minimumImages images, but only found $($imagesToOpen.Count)."
        exit
    }

    Write-Host ""
    Write-Host "Showing $($imagesToOpen.Count) images..."
    Write-Host ""

    Show-ImageStripWindow -Images $imagesToOpen -DurationSeconds 8

    Write-Host "Done."
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
