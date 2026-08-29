# Lucy Gmail Service

Lucy should inspect:

C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\gmail-service\schema.json

and call:

C:\Users\ragha\Downloads\LUCY\LucyPython\LUCY_ABILITIES\gmail-service\gmail.ps1

This service intentionally performs NO self-test while being installed.

The previous installation commands repeatedly timed out because a live Gmail
test was nested inside the same Lucy command. That testing pattern has been
removed.

Runtime behavior:
- no terminal action prompt
- no terminal search prompt
- uses existing cred.json
- refreshes expired access tokens with curl
- each HTTP call has a 3 second connect timeout and 8 second hard total timeout
- a 401 triggers one bounded refresh attempt
- if fresh Google consent is required, OAuth launches separately and the Gmail
  command returns instead of freezing Lucy
- Send supports attachments
- Search and Latest return JSON message metadata
