$ErrorActionPreference = "Stop"

$handler = 'C:\Users\ragha\OneDrive\Desktop\LucyPython\Services[IGNORE]\Emailing\Gmailhandler.py'
$docUrl = 'https://docs.google.com/document/d/11hiF3OP1vY_clzZslxCMw5dC6qHuIZlMup-Rbacgv40/edit'
$recipient = 'raghavkkapoor7@gmail.com'

$env:LUCY_GMAIL_HANDLER = $handler
$env:LUCY_DOC_URL = $docUrl
$env:LUCY_RECIPIENT = $recipient

$py = @"
import os
import sys
import base64
import importlib.util
from email.message import EmailMessage

handler_path = os.environ["LUCY_GMAIL_HANDLER"]
doc_url = os.environ["LUCY_DOC_URL"]
recipient = os.environ["LUCY_RECIPIENT"]

spec = importlib.util.spec_from_file_location("lucy_gmailhandler", handler_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

service = mod.setup_gmail()
if service is None:
    raise RuntimeError("Gmail API authentication failed.")

profile = service.users().getProfile(userId="me").execute()
sender = profile.get("emailAddress")

msg = EmailMessage()
msg["To"] = recipient
msg["From"] = sender
msg["Subject"] = "Hello from Lucy"
msg.set_content(
    "Hey! Just sending you a greeting from Lucy.\n\n"
    "Lucy Research Google Doc:\n"
    + doc_url
)

raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

result = service.users().messages().send(
    userId="me",
    body={"raw": raw}
).execute()

message_id = result.get("id")
if not message_id:
    raise RuntimeError("Gmail API returned no message ID.")

verified = service.users().messages().get(
    userId="me",
    id=message_id,
    format="metadata",
    metadataHeaders=["To", "Subject"]
).execute()

labels = verified.get("labelIds", [])

print("GMAIL_API_ONLY=True")
print("SENDER=" + str(sender))
print("RECIPIENT=" + recipient)
print("MESSAGE_ID=" + message_id)
print("API_SEND_VERIFIED=True")
print("LABELS=" + ",".join(labels))
"@

$tmp = Join-Path $env:TEMP "lucy_send_research_doc_gmail_api.py"
Set-Content -LiteralPath $tmp -Value $py -Encoding UTF8

python $tmp
if ($LASTEXITCODE -ne 0) {
    throw "Gmail API send failed."
}
