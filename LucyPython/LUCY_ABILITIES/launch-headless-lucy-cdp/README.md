# Headless Lucy CDP

Goal: launch an independent headless Chrome CDP instance carrying a snapshot
of Lucy's Chrome profile/state.

Source profile:
C:\Users\ragha\AppData\Local\Lucy\LucyChrome

Headless clone:
C:\Users\ragha\AppData\Local\LucyChromeHeadless-9333

CDP port:
9333

Result:
HEADLESS_CDP_READY=True
SECONDARY_CDP_STABLE=True

Robocopy returned 9. Robocopy codes are bitmasks, so code 9 means files were
copied while one or more files also failed. Live Chrome profiles commonly have
locked or transient files. The workflow therefore excludes disposable runtime
state and verifies the critical copied profile plus the actual CDP endpoint
instead of treating any value above 7 as an automatic total failure.

Risk/stability:
The second Chrome instance uses a clone rather than sharing Lucy's writable
user-data directory. This avoids Chrome profile locking/corruption. State is a
snapshot and will not automatically synchronize back into the original profile.
