## finds a file by name and/or type search on a drive specified and opens it.


function Open-DriveItem {
    param(
        [Parameter(Mandatory)]
        [Microsoft.Management.Infrastructure.CimInstance]$Drive,

        [string]$Name,
        [string]$FileType
    )

    if (-not $Drive -or -not $Drive.DriveLetter) {
        Write-Host "Missing drive." -ForegroundColor Red
        return $null
    }

    $root = "$($Drive.DriveLetter):\"

    if (-not $Name -and -not $FileType) {
        return
    }

    $items = Get-ChildItem -Path $root -Recurse -ErrorAction SilentlyContinue

    # If file type was specified, filter to that type.
    if ($FileType) {

        $ext = "." + $FileType.TrimStart(".")

        $typeMatches = $items | Where-Object {
            -not $_.PSIsContainer -and
            $_.Extension -ieq $ext
        }

        # No name specified -> return all files of that type.
        if (-not $Name) {

            $file = $typeMatches | Select-Object -First 1

            if ($file) {
                Start-Process $file.FullName
                return $file
            }

            return $null
        }
        # Search only inside that file type first.
        $items = $typeMatches
    }

    # If no name and no type, nothing to search.
    if (-not $Name) {
        Write-Host "Please specify either a file name or file type." -ForegroundColor Red
        return $null
    }

    $matches = foreach ($item in $items) {

        $itemName = $item.Name
        $score = 0

        if ($itemName -ieq $Name) {
            $score = 100
        }
        elseif ($itemName.StartsWith($Name, [StringComparison]::OrdinalIgnoreCase)) {
            $score = 80
        }
        elseif ($itemName.IndexOf($Name, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $score = 60
        }
        elseif ($Name.IndexOf($itemName, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $score = 40
        }

        if ($score -gt 0) {
            [PSCustomObject]@{
                Score = $score
                Item  = $item
            }
        }
    }

    $best = $matches |
        Sort-Object Score -Descending |
        Select-Object -First 1
          
    # If name was wrong but file type exists,
    # just use the first file of that type.
    if (-not $best -and $FileType) {

        $fallback = $items | Select-Object -First 1

        if ($fallback) {
            Start-Process $fallback.FullName
            return $fallback
        }
    }

    if (-not $best) {
        return $null
    }

    Start-Process $best.Item.FullName

    return $best.Item
}

