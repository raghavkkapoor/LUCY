$ErrorActionPreference = "Stop"

$abilityDir = Join-Path (Get-Location) "LUCY_ABILITIES\open-demonmika-photos"
New-Item -ItemType Directory -Force -Path $abilityDir | Out-Null

$chrome = @(
    "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
    "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
    "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $chrome) { throw "Chrome not found." }

$query = [uri]::EscapeDataString("DemonMika")
$url = "https://www.google.com/search?tbm=isch&safe=active&q=$query"

# Explicitly open a visible NEW Chrome window.
$proc = Start-Process -FilePath $chrome -ArgumentList @(
    "--new-window",
    "--start-maximized",
    $url
) -PassThru

Start-Sleep -Seconds 4

# Bring the newly opened Chrome window to the foreground.
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32Focus {
    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);
    [DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hWnd, int nCmdShow);
}
"@

$visibleChrome = Get-Process chrome -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle } |
    Sort-Object StartTime -Descending |
    Select-Object -First 1

if (-not $visibleChrome) {
    throw "Chrome started, but no visible browser window could be verified."
}

[Win32Focus]::ShowWindowAsync($visibleChrome.MainWindowHandle, 3) | Out-Null
[Win32Focus]::SetForegroundWindow($visibleChrome.MainWindowHandle) | Out-Null

$scriptPath = Join-Path $abilityDir "open-demonmika-photos.ps1"
$readmePath = Join-Path $abilityDir "README.md"

$MyInvocation.MyCommand.ScriptBlock.ToString() |
    Set-Content -Path $scriptPath -Encoding UTF8

@"
# Open DemonMika Photos

Goal: visibly display public DemonMika photos.

Method: launches a maximized Google Images search in a brand-new Chrome window and explicitly brings that window to the foreground.

Risk/Stability: low risk; public web search only. Stable as long as Chrome is installed.

Verified visible Chrome window:
$($visibleChrome.MainWindowTitle)
"@ | Set-Content -Path $readmePath -Encoding UTF8

Add-Type -AssemblyName System.Speech
$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer
$voice.Speak("I opened Demon Mika photos in a visible maximized window.")

Write-Output "PHOTO_WINDOW_VISIBLE=True"
Write-Output "WINDOW_TITLE=$($visibleChrome.MainWindowTitle)"
Write-Output "SCRIPT_EXISTS=$(Test-Path $scriptPath)"
Write-Output "README_EXISTS=$(Test-Path $readmePath)"
Write-Output "GOAL_COMPLETED=True"
