Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$spotifyPath = "$env:APPDATA\Spotify\Spotify.exe"

Start-Process $spotifyPath
Start-Sleep -Seconds 4

$spotify = Get-Process Spotify |
    Where-Object { $_.MainWindowHandle -ne 0 } |
    Select-Object -First 1

if (-not $spotify) {
    Write-Host "Spotify window not found."
    exit
}

$root = [System.Windows.Automation.AutomationElement]::FromHandle(
    $spotify.MainWindowHandle
)

function Dump-UI($element, $depth = 0) {
    $indent = "  " * $depth

    try {
        $name = $element.Current.Name
        $type = $element.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
        $id   = $element.Current.AutomationId

        if ([string]::IsNullOrWhiteSpace($name)) {
            $name = "(unnamed)"
        }

        Write-Host "$indent[$type] $name" -NoNewline

        if ($id) {
            Write-Host "  {AutomationId: $id}"
        } else {
            Write-Host
        }

        $walker = [System.Windows.Automation.TreeWalker]::ControlViewWalker
        $child = $walker.GetFirstChild($element)

        while ($child) {
            Dump-UI $child ($depth + 1)
            $child = $walker.GetNextSibling($child)
        }
    }
    catch {}
}

Dump-UI $root