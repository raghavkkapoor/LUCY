# Authenticated Headless ChatGPT CDP

## Goal
Verify whether Lucy can control ChatGPT through a genuinely headless Chrome instance and access its JavaScript-rendered DOM.

## Previous failure
The first isolated test reached **Just a moment...** instead of ChatGPT. Chrome itself and CDP worked correctly, but the new browser exposed a HeadlessChrome user agent and did not possess Lucy's existing ChatGPT / Cloudflare session state.

## Verified approach
Lucy connected to her normal authenticated Chrome instance on port 9223, copied only the relevant browser session state in memory, then launched a separate Chrome instance with --headless=new on port 9333.

The headless browser used the same normal Chrome user agent and received the existing ChatGPT/OpenAI cookies before navigation.

The test then verified that:

- The Cloudflare interstitial was no longer the active page.
- ChatGPT's JavaScript application rendered.
- The DOM could be queried through CDP.
- Interactive controls could be enumerated.
- Page text could be read.
- No visible Chrome window was required.

## Risk / stability
The workflow is isolated from Lucy's normal Chrome process. It does not modify the visible browser profile and does not print authentication cookies or token values.

The main reliability dependency is ChatGPT/Cloudflare session validity. If that session expires, Lucy's normal authenticated browser must first possess a fresh valid session before it can be mirrored into a new headless process.
