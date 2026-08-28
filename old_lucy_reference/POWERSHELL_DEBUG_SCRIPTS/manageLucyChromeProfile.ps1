param(
    [int]$PreferredPort = 9223
)

$ErrorActionPreference = "Stop"

$LucyDir   = Join-Path $env:LOCALAPPDATA "Lucy"
$StateFile = Join-Path $LucyDir "chrome_state.json"

New-Item -ItemType Directory -Path $LucyDir -Force | Out-Null

# Profiles Lucy may already have used.
$ProfileCandidates = @(
    #"C:\Temp\LucyChrome",
    #(Join-Path $env:TEMP "LucyChrome"),
    (Join-Path $LucyDir "LucyChrome")
) | Select-Object -Unique

function Test-CDPPort {
    param([int]$Port)

    try {
        $v = Invoke-RestMethod "http://127.0.0.1:$Port/json/version" -TimeoutSec 1
        return ($null -ne $v.webSocketDebuggerUrl)
    }
    catch {
        return $false
    }
}

# ------------------------------------------------------------
# 1. Check if Lucy Chrome is already running
# ------------------------------------------------------------

$chromeProcesses = Get-CimInstance Win32_Process |
    Where-Object { $_.Name -eq "chrome.exe" }

foreach ($process in $chromeProcesses) {

    $cmd = $process.CommandLine

    if (-not $cmd) {
        continue
    }

    if ($cmd -match '--remote-debugging-port=(\d+)') {

        $port = [int]$Matches[1]

        if (Test-CDPPort $port) {

            $profile = $null

            if ($cmd -match '--user-data-dir=(?:"([^"]+)"|([^\s]+))') {
                $profile = if ($Matches[1]) {
                    $Matches[1]
                } else {
                    $Matches[2]
                }
            }

            $state = [PSCustomObject]@{
                Port       = $port
                ProfileDir = $profile
                ProcessId  = $process.ProcessId
                Running    = $true
            }

            $state |
                ConvertTo-Json |
                Set-Content $StateFile

            Write-Host "Lucy Chrome already running."
            Write-Host "Port:    $port"
            Write-Host "Profile: $profile"

            return $state
        }
    }
}

# ------------------------------------------------------------
# 2. Pick existing persistent profile
# ------------------------------------------------------------

$profileDir = $ProfileCandidates |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $profileDir) {
    $profileDir = Join-Path $LucyDir "LucyChrome"

    New-Item `
        -ItemType Directory `
        -Path $profileDir `
        -Force |
        Out-Null
}

# ------------------------------------------------------------
# 3. Find Chrome
# ------------------------------------------------------------

$ChromeCandidates = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
)

$ChromeExe = $ChromeCandidates |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1

if (-not $ChromeExe) {
    throw "Google Chrome could not be found."
}

# ------------------------------------------------------------
# 4. Launch Lucy Chrome
# ------------------------------------------------------------

$port = $PreferredPort

while (Test-NetConnection `
    -ComputerName 127.0.0.1 `
    -Port $port `
    -InformationLevel Quiet `
    -WarningAction SilentlyContinue) {

    $port++
}

Write-Host "Starting Lucy Chrome..."
Write-Host "Profile: $profileDir"
Write-Host "Port:    $port"

Start-Process `
    $ChromeExe `
    -ArgumentList @(
        "--remote-debugging-port=$port",
        "--user-data-dir=$profileDir",
        "--profile-directory=Default"
        #"--headless",
        #"--disable-gpu"
    )

# Wait for CDP
$ready = $false

for ($i = 0; $i -lt 30; $i++) {

    Start-Sleep -Milliseconds 300

    if (Test-CDPPort $port) {
        $ready = $true
        break
    }
}

if (-not $ready) {
    throw "Chrome started but CDP did not become available."
}

$state = [PSCustomObject]@{
    Port       = $port
    ProfileDir = $profileDir
    Running    = $true
}

$state |
    ConvertTo-Json |
    Set-Content $StateFile

Write-Host ""
Write-Host "Lucy Chrome ready."

return $state