$ErrorActionPreference = "Stop"

$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    Start-Process -FilePath $python.Source -ArgumentList "`"$PSScriptRoot\cube.py`"" -WorkingDirectory $PSScriptRoot
}
else {
    $py = Get-Command py -ErrorAction Stop
    Start-Process -FilePath $py.Source -ArgumentList @("-3", "`"$PSScriptRoot\cube.py`"") -WorkingDirectory $PSScriptRoot
}

"RAYLIB_CUBE_LAUNCHED=True"
