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
