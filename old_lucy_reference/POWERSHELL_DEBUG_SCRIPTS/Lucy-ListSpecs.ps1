Clear-Host

$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
$gpu = Get-CimInstance Win32_VideoController | Select-Object -First 1
$ram = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB, 0)
$os  = Get-CimInstance Win32_OperatingSystem
$drives = @(Get-PSDrive -PSProvider FileSystem)
$totalStorage = [math]::Round((($drives | ForEach-Object { $_.Used + $_.Free }) | Measure-Object -Sum).Sum / 1GB, 0)
$driveCount = $drives.Length

Write-Host ""
Write-Host "================ PC SPECS ================" -ForegroundColor White
Write-Host ""

Write-Host ("CPU         {0}" -f $cpu.Name.Trim())
Write-Host ("GPU         {0}" -f $gpu.Name)
Write-Host ("VRAM        {0} GB" -f [math]::Round($gpu.AdapterRAM / 1GB, 1))
Write-Host ("RAM         {0} GB" -f $ram)

Write-Host ("Storage     {0} GB total | {1} drive(s)" -f $totalStorage, $driveCount)

foreach ($drive in $drives) {
    $free = [math]::Round($drive.Free / 1GB, 0)
    Write-Host ("            {0}: {1} GB free" -f $drive.Name, $free)
}


Write-Host ("OS          {0}" -f $os.Caption)

Write-Host ""
Write-Host "==================== DISPLAY(S) ====================" -ForegroundColor White
Write-Host ""

$displays = Get-CimInstance Win32_VideoController |
    Where-Object { $_.CurrentHorizontalResolution -and $_.CurrentVerticalResolution }

$i = 0

foreach ($display in $displays) {
    $i++

    Write-Host ("Display {0} : {1} x {2} @ {3} Hz" -f `
        $i,
        $display.CurrentHorizontalResolution,
        $display.CurrentVerticalResolution,
        $display.CurrentRefreshRate
    )
}