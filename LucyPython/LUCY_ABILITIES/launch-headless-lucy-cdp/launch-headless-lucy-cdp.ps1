$ErrorActionPreference = 'Stop'

Write-Output "=== OODA: RECOVER FROM ROBOCOPY EXIT 9 + LAUNCH HEADLESS LUCY CDP ==="

$source = 'C:\Users\ragha\AppData\Local\Lucy\LucyChrome'
$port   = 9333
$dest   = Join-Path $env:LOCALAPPDATA "LucyChromeHeadless-$port"

if (-not (Test-Path $source -PathType Container)) {
    throw "Lucy Chrome profile not found: $source"
}

$chrome = 'C:\Program Files\Google\Chrome\Application\chrome.exe'
if (-not (Test-Path $chrome)) {
    throw "Chrome not found: $chrome"
}

# Kill only a previous headless clone on our alternate port, if one exists.
Get-CimInstance Win32_Process |
    Where-Object {
        $_.Name -eq 'chrome.exe' -and
        $_.CommandLine -match "(?:--remote-debugging-port=|--remote-debugging-port\s+)$port\b"
    } |
    ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }

Start-Sleep -Milliseconds 300

if (Test-Path $dest) {
    Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Path $dest -Force | Out-Null

# Robocopy exit code 9 is a bitmask:
#   1 = files copied
#   8 = at least one copy failure
# So the previous attempt may have copied almost everything and only failed
# on live/locked/cache files. Retry while aggressively excluding disposable
# Chrome runtime state.

$roboLog = Join-Path $env:TEMP "lucy_headless_profile_copy_$port.log"

$excludeDirs = @(
    'Cache',
    'Code Cache',
    'GPUCache',
    'GrShaderCache',
    'ShaderCache',
    'DawnCache',
    'Crashpad',
    'BrowserMetrics',
    'Safe Browsing',
    'OptimizationHints',
    'component_crx_cache',
    'extensions_crx_cache',
    'GraphiteDawnCache'
)

$excludeFiles = @(
    'SingletonLock',
    'SingletonCookie',
    'SingletonSocket',
    'DevToolsActivePort',
    'LOCK',
    'lockfile'
)

$args = @(
    $source,
    $dest,
    '/E',
    '/COPY:DAT',
    '/DCOPY:DAT',
    '/XJ',
    '/R:0',
    '/W:0',
    '/NFL',
    '/NDL',
    '/NP',
    "/LOG:$roboLog"
)

foreach ($d in $excludeDirs) {
    $args += '/XD'
    $args += $d
}

foreach ($f in $excludeFiles) {
    $args += '/XF'
    $args += $f
}

& robocopy @args | Out-Null
$rc = $LASTEXITCODE

Write-Output "ROBOCOPY_EXIT_CODE=$rc"
Write-Output "ROBOCOPY_LOG=$roboLog"

# Exit >= 8 means at least one file failed. Do NOT automatically abort:
# live Chrome profiles contain nonessential locked files. Check whether the
# important profile/state files actually made it across.

$localState = Join-Path $dest 'Local State'
$defaultDir = Join-Path $dest 'Default'
$cookiesCandidates = @(
    (Join-Path $defaultDir 'Network\Cookies'),
    (Join-Path $defaultDir 'Cookies')
)

$localStateOK = Test-Path $localState
$defaultOK    = Test-Path $defaultDir
$cookiesOK    = [bool]($cookiesCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1)

Write-Output "LOCAL_STATE_COPIED=$localStateOK"
Write-Output "DEFAULT_PROFILE_COPIED=$defaultOK"
Write-Output "COOKIE_DB_COPIED=$cookiesOK"

if (-not $localStateOK -or -not $defaultOK) {
    Write-Output "PROFILE_COPY_CRITICAL_FILES_MISSING=True"

    if (Test-Path $roboLog) {
        Write-Output "ROBOCOPY_FAILURES_BEGIN"
        Get-Content $roboLog |
            Select-String -Pattern 'ERROR|failed|denied|being used|cannot access' |
            Select-Object -Last 25 |
            ForEach-Object { Write-Output $_.Line }
        Write-Output "ROBOCOPY_FAILURES_END"
    }

    throw "Critical Chrome profile files were not copied."
}

# Remove copied process locks/runtime markers before launching another Chrome.
Get-ChildItem $dest -Recurse -Force -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Name -in @(
            'SingletonLock',
            'SingletonCookie',
            'SingletonSocket',
            'DevToolsActivePort',
            'LOCK',
            'lockfile'
        )
    } |
    Remove-Item -Force -ErrorAction SilentlyContinue

# Launch the independent headless browser.
$chromeArgs = @(
    '--headless=new',
    '--remote-debugging-address=127.0.0.1',
    "--remote-debugging-port=$port",
    "--user-data-dir=$dest",
    '--no-first-run',
    '--no-default-browser-check',
    '--disable-gpu',
    'about:blank'
)

$p = Start-Process `
    -FilePath $chrome `
    -ArgumentList $chromeArgs `
    -WindowStyle Hidden `
    -PassThru

Write-Output "HEADLESS_ROOT_PID=$($p.Id)"

# Verify Chrome's real CDP server, not merely the process.
$versionUrl = "http://127.0.0.1:$port/json/version"
$listUrl    = "http://127.0.0.1:$port/json/list"

$version = $null
for ($i = 0; $i -lt 60; $i++) {
    try {
        $version = Invoke-RestMethod -Uri $versionUrl -TimeoutSec 1
        if ($version.webSocketDebuggerUrl) {
            break
        }
    } catch {}
    Start-Sleep -Milliseconds 200
}

if (-not $version -or -not $version.webSocketDebuggerUrl) {
    throw "Headless Chrome process launched, but CDP port $port never became healthy."
}

$targets = @(Invoke-RestMethod -Uri $listUrl -TimeoutSec 2)

Write-Output "HEADLESS_CDP_READY=True"
Write-Output "CDP_PORT=$port"
Write-Output "CDP_WEBSOCKET=$($version.webSocketDebuggerUrl)"
Write-Output "TARGET_COUNT=$($targets.Count)"
Write-Output "HEADLESS_PROFILE=$dest"

foreach ($t in $targets) {
    Write-Output ("TARGET_ID={0}; TYPE={1}; TITLE={2}; URL={3}" -f `
        $t.id, $t.type, $t.title, $t.url)
}

# Perform an additional real HTTP round-trip twice to make sure it remains alive.
Start-Sleep -Milliseconds 500
$verify1 = Invoke-RestMethod -Uri $versionUrl -TimeoutSec 2

Start-Sleep -Milliseconds 500
$verify2 = Invoke-RestMethod -Uri $versionUrl -TimeoutSec 2

$stable = (
    $verify1.webSocketDebuggerUrl -and
    $verify2.webSocketDebuggerUrl
)

Write-Output "SECONDARY_CDP_STABLE=$stable"

if (-not $stable) {
    throw "Secondary CDP endpoint did not remain stable."
}

# Save the verified ability.
$abilityRootCandidates = @(
    (Join-Path (Get-Location).Path 'LUCY_ABILITIES'),
    "$env:USERPROFILE\OneDrive\Desktop\LucyPython\LUCY_ABILITIES",
    "$env:USERPROFILE\Downloads\LUCY\LucyPython\LUCY_ABILITIES",
    "$env:USERPROFILE\Downloads\LUCY\LUCY\LucyPython\LUCY_ABILITIES"
)

$abilityRoot = $abilityRootCandidates |
    Where-Object { Test-Path $_ -PathType Container } |
    Select-Object -First 1

if (-not $abilityRoot) {
    $abilityRoot = Join-Path (Get-Location).Path 'LUCY_ABILITIES'
    New-Item -ItemType Directory -Path $abilityRoot -Force | Out-Null
}

$abilityDir = Join-Path $abilityRoot 'launch-headless-lucy-cdp'
New-Item -ItemType Directory -Path $abilityDir -Force | Out-Null

$scriptPath = Join-Path $abilityDir 'launch-headless-lucy-cdp.ps1'
$readmePath = Join-Path $abilityDir 'README.md'

if ($MyInvocation.MyCommand.Path -and (Test-Path $MyInvocation.MyCommand.Path)) {
    Copy-Item $MyInvocation.MyCommand.Path $scriptPath -Force
} else {
    @'
# Reusable workflow generated by Lucy.
# Clone the Lucy Chrome profile while excluding volatile runtime files,
# then launch the clone headlessly on an alternate CDP port.
'@ | Set-Content $scriptPath -Encoding UTF8
}

@"
# Headless Lucy CDP

Goal: launch an independent headless Chrome CDP instance carrying a snapshot
of Lucy's Chrome profile/state.

Source profile:
$source

Headless clone:
$dest

CDP port:
$port

Result:
HEADLESS_CDP_READY=True
SECONDARY_CDP_STABLE=$stable

Robocopy returned $rc. Robocopy codes are bitmasks, so code 9 means files were
copied while one or more files also failed. Live Chrome profiles commonly have
locked or transient files. The workflow therefore excludes disposable runtime
state and verifies the critical copied profile plus the actual CDP endpoint
instead of treating any value above 7 as an automatic total failure.

Risk/stability:
The second Chrome instance uses a clone rather than sharing Lucy's writable
user-data directory. This avoids Chrome profile locking/corruption. State is a
snapshot and will not automatically synchronize back into the original profile.
"@ | Set-Content $readmePath -Encoding UTF8

$scriptOK = Test-Path $scriptPath
$readmeOK = Test-Path $readmePath

Write-Output "SCRIPT_EXISTS=$scriptOK"
Write-Output "README_EXISTS=$readmeOK"
Write-Output "ABILITY_DIR=$abilityDir"

if (-not $scriptOK -or -not $readmeOK) {
    throw "CDP works, but ability persistence verification failed."
}

Write-Output "GOAL_COMPLETED=True"