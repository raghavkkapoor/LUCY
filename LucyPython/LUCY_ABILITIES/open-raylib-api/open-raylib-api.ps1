$ErrorActionPreference = "Stop"

$root = (Get-Location).Path
$raylibDir = Join-Path $root "raylib-api"
$header = Join-Path $raylibDir "raylib.h"
$url = "https://raw.githubusercontent.com/raysan5/raylib/master/src/raylib.h"

New-Item -ItemType Directory -Force -Path $raylibDir | Out-Null
Invoke-WebRequest -Uri $url -OutFile $header -UseBasicParsing

if (!(Test-Path $header) -or (Get-Item $header).Length -lt 10000) {
    throw "Failed to obtain a valid raylib.h API header."
}

Start-Process notepad.exe -ArgumentList "`"$header`""

Write-Output "RAYLIB_API_OPENED=True"
Write-Output "HEADER=$header"
