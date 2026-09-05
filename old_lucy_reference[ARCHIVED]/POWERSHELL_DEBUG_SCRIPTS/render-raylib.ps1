#Requires -Version 5.1
<#
.SYNOPSIS
Render API calls from the adjacent 'raylib current command.txt'.
.DESCRIPTION
Each window runs in a clean PowerShell process. This launcher never loads raylib
types into your shell. Edit the text file, then run with New or Override.
Override updates the latest managed window; if none exists it opens one.
.EXAMPLE
& .\render-raylib.ps1 -Mode New
.EXAMPLE
& .\render-raylib.ps1 -Mode Override -InstanceId <id returned by New>
.PARAMETER Calls
Optional plain text API calls supplied directly instead of reading the text file.
.PARAMETER Mode
New creates another window. Override replaces calls in an existing window.
Close closes an existing managed window. Override and Close default to the latest.
#>
[CmdletBinding()]
param(
    [ValidateSet('New', 'Override', 'Close')][string]$Mode = 'Override',
    [ValidatePattern('^[a-f0-9]{32}$')][string]$InstanceId,
    [string]$Calls,
    [ValidateSet('Auto', 'C', 'PowerShell')][string]$Language = 'Auto',
    [ValidateRange(1, 7680)][int]$Width = 960,
    [ValidateRange(1, 4320)][int]$Height = 640,
    [string]$Title = 'raylib',
    [ValidateRange(1, 240)][int]$TargetFPS = 30,
    [uint32]$BackgroundColor = 0x121621FF,
    [ValidateRange(0, 86400)][double]$DurationSeconds = 0,
    [string]$ScreenshotPath,
    [ValidateRange(1, 300)][int]$TimeoutSeconds = 60
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT) { throw 'This renderer requires Windows.' }
if ($Mode -eq 'New' -and $InstanceId) { throw 'New creates its own instance ID. Use InstanceId with Override or Close.' }
. (Join-Path $PSScriptRoot 'raylib\ipc.ps1')
$sessionRoot = Get-RaylibSessionRoot $PSScriptRoot
[IO.Directory]::CreateDirectory($sessionRoot) | Out-Null
$commandFile = Join-Path $PSScriptRoot 'raylib current command.txt'
$code = ''
$resolvedLanguage = $Language
if ($Mode -ne 'Close') {
    if ($PSBoundParameters.ContainsKey('Calls')) { $code = $Calls }
    else {
        if (-not (Test-Path -LiteralPath $commandFile)) { throw "Put your API calls in '$commandFile'." }
        $code = [IO.File]::ReadAllText($commandFile)
    }
    if ($resolvedLanguage -eq 'Auto') {
        $isPowerShell = $code -match '\[RaylibPowerShell\.' -or $code -match '(?m)^\s*(\$|param\s*\(|#\s)'
        $resolvedLanguage = $(if ($isPowerShell) { 'PowerShell' } else { 'C' })
    }
    if ($resolvedLanguage -eq 'C') {
        $sceneDll = & (Join-Path $PSScriptRoot 'raylib\compile-command.ps1') -Code $code
        $bridge = (Join-Path $PSScriptRoot 'raylib\NativeScene.cs').Replace("'", "''")
        $escapedDll = $sceneDll.Replace("'", "''")
        # Existing renderer processes can execute this adapter without a restart.
        $code = @'
if (-not ('RaylibCommandHost.Scene' -as [type])) {
    Add-Type -TypeDefinition ([IO.File]::ReadAllText('__BRIDGE__'))
}
[RaylibCommandHost.Scene]::Get('__DLL__').Draw($frame.Time, $frame.DeltaTime, $frame.Frame, $frame.Width, $frame.Height, [int]$frame.FirstFrame)
'@
        $code = $code.Replace('__BRIDGE__', $bridge).Replace('__DLL__', $escapedDll)
    }
    else {
        $parseTokens = $null
        $parseErrors = $null
        [Management.Automation.Language.Parser]::ParseInput($code, [ref]$parseTokens, [ref]$parseErrors) | Out-Null
        if ($parseErrors.Count) { throw (($parseErrors | ForEach-Object { "Line $($_.Extent.StartLineNumber): $($_.Message)" }) -join "`n") }
    }
}
$config = @{}
foreach ($name in @('Width', 'Height', 'Title', 'TargetFPS', 'BackgroundColor', 'DurationSeconds')) {
    if ($PSBoundParameters.ContainsKey($name)) { $config[$name] = Get-Variable -Name $name -ValueOnly }
}
if ($ScreenshotPath) {
    $ScreenshotPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($ScreenshotPath)
    if ([IO.Path]::GetExtension($ScreenshotPath) -ine '.png') { throw 'ScreenshotPath must end in .png.' }
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($ScreenshotPath)) | Out-Null
}
$selected = $null
if ($Mode -ne 'New') {
    $candidates = @()
    foreach ($directory in [IO.Directory]::GetDirectories($sessionRoot)) {
        if ($InstanceId -and [IO.Path]::GetFileName($directory) -ne $InstanceId) { continue }
        $stateFile = Join-Path $directory 'state.json'
        if (-not [IO.File]::Exists($stateFile)) { continue }
        try {
            $state = Read-RaylibJson $stateFile
            if (Test-RaylibProcess $state) { $candidates += $state }
        }
        catch { Write-Verbose "Ignored unavailable instance: $directory" }
    }
    $selected = $candidates | Sort-Object CreatedUtcTicks -Descending | Select-Object -First 1
    if (-not $selected -and $InstanceId) { throw "No live renderer with instance ID $InstanceId." }
    if (-not $selected -and $Mode -eq 'Close') { throw 'No managed rendering window is open.' }
}
$isNew = $null -eq $selected
if ($isNew) {
    $InstanceId = [Guid]::NewGuid().ToString('N')
    $sessionDir = Join-Path $sessionRoot $InstanceId
    [IO.Directory]::CreateDirectory($sessionDir) | Out-Null
}
else {
    $InstanceId = $selected.InstanceId
    $sessionDir = Join-Path $sessionRoot $InstanceId
}
$requestId = [Guid]::NewGuid().ToString('N')
$request = @{
    RequestId = $requestId; Action = $(if ($Mode -eq 'Close') { 'Close' } else { 'Render' })
    Code = $code; Config = $config; ScreenshotPath = $ScreenshotPath
}
$requestFile = Join-Path $sessionDir ('request-' + [DateTime]::UtcNow.Ticks.ToString('D19') + '-' + $requestId + '.json')
Write-RaylibJson $requestFile $request
$child = $null
if ($isNew) {
    $engine = Join-Path $PSHOME 'pwsh.exe'
    if (-not [IO.File]::Exists($engine)) { $engine = Join-Path $PSHOME 'powershell.exe' }
    if ([IntPtr]::Size -ne 8 -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
        $engine = Join-Path $env:WINDIR 'Sysnative\WindowsPowerShell\v1.0\powershell.exe'
        if (-not [IO.File]::Exists($engine)) { $engine = Join-Path $env:WINDIR 'System32\WindowsPowerShell\v1.0\powershell.exe' }
    }
    $hostFile = Join-Path $PSScriptRoot 'raylib\renderer-host.ps1'
    $escapedHost = $hostFile.Replace("'", "''")
    $escapedSession = $sessionDir.Replace("'", "''")
    $bootstrap = "& '$escapedHost' -SessionDirectory '$escapedSession'"
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($bootstrap))
    try {
        $child = Start-Process -FilePath $engine -ArgumentList @('-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-EncodedCommand', $encoded) -WindowStyle Hidden -PassThru -WorkingDirectory $sessionDir -RedirectStandardOutput (Join-Path $sessionDir 'stdout.log') -RedirectStandardError (Join-Path $sessionDir 'stderr.log')
    }
    catch {
        Remove-Item -LiteralPath $requestFile -ErrorAction SilentlyContinue
        throw
    }
}
$responseFile = Join-Path $sessionDir ('response-' + $requestId + '.json')
$timer = [Diagnostics.Stopwatch]::StartNew()
while (-not [IO.File]::Exists($responseFile)) {
    $fatalFile = Join-Path $sessionDir 'fatal.json'
    if ([IO.File]::Exists($fatalFile)) { throw (Read-RaylibJson $fatalFile).Error }
    if ($child) {
        $child.Refresh()
        if ($child.HasExited) { throw "Renderer exited before accepting the calls. See '$sessionDir\stderr.log'." }
    }
    elseif (-not (Test-RaylibProcess $selected)) { throw 'The selected rendering window closed before accepting the calls.' }
    if ($timer.Elapsed.TotalSeconds -ge $TimeoutSeconds) {
        throw "No response within $TimeoutSeconds seconds. Instance: $InstanceId. Logs: $sessionDir"
    }
    Start-Sleep -Milliseconds 50
}
$response = Read-RaylibJson $responseFile
Remove-Item -LiteralPath $responseFile
if (-not $response.Success) { throw $response.Error }
[pscustomobject]@{
    Mode = $(if ($Mode -eq 'Close') { 'Close' } elseif ($isNew) { 'New' } else { 'Override' })
    InstanceId = $InstanceId; ProcessId = $response.ProcessId; WindowHandle = $response.WindowHandle
    CommandFile = $(if ($PSBoundParameters.ContainsKey('Calls')) { $null } else { $commandFile })
    Screenshot = $ScreenshotPath
    Language = $resolvedLanguage
}
