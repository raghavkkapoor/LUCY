param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$Name,

    [int]$First = 100,

    [ValidateRange(0, 100)]
    [int]$MinScore = 55,

    [ValidateSet("Any", "File", "Folder", "App", "TrashItem")]
    [string]$Type = "Any",

    [switch]$Exact
)

$ErrorActionPreference = "Stop"

function Get-LucySearchRoot {
    $profile = [Environment]::GetFolderPath("UserProfile")

    @(
        [PSCustomObject]@{ Label = "Downloads"; Path = Join-Path $profile "Downloads" },
        [PSCustomObject]@{ Label = "Desktop"; Path = [Environment]::GetFolderPath("Desktop") },
        [PSCustomObject]@{ Label = "Documents"; Path = [Environment]::GetFolderPath("MyDocuments") },
        [PSCustomObject]@{ Label = "Pictures"; Path = [Environment]::GetFolderPath("MyPictures") },
        [PSCustomObject]@{ Label = "Music"; Path = [Environment]::GetFolderPath("MyMusic") },
        [PSCustomObject]@{ Label = "Videos"; Path = [Environment]::GetFolderPath("MyVideos") }
    ) | Where-Object { $_.Path -and (Test-Path -LiteralPath $_.Path) }
}

function Normalize-LucyName {
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }

    return $Text.ToLowerInvariant() -replace "[^a-z0-9]+", " "
}

function Get-LucyCollapsedName {
    param([string]$Text)
    return ((Normalize-LucyName $Text) -replace "\s+", "")
}

function Get-LucyTokens {
    param([string]$Text)

    @((Normalize-LucyName $Text) -split "\s+" | Where-Object { $_ })
}

function Get-LucyTokenVariants {
    param([string]$Token)

    $variants = New-Object System.Collections.Generic.HashSet[string]
    if ([string]::IsNullOrWhiteSpace($Token)) {
        return @()
    }

    [void]$variants.Add($Token)

    if ($Token.EndsWith("ies") -and $Token.Length -gt 4) {
        [void]$variants.Add($Token.Substring(0, $Token.Length - 3) + "y")
    }
    elseif ($Token.EndsWith("y") -and $Token.Length -gt 3) {
        [void]$variants.Add($Token.Substring(0, $Token.Length - 1) + "ies")
    }

    if ($Token.EndsWith("s") -and -not $Token.EndsWith("ss") -and $Token.Length -gt 3) {
        [void]$variants.Add($Token.Substring(0, $Token.Length - 1))
    }
    elseif ($Token.Length -gt 2) {
        [void]$variants.Add($Token + "s")
    }

    @($variants)
}

function Test-LucyTokenMatch {
    param(
        [string]$CandidateToken,
        [string]$SearchToken
    )

    if ($CandidateToken.Length -lt 3 -and $SearchToken.Length -gt 2) {
        return $false
    }

    $candidateVariants = Get-LucyTokenVariants $CandidateToken
    $searchVariants = Get-LucyTokenVariants $SearchToken

    foreach ($candidateVariant in $candidateVariants) {
        foreach ($searchVariant in $searchVariants) {
            if ($candidateVariant -eq $searchVariant -or
                ($searchVariant.Length -ge 3 -and $candidateVariant.Contains($searchVariant)) -or
                ($candidateVariant.Length -ge 3 -and $searchVariant.Contains($candidateVariant))) {
                return $true
            }

            $longer = [Math]::Max($candidateVariant.Length, $searchVariant.Length)
            $shorter = [Math]::Min($candidateVariant.Length, $searchVariant.Length)
            if ($longer -gt 0 -and ($shorter / $longer) -lt 0.78) {
                continue
            }

            $limit = if ($longer -le 5) { 1 } else { 2 }
            if ((Get-LucyEditDistance $candidateVariant $searchVariant $limit) -le $limit) {
                return $true
            }
        }
    }

    return $false
}

function Get-LucyEditDistance {
    param(
        [string]$Left,
        [string]$Right,
        [int]$Limit = 8
    )

    if ($Left -eq $Right) { return 0 }
    if ([string]::IsNullOrEmpty($Left)) { return $Right.Length }
    if ([string]::IsNullOrEmpty($Right)) { return $Left.Length }
    if ([Math]::Abs($Left.Length - $Right.Length) -gt $Limit) { return $Limit + 1 }

    $previous = 0..$Right.Length
    $current = New-Object int[] ($Right.Length + 1)

    for ($i = 1; $i -le $Left.Length; $i++) {
        $current[0] = $i
        $rowMin = $current[0]

        for ($j = 1; $j -le $Right.Length; $j++) {
            $cost = if ($Left[$i - 1] -eq $Right[$j - 1]) { 0 } else { 1 }
            $current[$j] = [Math]::Min(
                [Math]::Min($current[$j - 1] + 1, $previous[$j] + 1),
                $previous[$j - 1] + $cost
            )
            if ($current[$j] -lt $rowMin) { $rowMin = $current[$j] }
        }

        if ($rowMin -gt $Limit) { return $Limit + 1 }
        $temp = $previous
        $previous = $current
        $current = $temp
    }

    return $previous[$Right.Length]
}

function Get-LucyMatchScore {
    param(
        [string]$Candidate,
        [string]$SearchName,
        [bool]$ExactMatch
    )

    if ([string]::IsNullOrWhiteSpace($Candidate)) {
        return $null
    }

    if ($ExactMatch) {
        if ([string]::Equals($Candidate, $SearchName, [StringComparison]::OrdinalIgnoreCase)) {
            return [PSCustomObject]@{ Score = 100; Reason = "exact" }
        }
        return $null
    }

    if ($SearchName.IndexOfAny([char[]]"*?[]") -ge 0) {
        if ($Candidate -like $SearchName) {
            return [PSCustomObject]@{ Score = 95; Reason = "wildcard" }
        }
        return $null
    }

    $candidateNorm = Normalize-LucyName $Candidate
    $searchNorm = Normalize-LucyName $SearchName
    $candidateCollapsed = Get-LucyCollapsedName $Candidate
    $searchCollapsed = Get-LucyCollapsedName $SearchName
    $candidateTokens = Get-LucyTokens $Candidate
    $searchTokens = Get-LucyTokens $SearchName

    if (-not $searchCollapsed) {
        return $null
    }

    if ($candidateCollapsed -eq $searchCollapsed) {
        return [PSCustomObject]@{ Score = 100; Reason = "normalized exact" }
    }

    if ($candidateCollapsed.Contains($searchCollapsed)) {
        return [PSCustomObject]@{ Score = 92; Reason = "punctuation-insensitive contains" }
    }

    if ($searchTokens.Count -gt 0) {
        $matchedTokens = 0
        foreach ($searchToken in $searchTokens) {
            foreach ($candidateToken in $candidateTokens) {
                if (Test-LucyTokenMatch -CandidateToken $candidateToken -SearchToken $searchToken) {
                    $matchedTokens++
                    break
                }
            }
        }

        if ($matchedTokens -eq $searchTokens.Count) {
            return [PSCustomObject]@{ Score = 86; Reason = "fuzzy words" }
        }

        if ($matchedTokens -gt 0 -and $searchTokens.Count -gt 1) {
            $partialScore = [int](38 + (24 * $matchedTokens / $searchTokens.Count))
            return [PSCustomObject]@{ Score = $partialScore; Reason = "partial fuzzy words" }
        }
    }

    $length = [Math]::Max($candidateCollapsed.Length, $searchCollapsed.Length)
    $limit = [Math]::Max(1, [Math]::Min(8, [int][Math]::Ceiling($length * 0.28)))
    $distance = Get-LucyEditDistance $candidateCollapsed $searchCollapsed $limit
    if ($distance -le $limit) {
        $score = [Math]::Max(55, [int](88 - (38 * $distance / $length)))
        return [PSCustomObject]@{ Score = $score; Reason = "typo distance $distance" }
    }

    return $null
}

function Search-LucyNormalFolder {
    param(
        [PSCustomObject]$Root,
        [string]$SearchName,
        [bool]$ExactMatch
    )

    foreach ($item in Get-ChildItem -LiteralPath $Root.Path -Force -Recurse -ErrorAction SilentlyContinue) {
        $match = Get-LucyMatchScore -Candidate $item.Name -SearchName $SearchName -ExactMatch $ExactMatch
        if ($match) {
            [PSCustomObject]@{
                SearchRoot = $Root.Label
                RootRank   = $Root.Rank
                Score      = $match.Score
                Reason     = $match.Reason
                Type       = if ($item.PSIsContainer) { "Folder" } else { "File" }
                Name       = $item.Name
                Path       = $item.FullName
            }
        }
    }
}

function Search-LucyRecycleBin {
    param(
        [string]$SearchName,
        [bool]$ExactMatch
    )

    try {
        $shell = New-Object -ComObject Shell.Application
        $trash = $shell.NameSpace(10)
        if (-not $trash) {
            return
        }

        foreach ($item in $trash.Items()) {
            $match = Get-LucyMatchScore -Candidate $item.Name -SearchName $SearchName -ExactMatch $ExactMatch
            if (-not $match) {
                continue
            }

            $originalPath = $trash.GetDetailsOf($item, 1)
            [PSCustomObject]@{
                SearchRoot = "Trash"
                Score      = $match.Score
                Reason     = $match.Reason
                Type       = "TrashItem"
                Name       = $item.Name
                Path       = if ($originalPath) { $originalPath } else { $item.Path }
            }
        }
    }
    catch {
        Write-Warning "Could not search Trash: $($_.Exception.Message)"
    }
}

function Search-LucyInstalledApps {
    param(
        [string]$SearchName,
        [bool]$ExactMatch
    )

    $seen = New-Object System.Collections.Generic.HashSet[string]
    try {
        $shell = New-Object -ComObject Shell.Application
        $appsFolder = $shell.NameSpace("shell:AppsFolder")
        if ($appsFolder) {
            foreach ($appItem in $appsFolder.Items()) {
                if ([string]::IsNullOrWhiteSpace($appItem.Name)) {
                    continue
                }

                $match = Get-LucyMatchScore -Candidate $appItem.Name -SearchName $SearchName -ExactMatch $ExactMatch
                if (-not $match) {
                    continue
                }

                $key = "appsfolder::$($appItem.Name)::$($appItem.Path)"
                if (-not $seen.Add($key)) {
                    continue
                }

                [PSCustomObject]@{
                    SearchRoot = "Apps"
                    RootRank   = 6
                    Score      = $match.Score
                    Reason     = $match.Reason
                    Type       = "App"
                    Name       = $appItem.Name
                    Path       = if ($appItem.Path -match "^[A-Za-z]:\\") { $appItem.Path } else { "shell:AppsFolder\$($appItem.Path)" }
                }
            }
        }
    }
    catch { }

    $startMenuRoots = @(
        [Environment]::GetFolderPath("StartMenu"),
        [Environment]::GetFolderPath("CommonStartMenu")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) } | Select-Object -Unique

    foreach ($root in $startMenuRoots) {
        foreach ($shortcut in Get-ChildItem -LiteralPath $root -Filter "*.lnk" -Recurse -Force -ErrorAction SilentlyContinue) {
            $displayName = [IO.Path]::GetFileNameWithoutExtension($shortcut.Name)
            $match = Get-LucyMatchScore -Candidate $displayName -SearchName $SearchName -ExactMatch $ExactMatch
            if (-not $match) {
                continue
            }

            $key = "shortcut::$displayName::$($shortcut.FullName)"
            if (-not $seen.Add($key)) {
                continue
            }

            [PSCustomObject]@{
                SearchRoot = "Apps"
                RootRank   = 6
                Score      = $match.Score
                Reason     = $match.Reason
                Type       = "App"
                Name       = $displayName
                Path       = $shortcut.FullName
            }
        }
    }

    $registryRoots = @(
        "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*",
        "HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*"
    )

    foreach ($registryRoot in $registryRoots) {
        foreach ($app in Get-ItemProperty -Path $registryRoot -ErrorAction SilentlyContinue) {
            if ([string]::IsNullOrWhiteSpace($app.DisplayName)) {
                continue
            }

            $match = Get-LucyMatchScore -Candidate $app.DisplayName -SearchName $SearchName -ExactMatch $ExactMatch
            if (-not $match) {
                continue
            }

            $installPath = if ($app.InstallLocation) {
                $app.InstallLocation
            }
            elseif ($app.DisplayIcon) {
                ($app.DisplayIcon -replace '^\s*"', '') -replace '"?\s*,\d+\s*$', ''
            }
            else {
                $app.PSPath
            }

            $key = "registry::$($app.DisplayName)::$installPath"
            if (-not $seen.Add($key)) {
                continue
            }

            [PSCustomObject]@{
                SearchRoot = "Apps"
                RootRank   = 6
                Score      = $match.Score
                Reason     = $match.Reason
                Type       = "App"
                Name       = $app.DisplayName
                Path       = $installPath
            }
        }
    }
}

$results = New-Object System.Collections.Generic.List[object]
$rootIndex = 0

foreach ($root in Get-LucySearchRoot) {
    $root | Add-Member -NotePropertyName Rank -NotePropertyValue $rootIndex -Force
    $rootIndex++

    foreach ($match in Search-LucyNormalFolder -Root $root -SearchName $Name -ExactMatch $Exact.IsPresent) {
        if ($match.Score -lt $MinScore) {
            continue
        }
        $results.Add($match)
    }
}

foreach ($match in Search-LucyRecycleBin -SearchName $Name -ExactMatch $Exact.IsPresent) {
    if ($match.Score -lt $MinScore) {
        continue
    }
    $results.Add($match)
}

foreach ($match in Search-LucyInstalledApps -SearchName $Name -ExactMatch $Exact.IsPresent) {
    if ($match.Score -lt $MinScore) {
        continue
    }
    $results.Add($match)
}

$results |
    Where-Object { $Type -eq "Any" -or $_.Type -eq $Type } |
    Sort-Object @{ Expression = "Score"; Descending = $true }, RootRank, Type, Name |
    Select-Object -First $First -Property SearchRoot, Score, Reason, Type, Name, Path
