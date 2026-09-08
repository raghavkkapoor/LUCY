$ErrorActionPreference = "Stop"
$modulePath = Join-Path (Get-Location) "LUCY_ABILITIES\spotify-desktop-automation\SpotifyAutomation.psm1"
Import-Module $modulePath -Force
$required = @(
    "Get-SpotifySession","Get-SpotifyNowPlaying","Play-Spotify","Pause-Spotify",
    "Toggle-Spotify","Next-SpotifyTrack","Previous-SpotifyTrack","Seek-Spotify",
    "Set-SpotifyShuffle","Set-SpotifyRepeat","Start-Spotify","Open-SpotifySearch",
    "Open-SpotifyTrack","Open-SpotifyAlbum","Open-SpotifyArtist",
    "Open-SpotifyPlaylist","Open-SpotifyLikedSongs","Open-SpotifyUri"
)
foreach ($fn in $required) {
    if (-not (Get-Command $fn -ErrorAction SilentlyContinue)) {
        throw "Missing Spotify function: $fn"
    }
}
$session = Get-SpotifySession
$now = Get-SpotifyNowPlaying
Write-Output "SPOTIFY_SESSION_OK=$([bool]$session)"
Write-Output "TITLE=$($now.Title)"
Write-Output "ARTIST=$($now.Artist)"
Write-Output "STATUS=$($now.Status)"
Write-Output "AUTOMATION_SMOKE_TEST=True"
