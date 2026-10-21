#!/bin/zsh
set -euo pipefail

url="https://hawakening.com/"

if [[ ! -x /usr/bin/open ]]; then
  print -u2 "Failure: macOS 'open' command is unavailable."
  exit 1
fi

if /usr/bin/open "$url"; then
  print "Opened Hawakening: $url"
else
  print -u2 "Failure: Could not open Hawakening: $url"
  exit 1
fi
