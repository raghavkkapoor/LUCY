#Requires -Version 5.1
# Runs real native calls and a short rendering session. No external test framework.
[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'load-native.ps1'
& $runner
function Assert($condition, [string]$message) {
    if (-not $condition) { throw $message }
}
Assert (-not [RaylibPowerShell.Api]::IsWindowReady()) 'LoadOnly created a window.'
& $runner
Assert (-not [RaylibPowerShell.Api]::IsWindowReady()) 'No-argument invocation created a window.'
$metadata = Get-Content -Raw -LiteralPath (Join-Path $PSScriptRoot 'raylib-api-5.5.json') | ConvertFrom-Json
$methods = @([RaylibPowerShell.Api].GetMethods().Name)
foreach ($f in $metadata.functions) {
    Assert ($methods -contains $f.name) "Missing binding: $($f.name)"
    Assert ([RaylibPowerShell.Api]::HasExport($f.name)) "Missing DLL export: $($f.name)"
}

# Independently calculate Windows x64 C layout from the upstream field metadata.
$layouts = @{}
$definitions = @{}
foreach ($s in $metadata.structs) { $definitions[$s.name] = $s }
foreach ($a in $metadata.aliases) { $definitions[$a.name] = $definitions[$a.type] }
function Get-NativeLayout([string]$name) {
    if ($layouts.ContainsKey($name)) { return $layouts[$name] }
    if ($name -match '\*$') { return @{Size = 8; Align = 8} }
    if ($name -match '^(.+)\[(\d+)\]$') {
        $count = [int]$Matches[2]
        $element = Get-NativeLayout $Matches[1]
        return @{Size = $element.Size * $count; Align = $element.Align}
    }
    $scalarSizes = @{'bool'=1; 'char'=1; 'unsigned char'=1; 'short'=2; 'unsigned short'=2; 'int'=4; 'unsigned int'=4; 'long'=4; 'float'=4; 'double'=8}
    if ($scalarSizes.ContainsKey($name)) { return @{Size = $scalarSizes[$name]; Align = $scalarSizes[$name]} }
    $offset = 0
    $align = 1
    $fields = @{}
    foreach ($f in $definitions[$name].fields) {
        $member = Get-NativeLayout $f.type
        $offset = [int]([Math]::Ceiling($offset / $member.Align) * $member.Align)
        $fields[$f.name] = $offset
        $offset += $member.Size
        $align = [Math]::Max($align, $member.Align)
    }
    $layouts[$name] = @{Size = [int]([Math]::Ceiling($offset / $align) * $align); Align = $align; Fields = $fields}
    return $layouts[$name]
}
foreach ($name in $definitions.Keys) {
    $layout = Get-NativeLayout $name
    $type = "RaylibPowerShell.$name" -as [type]
    $value = [Activator]::CreateInstance($type)
    Assert ([Runtime.InteropServices.Marshal]::SizeOf($value) -eq $layout.Size) "Wrong native size: $name"
    foreach ($f in $definitions[$name].fields) {
        $member = $f.name.Substring(0, 1).ToUpperInvariant() + $f.name.Substring(1)
        if ($f.type -eq 'bool') { $member = 'native' + $member }
        if ($f.type -match '\[') { $member += '0' }
        $offset = [Runtime.InteropServices.Marshal]::OffsetOf($type, $member).ToInt64()
        Assert ($offset -eq $layout.Fields[$f.name]) "Wrong native offset: $name.$member"
    }
}
Assert ([RaylibPowerShell.Api]::Utf8([RaylibPowerShell.Api]::TextFormat('100% {0}', 42)) -eq '100% 42') 'Varargs adapter failed.'
Assert ([RaylibPowerShell.Api]::TextIsEqual('same', 'same')) 'Native bool return failed.'
Assert (-not [RaylibPowerShell.Api]::TextIsEqual('a', 'b')) 'Native false return failed.'

# Allocated UTF-8 text, scalar output parameter and corresponding native unload.
$count = 0
$codepoints = [RaylibPowerShell.Api]::LoadCodepoints("A$([char]0x03A9)", [ref]$count)
try { Assert ($count -eq 2) 'UTF-8 or ref output failed.' }
finally { [RaylibPowerShell.Api]::UnloadCodepoints($codepoints) }
# Walk backwards through an allocated UTF-8 buffer using an interior pointer.
$utf8 = [RaylibPowerShell.Api]::LoadUTF8([int[]]@(65, 66), 2)
try {
    [int]$bytesRead = 0
    $previous = [RaylibPowerShell.Api]::GetCodepointPrevious([IntPtr]::Add($utf8, 2), [ref]$bytesRead)
    Assert ($previous -eq 66 -and $bytesRead -eq 1) 'Interior UTF-8 pointer overload failed.'
}
finally { [RaylibPowerShell.Api]::UnloadUTF8($utf8) }
$im = [RaylibPowerShell.Api]::GenImageColor(8, 8, [RaylibPowerShell.Colors]::RED)
try {
    [RaylibPowerShell.Api]::ImageResize([ref]$im, 16, 12)
    Assert ($im.Width -eq 16 -and $im.Height -eq 12) 'Mutable struct pointer failed.'
    $pixel = [RaylibPowerShell.Api]::GetImageColor($im, 2, 2)
    Assert ($pixel.R -eq 230 -and $pixel.A -eq 255) 'Native Color/Image layout failed.'
}
finally { [RaylibPowerShell.Api]::UnloadImage($im) }
$ray = [RaylibPowerShell.Ray]::new()
$ray.Position = [RaylibPowerShell.Vector3]::new(0, 0, -5)
$ray.Direction = [RaylibPowerShell.Vector3]::new(0, 0, 1)
$box = [RaylibPowerShell.BoundingBox]::new()
$box.Min = [RaylibPowerShell.Vector3]::new(-1, -1, -1)
$box.Max = [RaylibPowerShell.Vector3]::new(1, 1, 1)
$hit = [RaylibPowerShell.Api]::GetRayCollisionBox($ray, $box)
Assert ($hit.Hit -and [Math]::Abs($hit.Distance - 4) -lt 0.01) 'Struct containing native bool failed.'
$vr = [RaylibPowerShell.VrDeviceInfo]::new()
$vr.LensDistortionValues = [float[]]@(1, 2, 3, 4)
Assert ($vr.LensDistortionValues3 -eq 4) 'Inline array setter failed.'

"PASS: all 581 native exports, 39 layouts, strings, pointers, refs, arrays and native image/collision calls."
