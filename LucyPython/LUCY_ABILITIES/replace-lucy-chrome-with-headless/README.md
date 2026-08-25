# Replace Lucy Chrome with Headless Chrome

## Goal
Replace Lucy's existing visible CDP Chrome instance on port 9223 with a
headless Chrome instance on port 9333 while continuing to use the exact same
LucyChrome profile.

## Profile
C:\Users\ragha\AppData\Local\Lucy\LucyChrome

## Old CDP
9223 — stopped and verified unreachable.

## New CDP
9333 — headless and verified healthy.

## Result
HEADLESS_CDP_READY=True
HEADLESS_9333_STABLE=True

## Stability
The original Chrome process tree is completely stopped before the same
user-data-dir is reopened. This avoids simultaneous writers and profile
corruption while retaining Lucy's existing cookies, storage, extensions,
and login state.
