$ErrorActionPreference = "Stop"
if (-not ("LucyTopmostLauncher.NativeMethods" -as [type])) {
    Add-Type @"
using System;
using System.Runtime.InteropServices;
namespace LucyTopmostLauncher {
    public static class NativeMethods {
        [DllImport("kernel32.dll")]
        public static extern IntPtr GetConsoleWindow();
        [DllImport("user32.dll")]
        public static extern bool SetWindowPos(
            IntPtr hWnd,
            IntPtr hWndInsertAfter,
            int X,
            int Y,
            int cx,
            int cy,
            uint uFlags
        );
        [DllImport("user32.dll")]
        public static extern IntPtr GetForegroundWindow();
    }
}
"@
}
$hwnd = [LucyTopmostLauncher.NativeMethods]::GetConsoleWindow()
if ($hwnd -eq [IntPtr]::Zero) {
    $hwnd = [LucyTopmostLauncher.NativeMethods]::GetForegroundWindow()
}
if ($hwnd -eq [IntPtr]::Zero) {
    throw "Could not identify terminal window."
}
$TOPMOST = [IntPtr](-1)
$flags = 0x0001 -bor 0x0002 -bor 0x0010
$result = [LucyTopmostLauncher.NativeMethods]::SetWindowPos(
    $hwnd,
    $TOPMOST,
    0, 0, 0, 0,
    $flags
)
if (-not $result) {
    throw "Failed to make terminal topmost."
}
$main = "C:\Users\ragha\Downloads\LUCY\LucyPython\main.py"
if (-not (Test-Path -LiteralPath $main)) {
    throw "main.py not found: $main"
}
Write-Host "LUCY TERMINAL TOPMOST = TRUE"
Write-Host "Starting main.py..."
python $main
