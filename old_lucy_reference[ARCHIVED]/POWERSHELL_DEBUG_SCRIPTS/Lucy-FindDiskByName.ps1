function Find-Drive {
        param(
            [Parameter(Mandatory)]
            [string]$Name
        )

        $name = $Name.Trim().TrimEnd(':')

        $drives = Get-Volume | Where-Object DriveLetter

        $matches = foreach ($drive in $drives) {

        $label  = [string]$drive.FileSystemLabel
        $letter = [string]$drive.DriveLetter

        $score = 0

        if ($label -ieq $name -or $letter -ieq $name) {
            $score = 100
        }
        elseif ($label.StartsWith($name, 'OrdinalIgnoreCase')) {
            $score = 80
        }
        elseif ($label.IndexOf($name, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $score = 60
        }
        elseif ($name.IndexOf($label, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
            $score = 40
        }

        if ($score -gt 0) {
            [PSCustomObject]@{
                Score = $score
                Drive = $drive
            }
        }
    }

    [Microsoft.Management.Infrastructure.CimInstance]$result = (
        $matches |
        Sort-Object Score -Descending |
        Select-Object -First 1
    ).Drive

    return $result
}