// C snippet environment. raylib retains its original C names, types and constants.
#include "raylib.h"
#include "raymath.h"
#include "rlgl.h"
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

// Compatibility helper: raylib has no DrawCone API. Cone axis is +Y, like DrawCylinder.
static void DrawCone(Vector3 position, float radius, float height, int slices, Color color)
{
    DrawCylinder(position, 0.0f, radius, height, slices, color);
}

// The persistent host begins/presents exactly one frame, including screenshot capture.
// Accept copied frame snippets that contain these two calls without double swapping.
#define BeginDrawing() ((void)0)
#define EndDrawing() ((void)0)
