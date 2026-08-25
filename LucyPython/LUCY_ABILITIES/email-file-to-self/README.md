# Email File To Self

## Goal
Email a specified local file to the user's own Gmail account.

## How it works
Uses Lucy's existing Gmail API handler and Google OAuth credentials. It creates a MIME email, attaches the requested local file, sends it through the Gmail API, and verifies that the returned message can be fetched.

## Proven result
Successfully sent:

C:\Users\ragha\OneDrive\Desktop\manageLucyChromeProfile.ps1

Gmail returned and verified message ID:

1a02383a58d6576a

## Stability
High once Gmail OAuth credentials are valid. Reauthorization may be required if the token is removed or scopes change.

## Risk
Low. The script sends only the explicitly specified local file to the user's own configured Gmail account.
