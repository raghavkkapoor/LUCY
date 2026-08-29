# Split Chrome Manager Terminal Ability

## Goal
Separate the Chrome profile manager PowerShell process from Lucy's main Python OODA loop terminal.

## Implementation
Updated main.py so manageLucyChromeProfile.ps1 launches with:
- subprocess.Popen
- CREATE_NEW_CONSOLE
- dedicated PowerShell window
- independent Chrome lifecycle logs

## Result
Lucy main terminal keeps stdin/input available while Chrome CDP management runs separately.

## Stability
Low risk. This only changes process launching behavior. Chrome profile logic and CDP communication remain unchanged.
