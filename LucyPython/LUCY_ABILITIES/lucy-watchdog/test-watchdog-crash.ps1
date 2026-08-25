$ErrorActionPreference = 'SilentlyContinue'

$root = 'C:\Users\ragha\Downloads\LUCY\LucyPython'
$ability = 'C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\lucy-watchdog'
$resultFile = 'C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\lucy-watchdog\crash-test-result.txt'
$oldPid = 11112

Remove-Item -LiteralPath $resultFile -Force -ErrorAction SilentlyContinue

$beforeLogs = @(
    Get-ChildItem -LiteralPath (Join-Path $ability 'logs') -Filter '*.log' -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty FullName
)

# Give the current Lucy command enough time to finish returning this setup output.
Start-Sleep -Seconds 3

$oldStillExists = Get-Process -Id $oldPid -ErrorAction SilentlyContinue

if ($oldStillExists) {
    Stop-Process -Id $oldPid -Force
}

$killTime = Get-Date

# Wait up to 10 seconds for watchdog to create a NEW main.py process.
$newLucy = $null

for ($i = 0; $i -lt 100; $i++) {
    $newLucy = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object {
            $_.CommandLine -match 'LucyPython.*main\.py' -and
            $_.ProcessId -ne $oldPid
        } |
        Select-Object -First 1

    if ($newLucy) { break }

    Start-Sleep -Milliseconds 100
}

# Wait briefly for watchdog to finish appending crash metadata/email status.
Start-Sleep -Seconds 3

$afterLogs = @(
    Get-ChildItem -LiteralPath (Join-Path $ability 'logs') -Filter '*.log' -ErrorAction SilentlyContinue |
    Sort-Object LastWriteTime -Descending
)

$crashLog = $afterLogs |
    Where-Object {
        $beforeLogs -notcontains $_.FullName -or
        $_.LastWriteTime -ge $killTime.AddSeconds(-2)
    } |
    Select-Object -First 1

$logHasCrash = $false
$emailSent = $false
$emailId = ''

if ($crashLog) {
    $content = Get-Content -LiteralPath $crashLog.FullName -Raw -ErrorAction SilentlyContinue

    $logHasCrash = (
        $content -match 'CRASH_DETECTED=True' -or
        $content -match 'WATCHDOG DETECTED FAILURE' -or
        $content -match 'PROCESS EXIT'
    )

    if ($content -match 'EMAIL_SENT=True') {
        $emailSent = $true
    }

    if ($content -match 'EMAIL_MESSAGE_ID=([^\r\n]+)') {
        $emailId = $matches[1].Trim()
    }
}

$watchdogNow = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like '*lucy-watchdog*watchdog.py*' } |
    Select-Object -First 1

$restartPassed = [bool]($newLucy -and $newLucy.ProcessId -ne $oldPid)

@(
    "CONTROLLED_CRASH_TEST=True"
    "OLD_LUCY_PID=$oldPid"
    "OLD_PROCESS_KILLED=$(-not [bool](Get-Process -Id $oldPid -ErrorAction SilentlyContinue))"
    "WATCHDOG_STILL_RUNNING=$([bool]$watchdogNow)"
    "RESTART_PASSED=$restartPassed"
    "NEW_LUCY_PID=$(if ($newLucy) { $newLucy.ProcessId } else { '' })"
    "CRASH_LOG_FOUND=$([bool]$crashLog)"
    "CRASH_LOG=$(if ($crashLog) { $crashLog.FullName } else { '' })"
    "CRASH_RECORDED_IN_LOG=$logHasCrash"
    "EMAIL_SENT=$emailSent"
    "EMAIL_MESSAGE_ID=$emailId"
    "TESTED_AT=$(Get-Date -Format o)"
) | Set-Content -LiteralPath $resultFile -Encoding UTF8
