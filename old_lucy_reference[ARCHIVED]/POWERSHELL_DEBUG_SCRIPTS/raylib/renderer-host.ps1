#Requires -Version 5.1
# Internal persistent renderer. Start through ../render-raylib.ps1.
param([Parameter(Mandatory)][string]$SessionDirectory)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'ipc.ps1')
$instance = [IO.Path]::GetFileName($SessionDirectory)
$stateFile = Join-Path $SessionDirectory 'state.json'
$process = Get-Process -Id $PID
$status = @{
    InstanceId = $instance; ProcessId = $PID; StartTimeUtcTicks = $process.StartTime.ToUniversalTime().Ticks.ToString()
    CreatedUtcTicks = [DateTime]::UtcNow.Ticks.ToString(); Status = 'Starting'; WindowHandle = 0
    LastRequestId = ''; LastError = ''
}
$options = @{Width = 960; Height = 640; Title = 'raylib'; TargetFPS = 30; BackgroundColor = [uint32]0x121621FF; DurationSeconds = 0.0}
$pending = $null
$closeRequest = $null
$windowReady = $false
$frame = $null

function Get-NextRequest {
    $file = [IO.Directory]::GetFiles($SessionDirectory, 'request-*.json') | Sort-Object | Select-Object -First 1
    if (-not $file) { return $null }
    $request = Read-RaylibJson $file
    [IO.File]::Delete($file)
    return $request
}
function Reply($request, [bool]$success, [string]$errorText = '') {
    Write-RaylibJson (Join-Path $SessionDirectory ('response-' + $request.RequestId + '.json')) @{
        Success = $success; Error = $errorText; ProcessId = $PID; WindowHandle = $status.WindowHandle
    }
}
function Apply-Options($config) {
    [RaylibPowerShell.Api]::SetWindowSize([int]$config.Width, [int]$config.Height)
    [RaylibPowerShell.Api]::SetWindowTitle([string]$config.Title)
    [RaylibPowerShell.Api]::SetTargetFPS([int]$config.TargetFPS)
}
try {
    & (Join-Path $PSScriptRoot 'load-native.ps1')
    $commandDirectory = Split-Path $PSScriptRoot -Parent
    Set-Location -LiteralPath $commandDirectory
    [Environment]::CurrentDirectory = $commandDirectory
    $pending = Get-NextRequest
    if (-not $pending) { throw 'The renderer did not receive an initial command.' }
    foreach ($property in $pending.Config.PSObject.Properties) { $options[$property.Name] = $property.Value }
    [RaylibPowerShell.Api]::SetTraceLogLevel([RaylibPowerShell.Constants]::LOG_WARNING)
    [RaylibPowerShell.Api]::InitWindow([int]$options.Width, [int]$options.Height, [string]$options.Title)
    if (-not [RaylibPowerShell.Api]::IsWindowReady()) { throw 'raylib could not open an OpenGL rendering window.' }
    $windowReady = $true
    [RaylibPowerShell.Api]::SetTargetFPS([int]$options.TargetFPS)
    $status.WindowHandle = [RaylibPowerShell.Api]::GetWindowHandle().ToInt64()
    $status.Status = 'Running'
    Write-RaylibJson $stateFile $status
    $frame = [pscustomobject]@{
        Time = 0.0; DeltaTime = 0.0; Frame = 0; FirstFrame = $true
        Width = $options.Width; Height = $options.Height; State = @{}; Cleanup = $null
        Api = [RaylibPowerShell.Api]; InstanceId = $instance
    }
    $activeCalls = [scriptblock]::Create('')
    $startTime = [RaylibPowerShell.Api]::GetTime()
    $durationStart = $startTime
    while (-not [RaylibPowerShell.Api]::WindowShouldClose()) {
        if (-not $pending) { $pending = Get-NextRequest }
        if ($pending -and $pending.Action -eq 'Close') { $closeRequest = $pending; $pending = $null; break }
        $previousOptions = $options.Clone()
        $callsToDraw = $activeCalls
        if ($pending) {
            try {
                $callsToDraw = [scriptblock]::Create([string]$pending.Code)
                foreach ($property in $pending.Config.PSObject.Properties) { $options[$property.Name] = $property.Value }
                Apply-Options $options
            }
            catch {
                $options = $previousOptions
                Apply-Options $options
                Reply $pending $false $_.Exception.Message
                $pending = $null
                $callsToDraw = $activeCalls
            }
        }
        $frame.Time = [RaylibPowerShell.Api]::GetTime() - $startTime
        $frame.DeltaTime = [RaylibPowerShell.Api]::GetFrameTime()
        $frame.FirstFrame = $null -ne $pending
        $frame.Width = [RaylibPowerShell.Api]::GetScreenWidth()
        $frame.Height = [RaylibPowerShell.Api]::GetScreenHeight()
        $renderError = $null
        [RaylibPowerShell.Api]::BeginDrawing()
        try {
            [RaylibPowerShell.Api]::ClearBackground([RaylibPowerShell.Api]::GetColor([uint32]$options.BackgroundColor))
            & $callsToDraw $frame | Out-Null
            if ($pending -and $pending.ScreenshotPath) {
                [RaylibPowerShell.Api]::rlDrawRenderBatchActive()
                $capture = [RaylibPowerShell.Api]::LoadImageFromScreen()
                try {
                    if (-not [RaylibPowerShell.Api]::ExportImage($capture, [string]$pending.ScreenshotPath)) {
                        throw "Could not save screenshot: $($pending.ScreenshotPath)"
                    }
                }
                finally { [RaylibPowerShell.Api]::UnloadImage($capture) }
            }
        }
        catch { $renderError = $_.Exception.Message }
        finally { [RaylibPowerShell.Api]::EndDrawing() }
        $frame.Frame++
        if ($pending) {
            if ($null -eq $renderError) {
                $activeCalls = $callsToDraw
                $status.LastRequestId = $pending.RequestId
                $status.LastError = ''
                if ($null -ne $pending.Config.PSObject.Properties['DurationSeconds']) {
                    $durationStart = [RaylibPowerShell.Api]::GetTime()
                }
                Reply $pending $true
            }
            else {
                $options = $previousOptions
                Apply-Options $options
                $status.LastError = $renderError
                Reply $pending $false $renderError
            }
            Write-RaylibJson $stateFile $status
            $pending = $null
        }
        elseif ($null -ne $renderError) {
            # Stop re-executing a failing command; another Override can recover.
            $activeCalls = [scriptblock]::Create('')
            $status.LastError = $renderError
            Write-RaylibJson $stateFile $status
        }
        if ([double]$options.DurationSeconds -gt 0 -and ([RaylibPowerShell.Api]::GetTime() - $durationStart) -ge [double]$options.DurationSeconds) { break }
    }
}
catch {
    $status.LastError = $_.Exception.Message
    Write-RaylibJson (Join-Path $SessionDirectory 'fatal.json') @{Error = $_.Exception.Message}
    if ($pending) { Reply $pending $false $_.Exception.Message }
}
finally {
    try {
        if ($frame -and $frame.Cleanup) { & $frame.Cleanup $frame.State | Out-Null }
    }
    catch { $status.LastError = $_.Exception.Message }
    finally {
        if ($windowReady -and [RaylibPowerShell.Api]::IsWindowReady()) { [RaylibPowerShell.Api]::CloseWindow() }
        $status.Status = 'Closed'
        Write-RaylibJson $stateFile $status
        if ($closeRequest) { Reply $closeRequest $true }
    }
}
