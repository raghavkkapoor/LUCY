Get-CimInstance Win32_Process |
Where-Object {
    $_.Name -eq "Spotify.exe" -and
    $_.CommandLine -match '--remote-debugging-port=(\d+)'
} |
ForEach-Object {
    $Matches[1]
}

Invoke-RestMethod "http://127.0.0.1:9222/json/version"