#Requires -Version 5.1
# Integration test: actual windows and screenshot pixels, including a polluted caller.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
function Assert($condition, [string]$message) { if (-not $condition) { throw $message } }
Add-Type -AssemblyName System.Drawing
if (-not ('RaylibPowerShell.Api' -as [type])) {
    Add-Type -TypeDefinition 'namespace RaylibPowerShell { public static class Api { public const string Legacy = "old binding"; } }'
}
Assert ([RaylibPowerShell.Api].GetField('Legacy')) 'Run this test in a fresh PowerShell process.'
$testDirectory = Join-Path $env:TEMP ("raylib test [literal] user's " + [Guid]::NewGuid().ToString('N'))
[IO.Directory]::CreateDirectory((Join-Path $testDirectory 'raylib')) | Out-Null
$runner = Join-Path $testDirectory 'render-raylib.ps1'
[IO.File]::Copy((Join-Path (Split-Path $PSScriptRoot -Parent) 'render-raylib.ps1'), $runner)
foreach ($name in @('Bindings.cs', 'load-native.ps1', 'ipc.ps1', 'renderer-host.ps1', 'compile-command.ps1', 'command-prelude.h', 'NativeScene.cs', 'raylibdll.lib')) {
    [IO.File]::Copy((Join-Path $PSScriptRoot $name), (Join-Path $testDirectory ('raylib\' + $name)))
}
[IO.Directory]::CreateDirectory((Join-Path $testDirectory 'raylib\include')) | Out-Null
foreach ($name in @('raylib.h', 'raymath.h', 'rlgl.h')) {
    [IO.File]::Copy((Join-Path $PSScriptRoot ('include\' + $name)), (Join-Path $testDirectory ('raylib\include\' + $name)))
}
$command = Join-Path $testDirectory 'raylib current command.txt'
function Set-Calls([string]$color) {
    [IO.File]::WriteAllText($command, "[RaylibPowerShell.Api]::DrawRectangle(20,20,60,60,[RaylibPowerShell.Colors]::$color)")
}
function Assert-Pixel([string]$path, [int]$r, [int]$g, [int]$b) {
    $bitmap = [Drawing.Bitmap]::new($path)
    try {
        $pixel = $bitmap.GetPixel(40, 40)
        Assert ($pixel.R -eq $r -and $pixel.G -eq $g -and $pixel.B -eq $b) "Wrong rendered pixel in $path : $pixel"
    }
    finally { $bitmap.Dispose() }
}
$instances = [Collections.Generic.List[string]]::new()
try {
    Set-Calls RED
    $redPath = Join-Path $env:TEMP ('raylib-red-' + [Guid]::NewGuid().ToString('N') + '.png')
    $a = & $runner -Mode New -Width 320 -Height 240 -DurationSeconds 60 -ScreenshotPath $redPath
    $instances.Add($a.InstanceId)
    Assert-Pixel $redPath 230 41 55
    Set-Calls GREEN
    $greenPath = Join-Path $env:TEMP ('raylib-green-' + [Guid]::NewGuid().ToString('N') + '.png')
    $updated = & $runner -Mode Override -InstanceId $a.InstanceId -ScreenshotPath $greenPath
    Assert ($updated.ProcessId -eq $a.ProcessId -and $updated.WindowHandle -eq $a.WindowHandle) 'Override replaced the native process/window.'
    Assert-Pixel $greenPath 0 228 48
    Set-Calls BLUE
    $bluePath = Join-Path $env:TEMP ('raylib-blue-' + [Guid]::NewGuid().ToString('N') + '.png')
    $b = & $runner -Mode New -Width 320 -Height 240 -DurationSeconds 60 -ScreenshotPath $bluePath
    $instances.Add($b.InstanceId)
    Assert ($a.ProcessId -ne $b.ProcessId -and $a.WindowHandle -ne $b.WindowHandle) 'New reused an existing native window.'
    Assert-Pixel $bluePath 0 121 241
    Set-Calls GOLD
    $latest = & $runner -Mode Override
    Assert ($latest.InstanceId -eq $b.InstanceId) 'Override did not choose the latest created window.'
    [IO.File]::WriteAllText($command, '[RaylibPowerShell.Api]::DrawCircle(')
    try { & $runner -Mode Override -InstanceId $a.InstanceId | Out-Null; throw 'Syntax error was accepted' }
    catch { Assert ($_.Exception.Message -ne 'Syntax error was accepted') 'Syntax error was accepted.' }
    [IO.File]::WriteAllText($command, "throw 'Expected rendering error'")
    try { & $runner -Mode Override -InstanceId $a.InstanceId -Language PowerShell | Out-Null; throw 'Runtime error was accepted' }
    catch { Assert ($_.Exception.Message -match 'Expected rendering error') 'Runtime error was not returned to the caller.' }
    $recovered = & $runner -Mode Override -InstanceId $a.InstanceId -Calls '[RaylibPowerShell.Api]::DrawPixel(0,0,[RaylibPowerShell.Colors]::RED)'
    Assert ($recovered.WindowHandle -eq $a.WindowHandle) 'Window could not recover after a bad command.'
    # Real C, including compound literals, imports, pasted Markdown and escaped underscores.
    $nativeCode = @'
Camera3D camera = {0};
camera.position = (Vector3){0.0f, 10.0f, 10.0f};
camera.target = Vector3Add((Vector3){0}, (Vector3){0});
camera.up = (Vector3){0,1,0};
camera.fovy = 45.0f;
camera.projection = CAMERA\_PERSPECTIVE;
BeginDrawing();
ClearBackground(RAYWHITE);
BeginMode3D(camera);
```scss
rlDisableBackfaceCulling();
DrawCone((Vector3){0}, 1.0f, 2.0f, 6, BLUE);
rlEnableBackfaceCulling();
```
EndMode3D();
for (int i = 0; i < 3; i++) DrawRectangle(20+i,20,60,60,RED);
DrawText(TextFormat("%i", 42), 100, 20, 20, BLACK);
EndDrawing();
'@
    $nativeCode += "`n// Tested with PowerShell $($PSVersionTable.PSVersion)"
    [IO.File]::WriteAllText($command, $nativeCode)
    $cPath = Join-Path $env:TEMP ('raylib-c-' + [Guid]::NewGuid().ToString('N') + '.png')
    $cScene = & $runner -Mode Override -InstanceId $a.InstanceId -ScreenshotPath $cPath
    Assert ($cScene.Language -eq 'C') 'C language detection failed.'
    Assert ($cScene.WindowHandle -eq $a.WindowHandle -and $cScene.ProcessId -eq $a.ProcessId) 'C override replaced the native window.'
    Assert-Pixel $cPath 230 41 55
    try { & $runner -Mode Override -InstanceId $a.InstanceId -Language C -Calls 'DrawFunctionThatDoesNotExist();' | Out-Null; throw 'Invalid C was accepted' }
    catch { Assert ($_.Exception.Message -match 'C compilation failed') 'C compiler error was not reported.' }
    $sameScene = & $runner -Mode Override -InstanceId $a.InstanceId -Language C -Calls 'DrawRectangle(20,20,60,60,GREEN);' -ScreenshotPath $cPath
    Assert ($sameScene.WindowHandle -eq $a.WindowHandle) 'C compiler error destroyed the window.'
    Assert-Pixel $cPath 0 228 48
    [IO.File]::WriteAllText($command, '# No drawing calls')
    $blankPath = Join-Path $env:TEMP ('raylib-blank-' + [Guid]::NewGuid().ToString('N') + '.png')
    $blank = & $runner -ScreenshotPath $blankPath
    Assert ($blank.InstanceId -eq $b.InstanceId) 'Default invocation did not override the latest window.'
    Assert-Pixel $blankPath 18 22 33
    Assert ([RaylibPowerShell.Api]::Legacy -eq 'old binding') 'Launcher replaced or depended on the caller bindings.'
    & $runner -Mode Close -InstanceId $a.InstanceId | Out-Null
    [void]$instances.Remove($a.InstanceId)
    & $runner -Mode Close -InstanceId $b.InstanceId | Out-Null
    [void]$instances.Remove($b.InstanceId)
    try { & $runner -Mode Override -InstanceId $a.InstanceId | Out-Null; throw 'Closed instance was accepted' }
    catch { Assert ($_.Exception.Message -match 'No live renderer') 'Closed instance detection failed.' }
    $c = & $runner -DurationSeconds 60
    $instances.Add($c.InstanceId)
    Assert ($c.Mode -eq 'New') 'Override did not open a window when none existed.'
    'PASS: C and PowerShell calls, C11 literals/loops, Markdown cleanup, raymath/rlgl, New/Override (same PID/HWND), compile errors, multiple windows, Close, polluted caller.'
}
finally {
    foreach ($id in $instances) { & $runner -Mode Close -InstanceId $id | Out-Null }
}
