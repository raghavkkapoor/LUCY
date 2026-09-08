$ErrorActionPreference = "Stop"
$root = "C:\Users\ragha\Downloads\LUCY\LucyPython"
$main = Join-Path $root "main.py"
if (-not (Test-Path -LiteralPath $main)) {
    throw "main.py not found: $main"
}
$before = @(
    Get-Process WindowsTerminal -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -ExpandProperty MainWindowHandle
)
# Use cmd /k inside Windows Terminal because quoting is simple and stdin stays interactive.
$command = "cd /d `"$root`" && title LUCY && python main.py"
Start-Process "wt.exe" -ArgumentList @(
    "-w","new",
    "new-tab",
    "--title","LUCY",
    "cmd.exe","/k",$command
)
Start-Sleep -Seconds 2
$terminal = $null
for ($i = 0; $i -lt 40; $i++) {
    $terminal = Get-Process WindowsTerminal -ErrorAction SilentlyContinue |
        Where-Object {
            $_.MainWindowHandle -ne 0 -and
            (
                $_.MainWindowTitle -eq "LUCY" -or
                $before -notcontains $_.MainWindowHandle
            )
        } |
        Select-Object -Last 1
    if ($terminal) { break }
    Start-Sleep -Milliseconds 250
}
if (-not $terminal) {
    throw "Could not locate Lucy's new Windows Terminal window."
}
if (-not ("LucyTopLauncher.Native" -as [type])) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
namespace LucyTopLauncher {
    public static class Native {
        [DllImport("user32.dll")]
        public static extern bool SetWindowPos(
            IntPtr hWnd,
            IntPtr hWndInsertAfter,
            int X, int Y, int cx, int cy,
            uint flags
        );
    }
}
"@
}
$ok = [LucyTopLauncher.Native]::SetWindowPos(
    [IntPtr]$terminal.MainWindowHandle,
    [IntPtr](-1),
    0,0,0,0,
    0x0001 -bor 0x0002 -bor 0x0010
)
if (-not $ok) {
    throw "Failed to make Lucy terminal topmost."
}
Write-Host "Lucy terminal is now always on top."
