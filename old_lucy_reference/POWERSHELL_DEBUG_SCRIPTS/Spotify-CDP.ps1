# ============================================================
# SPOTIFY CDP CONTROLLER
# Spotify remote debugging port: 9222
# ============================================================

$script:SpotifyCDPPort = 9222
$script:SpotifyCDPBase = "http://127.0.0.1:$($script:SpotifyCDPPort)"
$script:SpotifyTargetWebSocket = $null

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

    if (-not $script:SpotifyTargetWebSocket) {
        $script:SpotifyTargetWebSocket = (Get-SpotifyCDPTarget).webSocketDebuggerUrl
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
        $ws.ConnectAsync([Uri]$wsUrl, $ct).GetAwaiter().GetResult()

        $id = Get-Random -Minimum 1000 -Maximum 999999999
        $payload = @{
            id     = $id
            method = $Method
            params = $Params
        } | ConvertTo-Json -Depth 30 -Compress

        $sendBytes = [System.Text.Encoding]::UTF8.GetBytes($payload)
        $sendSeg = [System.ArraySegment[byte]]::new($sendBytes)

        $ws.SendAsync(
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
                    $stream.Write($buffer, 0, $result.Count)
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
        # Target may have changed after navigation/reload.
        $script:SpotifyTargetWebSocket = $null
        Write-Host "Spotify CDP command failed due to a network issue." -ForegroundColor Red
    }
    finally {
        try {
            if ($ws.State -eq [System.Net.WebSockets.WebSocketState]::Open) {
                $ws.CloseAsync(
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

    if ($result.exceptionDetails) {
        Write-Host "Spotify JavaScript failed: $($result.exceptionDetails.text)" -ForegroundColor Red
    }

    return $result.result.value
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

    return [bool](Invoke-SpotifyJS -Script @'
(() => {

    // When queue is open Spotify literally renders "Recently played",
    // "Now playing", "Next from:", etc.

    const text = document.body.innerText || '';

    return (
        text.includes('Recently played') &&
        text.includes('Now playing') &&
        text.includes('Next from:')
    );
})()
'@)
}


function Open-SpotifyQueue {

    if (Test-SpotifyQueueOpen) {
        return
    }

    $result = Invoke-SpotifyJS @'
(() => {
    const el = document.querySelector('button[aria-label="Queue"]');

    if (!el)
        return "NOT_FOUND";

    el.click();
    return "OK";
})()
'@

    if ($result -ne "OK") {
        Write-Host "Queue button not found." -ForegroundColor Red
    }
}


function Close-SpotifyQueue {

    if (-not (Test-SpotifyQueueOpen)) {
        return
    }

    $result = Invoke-SpotifyJS @'
(() => {
    const el = document.querySelector('button[aria-label="Queue"]');

    if (!el)
        return "NOT_FOUND";

    el.click();
    return "OK";
})()
'@

    if ($result -ne "OK") {
        Write-Host "Queue button not found." -ForegroundColor Red
    }
}


#broken
function Get-SpotifyQueueSongs {

    $wasOpen = Test-SpotifyQueueOpen

    if (-not $wasOpen) {
        Open-SpotifyQueue
        Start-Sleep -Milliseconds 250
    }

    $songs = Invoke-SpotifyJS -Script @'
(() => {

    // Queue tracks expose buttons like:
    // "Play Sleepwalker ... by akiaura, LONOWN, STM"

    const buttons = [...document.querySelectorAll('button')];

    const songs = buttons
        .map(b => b.getAttribute('aria-label') || '')
        .filter(name => /^Play .+ by .+/.test(name))
        .map(name => name.replace(/^Play /, ''));

    return [...new Set(songs)];
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










#### THIS DOES WORK FOR LIBRARY BUT NOT GENERAL SEARCHING 
function Play-SpotifyPlaylist {

    param(
        [Parameter(Mandatory)]
        [string]$PlaylistName
    )

    $nameJson = $PlaylistName | ConvertTo-Json -Compress

    $searched = Invoke-SpotifyJS -Script @"
(() => {

    const input = document.querySelector('input[role="searchbox"]');

    if (!input)
        return false;

    const setter = Object.getOwnPropertyDescriptor(
        HTMLInputElement.prototype,
        'value'
    ).set;

    setter.call(input, $nameJson);

    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));

    return true;
})()
"@

    if (-not $searched) {
        Write-Host "Library search input not found."  -ForegroundColor Red
    }

    Start-Sleep -Milliseconds 300

    $result = Invoke-SpotifyJS -Script @'
(() => {

    const library = document.querySelector('#Desktop_LeftSidebar_Id');

    if (!library)
        return "LIBRARY_NOT_FOUND";

    const buttons = [...library.querySelectorAll('button')];

    const button = buttons.find(b => {
        const aria = b.getAttribute('aria-label') || '';

        return (
            aria.startsWith('Play ') ||
            aria.startsWith('Pause ')
        );
    });

    if (!button)
        return "NO_RESULT";

    const aria = button.getAttribute('aria-label') || '';

    if (aria.startsWith('Pause '))
        return "ALREADY_PLAYING";

    button.click();

    return aria;
})()
'@

    if ($result -eq "LIBRARY_NOT_FOUND") {
        Write-Host "Spotify library not found."  -ForegroundColor Red
        return
    }

    if ($result -eq "NO_RESULT") {
        Write-Host "No playlist result found for '$PlaylistName'."  -ForegroundColor Red
        return
    }

    return $result
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

# search doesnt work
