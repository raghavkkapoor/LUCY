$ErrorActionPreference = 'Continue'
$root = 'C:\Users\ragha\Downloads\LUCY\LucyPython'
$main = Join-Path $root 'main.py'
$stdout = 'C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\main-crash-diagnostics\main-stdout.log'
$stderr = 'C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\main-crash-diagnostics\main-stderr.log'
Remove-Item -LiteralPath $stdout,$stderr -Force -ErrorAction SilentlyContinue
$p = Start-Process 
    -FilePath 'python.exe' 
    -ArgumentList "-X utf8 "$main"" 
    -WorkingDirectory $root 
    -PassThru 
    -RedirectStandardOutput $stdout 
    -RedirectStandardError $stderr
"MAIN_PID=$($p.Id)" | Set-Content -LiteralPath (Join-Path $root 'LucyMainDiagnosticState.txt') -Encoding UTF8
"STARTED=$(Get-Date -Format o)" | Add-Content -LiteralPath (Join-Path $root 'LucyMainDiagnosticState.txt') -Encoding UTF8
$p.WaitForExit()
"EXIT_CODE=$($p.ExitCode)" | Add-Content -LiteralPath (Join-Path $root 'LucyMainDiagnosticState.txt') -Encoding UTF8
"EXITED=$(Get-Date -Format o)" | Add-Content -LiteralPath (Join-Path $root 'LucyMainDiagnosticState.txt') -Encoding UTF8
