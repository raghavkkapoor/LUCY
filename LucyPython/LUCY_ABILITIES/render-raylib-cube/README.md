# Render raylib 3D Cube

## Goal
Render a basic 3D cube in a native raylib window.

## Implementation
Uses the installed Python raylib package through its pyray API. The scene contains a perspective Camera3D, solid cube, wireframe cube edges, and ground grid at 60 FPS.

## Files
- cube.py
- render-raylib-cube.ps1
- README.md

## Stability / Risk
Low risk. Rendering is local and runs in a detached process. The earlier failure was caused by importing aylib, whose low-level binding does not expose the snake_case functions used by the script. The workflow now imports pyray, which provides that API.
