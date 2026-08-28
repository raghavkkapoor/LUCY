

# ============================================================
# ONE-TIME LUCY CHROME URL HANDLER SETUP
# ============================================================

$ErrorActionPreference = "Stop"

$HandlerExe = "C:\Users\ragha\OneDrive\Desktop\Lucy-UrlHandler.exe"

if (-not (Test-Path $HandlerExe)) {
    throw "LucyUrlHandler.exe not found at: $HandlerExe"
}

# ------------------------------------------------------------
# 1. Register Lucy URL protocol handler
# ------------------------------------------------------------

$ProgId = "LucyChromeURL"
$ProgRoot = "HKCU:\Software\Classes\$ProgId"

New-Item $ProgRoot -Force | Out-Null

Set-ItemProperty `
    -Path $ProgRoot `
    -Name "(Default)" `
    -Value "Lucy Chrome URL"

New-ItemProperty `
    -Path $ProgRoot `
    -Name "URL Protocol" `
    -Value "" `
    -PropertyType String `
    -Force | Out-Null

New-Item "$ProgRoot\shell\open\command" -Force | Out-Null

Set-ItemProperty `
    -Path "$ProgRoot\shell\open\command" `
    -Name "(Default)" `
    -Value "`"$HandlerExe`" `"%1`""

# ------------------------------------------------------------
# 2. Register Lucy Chrome as a Windows browser candidate
# ------------------------------------------------------------

$ClientRoot = "HKCU:\Software\Clients\StartMenuInternet\LucyChrome"

New-Item $ClientRoot -Force | Out-Null

Set-ItemProperty `
    -Path $ClientRoot `
    -Name "(Default)" `
    -Value "Lucy Chrome"

# ------------------------------------------------------------
# 3. Capabilities
# ------------------------------------------------------------

$Capabilities = "$ClientRoot\Capabilities"

New-Item $Capabilities -Force | Out-Null

Set-ItemProperty `
    -Path $Capabilities `
    -Name "ApplicationName" `
    -Value "Lucy Chrome"

Set-ItemProperty `
    -Path $Capabilities `
    -Name "ApplicationDescription" `
    -Value "Routes web links into Lucy's existing Chrome instance."

# ------------------------------------------------------------
# 4. HTTP / HTTPS associations
# ------------------------------------------------------------

$Associations = "$Capabilities\URLAssociations"

New-Item $Associations -Force | Out-Null

Set-ItemProperty `
    -Path $Associations `
    -Name "http" `
    -Value $ProgId

Set-ItemProperty `
    -Path $Associations `
    -Name "https" `
    -Value $ProgId

# ------------------------------------------------------------
# 5. Register application with Windows
# ------------------------------------------------------------

$RegisteredApps = "HKCU:\Software\RegisteredApplications"

if (-not (Test-Path $RegisteredApps)) {
    New-Item $RegisteredApps -Force | Out-Null
}

Set-ItemProperty `
    -Path $RegisteredApps `
    -Name "Lucy Chrome" `
    -Value "Software\Clients\StartMenuInternet\LucyChrome\Capabilities"

# ------------------------------------------------------------
# 6. Register Applications entry too
# ------------------------------------------------------------

$ApplicationRoot =
    "HKCU:\Software\Classes\Applications\LucyUrlHandler.exe"

New-Item "$ApplicationRoot\shell\open\command" -Force | Out-Null

Set-ItemProperty `
    -Path "$ApplicationRoot\shell\open\command" `
    -Name "(Default)" `
    -Value "`"$HandlerExe`" `"%1`""

# ------------------------------------------------------------
# DONE
# ------------------------------------------------------------

Write-Host ""
Write-Host "Lucy Chrome URL handler installed."
Write-Host ""
Write-Host "Handler:"
Write-Host "  $HandlerExe"
Write-Host ""
Write-Host "Now set Lucy Chrome as the default for:"
Write-Host "  HTTP"
Write-Host "  HTTPS"
Write-Host ""

Start-Process "ms-settings:defaultapps"