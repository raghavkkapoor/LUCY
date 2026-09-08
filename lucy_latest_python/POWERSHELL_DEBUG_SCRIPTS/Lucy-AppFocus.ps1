param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$AppName,

    [Parameter(Mandatory = $true, Position = 1)]
    [ValidateNotNullOrEmpty()]
    [string]$Position
)

$ErrorActionPreference = "Stop"

Add-Type -AssemblyName System.Windows.Forms

if (-not ("LucyAppFocus.Native" -as [type])) {
    Add-Type @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

namespace LucyAppFocus {
    public static class Native {
        public delegate bool EnumWindowsProc(IntPtr hwnd, IntPtr lParam);

        [DllImport("user32.dll")] public static extern bool EnumWindows(EnumWindowsProc callback, IntPtr lParam);
        [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern bool IsIconic(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
        [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hwnd, out uint processId);
        [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr hwnd);
        [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr hwnd, int command);
        [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr hwnd, IntPtr insertAfter, int x, int y, int cx, int cy, uint flags);
        [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr hwnd, StringBuilder text, int maxLength);

        public struct Rect {
            public int Left;
            public int Top;
            public int Right;
            public int Bottom;
        }
    }
}
"@
}

function Find-LucyScript {
    param([string]$FileName)

    $directory = $PSScriptRoot
    while ($directory) {
        $candidate = Join-Path $directory $FileName
        if (Test-Path -LiteralPath $candidate) {
            return $candidate
        }

        $parent = Split-Path -Parent $directory
        if ($parent -eq $directory) {
            break
        }
        $directory = $parent
    }

    throw "Could not find $FileName."
}

function Resolve-LucyShortcutTarget {
    param([string]$Path)

    if (-not $Path.EndsWith(".lnk", [StringComparison]::OrdinalIgnoreCase)) {
        return $Path
    }

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($Path)
        if ($shortcut.TargetPath) {
            return $shortcut.TargetPath
        }
    }
    catch { }

    return $Path
}

function Start-LucyResolvedApp {
    param([string]$Path)

    if ($Path.StartsWith("shell:AppsFolder\", [StringComparison]::OrdinalIgnoreCase)) {
        Start-Process -FilePath "explorer.exe" -ArgumentList $Path | Out-Null
        return
    }

    Start-Process -FilePath $Path | Out-Null
}

function Normalize-LucyText {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    return $Text.ToLowerInvariant() -replace "[^a-z0-9]+", " "
}

function Test-LucyWindowTitleMatch {
    param(
        [string]$Title,
        [string]$AppDisplayName,
        [string]$UserAppName
    )

    $titleText = Normalize-LucyText $Title
    if (-not $titleText) {
        return $false
    }

    foreach ($name in @($AppDisplayName, $UserAppName)) {
        $tokens = @(Normalize-LucyText $name -split "\s+" | Where-Object { $_.Length -ge 3 })
        if ($tokens.Count -gt 0 -and @($tokens | Where-Object { $titleText.Contains($_) }).Count -gt 0) {
            return $true
        }
    }

    return $false
}

function Get-LucyWindowCandidate {
    param(
        [string]$ProcessName,
        [string]$AppDisplayName,
        [string]$UserAppName
    )

    $windows = New-Object System.Collections.Generic.List[object]
    $callback = [LucyAppFocus.Native+EnumWindowsProc]{
        param([IntPtr]$hwnd, [IntPtr]$lparam)

        if (-not [LucyAppFocus.Native]::IsWindowVisible($hwnd)) {
            return $true
        }

        $titleBuilder = New-Object System.Text.StringBuilder 512
        [void][LucyAppFocus.Native]::GetWindowText($hwnd, $titleBuilder, $titleBuilder.Capacity)
        $title = $titleBuilder.ToString()

        [uint32]$windowProcessId = 0
        [void][LucyAppFocus.Native]::GetWindowThreadProcessId($hwnd, [ref]$windowProcessId)

        $processMatches = $false
        if ($ProcessName) {
            try {
                $process = Get-Process -Id $windowProcessId -ErrorAction Stop
                $processMatches = $process.ProcessName -eq $ProcessName
            }
            catch { }
        }

        if (-not $processMatches -and -not (Test-LucyWindowTitleMatch -Title $title -AppDisplayName $AppDisplayName -UserAppName $UserAppName)) {
            return $true
        }

        $rect = New-Object LucyAppFocus.Native+Rect
        if (-not [LucyAppFocus.Native]::GetWindowRect($hwnd, [ref]$rect)) {
            return $true
        }

        $area = [Math]::Max(0, $rect.Right - $rect.Left) * [Math]::Max(0, $rect.Bottom - $rect.Top)
        $windows.Add([PSCustomObject]@{
            Hwnd = $hwnd
            Title = $title
            Area = $area
            ProcessId = $windowProcessId
        })

        return $true
    }

    [void][LucyAppFocus.Native]::EnumWindows($callback, [IntPtr]::Zero)
    $windows | Sort-Object Area -Descending | Select-Object -First 1
}

function Get-LucyTargetScreen {
    param([string]$Placement)

    $monitorMatch = [regex]::Match($Placement, "(?i)\bmonitor\s*(\d+)\b")
    if ($monitorMatch.Success) {
        $index = [int]$monitorMatch.Groups[1].Value - 1
        $screens = [System.Windows.Forms.Screen]::AllScreens
        if ($index -ge 0 -and $index -lt $screens.Count) {
            return $screens[$index]
        }
    }

    $cursor = [System.Windows.Forms.Cursor]::Position
    [System.Windows.Forms.Screen]::FromPoint($cursor)
}

function Get-LucyPlacementBounds {
    param(
        [string]$Placement,
        [System.Windows.Forms.Screen]$Screen
    )

    $positionText = (Normalize-LucyText $Placement).Trim()
    $positionText = ($positionText -replace "\bmonitor\s*\d+\b", "").Trim()
    $area = $Screen.WorkingArea

    switch ($positionText) {
        "top left" {
            return [Drawing.Rectangle]::new($area.Left, $area.Top, [int]($area.Width / 2), [int]($area.Height / 2))
        }
        "top right" {
            return [Drawing.Rectangle]::new($area.Left + [int]($area.Width / 2), $area.Top, [int]($area.Width / 2), [int]($area.Height / 2))
        }
        "bottom left" {
            return [Drawing.Rectangle]::new($area.Left, $area.Top + [int]($area.Height / 2), [int]($area.Width / 2), [int]($area.Height / 2))
        }
        "bottom right" {
            return [Drawing.Rectangle]::new($area.Left + [int]($area.Width / 2), $area.Top + [int]($area.Height / 2), [int]($area.Width / 2), [int]($area.Height / 2))
        }
        "top half" {
            return [Drawing.Rectangle]::new($area.Left, $area.Top, $area.Width, [int]($area.Height / 2))
        }
        "bottom half" {
            return [Drawing.Rectangle]::new($area.Left, $area.Top + [int]($area.Height / 2), $area.Width, [int]($area.Height / 2))
        }
        "left" {
            return [Drawing.Rectangle]::new($area.Left, $area.Top, [int]($area.Width / 2), $area.Height)
        }
        "left half" {
            return [Drawing.Rectangle]::new($area.Left, $area.Top, [int]($area.Width / 2), $area.Height)
        }
        "right" {
            return [Drawing.Rectangle]::new($area.Left + [int]($area.Width / 2), $area.Top, [int]($area.Width / 2), $area.Height)
        }
        "right half" {
            return [Drawing.Rectangle]::new($area.Left + [int]($area.Width / 2), $area.Top, [int]($area.Width / 2), $area.Height)
        }
        "focus" {
            return $null
        }
        "bring focus" {
            return $null
        }
        "minimize" {
            return $null
        }
        "minimized" {
            return $null
        }
        default {
            throw "Unsupported position '$Placement'. Use: top right, top left, right, left, bottom right, bottom left, top half, bottom half, focus, or minimize. You can also prefix monitor 2, like 'monitor 2 top right'."
        }
    }
}

function Invoke-LucyAppFocus {
    param(
        [string]$AppName,
        [string]$Position
    )

    $finder = Find-LucyScript "Lucy-FindFileOrFolderByName.ps1"
    $app = @(& $finder -Name $AppName -Type App -First 10 | Where-Object { $_.Type -eq "App" } | Sort-Object @{ Expression = "Score"; Descending = $true }, Name | Select-Object -First 1)
    if (-not $app) {
        throw "No installed app matched '$AppName'."
    }

    $launchPath = $app[0].Path
    $targetPath = Resolve-LucyShortcutTarget $launchPath
    $processName = if ($targetPath -and $targetPath.EndsWith(".exe", [StringComparison]::OrdinalIgnoreCase)) {
        [IO.Path]::GetFileNameWithoutExtension($targetPath)
    }
    else {
        $null
    }

    $window = Get-LucyWindowCandidate -ProcessName $processName -AppDisplayName $app[0].Name -UserAppName $AppName
    if (-not $window) {
        Start-LucyResolvedApp $launchPath

        for ($i = 0; $i -lt 80 -and -not $window; $i++) {
            Start-Sleep -Milliseconds 250
            $window = Get-LucyWindowCandidate -ProcessName $processName -AppDisplayName $app[0].Name -UserAppName $AppName
        }
    }

    if (-not $window) {
        throw "Launched '$($app[0].Name)', but no visible app window was found."
    }

    $positionText = (Normalize-LucyText $Position).Trim()
    if ($positionText -match "\bminimi[sz]e[ds]?\b") {
        [void][LucyAppFocus.Native]::ShowWindow($window.Hwnd, 6)
    }
    else {
        $screen = Get-LucyTargetScreen $Position
        $bounds = Get-LucyPlacementBounds -Placement $Position -Screen $screen

        [void][LucyAppFocus.Native]::ShowWindow($window.Hwnd, 9)
        if ($bounds) {
            [void][LucyAppFocus.Native]::SetWindowPos(
                $window.Hwnd,
                [IntPtr]::Zero,
                $bounds.Left,
                $bounds.Top,
                $bounds.Width,
                $bounds.Height,
                0x0040
            )
        }
        [void][LucyAppFocus.Native]::SetForegroundWindow($window.Hwnd)
    }

    [PSCustomObject]@{
        App        = $app[0].Name
        MatchScore = $app[0].Score
        Action     = $Position
        Hwnd       = $window.Hwnd.ToInt64()
        Path       = $launchPath
    }
}

function app_focus {
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [string]$app_name,

        [Parameter(Mandatory = $true, Position = 1)]
        [string]$position
    )

    Invoke-LucyAppFocus -AppName $app_name -Position $position
}

app_focus -app_name $AppName -position $Position
