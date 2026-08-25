# Shuffle Liked Songs

Goal:
Shuffle and play the user's Spotify Liked Songs.

Method:
Opens Spotify's Liked Songs collection through its desktop URI, then uses Windows Global System Media Transport Controls to explicitly enable shuffle and start playback.

Risk:
Low. Only Spotify playback state is changed.

Stability:
Good when the Spotify desktop application exposes its Windows media session.

Usage:
powershell -ExecutionPolicy Bypass -File .\shuffle-liked-songs.ps1
