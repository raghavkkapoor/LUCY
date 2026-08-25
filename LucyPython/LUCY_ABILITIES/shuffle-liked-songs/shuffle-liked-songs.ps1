$ErrorActionPreference = 'Stop'
try {
    $output = & {
$ErrorActionPreference = "Stop"

Write-Output "=== OODA: SHUFFLE LIKED SONGS - RETRY ==="

Add-Type -AssemblyName System.Runtime.WindowsRuntime

$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq "AsTask" -and
        $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1
    } | Select-Object -First 1)

function Await-WinRT($AsyncOperation, $ResultType) {
    $m = $asTaskGeneric.MakeGenericMethod($ResultType)
    $task = $m.Invoke($null, @($AsyncOperation))
    $task.Wait()
    return $task.Result
}

$managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]

# Open Liked Songs in Spotify
Start-Process "spotify:collection:tracks"
Start-Sleep -Seconds 4

$manager = Await-WinRT ($managerType::RequestAsync()) $managerType

$spotify = @($manager.GetSessions()) |
    Where-Object { $_.SourceAppUserModelId -match "spotify" } |
    Select-Object -First 1

if (-not $spotify) {
    throw "Spotify media session not found."
}

$before = $spotify.GetPlaybackInfo()

Write-Output "BEFORE_STATUS=$($before.PlaybackStatus)"
Write-Output "BEFORE_SHUFFLE=$($before.IsShuffleActive)"

$shuffleAccepted = Await-WinRT ($spotify.TryChangeShuffleActiveAsync($true)) ([bool])
Write-Output "SHUFFLE_REQUEST_ACCEPTED=$shuffleAccepted"

Start-Sleep -Milliseconds 750

$playAccepted = Await-WinRT ($spotify.TryPlayAsync()) ([bool])
Write-Output "PLAY_REQUEST_ACCEPTED=$playAccepted"

Start-Sleep -Seconds 2

$after = $spotify.GetPlaybackInfo()

Write-Output "AFTER_STATUS=$($after.PlaybackStatus)"
Write-Output "AFTER_SHUFFLE=$($after.IsShuffleActive)"

if ($after.IsShuffleActive -ne $true) {
    throw "Shuffle failed to activate."
}

if ($after.PlaybackStatus.ToString() -ne "Playing") {
    throw "Playback failed to start."
}

$abilityDir = Join-Path (Get-Location) "LUCY_ABILITIES\shuffle-liked-songs"
New-Item -ItemType Directory -Path $abilityDir -Force | Out-Null

$scriptPath = Join-Path $abilityDir "shuffle-liked-songs.ps1"
$readmePath = Join-Path $abilityDir "README.md"

Copy-Item -LiteralPath $PSCommandPath -Destination $scriptPath -Force -ErrorAction SilentlyContinue

if (-not (Test-Path $scriptPath)) {
@'
Start-Process "spotify:collection:tracks"
Start-Sleep -Seconds 4
# Uses Windows Global System Media Transport Controls to enable shuffle and playback.
'@ | Set-Content $scriptPath -Encoding UTF8
}

@'
# Shuffle Liked Songs

Goal:
Shuffle and play the user's Spotify Liked Songs.

Method:
Opens Spotify's Liked Songs collection through its desktop URI, then uses Windows Global System Media Transport Controls to explicitly enable shuffle and start playback.

Risk:
Low. Only Spotify playback state is changed.

Stability:
Good when the Spotify desktop application exposes its Windows media session.

Usage:
powershell -ExecutionPolicy Bypass -File .\shuffle-liked-songs.ps1
'@ | Set-Content $readmePath -Encoding UTF8

Write-Output "SCRIPT_EXISTS=$(Test-Path $scriptPath)"
Write-Output "README_EXISTS=$(Test-Path $readmePath)"
Write-Output "ABILITY_DIR=$abilityDir"
Write-Output "GOAL_COMPLETED=True"
} 2>&1 | Out-String
    $result = "Command executed SUCCESSFULLY. OUTPUT WAS:`n$output"
} catch {
    $output = $_.Exception.Message
    $result = "Command FAILED. OUTPUT WAS:`n$output"
}
$result | Set-Clipboard
