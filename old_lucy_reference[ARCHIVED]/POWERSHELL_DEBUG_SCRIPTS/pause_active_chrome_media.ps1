Add-Type -AssemblyName System.Runtime.WindowsRuntime

# Load Windows media-control WinRT types
$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager, Windows.Media.Control, ContentType = WindowsRuntime]
$null = [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties, Windows.Media.Control, ContentType = WindowsRuntime]

# PowerShell can't call .AsTask() directly on these WinRT COM objects,
# so invoke the .NET WinRT extension method manually.
$asTaskMethods = [System.WindowsRuntimeSystemExtensions].GetMethods() |
    Where-Object {
        $_.Name -eq "AsTask" -and
        $_.IsGenericMethod -and
        $_.GetParameters().Count -eq 1
    }

function Await-WinRT($Operation, $ResultType) {
    $method = $asTaskMethods[0].MakeGenericMethod($ResultType)
    $task = $method.Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

Write-Host "Looking for active media sessions..."

# Get media session manager
$managerOp =
    [Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager]::RequestAsync()

$manager = Await-WinRT `
    $managerOp `
    ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionManager])

$sessions = $manager.GetSessions()

foreach ($session in $sessions) {

    $app = $session.SourceAppUserModelId
    $playback = $session.GetPlaybackInfo()

    $propsOp = $session.TryGetMediaPropertiesAsync()

    $props = Await-WinRT `
        $propsOp `
        ([Windows.Media.Control.GlobalSystemMediaTransportControlsSessionMediaProperties])

    Write-Host ""
    Write-Host "APP:    $app"
    Write-Host "TITLE:  $($props.Title)"
    Write-Host "ARTIST: $($props.Artist)"
    Write-Host "STATUS: $($playback.PlaybackStatus)"

    $browser =
        $app -match "chrome|msedge|firefox|brave|opera"

    if (
        $browser -and
        $playback.PlaybackStatus.ToString() -eq "Playing"
    ) {
        Write-Host ""
        Write-Host "Found playing browser media:"
        Write-Host $props.Title

        $pauseOp = $session.TryPauseAsync()

        $success = Await-WinRT `
            $pauseOp `
            ([bool])

        Write-Host ""
        Write-Host "PAUSE RESULT: $success"

        if ($success) {
            Write-Host "Paused."
            break
        }
    }
}