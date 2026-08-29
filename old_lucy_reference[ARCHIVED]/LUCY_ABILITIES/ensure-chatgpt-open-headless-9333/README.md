# Ensure ChatGPT Open in Headless 9333

Goal:
Keep a ChatGPT page open inside Lucy's headless Chrome CDP instance on port 9333.

Result:
A ChatGPT page target is created or reused and verified through CDP.

Important:
If ChatGPT displays its "Just a moment..." verification page, the page is still open successfully, but the site has not granted the headless browser access to the normal ChatGPT interface. This workflow does not attempt to defeat that verification.

Port:
9333

Risk:
Low. The script only opens/reuses the ChatGPT page and leaves the headless browser running.
