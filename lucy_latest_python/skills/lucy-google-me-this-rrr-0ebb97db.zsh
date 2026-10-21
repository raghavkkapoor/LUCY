#!/bin/zsh
set -euo pipefail

url='https://www.google.com/search?q=rrr'

if ! command -v open >/dev/null 2>&1; then
  print -u2 -- 'Failure: macOS open command is unavailable.'
  exit 1
fi

if open "$url"; then
  print -- 'Success: opened Google search for rrr.'
else
  print -u2 -- 'Failure: could not open the Google search.'
  exit 1
fi
