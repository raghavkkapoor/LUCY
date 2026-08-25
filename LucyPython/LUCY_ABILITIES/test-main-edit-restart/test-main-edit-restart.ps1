$ErrorActionPreference = "Stop"
$root = "C:\Users\ragha\Downloads\LUCY\LucyPython"
$main = Join-Path $root "main.py"
$exe = Join-Path $root "Lucy.exe"
$code = Get-Content -LiteralPath $main -Raw -Encoding UTF8
if (-not $code.Contains('LUCY_TEST_PRINT_2026_08_22: UPDATED MAIN.PY LOADED')) {
    throw "Expected test print is missing."
}
Start-Process -FilePath $exe -WorkingDirectory $root
Write-Output "LUCY_EXE_LAUNCHED=True"
