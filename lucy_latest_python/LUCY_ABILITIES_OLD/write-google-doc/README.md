# Write Google Doc

Goal: Write or replace the body text of an already-open Google Docs document.

How it works:
- Connects to Lucy's authenticated Chrome instance through CDP on port 9223.
- Finds the already-open Google Doc by its title.
- Focuses the Google Docs editing surface.
- Replaces the document body with requested text.
- Copies the resulting document body and verifies that the requested text is present.
- Does not navigate away from or replace unrelated browser tabs.

Usage:

    .\write-google-doc.ps1 -Title "LUCY RESEARCH DOC" -Text "Your document text"

Risk: Medium-low. The workflow intentionally replaces the body of the matched document, so using the wrong title could overwrite content in that document.

Stability: Good, but dependent on Google Docs editor selectors and Chrome CDP remaining compatible.
