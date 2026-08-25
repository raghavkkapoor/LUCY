# Create Google Doc

Goal: Create a fresh Google Docs document in a separate Chrome window and assign it a requested title.

How it works:
- Connects to Lucy's existing Chrome instance over CDP, normally port 9223.
- Reuses the existing authenticated Google session.
- Opens docs.new in a new Chrome window.
- Sets the Google Docs title.
- Verifies the title before reporting success.

Usage:

    .\create-google-doc.ps1 -Title "LUCY RESEARCH DOC"

Risk: Low. The workflow creates a new document and does not modify existing documents or currently open tabs.

Stability: Good. It depends on Chrome CDP remaining available and Google Docs retaining compatible title-field selectors.
