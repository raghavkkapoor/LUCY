$ErrorActionPreference = 'Continue'

$gmail = 'C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\gmail-service\gmail.ps1'
$result = 'C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\gmail-service\detached-test-result.txt'

Remove-Item -LiteralPath $result -Force -ErrorAction SilentlyContinue

$out = Join-Path $env:TEMP 'lucy_gmail_detached_stdout.txt'
$err = Join-Path $env:TEMP 'lucy_gmail_detached_stderr.txt'

Remove-Item $out,$err -Force -ErrorAction SilentlyContinue

$p = Start-Process powershell.exe `
    -ArgumentList @(
        '-NoProfile',
        '-ExecutionPolicy','Bypass',
        '-File',""$gmail"",
        '-Action','WhoAmI'
    ) `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -PassThru

$finished = $p.WaitForExit(12000)

if (-not $finished) {
    taskkill /PID $p.Id /T /F 2>$null | Out-Null

    @(
        'DETACHED_TEST_COMPLETE=True'
        'GMAIL_PROCESS_TIMEOUT=True'
        'SERVICE_RETURNED=False'
        'TEST_PASSED=False'
    ) | Set-Content -LiteralPath $result -Encoding UTF8

    exit
}

$stdout = if (Test-Path $out) {
    Get-Content $out -Raw -Encoding UTF8
} else { '' }

$stderr = if (Test-Path $err) {
    Get-Content $err -Raw -Encoding UTF8
} else { '' }

$auth = $stdout -match 'GMAIL_AUTHENTICATED=True'
$authPending = $stdout -match 'GMAIL_AUTH_REQUIRED=True'
$complete = $stdout -match 'GMAIL_CALL_COMPLETE=True'

@(
    'DETACHED_TEST_COMPLETE=True'
    "EXIT_CODE=$($p.ExitCode)"
    "GMAIL_PROCESS_TIMEOUT=False"
    "SERVICE_RETURNED=True"
    "AUTHENTICATED=$auth"
    "AUTHORIZATION_PENDING=$authPending"
    "CALL_COMPLETE=$complete"
    "TEST_PASSED=$([bool]($complete -and ($auth -or $authPending)))"
    '=== STDOUT ==='
    $stdout
    '=== STDERR ==='
    $stderr
) | Set-Content -LiteralPath $result -Encoding UTF8
