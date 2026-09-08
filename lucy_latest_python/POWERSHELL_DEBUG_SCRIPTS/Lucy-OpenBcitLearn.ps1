param(
    [int]$Port = 9223
)

$ErrorActionPreference = "Stop"

$targetUrl = "https://learn.bcit.ca/"
$baseUrl = "http://127.0.0.1:$Port"

function Expand-LucyItems {
    param([object]$Items)

    foreach ($item in @($Items)) {
        if ($item -is [Array]) {
            foreach ($child in $item) {
                $child
            }
        }
        else {
            $item
        }
    }
}

function Get-LucyChromePage {
    param([string]$UrlPrefix)

    $json = (Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/json/list" -TimeoutSec 3).Content
    $targets = Expand-LucyItems ($json | ConvertFrom-Json)
    foreach ($target in $targets) {
        if ($target.type -eq "page" -and $target.url -like "$UrlPrefix*") {
            return $target
        }
    }

    return $null
}

try {
    $version = Invoke-RestMethod -Uri "$baseUrl/json/version" -TimeoutSec 3
    if (-not $version.webSocketDebuggerUrl) {
        throw "Chrome on port $Port did not expose CDP."
    }

    $page = Get-LucyChromePage "https://learn.bcit.ca/"

    if (-not $page) {
        $escapedUrl = [Uri]::EscapeDataString($targetUrl)
        $page = Invoke-RestMethod -Uri "$baseUrl/json/new?$escapedUrl" -Method Put -TimeoutSec 5
    }

    if ($page.id) {
        try {
            Invoke-RestMethod -Uri "$baseUrl/json/activate/$($page.id)" -TimeoutSec 3 | Out-Null
        }
        catch { }
    }

    $verified = $null
    for ($i = 0; $i -lt 40 -and -not $verified; $i++) {
        Start-Sleep -Milliseconds 250
        $verified = Get-LucyChromePage "https://learn.bcit.ca/"
    }

    if (-not $verified) {
        throw "Chrome did not report a learn.bcit.ca page after navigation."
    }

    [PSCustomObject]@{
        Success = $true
        Port    = $Port
        Title   = $verified.title
        Url     = $verified.url
        Target  = $verified.id
    }
}
catch {
    throw "Could not open BCIT Learn on Chrome port $Port. $($_.Exception.Message)"
}
