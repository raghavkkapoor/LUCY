Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or [IntPtr]::Size -ne 8) {
    throw 'Run this script in 64-bit PowerShell on Windows.'
}
if ($env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw 'Use x64 PowerShell (under emulation) on ARM64 Windows; this DLL is x64.'
}

$cache = Join-Path $env:LOCALAPPDATA 'RaylibPowerShell\5.5-win64'
$dll = Join-Path $cache 'raylib.dll'
$dllHash = 'C8D29FBDA31417B900BB0220CFB6C288544264A93764F5EA7CF5727FEEC76994'
$archiveHash = '8D046084D12353183E701EF4C9D276C21FCD3243C2A368091FABFB2769B8507C'
if (-not (Test-Path -LiteralPath $dll)) {
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $downloadDir = Join-Path $cache ([Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $downloadDir | Out-Null
    $previousTls = [Net.ServicePointManager]::SecurityProtocol
    try {
        [Net.ServicePointManager]::SecurityProtocol = $previousTls -bor [Net.SecurityProtocolType]::Tls12
        $zip = Join-Path $downloadDir 'raylib.zip'
        Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/raysan5/raylib/releases/download/5.5/raylib-5.5_win64_msvc16.zip' -OutFile $zip
        if ((Get-FileHash -LiteralPath $zip -Algorithm SHA256).Hash -ne $archiveHash) {
            throw 'The raylib download failed SHA256 verification.'
        }
        Expand-Archive -LiteralPath $zip -DestinationPath $downloadDir
        Copy-Item -LiteralPath (Join-Path $downloadDir 'raylib-5.5_win64_msvc16\lib\raylib.dll') -Destination $dll
    }
    finally {
        [Net.ServicePointManager]::SecurityProtocol = $previousTls
        # Only delete the unique temporary directory created by this invocation.
        $resolvedTemp = [IO.Path]::GetFullPath($downloadDir)
        $cachePrefix = [IO.Path]::GetFullPath($cache).TrimEnd('\') + '\'
        if ($resolvedTemp.StartsWith($cachePrefix, [StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}
if ((Get-FileHash -LiteralPath $dll -Algorithm SHA256).Hash -ne $dllHash) {
    throw "Cached raylib DLL failed SHA256 verification. Remove '$dll' and rerun to download it again."
}

$bindingsPath = Join-Path $PSScriptRoot 'Bindings.cs'
if (-not (Test-Path -LiteralPath $bindingsPath)) {
    throw "Missing '$bindingsPath'. Keep the raylib folder beside render-raylib.ps1."
}
$existingApi = 'RaylibPowerShell.Api' -as [type]
if ($existingApi) {
    $versionField = $existingApi.GetField('BindingVersion')
    if ($null -eq $versionField -or $versionField.GetRawConstantValue() -ne '5.5-complete-v1') {
        throw 'An older raylib binding is already loaded. Start a fresh PowerShell process.'
    }
}
else {
    Add-Type -TypeDefinition ([IO.File]::ReadAllText($bindingsPath))
}
[RaylibPowerShell.Api]::Load($dll)
