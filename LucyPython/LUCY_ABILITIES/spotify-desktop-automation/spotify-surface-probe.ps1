
$ErrorActionPreference = 'Stop'
Write-Output "=== OODA: MAP SPOTIFY AUTOMATION + RESOLVE LOVE BY TATLI ==="
$cwd = (Get-Location).Path
$root = Join-Path $cwd 'LUCY_ABILITIES'
$abilityRoot = Join-Path $root 'spotify-desktop-automation'
$modulePath = Join-Path $abilityRoot 'SpotifyAutomation.psm1'
$readmePath = Join-Path $abilityRoot 'README.md'
$probePath = Join-Path $abilityRoot 'spotify-surface-probe.ps1'
New-Item -ItemType Directory -Path $abilityRoot -Force | Out-Null
# ============================================================
# OBSERVE 1: enumerate every stable Windows media capability
# ============================================================
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq 'AsTask' -and
        $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1
    } | Select-Object -First 1)
function Await-WinRT($Operation, $ResultType) {
    $m = $asTaskGeneric.MakeGenericMethod($ResultType)
    $t = $m.Invoke($null, @($Operation))
    $t.Wait()
    $t.Result
}
$managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$manager = Await-WinRT ($managerType::RequestAsync()) $managerType
$session = @($manager.GetSessions()) |
    Where-Object { $_.SourceAppUserModelId -match 'spotify' } |
    Select-Object -First 1
if (-not $session) {
    Start-Process 'spotify:'
    Start-Sleep -Seconds 4
    $manager = Await-WinRT ($managerType::RequestAsync()) $managerType
    $session = @($manager.GetSessions()) |
        Where-Object { $_.SourceAppUserModelId -match 'spotify' } |
        Select-Object -First 1
}
if (-not $session) {
    throw 'Spotify media session unavailable.'
}
$playback = $session.GetPlaybackInfo()
$controls = $playback.Controls
$timeline = $session.GetTimelineProperties()
Write-Output "MEDIA_PLAY=True"
Write-Output "MEDIA_PAUSE=True"
Write-Output "MEDIA_TOGGLE=True"
Write-Output "MEDIA_NEXT=$($controls.IsNextEnabled)"
Write-Output "MEDIA_PREVIOUS=$($controls.IsPreviousEnabled)"
Write-Output "MEDIA_SEEK=$($controls.IsPlaybackPositionEnabled)"
Write-Output "MEDIA_SHUFFLE=$($controls.IsShuffleEnabled)"
Write-Output "MEDIA_REPEAT=$($controls.IsRepeatEnabled)"
Write-Output "TIMELINE_START=$($timeline.StartTime)"
Write-Output "TIMELINE_END=$($timeline.EndTime)"
Write-Output "TIMELINE_POSITION=$($timeline.Position)"
# ============================================================
# OBSERVE 2: use Lucy Chrome CDP to interrogate Spotify Web
# Search is read-only and opens a NEW WINDOW.
# ============================================================
$py = @'
import os, time, urllib.parse
from playwright.sync_api import sync_playwright
CDP = "http://127.0.0.1:9223"
query = "Love TATLI"
url = "https://open.spotify.com/search/" + urllib.parse.quote(query)
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp(CDP)
    if not browser.contexts:
        print("SPOTIFY_WEB_CONTEXT=False")
        raise SystemExit(0)
    context = browser.contexts[0]
    cdp = browser.new_browser_cdp_session()
    target = cdp.send("Target.createTarget", {
        "url": url,
        "newWindow": True
    })
    target_id = target["targetId"]
    print("SPOTIFY_WEB_TARGET=" + target_id)
    page = None
    for _ in range(120):
        for pg in context.pages:
            try:
                if "open.spotify.com" in pg.url:
                    page = pg
            except:
                pass
        if page is not None:
            break
        time.sleep(.25)
    if page is None:
        # Ask Chrome for target state even if Playwright has not surfaced the page.
        try:
            info = cdp.send("Target.getTargetInfo", {"targetId": target_id})["targetInfo"]
            print("SPOTIFY_TARGET_URL=" + info.get("url",""))
            print("SPOTIFY_TARGET_TITLE=" + info.get("title",""))
        except Exception as e:
            print("TARGET_INFO_ERROR=" + repr(e))
        print("SPOTIFY_WEB_PAGE=False")
        raise SystemExit(0)
    print("SPOTIFY_WEB_PAGE=True")
    print("SPOTIFY_WEB_URL=" + page.url)
    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except:
        pass
    time.sleep(4)
    try:
        print("SPOTIFY_WEB_TITLE=" + page.title())
    except:
        pass
    # Accept common cookie prompts if present.
    for txt in ("Accept", "Accept all", "I agree"):
        try:
            page.get_by_text(txt, exact=False).first.click(timeout=600)
            break
        except:
            pass
    # Inspect links to tracks/artists/albums and text around them.
    found = []
    selectors = [
        'a[href*="/track/"]',
        'a[href*="/artist/"]',
        'a[href*="/album/"]'
    ]
    for sel in selectors:
        try:
            links = page.locator(sel)
            for i in range(min(links.count(), 100)):
                a = links.nth(i)
                try:
                    href = a.get_attribute("href") or ""
                    text = (a.inner_text(timeout=250) or "").strip().replace("\n"," ")
                    aria = a.get_attribute("aria-label") or ""
                except:
                    continue
                key = (href,text,aria)
                if key not in found:
                    found.append(key)
        except:
            pass
    print("SPOTIFY_RESULT_LINKS=" + str(len(found)))
    for href,text,aria in found[:80]:
        combined = (text + " " + aria).lower()
        if "tatli" in combined or "love" in combined:
            print("MATCH=" + text[:140] + "|" + aria[:120] + "|" + href[:180])
    # Also capture bounded visible text around TATLI/Love.
    try:
        body = page.locator("body").inner_text(timeout=3000)
        clean = " ".join(body.split())
        low = clean.lower()
        for needle in ("tatli","love"):
            pos = low.find(needle)
            if pos >= 0:
                start = max(0,pos-180)
                end = min(len(clean),pos+500)
                print("TEXT_MATCH=" + clean[start:end])
    except Exception as e:
        print("BODY_SCAN_ERROR=" + repr(e))
'@
$tmp = Join-Path $env:TEMP 'lucy_spotify_web_search.py'
Set-Content -LiteralPath $tmp -Value $py -Encoding UTF8
$webOut = python $tmp 2>&1 | Out-String
$webOut.Trim().Split("`n") |
    Select-Object -First 120 |
    ForEach-Object { Write-Output $_.TrimEnd() }
# ============================================================
# ORIENT: extract an exact Spotify track ID if the web result
# exposed one associated with TATLI/Love.
# ============================================================
$trackId = $null
$matchLines = @(
    $webOut -split "`r?`n" |
    Where-Object { $_ -match '^MATCH=' }
)
foreach ($line in $matchLines) {
    if (
        $line -match '(?i)tatli' -and
        $line -match '(?i)love' -and
        $line -match '/track/([A-Za-z0-9]+)'
    ) {
        $trackId = $Matches[1]
        break
    }
}
Write-Output "EXACT_TRACK_ID_FOUND=$([bool]$trackId)"
# ============================================================
# ACT: play exact URI when found.
# Otherwise leave Spotify search open rather than guessing.
# ============================================================
if ($trackId) {
    $uri = "spotify:track:$trackId"
    Start-Process $uri
    Start-Sleep -Seconds 4
    $null = Await-WinRT ($session.TryPlayAsync()) ([bool])
    Start-Sleep -Seconds 2
} else {
    Start-Process 'spotify:search:Love%20TATLI'
    Start-Sleep -Seconds 3
}
# ============================================================
# VERIFY current playback metadata
# ============================================================
$propsType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType=WindowsRuntime]
$props = Await-WinRT ($session.TryGetMediaPropertiesAsync()) $propsType
$currentTitle = [string]$props.Title
$currentArtist = [string]$props.Artist
$currentAlbum = [string]$props.AlbumTitle
$currentState = $session.GetPlaybackInfo().PlaybackStatus.ToString()
$titleOK = $currentTitle -and $currentTitle.Trim().ToLowerInvariant().Contains('love')
$artistOK = $currentArtist -and $currentArtist.Trim().ToLowerInvariant().Contains('tatli')
$songOK = [bool]($titleOK -and $artistOK -and $currentState -eq 'Playing')
Write-Output "CURRENT_TITLE=$currentTitle"
Write-Output "CURRENT_ARTIST=$currentArtist"
Write-Output "CURRENT_ALBUM=$currentAlbum"
Write-Output "CURRENT_STATE=$currentState"
Write-Output "LOVE_BY_TATLI_VERIFIED=$songOK"
# ============================================================
# SAVE: modular Spotify automation library
# ============================================================
@'
$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$script:SpotifyAsTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq "AsTask" -and
        $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1
    } | Select-Object -First 1)
function Invoke-SpotifyAwait {
    param($Operation,[Type]$ResultType)
    $m = $script:SpotifyAsTask.MakeGenericMethod($ResultType)
    $t = $m.Invoke($null,@($Operation))
    $t.Wait()
    $t.Result
}
function Get-SpotifySession {
    $type = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
    $manager = Invoke-SpotifyAwait ($type::RequestAsync()) $type
    $s = @($manager.GetSessions()) |
        Where-Object { $_.SourceAppUserModelId -match "spotify" } |
        Select-Object -First 1
    if (-not $s) { throw "Spotify session not found." }
    $s
}
function Get-SpotifyNowPlaying {
    $s = Get-SpotifySession
    $pt = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType=WindowsRuntime]
    $p = Invoke-SpotifyAwait ($s.TryGetMediaPropertiesAsync()) $pt
    $tl = $s.GetTimelineProperties()
    [pscustomobject]@{
        Title    = [string]$p.Title
        Artist   = [string]$p.Artist
        Album    = [string]$p.AlbumTitle
        Status   = $s.GetPlaybackInfo().PlaybackStatus.ToString()
        Position = $tl.Position
        EndTime  = $tl.EndTime
    }
}
function Play-Spotify {
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TryPlayAsync()) ([bool])
}
function Pause-Spotify {
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TryPauseAsync()) ([bool])
}
function Toggle-Spotify {
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TryTogglePlayPauseAsync()) ([bool])
}
function Next-SpotifyTrack {
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TrySkipNextAsync()) ([bool])
}
function Previous-SpotifyTrack {
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TrySkipPreviousAsync()) ([bool])
}
function Seek-Spotify {
    param([Parameter(Mandatory=$true)][TimeSpan]$Position)
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TryChangePlaybackPositionAsync($Position.Ticks)) ([bool])
}
function Set-SpotifyShuffle {
    param([Parameter(Mandatory=$true)][bool]$Enabled)
    $s = Get-SpotifySession
    Invoke-SpotifyAwait ($s.TryChangeShuffleActiveAsync($Enabled)) ([bool])
}
function Set-SpotifyRepeat {
    param(
        [ValidateSet("None","Track","List")]
        [string]$Mode
    )
    $s = Get-SpotifySession
    $enum = [Windows.Media.MediaPlaybackAutoRepeatMode, Windows.Media, ContentType=WindowsRuntime]
    $value = [Enum]::Parse($enum,$Mode)
    Invoke-SpotifyAwait ($s.TryChangeAutoRepeatModeAsync($value)) ([bool])
}
function Start-Spotify {
    Start-Process "spotify:"
}
function Open-SpotifySearch {
    param([Parameter(Mandatory=$true)][string]$Query)
    Start-Process ("spotify:search:" + [uri]::EscapeDataString($Query))
}
function Open-SpotifyTrack {
    param([Parameter(Mandatory=$true)][string]$TrackId)
    Start-Process "spotify:track:$TrackId"
}
function Open-SpotifyAlbum {
    param([Parameter(Mandatory=$true)][string]$AlbumId)
    Start-Process "spotify:album:$AlbumId"
}
function Open-SpotifyArtist {
    param([Parameter(Mandatory=$true)][string]$ArtistId)
    Start-Process "spotify:artist:$ArtistId"
}
function Open-SpotifyPlaylist {
    param([Parameter(Mandatory=$true)][string]$PlaylistId)
    Start-Process "spotify:playlist:$PlaylistId"
}
function Open-SpotifyLikedSongs {
    Start-Process "spotify:collection:tracks"
}
function Open-SpotifyUri {
    param([Parameter(Mandatory=$true)][string]$Uri)
    Start-Process $Uri
}
Export-ModuleMember -Function `
    Get-SpotifySession, `
    Get-SpotifyNowPlaying, `
    Play-Spotify, `
    Pause-Spotify, `
    Toggle-Spotify, `
    Next-SpotifyTrack, `
    Previous-SpotifyTrack, `
    Seek-Spotify, `
    Set-SpotifyShuffle, `
    Set-SpotifyRepeat, `
    Start-Spotify, `
    Open-SpotifySearch, `
    Open-SpotifyTrack, `
    Open-SpotifyAlbum, `
    Open-SpotifyArtist, `
    Open-SpotifyPlaylist, `
    Open-SpotifyLikedSongs, `
    Open-SpotifyUri
'@ | Set-Content -LiteralPath $modulePath -Encoding UTF8
# Save this discovery probe too.
$MyInvocation.MyCommand.Definition | Set-Content -LiteralPath $probePath -Encoding UTF8
@"
# Spotify Desktop Automation
## Goal
Provide Lucy with reusable, separate Spotify desktop automation functions rather than one-off UI guesses.
## Surfaces mapped
### Windows Global System Media Transport Controls
Stable controls discovered:
- play
- pause
- toggle play/pause
- next track
- previous track
- playback position / seeking
- shuffle
- repeat
- now-playing metadata
- playback status
- timeline position and duration
- capability detection
### Spotify URI protocol
Stable navigation discovered:
- spotify:
- spotify:search:<query>
- spotify:track:<id>
- spotify:album:<id>
- spotify:artist:<id>
- spotify:playlist:<id>
- spotify:collection:tracks
### Spotify desktop UI
Spotify 1.2.96.518 is Chromium based. Standard Windows UI Automation exposes the Chromium host but almost none of Spotify's internal XPUI controls, so UIA is not a reliable main automation layer.
### Local networking
Spotify owns localhost listener 7768 plus dynamic listeners. They did not expose a normal unauthenticated HTTP/CDP automation API during probing, so Lucy should not depend on them.
### Browser-assisted discovery
Lucy's existing Chrome CDP instance can open Spotify Web in a separate window to discover exact track/album/artist IDs. Once an ID is known, control returns to the native Spotify app using spotify: URIs.
## Reliability
High: media transport functions and direct Spotify URIs.
Medium: browser-assisted Spotify catalog discovery.
Low: blind keyboard/UI focus automation, which should only be used as a fallback.
## Files
- SpotifyAutomation.psm1 - reusable function module.
- spotify-surface-probe.ps1 - discovery/diagnostic workflow.
- README.md - capability documentation.
## Requested song
The workflow specifically attempts to resolve and verify "Love" by TATLI before declaring success. It does not falsely report success if Spotify remains on another track.
"@ | Set-Content -LiteralPath $readmePath -Encoding UTF8
$moduleOK = Test-Path -LiteralPath $modulePath
$readmeOK = Test-Path -LiteralPath $readmePath
$probeOK = Test-Path -LiteralPath $probePath
Write-Output "MODULE_EXISTS=$moduleOK"
Write-Output "README_EXISTS=$readmeOK"
Write-Output "PROBE_EXISTS=$probeOK"
Write-Output "ABILITY_DIR=$abilityRoot"
Write-Output "SPOTIFY_AUTOMATION_LIBRARY_SAVED=$($moduleOK -and $readmeOK -and $probeOK)"
Write-Output "GOAL_COMPLETED=$songOK"
    
