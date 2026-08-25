# Open Raylib API

## Goal
Download the current official raylib C API header and open it locally for inspection.

## Method
Downloads `src/raylib.h` directly from the official `raysan5/raylib` GitHub repository using PowerShell, validates the file, and opens it in Notepad.

## Stability / Risk
Low risk. The workflow performs a read-only HTTPS download from the official upstream repository and writes only into the current working directory.

## Files
- `open-raylib-api.ps1` - reusable workflow.
- `C:\Users\ragha\Downloads\LUCY\LucyPython\raylib-api\raylib.h` - downloaded raylib public API header.
