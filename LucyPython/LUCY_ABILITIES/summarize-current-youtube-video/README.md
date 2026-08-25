# Summarize Current YouTube Video

## Goal
Avoid sitting through a long YouTube video by extracting its transcript and summarizing what the speaker is actually saying.

## Successful test
Video: **15 Years Writing C++ - Advice for new programmers**

## Method
Lucy located the visible Chrome window, copied the YouTube URL, retrieved English captions using yt-dlp, cleaned the VTT transcript, and summarized the speaker's main argument.

## Result
The speaker's central advice is to stop obsessing over the perfect programming language or perfect learning path. Beginners should write lots of code, make mistakes, debug problems, and learn through building things.

## Stability / Risk
Low risk. The workflow only reads a public YouTube video's URL and captions. It does not modify accounts or files other than temporary transcript data and this saved ability.

## Files
Script: C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\summarize-current-youtube-video\summarize-current-youtube-video.ps1
README: C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\summarize-current-youtube-video\README.md
