$ErrorActionPreference = 'Stop'
try {
    # Run the block normally. If it fails, -ErrorAction Stop will immediately trigger 'catch'.
    # If it succeeds, the output is saved to $output.
    $output = & {Get-Acl 
    -ErrorAction Stop} | Out-String
    $timestamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    $result = "Lucy SUCCEEDED running the last command at $timestamp. Here's its Output:`n$output"
} catch {
    $errType = $_.Exception.GetType().FullName
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $lineCode = ($_.InvocationInfo.Line -replace '\s*-ErrorAction\s+Stop\s*', ' ').Trim()
    $result = "Lucy FAILED running the last command at $timestamp.`nError Type: $errType`nAt line: $lineCode"
}
$result | Set-Clipboard

Clear-Host



