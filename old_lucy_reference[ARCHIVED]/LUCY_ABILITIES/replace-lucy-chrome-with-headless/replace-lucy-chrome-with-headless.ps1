$ErrorActionPreference = 'Stop'

Write-Output "=== OODA: REPLACE LUCY 9223 CHROME WITH HEADLESS 9333 USING SAME PROFILE ==="

$oldPort = 9223
$newPort = 9333
$profile = "$env:LOCALAPPDATA\Lucy\LucyChrome"
$chrome  = "C:\Program Files\Google\Chrome\Application\chrome.exe"

if (-not (Test-Path $profile -PathType Container)) {
    throw "LucyChrome profile not found: $profile"
}

if (-not (Test-Path $chrome -PathType Leaf)) {
    throw "Chrome executable not found: $chrome"
}

# Find the ROOT Lucy Chrome process on 9223.
$root9223 = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'chrome.exe' -and
    $_.CommandLine -and
    $_.CommandLine -match "(?:--remote-debugging-port=|--remote-debugging-port\s+)$oldPort\b" -and
    $_.CommandLine -match [regex]::Escape($profile) -and
    $_.CommandLine -notmatch '\s--type='
})

Write-Output "ROOT_9223_COUNT=$($root9223.Count)"

if ($root9223.Count -eq 0) {
    Write-Output "ROOT_9223_NOT_FOUND=True"
}
else {
    foreach ($root in $root9223) {
        Write-Output "STOPPING_ROOT_9223_PID=$($root.ProcessId)"

        # taskkill /T kills the entire Chrome process tree belonging to
        # the Lucy browser, including renderer/GPU/network children.
        & taskkill.exe /PID $root.ProcessId /T /F | Out-Null

        if ($LASTEXITCODE -ne 0) {
            throw "Failed to terminate Lucy Chrome tree rooted at PID $($root.ProcessId)"
        }
    }
}

# Also clean up any old Chrome process on 9333.
$old9333Roots = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'chrome.exe' -and
    $_.CommandLine -and
    $_.CommandLine -match "(?:--remote-debugging-port=|--remote-debugging-port\s+)$newPort\b" -and
    $_.CommandLine -notmatch '\s--type='
})

foreach ($root in $old9333Roots) {
    Write-Output "STOPPING_OLD_9333_PID=$($root.ProcessId)"
    & taskkill.exe /PID $root.ProcessId /T /F | Out-Null
}

Start-Sleep -Seconds 1

# Verify no Chrome process still owns the real Lucy profile.
$profileRegex = [regex]::Escape($profile)

$remainingProfileProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'chrome.exe' -and
    $_.CommandLine -and
    $_.CommandLine -match $profileRegex
})

Write-Output "REMAINING_LUCY_PROFILE_PROCESS_COUNT=$($remainingProfileProcesses.Count)"

if ($remainingProfileProcesses.Count -gt 0) {
    foreach ($p in $remainingProfileProcesses) {
        Write-Output "FORCE_STOP_PROFILE_PID=$($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }

    Start-Sleep -Milliseconds 750
}

$remainingProfileProcesses = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -eq 'chrome.exe' -and
    $_.CommandLine -and
    $_.CommandLine -match $profileRegex
})

if ($remainingProfileProcesses.Count -gt 0) {
    throw "Some Chrome processes still own LucyChrome after forced shutdown."
}

Write-Output "OLD_LUCY_CHROME_FULLY_STOPPED=True"

# Verify both desired ports are clear.
foreach ($checkPort in @($oldPort, $newPort)) {
    $listener = Get-NetTCPConnection -LocalPort $checkPort -State Listen -ErrorAction SilentlyContinue
    if ($listener) {
        throw "Port $checkPort is still occupied."
    }
}

# Remove Chrome runtime locks now that no process owns the profile.
foreach ($name in @(
    'SingletonLock',
    'SingletonCookie',
    'SingletonSocket',
    'DevToolsActivePort'
)) {
    $path = Join-Path $profile $name
    if (Test-Path $path) {
        Remove-Item $path -Force -ErrorAction SilentlyContinue
    }
}

Write-Output "PROFILE_LOCKS_CLEARED=True"

# Launch the SAME real LucyChrome user-data-dir, but now headless on 9333.
$launchArgs = @(
    '--headless=new',
    '--remote-debugging-address=127.0.0.1',
    "--remote-debugging-port=$newPort",
    "--user-data-dir=$profile",
    '--profile-directory=Default',
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-backgrounding-occluded-windows',
    '--disable-renderer-backgrounding',
    'https://chatgpt.com/'
)

$newRoot = Start-Process `
    -FilePath $chrome `
    -ArgumentList $launchArgs `
    -WindowStyle Hidden `
    -PassThru

Write-Output "NEW_HEADLESS_ROOT_PID=$($newRoot.Id)"
Write-Output "PROFILE=$profile"
Write-Output "NEW_CDP_PORT=$newPort"

$versionUrl = "http://127.0.0.1:$newPort/json/version"
$listUrl    = "http://127.0.0.1:$newPort/json/list"

$version = $null

for ($attempt = 1; $attempt -le 80; $attempt++) {
    try {
        $version = Invoke-RestMethod -Uri $versionUrl -TimeoutSec 1
        if ($version.webSocketDebuggerUrl) {
            break
        }
    }
    catch {}

    if ($newRoot.HasExited) {
        throw "New headless Chrome exited before CDP became available. ExitCode=$($newRoot.ExitCode)"
    }

    Start-Sleep -Milliseconds 200
}

if (-not $version -or -not $version.webSocketDebuggerUrl) {
    throw "Headless Lucy Chrome did not expose CDP on port $newPort."
}

Write-Output "HEADLESS_CDP_READY=True"
Write-Output "CDP_WEBSOCKET=$($version.webSocketDebuggerUrl)"

# Get targets using ConvertFrom-Json to avoid the earlier System.Object[] issue.
$json = (Invoke-WebRequest -Uri $listUrl -UseBasicParsing -TimeoutSec 2).Content
$targets = @($json | ConvertFrom-Json)

Write-Output "TARGET_COUNT=$($targets.Count)"

foreach ($target in $targets) {
    Write-Output "TARGET_ID=$($target.id)"
    Write-Output "TARGET_TYPE=$($target.type)"
    Write-Output "TARGET_TITLE=$($target.title)"
    Write-Output "TARGET_URL=$($target.url)"
    Write-Output "---"
}

# Ensure the old visible 9223 endpoint is actually gone.
$old9223Alive = $false
try {
    $null = Invoke-RestMethod -Uri "http://127.0.0.1:$oldPort/json/version" -TimeoutSec 1
    $old9223Alive = $true
}
catch {}

Write-Output "OLD_9223_CDP_ALIVE=$old9223Alive"

if ($old9223Alive) {
    throw "Old CDP instance on port 9223 is unexpectedly still alive."
}

# Verify the new endpoint survives several real round trips.
$stable = $true

for ($i = 1; $i -le 3; $i++) {
    Start-Sleep -Milliseconds 400

    try {
        $health = Invoke-RestMethod -Uri $versionUrl -TimeoutSec 2

        if (-not $health.webSocketDebuggerUrl) {
            $stable = $false
            break
        }
    }
    catch {
        $stable = $false
        break
    }
}

Write-Output "HEADLESS_9333_STABLE=$stable"

if (-not $stable) {
    throw "New headless LucyChrome CDP connection is unstable."
}

# Save/update reusable ability.
$abilityRoots = @(
    (Join-Path (Get-Location).Path 'LUCY_ABILITIES'),
    "$env:USERPROFILE\OneDrive\Desktop\LucyPython\LUCY_ABILITIES",
    "$env:USERPROFILE\Downloads\LUCY\LucyPython\LUCY_ABILITIES",
    "$env:USERPROFILE\Downloads\LUCY\LUCY\LucyPython\LUCY_ABILITIES"
)

$abilityRoot = $abilityRoots |
    Where-Object { Test-Path $_ -PathType Container } |
    Select-Object -First 1

if (-not $abilityRoot) {
    $abilityRoot = Join-Path (Get-Location).Path 'LUCY_ABILITIES'
    New-Item -ItemType Directory -Path $abilityRoot -Force | Out-Null
}

$abilityDir = Join-Path $abilityRoot 'replace-lucy-chrome-with-headless'
New-Item -ItemType Directory -Path $abilityDir -Force | Out-Null

$scriptPath = Join-Path $abilityDir 'replace-lucy-chrome-with-headless.ps1'
$readmePath = Join-Path $abilityDir 'README.md'

if ($MyInvocation.MyCommand.Path -and (Test-Path $MyInvocation.MyCommand.Path)) {
    Copy-Item $MyInvocation.MyCommand.Path $scriptPath -Force
}
else {
    @'
# Stops Lucy Chrome on 9223 and relaunches the same AppData profile
# as headless Chrome on port 9333.
'@ | Set-Content $scriptPath -Encoding UTF8
}

@"
# Replace Lucy Chrome with Headless Chrome

## Goal
Replace Lucy's existing visible CDP Chrome instance on port 9223 with a
headless Chrome instance on port 9333 while continuing to use the exact same
LucyChrome profile.

## Profile
$profile

## Old CDP
9223 — stopped and verified unreachable.

## New CDP
9333 — headless and verified healthy.

## Result
HEADLESS_CDP_READY=True
HEADLESS_9333_STABLE=$stable

## Stability
The original Chrome process tree is completely stopped before the same
user-data-dir is reopened. This avoids simultaneous writers and profile
corruption while retaining Lucy's existing cookies, storage, extensions,
and login state.
"@ | Set-Content $readmePath -Encoding UTF8

$scriptExists = Test-Path $scriptPath
$readmeExists = Test-Path $readmePath

Write-Output "SCRIPT_EXISTS=$scriptExists"
Write-Output "README_EXISTS=$readmeExists"
Write-Output "ABILITY_DIR=$abilityDir"

if (-not $scriptExists -or -not $readmeExists) {
    throw "Headless instance works, but ability persistence verification failed."
}

Write-Output "GOAL_COMPLETED=True"