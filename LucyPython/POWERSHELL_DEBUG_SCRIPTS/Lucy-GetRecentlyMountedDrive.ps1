function Get-MostRecentlyMountedDrive {
    $candidates = foreach ($disk in Get-CimInstance Win32_DiskDrive) {

        $arrival = Get-PnpDeviceProperty `
            -InstanceId $disk.PNPDeviceID `
            -KeyName 'DEVPKEY_Device_LastArrivalDate' `
            -ErrorAction SilentlyContinue

        if (-not $arrival.Data) {
            continue
        }

        $partitions = Get-Partition -DiskNumber $disk.Index -ErrorAction SilentlyContinue |
            Where-Object DriveLetter

        foreach ($partition in $partitions) {

            $volume = Get-Volume -DriveLetter $partition.DriveLetter -ErrorAction SilentlyContinue

            if ($volume) {
                [PSCustomObject]@{
                    ArrivalTime = $arrival.Data
                    Volume      = $volume
                }
            }
        }
    }

    return (
        $candidates |
        Sort-Object ArrivalTime -Descending |
        Select-Object -First 1
    ).Volume
}

