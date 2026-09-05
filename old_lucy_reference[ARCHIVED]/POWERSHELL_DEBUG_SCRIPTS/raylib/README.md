# raylib command renderer

Edit `raylib current command.txt` next to `render-raylib.ps1` in
`old_lucy_reference[ARCHIVED]\POWERSHELL_DEBUG_SCRIPTS`.
The file accepts **C raylib calls directly**, with the types, constants, and functions
already included. No PowerShell namespace prefixes or `.ps1` command file are needed.
The current file contains the supplied aircraft snippet.

```c
Camera3D camera = {0};
camera.position = (Vector3){0.0f, 10.0f, 10.0f};
camera.target = (Vector3){0};
camera.up = (Vector3){0, 1, 0};
camera.fovy = 45;
camera.projection = CAMERA_PERSPECTIVE;

BeginDrawing();
ClearBackground(RAYWHITE);
BeginMode3D(camera);
DrawCube((Vector3){0}, 2, 2, 2, RED);
EndMode3D();
EndDrawing();
```

Run from the debug scripts folder:

```powershell
.\render-raylib.ps1 -Mode New       # Another independent window
.\render-raylib.ps1 -Mode Override  # Apply the current text to the latest window
```

Save changes and run Override to apply them. Editing the file alone does not change
a window. Override preserves the native window and process. If no managed window
exists it opens one. New windows retain independent command snapshots.

To select a particular window:

```powershell
$window = .\render-raylib.ps1 -Mode New
.\render-raylib.ps1 -Mode Override -InstanceId $window.InstanceId
.\render-raylib.ps1 -Mode Close -InstanceId $window.InstanceId
```

The launcher returns after the first successful frame. Escape and the window close
button work. Without an ID, Override/Close select the latest-created live managed
window from this launcher directory. Old, unrelated demo windows are separate.

## C snippet environment

- Real C11 compilation, using the installed Visual Studio C++ toolchain and Windows
  SDK. The Desktop development with C++ workload is required on another computer.
  Compiled results are cached; repeat submissions reuse the scene DLL.
- `raylib.h`, `raymath.h`, `rlgl.h`, and common C standard headers are included.
  All 581 raylib 5.5 functions use their original C signatures. Ordinary declarations,
  compound literals, pointers, loops, conditions, and C format strings work.
- Paste statements for one frame, not a complete `main()` program or an infinite
  rendering loop. The host owns window creation and the outer frame loop.
- Copied `BeginDrawing()` / `EndDrawing()` calls are accepted as no-ops inside the
  snippet. The host begins and presents exactly once, and captures screenshots
  before swapping buffers. Do not create or close the window inside a snippet.
- `DrawCone(position, radius, height, slices, color)` is an added convenience helper,
  not a raylib API. It uses `DrawCylinder` with a zero top radius and points along +Y.
- Markdown fence lines such as triple-backtick `scss` are discarded. Escaped
  underscores in identifiers, such as `CAMERA\_PERSPECTIVE`, are normalized.
  C strings and comments are preserved. The complete supplied snippet is supported.
- Available frame variables: `rlTime` (double), `rlDeltaTime` (float), `rlFrame`,
  `rlWidth`, `rlHeight`, `rlFirstFrame` (integers). raylib's `GetTime()` and
  `GetFrameTime()` also work. Ordinary local variables reset each frame; use C
  `static` locals for persistent state. The same cached snippet retains its statics
  when resubmitted to the same window.
- Resource ownership remains normal raylib C ownership: unload allocations when
  finished and detach callbacks before abandoning their state. Scene modules stay
  loaded until window-process exit so outstanding native callback code stays valid.
- Compile errors refer to lines in `raylib current command.txt` and are returned
  before dispatch, leaving the live scene unchanged. Native misuse can still crash
  that isolated window process.

## Options

`-Width`, `-Height`, `-Title`, `-TargetFPS` (default 30), `-BackgroundColor` (packed
RGBA), `-DurationSeconds` (zero means indefinite), and `-ScreenshotPath` (PNG) are
available. Override preserves omitted options. Supplying DurationSeconds restarts
its timer. ScreenshotPath overwrites that file with the submitted scene's first frame.

Direct command text can also be supplied without editing the file:

```powershell
.\render-raylib.ps1 -Mode New -Calls 'ClearBackground(RAYWHITE); DrawCircle(200,200,60,RED);'
```

`-Language Auto` is the default: plain calls use C, while recognizable PowerShell
syntax uses the existing PowerShell bindings. Use `-Language C` or
`-Language PowerShell` to resolve an ambiguous snippet. For C, use `//` or `/* */`
comments; a leading `# ` comment selects PowerShell in Auto mode.

Every window uses a clean process; bindings loaded in your calling shell do not
conflict. C scenes can also be sent to an already-running managed window from the
previous launcher version. Windows x64 PowerShell 5.1 and 7 are tested.

Logs and instance state are under `%LOCALAPPDATA%\RaylibPowerShell\sessions`;
compiled C DLLs, generated sources, and compiler diagnostics are under
`%LOCALAPPDATA%\RaylibPowerShell\compiled`.

## Optional PowerShell syntax

The previous `[RaylibPowerShell.Api]::DrawCircle(...)` form still works with
`-Language PowerShell`. These callbacks receive `$frame`, containing `Time`,
`DeltaTime`, `Frame`, `FirstFrame`, `Width`, `Height`, `InstanceId`, `Api`, `State`
(a persistent hashtable), and `Cleanup` (an optional scriptblock executed at closure
with State as its argument). Balance your own 3D/texture/shader modes, and let the
host own BeginDrawing/EndDrawing. PowerShell failures on a replacement's first frame
restore the previous calls; native/state mutations cannot be rolled back.

The following reference concerns only those optional PowerShell bindings. C calls
use native raylib types and pointer semantics directly.

## Binding coverage and native memory

`Bindings.cs` covers all **581 functions in raylib 5.5's raylib.h**, plus 34 structs,
5 type aliases, 21 enums, 6 callback delegates, colors and numeric constants.
`rlDrawRenderBatchActive` is also exposed for screenshot capture. Separate libraries
such as raygui and the header-only raymath/rlgl APIs are outside raylib.h coverage.

- Functions: `[RaylibPowerShell.Api]::FunctionName(...)`.
- Colors: `[RaylibPowerShell.Colors]::RED` or `[RaylibPowerShell.Color]::new(r,g,b,a)`.
- Constants: `[RaylibPowerShell.Constants]::KEY_SPACE`; named enums are also exposed.
- Structs: `[RaylibPowerShell.Vector2]::new(x,y)` etc. Other structs use `::new()`
  and property/field assignment. Field names use initial capitals, e.g. `Width`.
- Native pointers are `IntPtr`. Pointer-returning functions retain raylib ownership
  rules; release allocations with the matching raylib `Unload...` or `MemFree`.
  Never free borrowed pointers such as those from `GetWorkingDirectory`.
- Copy returned UTF-8 strings using `[RaylibPowerShell.Api]::Utf8($pointer)`.
  The copy does not free the native pointer. Pass input text as ordinary strings.
- Common output/mutable pointers have `[ref]` overloads, e.g.
  `ImageResize([ref]$image, 100, 100)` or `LoadCodepoints('text', [ref]$count)`.
  Declare output variables with the right type first (`[int]$count = 0`).
- Borrowed input arrays have typed overloads, e.g. `DrawTriangleFan($points, 3, $color)`
  with a `Vector2[]`. Counts must match the supplied storage. Raw pointer overloads
  remain available for every pointer-based API. `void*` buffers use `IntPtr`.
  String parameters also have `IntPtr` overloads for native buffers/interior pointers
  (for example, when walking backwards with `GetCodepointPrevious`). Use typed
  arguments to distinguish null strings from null pointers in overloaded calls.
- APIs that retain memory, including `SetAutomationEventList` and
  `LoadMusicStreamFromMemory`, require stable unmanaged storage for the whole native
  lifetime. Do not pass a temporary managed array or a temporary `[ref]` value.
- Fixed struct arrays have numbered inline fields and array properties, e.g.
  `$vr.LensDistortionValues = [float[]]@(1, 0.22, 0.24, 0)`.
  Array getters return a copy: assign the whole property back to update it.
- C `long` is represented as 32-bit `int` on Windows; native booleans use one byte.

`TextFormat` and `TraceLog` adapt C varargs to .NET composite formatting:
`TextFormat('Value: {0}', 42)`. They call native raylib with a fixed `%s` format.
Use `{0}` placeholders, not C `%d`/`%f` placeholders. `TextFormat` returns a borrowed
native pointer just like raylib; copy it with `Utf8` before a later call replaces it.

Callbacks use native delegate signatures. Keep a strong reference to a delegate
until you unregister it, then stop the native producer before releasing its state.
Implement audio/background-thread callbacks in compiled C#; a PowerShell scriptblock
has no runspace on raylib's audio thread. The logging callback's `va_list` is opaque
native memory. Do not let managed exceptions cross a native callback boundary.

## Regenerate and verify

`python .\raylib\generate-bindings.py` regenerates the C# from the checked-in official
API metadata. Python is needed only for regeneration, not for running raylib.
`raylib/test-bindings.ps1` and `raylib/test-renderer.ps1` checks every native export and struct layout and exercises
real rendering, resource cleanup, strings and pointers on the local desktop.

Source: [raylib 5.5 API](https://github.com/raysan5/raylib/blob/5.5/src/raylib.h)
and [official parser metadata](https://github.com/raysan5/raylib/blob/5.5/parser/output/raylib_api.json).
