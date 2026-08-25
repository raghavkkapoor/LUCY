$ErrorActionPreference = "Stop"
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
    $task.Result
}

$managerType = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType=WindowsRuntime]
$manager = Await-WinRT ($managerType::RequestAsync()) $managerType

$spotify = @($manager.GetSessions()) |
    Where-Object { $_.SourceAppUserModelId -match "spotify" } |
    Select-Object -First 1

if (-not $spotify) {
    Start-Process "spotify:"
    Start-Sleep -Seconds 4
    $manager = Await-WinRT ($managerType::RequestAsync()) $managerType
    $spotify = @($manager.GetSessions()) |
        Where-Object { $_.SourceAppUserModelId -match "spotify" } |
        Select-Object -First 1
}

if (-not $spotify) { throw "Spotify media session not found." }

$accepted = Await-WinRT ($spotify.TryPlayAsync()) ([bool])
Start-Sleep -Seconds 1

$status = $spotify.GetPlaybackInfo().PlaybackStatus
if ($status.ToString() -ne "Playing") {
    throw "Spotify did not begin playback."
}

Write-Output "SPOTIFY_PLAYING=True"
