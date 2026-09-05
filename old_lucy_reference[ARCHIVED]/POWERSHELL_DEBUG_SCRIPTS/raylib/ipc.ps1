# Internal helpers; no raylib types are loaded in the launcher.
function Get-RaylibSessionRoot([string]$directory) {
    $hash = [Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [Text.Encoding]::UTF8.GetBytes([IO.Path]::GetFullPath($directory).ToLowerInvariant())
        $key = ([BitConverter]::ToString($hash.ComputeHash($bytes))).Replace('-', '').Substring(0, 24)
        return Join-Path $env:LOCALAPPDATA ('RaylibPowerShell\sessions\' + $key)
    }
    finally { $hash.Dispose() }
}
function Write-RaylibJson([string]$path, $value) {
    $temporary = $path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    $backup = $temporary + '.bak'
    try {
        [IO.File]::WriteAllText($temporary, (ConvertTo-Json -InputObject $value -Depth 8 -Compress), [Text.UTF8Encoding]::new($false))
        if ([IO.File]::Exists($path)) { [IO.File]::Replace($temporary, $path, $backup) }
        else { [IO.File]::Move($temporary, $path) }
    }
    finally {
        if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) }
        if ([IO.File]::Exists($backup)) { [IO.File]::Delete($backup) }
    }
}
function Read-RaylibJson([string]$path) {
    return ConvertFrom-Json -InputObject ([IO.File]::ReadAllText($path))
}
function Test-RaylibProcess($state) {
    if ($state.Status -ne 'Running') { return $false }
    try {
        $process = Get-Process -Id $state.ProcessId -ErrorAction Stop
        return $process.StartTime.ToUniversalTime().Ticks.ToString() -eq $state.StartTimeUtcTicks
    }
    catch { return $false }
}
