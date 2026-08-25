# 1. Locate primary Steam installation path
$SteamReg = Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue
$SteamPath = Split-Path $SteamReg.SteamExe

# 2. Add all library paths
$LibraryPaths = [System.Collections.Generic.List[string]]::new()
$LibraryPaths.Add((Join-Path $SteamPath "steamapps"))

$LibraryVDF = Join-Path $SteamPath "steamapps\libraryfolders.vdf"
if (Test-Path $LibraryVDF) {
    Select-String -Path $LibraryVDF -Pattern '"path"\s+"([^"]+)"' | ForEach-Object {
        $Path = $_.Matches.Value -split '"' | Where-Object { [string]::IsNullOrWhiteSpace($_) -eq $false } | Select-Object -Last 1
        $LibraryPaths.Add((Join-Path $Path "steamapps"))
    }
}

# 3. Check which 'downloading' folder was modified within the last 15 seconds
$ActiveAppID = $null
foreach ($Folder in $LibraryPaths) {
    $DownloadDir = Join-Path $Folder "downloading"
    if (Test-Path $DownloadDir) {
        # Check folders under 'downloading' for very recent file writes
        $RecentWrite = Get-ChildItem -Path $DownloadDir -Recurse -File -ErrorAction SilentlyContinue | 
                       Where-Object { $_.LastWriteTime -gt (Get-Date).AddSeconds(-15) } | 
                       Select-Object -First 1
        
        if ($RecentWrite) {
            # Extract AppID (the root folder inside the 'downloading' directory)
            $RelativePath = $RecentWrite.FullName.Substring($DownloadDir.Length + 1)
            $ActiveAppID = $RelativePath -split '\\' | Select-Object -First 1
            break
        }
    }
}

# 4. Resolve the AppID to a Game Name in real-time
if ($ActiveAppID -and $ActiveAppID -match '^\d+$') {
    Write-Host "Active Download AppID Detected: $ActiveAppID" -ForegroundColor Cyan
    
    # Try fetching the game name from the local manifest
    $ManifestPath = Join-Path $Folder "appmanifest_$ActiveAppID.acf"
    if (Test-Path $ManifestPath) {
        $Content = Get-Content $ManifestPath -Raw
        if ($Content -match '"name"\s+"([^"]+)"') {
            Write-Host "CURRENTLY DOWNLOADING: $($Matches[1])" -ForegroundColor Green
            return
        }
    }
    
    # Fallback: Hit Steam's public WebAPI to resolve the ID to a name
    try {
        $UIString = Invoke-RestMethod -Uri "https://steampowered.com" -TimeoutSec 3
        $GameName = $UIString.$ActiveAppID.data.name
        if ($GameName) {
            Write-Host "CURRENTLY DOWNLOADING: $GameName" -ForegroundColor Green
        }
    } catch {
        Write-Host "CURRENTLY DOWNLOADING: AppID $ActiveAppID (Could not fetch name)" -ForegroundColor Yellow
    }
} else {
    Write-Host "No active disk-writes detected. Steam is not downloading right now." -ForegroundColor Red
}

