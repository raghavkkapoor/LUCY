# Spotify Desktop Automation
## Goal
Provide Lucy with reusable, separate Spotify desktop automation functions rather than one-off UI guesses.
## Surfaces mapped
### Windows Global System Media Transport Controls
Stable controls discovered:
- play
- pause
- toggle play/pause
- next track
- previous track
- playback position / seeking
- shuffle
- repeat
- now-playing metadata
- playback status
- timeline position and duration
- capability detection
### Spotify URI protocol
Stable navigation discovered:
- spotify:
- spotify:search:<query>
- spotify:track:<id>
- spotify:album:<id>
- spotify:artist:<id>
- spotify:playlist:<id>
- spotify:collection:tracks
### Spotify desktop UI
Spotify 1.2.96.518 is Chromium based. Standard Windows UI Automation exposes the Chromium host but almost none of Spotify's internal XPUI controls, so UIA is not a reliable main automation layer.
### Local networking
Spotify owns localhost listener 7768 plus dynamic listeners. They did not expose a normal unauthenticated HTTP/CDP automation API during probing, so Lucy should not depend on them.
### Browser-assisted discovery
Lucy's existing Chrome CDP instance can open Spotify Web in a separate window to discover exact track/album/artist IDs. Once an ID is known, control returns to the native Spotify app using spotify: URIs.
## Reliability
High: media transport functions and direct Spotify URIs.
Medium: browser-assisted Spotify catalog discovery.
Low: blind keyboard/UI focus automation, which should only be used as a fallback.
## Files
- SpotifyAutomation.psm1 - reusable function module.
- spotify-surface-probe.ps1 - discovery/diagnostic workflow.
- README.md - capability documentation.
## Requested song
The workflow specifically attempts to resolve and verify "Love" by TATLI before declaring success. It does not falsely report success if Spotify remains on another track.
