# YouTube Fallback for Unavailable Tracks
If a requested song is not available through Spotify, Lucy should use the existing
play-youtube-search ability through the Chrome CDP instance on port 9223.
Requested example:
- Query: Love TATLI Russian song
- YouTube playback verified: True
- Matched requested title: True
- Video title: Tatli - Love
- Video URL: https://www.youtube.com/watch?v=FSrXmCRuiqo&list=RDFSrXmCRuiqo&start_radio=1
Spotify desktop automation remains available independently for playback controls,
metadata, seek, shuffle, repeat, search URI navigation, tracks, albums, artists,
playlists, and Liked Songs.
