#!/bin/zsh
set -euo pipefail

if /usr/bin/open -a Calendar; then
  printf '%s\n' 'Success: Calendar opened.'
else
  printf '%s\n' 'Failure: Could not open Calendar.' >&2
  exit 1
fi
