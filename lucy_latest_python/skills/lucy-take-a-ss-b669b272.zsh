#!/bin/zsh
set -euo pipefail

fail() {
  print -u2 -- "FAILURE: $1"
  exit 1
}

desktop="$HOME/Desktop"
[[ -d "$desktop" ]] || fail "Desktop folder not found: $desktop"
[[ -w "$desktop" ]] || fail "Desktop folder is not writable: $desktop"

timestamp=$(/bin/date '+%Y%m%d-%H%M%S')
screenshot="$desktop/screenshot-$timestamp.png"

if ! /usr/bin/osascript -e 'tell application "Calendar" to activate'; then
  fail "Could not activate Calendar."
fi

if ! /usr/sbin/screencapture -x "$screenshot"; then
  fail "Screenshot capture failed."
fi

[[ -s "$screenshot" ]] || fail "Screenshot file was not created or is empty: $screenshot"
print -- "SUCCESS: Screenshot saved to $screenshot"
