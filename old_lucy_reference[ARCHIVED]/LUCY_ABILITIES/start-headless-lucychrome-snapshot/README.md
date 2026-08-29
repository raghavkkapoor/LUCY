# Headless LucyChrome Snapshot

Goal:
Run another Chrome CDP browser on port 9333 using the active LucyChrome profile state without disrupting the live Chrome on port 9223.

Approach:
Chromium prevents two independent Chrome browser processes from simultaneously owning exactly the same user-data directory.

The working method creates a filesystem snapshot of:
C:\Users\ragha\AppData\Local\Lucy\LucyChrome

into:
C:\Users\ragha\AppData\Local\Lucy\LucyChrome_Headless_9333

Locked/cache/ephemeral files are skipped rather than aborting the copy. Files that permit shared reads are copied while the main LucyChrome instance remains running.

The headless browser then runs independently on CDP port 9333.

Risk / stability:
This avoids concurrent writes to the live LucyChrome profile and is significantly safer than forcing both Chrome processes onto exactly the same directory. The snapshot represents the LucyChrome state at launch time and does not automatically receive later state changes from the 9223 browser.

CDP verified:
True

Port:
9333
