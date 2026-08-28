param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Name
)

$ErrorActionPreference = "Stop"

$LucyDir   = Join-Path $env:LOCALAPPDATA "Lucy"
$StateFile = Join-Path $LucyDir "chrome_state.json"

if (-not (Test-Path $StateFile)) {
    throw "Lucy Chrome state not found. Run Manage-LucyChrome.ps1 first."
}

$state = Get-Content $StateFile -Raw | ConvertFrom-Json
$port  = $state.Port

$targets = Invoke-RestMethod "http://127.0.0.1:$port/json/list"

$pages = @(
    $targets | Where-Object {
        $_.type -eq "page" -and
        $_.webSocketDebuggerUrl
    }
)

if ($pages.Count -eq 0) {
    throw "No Chrome tabs found."
}

$query = $Name.ToLowerInvariant()

$results = foreach ($page in $pages) {

    $title = [string]$page.title
    $url   = [string]$page.url

    $score = 0

    if ($url.ToLowerInvariant().Contains($query)) {
        $score += 100
    }

    if ($title.ToLowerInvariant().Contains($query)) {
        $score += 80
    }

    foreach ($word in ($query -split '\s+')) {

        if ($word.Length -lt 2) {
            continue
        }

        if ($url.ToLowerInvariant().Contains($word)) {
            $score += 20
        }

        if ($title.ToLowerInvariant().Contains($word)) {
            $score += 15
        }
    }

    [PSCustomObject]@{
        Score                = $score
        Id                   = $page.id
        Title                = $page.title
        Url                  = $page.url
        WebSocketDebuggerUrl = $page.webSocketDebuggerUrl
    }
}

$best = $results |
    Sort-Object Score -Descending |
    Select-Object -First 1

if (-not $best -or $best.Score -le 0) {
    throw "No matching tab found for '$Name'."
}

$best