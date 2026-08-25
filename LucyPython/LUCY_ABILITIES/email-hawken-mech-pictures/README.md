# Email Hawken Mech Pictures

## Goal
Find several pictures of mechs from the game HAWKEN and email them to the user.

## How it works
Uses Playwright through the existing Chrome CDP session on port 9223.

1. Opens Google Images in a separate browser page.
2. Captures five useful HAWKEN mech images.
3. Reuses the authenticated Gmail session.
4. Composes an email to the user.
5. Attaches the images and sends it.
6. Verifies Gmail displays "Message sent".

## Stability
Moderately stable.

It avoids disturbing Lucy's active ChatGPT tab and reuses the existing authenticated browser session. Google Images or Gmail DOM changes could require selector updates.

## Risk
Low.

The workflow only searches public images and sends an email to the user's own Gmail address.
