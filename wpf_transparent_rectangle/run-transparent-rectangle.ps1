$ErrorActionPreference = "Stop"

$project = Join-Path $PSScriptRoot "TransparentRectangle.csproj"
$app = Join-Path $PSScriptRoot "bin\Release\net8.0-windows\TransparentRectangleWpf.exe"

dotnet build $project --configuration Release
if ($LASTEXITCODE -ne 0) {
    throw "WPF build failed with exit code $LASTEXITCODE."
}

Start-Process -FilePath $app
