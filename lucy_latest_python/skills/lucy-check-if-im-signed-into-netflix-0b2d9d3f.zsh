#!/bin/zsh
set -euo pipefail

if ! RESULT="$(osascript <<'APPLESCRIPT'
tell application "Google Chrome"
  activate
  set newTab to make new tab at end of tabs of front window with properties {URL:"https://www.netflix.com/"}
  delay 8
  set pageText to execute newTab javascript "document.body.innerText"
  return "URL: " & URL of newTab & linefeed & pageText
end tell
APPLESCRIPT
)"; then
  printf '%s\n' 'FAILURE: Could not check Netflix in Google Chrome.' >&2
  exit 1
fi

if [[ "$RESULT" != *$'\n'* ]]; then
  printf '%s\n' 'FAILURE: Netflix returned no usable page information.' >&2
  exit 1
fi

PAGE_URL="${RESULT#URL: }"
PAGE_URL="${PAGE_URL%%$'\n'*}"
PAGE_TEXT="${RESULT#*$'\n'}"

if [[ -z "$PAGE_URL" ]]; then
  printf '%s\n' 'FAILURE: Could not determine the Netflix page URL.' >&2
  exit 1
fi

printf 'Netflix page: %s\n' "$PAGE_URL"

case "$PAGE_TEXT" in
  *"Sign In"*)
    printf '%s\n' 'SUCCESS: You are not signed into Netflix in this Chrome session.'
    ;;
  *"Who's watching?"*|*"Manage Profiles"*|*"My List"*)
    printf '%s\n' 'SUCCESS: You appear to be signed into Netflix in this Chrome session.'
    ;;
  *)
    case "$PAGE_URL" in
      */browse*|*/YourAccount*)
        printf '%s\n' 'SUCCESS: You appear to be signed into Netflix in this Chrome session.'
        ;;
      *)
        printf '%s\n' 'FAILURE: Could not determine whether you are signed into Netflix from the page content.' >&2
        exit 2
        ;;
    esac
    ;;
esac
