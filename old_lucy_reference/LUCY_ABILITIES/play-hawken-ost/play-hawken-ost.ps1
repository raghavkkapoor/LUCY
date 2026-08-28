$ErrorActionPreference = "Stop"
Start-Process "spotify:album:0UNTrituFTZdMBUppnrk8K"
Start-Sleep -Seconds 4
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
$spotify = @($manager.GetSessions()) | Where-Object { $_.SourceAppUserModelId -match "spotify" } | Select-Object -First 1
if (-not $spotify) { throw "Spotify media session not found." }
$null = Await-WinRT ($spotify.TryPlayAsync()) ([bool])
Write-Output "HAWKEN_OST_OPENED=True"
