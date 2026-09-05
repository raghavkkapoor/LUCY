#Requires -Version 5.1
# Compile real C11 into a scene DLL before any command is sent to a live renderer.
param([Parameter(Mandatory)][AllowEmptyString()][string]$Code)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Remove only Markdown fence lines. Preserve line numbers for C diagnostics.
$normalized = [regex]::Replace($Code, '(?m)^\s*```[^\r\n]*', '')
# Unescape underscores in identifiers, without modifying strings or comments.
$tokens = '"(?:\\.|[^"\\])*"|''(?:\\.|[^''\\])*''|//[^\r\n]*|/\*[\s\S]*?\*/|[A-Za-z_]\w*(?:\\_\w+)+'
$normalized = [regex]::Replace($normalized, $tokens, [Text.RegularExpressions.MatchEvaluator]{
    param($match)
    if ($match.Value -match '^[A-Za-z_]') { return $match.Value.Replace('\_', '_') }
    return $match.Value
})
$prelude = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'command-prelude.h'))
$source = $prelude + "`n__declspec(dllexport) void RaylibCommandFrame(double rlTime, float rlDeltaTime, int rlFrame, int rlWidth, int rlHeight, int rlFirstFrame) {`n#line 1 `"raylib current command.txt`"`n" + $normalized + "`n}`n"
$hash = [Security.Cryptography.SHA256]::Create()
try {
    $identity = $source
    foreach ($name in @('include\raylib.h', 'include\raymath.h', 'include\rlgl.h', 'raylibdll.lib')) {
        $identity += (Get-FileHash -LiteralPath (Join-Path $PSScriptRoot $name) -Algorithm SHA256).Hash
    }
    $key = ([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($identity)))).Replace('-', '').ToLowerInvariant()
}
finally { $hash.Dispose() }
$cache = Join-Path $env:LOCALAPPDATA ('RaylibPowerShell\compiled\' + $key)
$dllPath = Join-Path $cache 'scene.dll'
if ([IO.File]::Exists($dllPath)) { return $dllPath }

$vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not [IO.File]::Exists($vswhere)) { throw 'C calls require Visual Studio C++ Build Tools with the Windows SDK.' }
$installation = & $vswhere -latest -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $installation) { throw 'Install the Desktop development with C++ workload to compile C calls.' }
$vcvars = Join-Path $installation 'VC\Auxiliary\Build\vcvars64.bat'
if (-not [IO.File]::Exists($vcvars)) { throw "Missing compiler environment: $vcvars" }
[IO.Directory]::CreateDirectory($cache) | Out-Null
$build = Join-Path $cache ([Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory($build) | Out-Null
$sourceFile = Join-Path $build 'command.c'
$outputFile = Join-Path $build 'scene.dll'
[IO.File]::WriteAllText($sourceFile, $source, [Text.UTF8Encoding]::new($false))
# Source and paths go through a compiler response file, never interpolated as shell code.
$arguments = @('/nologo', '/LD', '/std:c11', '/utf-8', '/O2', '/MT', '/DUSE_LIBTYPE_SHARED', '/D_CRT_SECURE_NO_WARNINGS', '/we4013')
$arguments += '/I"' + (Join-Path $PSScriptRoot 'include') + '"'
$arguments += '"' + $sourceFile + '"'
$arguments += '/Fo"' + (Join-Path $build 'command.obj') + '"'
$arguments += '/Fe"' + $outputFile + '"'
$arguments += '/link'
$arguments += '"' + (Join-Path $PSScriptRoot 'raylibdll.lib') + '"'
$arguments += '/IMPLIB:"' + (Join-Path $build 'scene.lib') + '"'
$response = Join-Path $build 'compile.rsp'
[IO.File]::WriteAllText($response, ($arguments -join ' '), [Text.Encoding]::Unicode)
# Only fixed tool paths enter cmd, with delayed expansion disabled and literal percent escaping.
$batch = Join-Path $build 'compile.cmd'
$batchText = '@echo off' + "`r`nsetlocal DisableDelayedExpansion`r`ncall `"" + $vcvars.Replace('%', '%%') + "`" >nul`r`nif errorlevel 1 exit /b 1`r`ncl.exe @`"" + $response.Replace('%', '%%') + "`"`r`nexit /b %errorlevel%`r`n"
[IO.File]::WriteAllText($batch, $batchText, [Text.Encoding]::Default)
$compilerOutput = & $env:ComSpec /d /c $batch 2>&1
$exitCode = $LASTEXITCODE
[IO.File]::WriteAllText((Join-Path $build 'compile.log'), ($compilerOutput -join "`r`n"))
if ($exitCode -ne 0 -or -not [IO.File]::Exists($outputFile)) {
    throw ("C compilation failed. The existing window is unchanged.`n" + (($compilerOutput | Select-Object -First 40) -join "`n") + "`nFull log: $build\compile.log")
}
try { [IO.File]::Move($outputFile, $dllPath) }
catch { if (-not [IO.File]::Exists($dllPath)) { throw } }
return $dllPath
