# Play YouTube Search

Goal: Search YouTube for requested media and begin playing a matching result.

How it works:
- Connects to Lucy's existing Chrome instance through CDP on port 9223.
- Opens YouTube search in a completely new Chrome window.
- Reuses any existing YouTube/Google authentication.
- Prefers a result whose title matches the requested terms.
- Opens the video and verifies the HTML5 video is actively playing.

Usage:

    .\play-youtube-search.ps1 -Query "Ford vs Ferrari remix"

Risk: Low. It only opens and plays public YouTube content.

Stability: Good. It depends on Chrome CDP, Playwright, and YouTube retaining compatible page selectors.
