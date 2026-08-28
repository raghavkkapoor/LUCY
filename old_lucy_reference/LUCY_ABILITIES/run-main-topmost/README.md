# Lucy Topmost Terminal Launcher
Launches Lucy from any PowerShell working directory in a separate interactive
Windows Terminal window and marks that Windows Terminal window as always-on-top.
The launcher deliberately keeps `main.py` attached to an interactive terminal
so Python `input()` continues to work normally.
Run from anywhere:
powershell -ExecutionPolicy Bypass -File "C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\run-main-topmost\lucy-topmost.ps1"
