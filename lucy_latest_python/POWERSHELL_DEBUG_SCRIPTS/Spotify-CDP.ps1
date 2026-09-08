# ============================================================
# SPOTIFY CDP CONTROLLER
# Spotify remote debugging port: 9222
# ============================================================

$script:SpotifyCDPPort = 9222
$script:SpotifyCDPBase = "http://127.0.0.1:$($script:SpotifyCDPPort)"
$script:SpotifyTargetWebSocket = $null
$script:SpotifyCDPRetrying = $false

# ============================================================
# PROCESS / CDP SESSION
# ============================================================
    
function Get-SpotifyExecutable {
    $p = Get-Process Spotify -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($p) {
        try {
            if ($p.Path -and (Test-Path $p.Path)) { return $p.Path }
        } catch {}
    }

    $candidates = @(
        "$env:APPDATA\Spotify\Spotify.exe",
        "$env:LOCALAPPDATA\Microsoft\WindowsApps\Spotify.exe"
    )

    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }

    Write-Host "Spotify process not found." -ForegroundColor Red
}

function Test-SpotifyCDP {
    try {
        $null = Invoke-RestMethod -Uri "$script:SpotifyCDPBase/json" -TimeoutSec 1
        return $true
    } catch {
        return $false
    }
}

function Start-SpotifyCDP {

    if (Test-SpotifyCDP) {
        Write-Host "Spotify already running on port 9222." -ForegroundColor Green
        return
    }

    $exe = Get-SpotifyExecutable
    if (-not $exe) {
        Write-Host "Spotify executable could not be found." -ForegroundColor Red
        return
    }

    $running = Get-Process Spotify -ErrorAction SilentlyContinue

    if ($running) {
        Write-Host "Spotify not running on port 9222. Relaunching Spotify for CDP controls..." -ForegroundColor Red

        $running | Stop-Process -Force
        Start-Sleep -Milliseconds 500
    }

    Start-Process -FilePath $exe -ArgumentList "--remote-debugging-port=$script:SpotifyCDPPort"

    for ($i = 0; $i -lt 50; $i++) {
        if (Test-SpotifyCDP) {
            $script:SpotifyTargetWebSocket = $null
            return
        }
        Start-Sleep -Milliseconds 100
    }

    Write-Host "Spotify started, but CDP did not appear on port 9222." -ForegroundColor Red
}

function Get-SpotifyCDPTarget {
    $targets = Invoke-RestMethod -Uri "$script:SpotifyCDPBase/json"

    # Spotify owns this debugging port, so prefer a normal page target.
    $target = $targets |
        Where-Object {
            $_.type -eq 'page' -and
            $_.webSocketDebuggerUrl
        } |
        Select-Object -First 1

    if (-not $target) {
        $target = $targets |
            Where-Object { $_.webSocketDebuggerUrl } |
            Select-Object -First 1
    }

    if (-not $target) {
        Write-Host "No Spotify CDP target found on port 9222." -ForegroundColor Red
    }

    return $target
}

function Initialize-SpotifyCDP {
    if (-not (Test-SpotifyCDP)) {
        Start-SpotifyCDP
    }

    $target = Get-SpotifyCDPTarget
    if ($target -and $target.webSocketDebuggerUrl) {
        $script:SpotifyTargetWebSocket = $target.webSocketDebuggerUrl
    }
    else {
        $script:SpotifyTargetWebSocket = $null
    }

    return $script:SpotifyTargetWebSocket
}

function Invoke-SpotifyCDPCommand {
    param(
        [Parameter(Mandatory)][string]$Method,
        [hashtable]$Params = @{}
    )

    $wsUrl = Initialize-SpotifyCDP
    $ws = [System.Net.WebSockets.ClientWebSocket]::new()
    $ct = [System.Threading.CancellationToken]::None

    try {
        $null = $ws.ConnectAsync([Uri]$wsUrl, $ct).GetAwaiter().GetResult()

        $id = Get-Random -Minimum 1000 -Maximum 999999999
        $payload = @{
            id     = $id
            method = $Method
            params = $Params
        } | ConvertTo-Json -Depth 30 -Compress

        $sendBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
        $sendSeg = [System.ArraySegment[byte]]::new($sendBytes)

        $null = $ws.SendAsync(
            $sendSeg,
            [System.Net.WebSockets.WebSocketMessageType]::Text,
            $true,
            $ct
        ).GetAwaiter().GetResult()

        while ($true) {
            $stream = [System.IO.MemoryStream]::new()

            do {
                $buffer = New-Object byte[] 65536
                $segment = [System.ArraySegment[byte]]::new($buffer)

                $result = $ws.ReceiveAsync($segment, $ct).GetAwaiter().GetResult()

                if ($result.Count -gt 0) {
                    $null = $stream.Write($buffer, 0, $result.Count)
                }
            }
            while (-not $result.EndOfMessage)

            $text = [System.Text.Encoding]::UTF8.GetString($stream.ToArray())
            $message = $text | ConvertFrom-Json

            if ($message.id -eq $id) {
                if ($message.error) {
                    Write-Host "CDP error: $($message.error.message)" -ForegroundColor Red
                }
                return $message.result
            }
        }
    }
    catch {
        # Refresh a stale target once. This also handles Spotify being
        # minimized or refreshed without requiring the caller to reload the script.
        $script:SpotifyTargetWebSocket = $null
        if (-not $script:SpotifyCDPRetrying) {
            $script:SpotifyCDPRetrying = $true
            try {
                return Invoke-SpotifyCDPCommand -Method $Method -Params $Params
            }
            finally {
                $script:SpotifyCDPRetrying = $false
            }
        }

        Write-Host "Spotify CDP command failed. Verify Spotify is running with remote debugging enabled on port $script:SpotifyCDPPort." -ForegroundColor Red
    }
    finally {
        try {
            if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
                $null = $ws.CloseAsync(
                    [System.Net.WebSockets.WebSocketCloseStatus]::NormalClosure,
                    "done",
                    $ct
                ).GetAwaiter().GetResult()
            }
        } catch {}
        $ws.Dispose()
    }
}

function Invoke-SpotifyJS {
    param(
        [Parameter(Mandatory)][string]$Script
    )

    $result = Invoke-SpotifyCDPCommand `
        -Method "Runtime.evaluate" `
        -Params @{
            expression    = $Script
            returnByValue = $true
            awaitPromise  = $true
        }

    if (-not $result) {
        return $null
    }

    $exceptionDetails = $result.PSObject.Properties['exceptionDetails']
    if ($exceptionDetails -and $exceptionDetails.Value) {
        $errorText = $exceptionDetails.Value.text
        if (-not $errorText) {
            $exceptionProperty = $exceptionDetails.Value.PSObject.Properties['exception']
            if ($exceptionProperty -and $exceptionProperty.Value) {
                $errorText = $exceptionProperty.Value.description
            }
        }
        Write-Host "Spotify JavaScript failed: $errorText" -ForegroundColor Red
    }

    $resultValue = $result.PSObject.Properties['result']
    if (-not $resultValue -or -not $resultValue.Value) {
        return $null
    }

    $valueProperty = $resultValue.Value.PSObject.Properties['value']
    if ($valueProperty) {
        return $valueProperty.Value
    }

    return $null
}

# ============================================================
# SHARED DOM HELPERS
# ============================================================

$script:SpotifyDOMHelpers = @'
const norm = s => (s || '').replace(/\s+/g, ' ').trim();
const visible = el => {
    if (!el) return false;
    const s = getComputedStyle(el);
    const r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
};
const accName = el => norm(
    el.getAttribute?.('aria-label') ||
    el.getAttribute?.('title') ||
    el.innerText ||
    el.textContent
);
const all = (root = document, selector = '*') => [...root.querySelectorAll(selector)];
const byName = (name, root = document) =>
    all(root).find(el => accName(el) === name) || null;
const buttonByName = (name, root = document) =>
    all(root, 'button,[role="button"]').find(el => accName(el) === name) || null;
const clickEl = el => {
    if (!el) return false;
    el.click();
    return true;
};
const setNativeValue = (el, value) => {
    const proto = el instanceof HTMLInputElement
        ? HTMLInputElement.prototype
        : el instanceof HTMLTextAreaElement
            ? HTMLTextAreaElement.prototype
            : null;
    if (proto) {
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (setter) setter.call(el, value);
        else el.value = value;
    } else {
        el.value = value;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
};
'@

function Invoke-SpotifyDOM {
    param(
        [Parameter(Mandatory)][string]$Body
    )

    $script = @"
(() => {
$script:SpotifyDOMHelpers
$Body
})()
"@

    return Invoke-SpotifyJS -Script $script
}

# ============================================================
# INTERNAL PLAYER HELPERS
# ============================================================

function Get-SpotifyPlayerControlsInternal {
    return Invoke-SpotifyDOM @'
const el = byName('Player controls');
return !!el;
'@
}

function Find-SpotifyPlayerButtonInternal {
    param([Parameter(Mandatory)][string]$Name)

    $nameJson = $Name | ConvertTo-Json -Compress

    return Invoke-SpotifyDOM @"
const controls = byName('Player controls') || document;
return !!buttonByName($nameJson, controls);
"@
}

# ============================================================
# PLAYBACK STATE
# ============================================================

function Get-SpotifyPlaybackState {
    return Invoke-SpotifyDOM @'
const controls = byName('Player controls') || document;
if (buttonByName('Pause', controls)) return 'Playing';
if (buttonByName('Play', controls)) return 'Paused';
return 'Unknown';
'@
}

# ============================================================
# PLAY / PAUSE
# ============================================================

function Toggle-SpotifyPlayPause {
    $ok = Invoke-SpotifyDOM @'
const controls = byName('Player controls') || document;
const button = buttonByName('Pause', controls) || buttonByName('Play', controls);
return clickEl(button);
'@

    if (-not $ok) { Write-Host "Play/Pause button not found." -ForegroundColor Red }
}

function Play-Spotify {
    if ((Get-SpotifyPlaybackState) -eq 'Paused') {
        Toggle-SpotifyPlayPause
    }
}

function Pause-Spotify {
    if ((Get-SpotifyPlaybackState) -eq 'Playing') {
        Toggle-SpotifyPlayPause
    }
}

# ============================================================
# NEXT / PREVIOUS
# ============================================================

function Next-SpotifyTrack {
    $ok = Invoke-SpotifyDOM @'
const controls = byName('Player controls') || document;
return clickEl(buttonByName('Next', controls));
'@
    if (-not $ok) { Write-Host "Next button not found." -ForegroundColor Red }
}

function Previous-SpotifyTrack {

    $result = Invoke-SpotifyDOM @'
return (async () => {

    const getSong = () => {
        const bar = byName('Now playing bar');

        if (!bar)
            return null;

        const names = all(bar, 'a')
            .map(accName)
            .filter(Boolean);

        return names[0] || null;
    };

    const controls = byName('Player controls') || document;
    const button = buttonByName('Previous', controls);

    if (!button)
        return "BUTTON_NOT_FOUND";

    const originalSong = getSong();

    for (let i = 0; i < 2; i++) {

        clickEl(button);

        await new Promise(resolve => setTimeout(resolve, 100));

        const currentSong = getSong();

        if (currentSong !== originalSong)
            return "CHANGED";
    }

    return "NO_CHANGE";

})();
'@

    if ($result -eq "BUTTON_NOT_FOUND") {
        Write-Host "Previous button not found." -ForegroundColor Red
    }
}

# ============================================================
# CURRENT SONG / ARTIST
# ============================================================

function Get-SpotifyNowPlayingNamesInternal {
    $value = Invoke-SpotifyDOM @'
const bar = byName('Now playing bar');
if (!bar) return [];

return all(bar, 'a')
    .map(accName)
    .filter(Boolean);
'@

    return @($value)
}

function Get-SpotifyCurrentSong {
    $names = @(Get-SpotifyNowPlayingNamesInternal)
    if ($names.Count -ge 1) { return $names[0] }
    return $null
}

function Get-SpotifyCurrentArtist {
    $names = @(Get-SpotifyNowPlayingNamesInternal)
    if ($names.Count -ge 2) { return $names[1] }
    return $null
}

# ============================================================
# CURRENT PLAYLIST / ALBUM
# ============================================================

function Get-SpotifyCurrentContext {
    return Invoke-SpotifyDOM @'
const controls = byName('Player controls') || document;
for (const button of all(controls, 'button,[role="button"]')) {
    const name = accName(button);
    const m = name.match(/^(Enable|Disable) Shuffle for (.+)$/);
    if (m) return m[2];
}
return null;
'@
}

function Get-SpotifyCurrentPlaylist {
    return Get-SpotifyCurrentContext
}

# ============================================================
# VOLUME
# ============================================================

function Get-SpotifyVolume {

    Invoke-SpotifyJS @'
(() => {
    const slider = document.querySelector(
        'input[type="range"][min="0"][max="1"][step="0.1"]'
    );

    return slider ? slider.value * 100 + "%" : null;
})()
'@
}

function Set-SpotifyVolume {

    param(
        [Parameter(Mandatory)]
        [double]$Volume
    )

    if ($Volume -lt 0 -or $Volume -gt 100) {
        Write-Host "Volume must be between 0 and 100." -ForegroundColor Red
    }

    $normalizedVolume = $Volume / 100

    $value = $normalizedVolume.ToString(
        [System.Globalization.CultureInfo]::InvariantCulture
    )

    $result = Invoke-SpotifyJS @"
(() => {

    const slider = document.querySelector(
        'input[type="range"][min="0"][max="1"][step="0.1"]'
    );

    if (!slider)
        return "NOT_FOUND";

    const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        "value"
    ).set;

    setter.call(slider, "$value");

    slider.dispatchEvent(new Event("input", { bubbles: true }));
    slider.dispatchEvent(new Event("change", { bubbles: true }));

    return slider.value;
})()
"@

    if ($result -eq "NOT_FOUND") {
        Write-Host "Volume slider not found." -ForegroundColor Red
    }

    return $result
}






# ============================================================
# QUEUE STATE / OPEN / CLOSE
# ============================================================

function Test-SpotifyQueueOpen {
    return [bool](Invoke-SpotifyDOM -Body @'
const panel = document.getElementById('queue-panel');
return !!panel && visible(panel);
'@)
}


function Open-SpotifyQueue {

    if (Test-SpotifyQueueOpen) {
        return
    }

    $result = Invoke-SpotifyDOM -Body @'
const button = buttonByName('Queue');
if (!button) return "NOT_FOUND";
return clickEl(button) ? "OK" : "NOT_FOUND";
'@

    if ($result -ne "OK") {
        Write-Host "Queue button not found." -ForegroundColor Red
    }
}


function Close-SpotifyQueue {

    if (-not (Test-SpotifyQueueOpen)) {
        return
    }

    $result = Invoke-SpotifyDOM -Body @'
const button = buttonByName('Queue');
if (!button) return "NOT_FOUND";
return clickEl(button) ? "OK" : "NOT_FOUND";
'@

    if ($result -ne "OK") {
        Write-Host "Queue button not found." -ForegroundColor Red
    }
}


function Get-SpotifyQueueSongs {

    $wasOpen = Test-SpotifyQueueOpen

    if (-not $wasOpen) {
        Open-SpotifyQueue
        Start-Sleep -Milliseconds 250
    }

    $songs = Invoke-SpotifyDOM -Body @'
return (() => {

    // Queue tracks expose buttons like:
    // "Play Sleepwalker ... by akiaura, LONOWN, STM"

    const panel = document.querySelector('#queue-panel');
    if (!panel) return [];

    const headingText = node => [...node.querySelectorAll(
        'h1,h2,h3,h4,[role="heading"]'
    )].map(accName).join(' ');

    const isQueueSection = button => {
        let node = button;
        for (let depth = 0; node && node !== panel && depth < 8; depth++, node = node.parentElement) {
            const text = headingText(node);
            if (/Recently played|Now playing/i.test(text)) return false;
            if (/Next in queue|Next from:/i.test(text)) return true;
        }
        return null;
    };

    const buttons = [...panel.querySelectorAll('button,[role="button"]')]
        .filter(visible)
        .map(button => ({
            button,
            label: norm(button.getAttribute('aria-label'))
        }))
        .filter(item => /^Play .+/i.test(item.label));

    const marked = buttons.filter(item => isQueueSection(item.button) === true);
    const scoped = marked.length
        ? marked
        : buttons.filter(item => isQueueSection(item.button) !== false);

    return [...new Set(scoped.map(item => item.label.replace(/^Play /i, '')))];
})()
'@

    if (-not $wasOpen) {
        Close-SpotifyQueue
    }

    return @($songs)
}

# ============================================================
# LIBRARY
# ============================================================

function Get-SpotifyLibraryRootInternal {
    return Invoke-SpotifyDOM @'
return !!document.getElementById('Desktop_LeftSidebar_Id');
'@
}










# Search the library first, then fall back to Spotify's main search.
function Play-SpotifyPlaylist {

    param(
        [Parameter(Mandatory)]
        [string]$PlaylistName
    )

    $nameJson = $PlaylistName | ConvertTo-Json -Compress

    $searched = Invoke-SpotifyDOM -Body @"
return (() => {

    const input = document.querySelector(
        'input[role="searchbox"], input[role="combobox"]'
    );

    if (!input)
        return false;

    setNativeValue(input, $nameJson);
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown', {
        key: 'Enter',
        code: 'Enter',
        bubbles: true
    }));
    input.dispatchEvent(new KeyboardEvent('keyup', {
        key: 'Enter',
        code: 'Enter',
        bubbles: true
    }));

    return true;
})()
"@

    if (-not $searched) {
        Write-Host "Library search input not found."  -ForegroundColor Red
    }

    # Spotify updates its search results asynchronously after the input event.
    Start-Sleep -Milliseconds 1500

    $libraryResult = Invoke-SpotifyDOM -Body @"
return (() => {

    const library = document.querySelector('#Desktop_LeftSidebar_Id');

    if (!library)
        return "LIBRARY_NOT_FOUND";

    const query = $nameJson.toLowerCase();
    const buttons = [...library.querySelectorAll('button,[role="button"]')]
        .filter(visible)
        .map(button => ({
            button,
            label: norm(button.getAttribute('aria-label')),
            text: norm(button.innerText || button.textContent)
        }))
        .filter(item => /^(Play|Pause) .+/i.test(item.label));

    const match = buttons.find(item =>
        (item.label + ' ' + item.text).toLowerCase().includes(query)
    );

    if (!match) return "NO_RESULT";
    if (/^Pause /i.test(match.label)) return "ALREADY_PLAYING";

    match.button.click();
    return match.label;
})()
"@

    if ($libraryResult -eq "ALREADY_PLAYING") { return $libraryResult }
    if ($libraryResult -ne "LIBRARY_NOT_FOUND" -and $libraryResult -ne "NO_RESULT") {
        return $libraryResult
    }

    # Fall back to Spotify's main search results when the library has no match.
    Start-Sleep -Milliseconds 300
    $mainResult = Invoke-SpotifyDOM -Body @"
return (() => {
    const library = document.querySelector('#Desktop_LeftSidebar_Id');
    const controls = byName('Player controls');
    const buttons = [...document.querySelectorAll('button,[role="button"]')]
        .filter(visible)
        .filter(button => !library?.contains(button) && !controls?.contains(button))
        .map(button => ({
            button,
            label: norm(button.getAttribute('aria-label')),
            text: norm(button.innerText || button.textContent)
        }))
        .filter(item => /^(Play|Pause)( .+)?$/i.test(item.label));

    const query = $nameJson.toLowerCase();
    const match = buttons.find(item =>
        (item.label + ' ' + item.text).toLowerCase().includes(query)
    ) || buttons[0];

    if (!match) return "NO_MAIN_RESULT";
    if (/^Pause /i.test(match.label)) return "ALREADY_PLAYING";

    match.button.click();
    return match.label;
})()
"@

    if ($mainResult -eq "NO_MAIN_RESULT") {
        Write-Host "No Spotify library or main-search result found for '$PlaylistName'." -ForegroundColor Red
        return
    }

    return $mainResult
}


# ============================================================
# STATUS -- ONE CDP EVALUATION
# ============================================================

function Get-SpotifyStatus {
    $obj = Invoke-SpotifyDOM @'
const controls = byName('Player controls') || document;

let playbackState = 'Unknown';
if (buttonByName('Pause', controls)) playbackState = 'Playing';
else if (buttonByName('Play', controls)) playbackState = 'Paused';

let song = null;
let artist = null;
const bar = byName('Now playing bar');
if (bar) {
    const names = all(bar, 'a').map(accName).filter(Boolean);
    song = names[0] || null;
    artist = names[1] || null;
}

let context = null;
for (const button of all(controls, 'button,[role="button"]')) {
    const m = accName(button).match(/^(Enable|Disable) Shuffle for (.+)$/);
    if (m) {
        context = m[2];
        break;
    }
}

let volume = null;
const slider = all(document, 'input[type="range"],[role="slider"]')
    .find(el => accName(el) === 'Change volume');
if (slider) {
    const raw = Number(slider.value ?? slider.getAttribute('aria-valuenow'));
    const min = Number(slider.min ?? slider.getAttribute('aria-valuemin') ?? 0);
    const max = Number(slider.max ?? slider.getAttribute('aria-valuemax') ?? 1);
    if (Number.isFinite(raw)) {
        volume = max !== min ? (raw - min) / (max - min) : raw;
    }
}

const panel = document.getElementById('queue-panel');
const queueOpen = !!panel && visible(panel);

return {
    PlaybackState: playbackState,
    Song: song,
    Artist: artist,
    Playlist: context,
    Volume: volume,
    QueueOpen: queueOpen
};
'@

    return [PSCustomObject]@{
        PlaybackState = $obj.PlaybackState
        Song          = $obj.Song
        Artist        = $obj.Artist
        Playlist      = $obj.Playlist
        Volume        = $obj.Volume
        QueueOpen     = [bool]$obj.QueueOpen
    }
}

# ============================================================
# LUCY-MUSIC COMMAND NAMES
# ============================================================

# Keep the original names working while providing one consistent command prefix.
@(
    'Get-SpotifyExecutable',
    'Test-SpotifyCDP',
    'Start-SpotifyCDP',
    'Get-SpotifyCDPTarget',
    'Initialize-SpotifyCDP',
    'Invoke-SpotifyCDPCommand',
    'Invoke-SpotifyJS',
    'Invoke-SpotifyDOM',
    'Get-SpotifyPlayerControlsInternal',
    'Find-SpotifyPlayerButtonInternal',
    'Get-SpotifyPlaybackState',
    'Toggle-SpotifyPlayPause',
    'Play-Spotify',
    'Pause-Spotify',
    'Next-SpotifyTrack',
    'Previous-SpotifyTrack',
    'Get-SpotifyNowPlayingNamesInternal',
    'Get-SpotifyCurrentSong',
    'Get-SpotifyCurrentArtist',
    'Get-SpotifyCurrentContext',
    'Get-SpotifyCurrentPlaylist',
    'Get-SpotifyVolume',
    'Set-SpotifyVolume',
    'Test-SpotifyQueueOpen',
    'Open-SpotifyQueue',
    'Close-SpotifyQueue',
    'Get-SpotifyQueueSongs',
    'Get-SpotifyLibraryRootInternal',
    'Play-SpotifyPlaylist',
    'Get-SpotifyStatus'
) | ForEach-Object {
    Set-Alias -Name "Lucy-Music-$_" -Value $_ -Scope Global
}
