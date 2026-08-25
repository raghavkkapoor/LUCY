# Lucy EXE Launcher
## Goal
Launch Lucy by double-clicking `Lucy.exe` while keeping `main.py` fully editable.
## How it works
`Lucy.exe` is only a tiny launcher. It does not contain or copy `main.py`.
Every time `Lucy.exe` starts, it runs:
`python.exe C:\Users\ragha\Downloads\LUCY\LucyPython\main.py`
That means any saved change to `main.py` is automatically used the next time Lucy launches. There is no need to rebuild the EXE after Python code changes.
The launcher also:
- uses LucyPython as the working directory
- gives the console the title `LUCY`
- attempts to keep its console window always on top
- waits for main.py to exit and returns the same exit code
## Files
- `Lucy.exe` ΓÇö launcher in the LucyPython root
- `LucyLauncher.cs` ΓÇö launcher source
- `README.md` ΓÇö documentation
## Risk / Stability
Low risk. The launcher does not modify main.py or bundle project code. If main.py changes, Lucy.exe automatically uses the updated version on the next run.
