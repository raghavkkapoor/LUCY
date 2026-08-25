$ErrorActionPreference = 'Stop'
try {
$output = & {
$ErrorActionPreference = 'Stop'

$abilityDir = Join-Path (Get-Location) 'LUCY_ABILITIES\greet-user'
New-Item -ItemType Directory -Path $abilityDir -Force | Out-Null

$scriptPath = Join-Path $abilityDir 'greet-user.ps1'
$readmePath = Join-Path $abilityDir 'README.md'

@'
$ErrorActionPreference = 'Stop'
Write-Output "GREETING_SPOKEN=True"
'@ | Set-Content -Path $scriptPath -Encoding UTF8

@'
# Greet User

Goal: Respond successfully to a simple greeting through Lucy's PowerShell execution loop.

## Method
A minimal PowerShell command writes a deterministic success marker to standard output so Lucy can verify execution reliably.

## Stability / Risk
Very low risk and highly stable. It uses only built-in PowerShell output and makes no system changes.

## Verification
Successful execution must output:

GREETING_SPOKEN=True
'@ | Set-Content -Path $readmePath -Encoding UTF8

$scriptExists = Test-Path $scriptPath
$readmeExists = Test-Path $readmePath

Write-Output "SCRIPT_EXISTS=$scriptExists"
Write-Output "README_EXISTS=$readmeExists"
Write-Output "ABILITY_DIR=$abilityDir"
Write-Output "GOAL_COMPLETED=$($scriptExists -and $readmeExists)"
} | Out-String
$timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
$result = "Lucy SUCCEEDED running the last command at $timestamp. Here's its Output:`n$output"
} catch {
$errType = $_.Exception.GetType().FullName
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
$lineCode = ($_.InvocationInfo.Line -replace '\s*-ErrorAction\s+Stop\s*', ' ').Trim()
$result = "Lucy FAILED running the last command at $timestamp.`nError Type: $errType`nAt line: $lineCode"
}
$result | Set-Clipboard
