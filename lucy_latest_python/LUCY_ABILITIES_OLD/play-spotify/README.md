# Play Spotify

## Goal
Resume Spotify playback on Windows 11.

## Method
Uses Windows Global System Media Transport Controls to locate Spotify's current media session and issue a Play command. If Spotify is not running, the Spotify URI is launched first.

## Stability / Risk
Low risk and stable. Uses Windows media controls rather than mouse/keyboard automation and does not modify Spotify data, credentials, playlists, or browser tabs.

## Usage
Run:

powershell -ExecutionPolicy Bypass -File .\play-spotify.ps1

The script verifies that Spotify reaches the Playing state before reporting success.
