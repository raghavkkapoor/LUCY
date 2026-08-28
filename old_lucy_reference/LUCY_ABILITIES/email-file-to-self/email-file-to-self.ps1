param(
    [Parameter(Mandatory=$true)][string]$FilePath,
    [string]$Subject = "File from Lucy"
)

$ErrorActionPreference = "Stop"

$handler = "C:\Users\ragha\Downloads\LUCY\LucyPython\Services[IGNORE]\Emailing\Gmailhandler.py"
$recipient = "raghavkkapoor7@gmail.com"

if (-not (Test-Path -LiteralPath $FilePath)) {
    throw "File not found: $FilePath"
}

$env:LUCY_ATTACHMENT = (Resolve-Path -LiteralPath $FilePath).Path
$env:LUCY_GMAIL_HANDLER = $handler
$env:LUCY_RECIPIENT = $recipient
$env:LUCY_SUBJECT = $Subject

$py = @"
import os, base64, importlib.util
from email.message import EmailMessage

attachment = os.environ["LUCY_ATTACHMENT"]
handler_path = os.environ["LUCY_GMAIL_HANDLER"]
recipient = os.environ["LUCY_RECIPIENT"]
subject = os.environ["LUCY_SUBJECT"]

spec = importlib.util.spec_from_file_location("lucy_gmailhandler", handler_path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

service = mod.setup_gmail()
if service is None:
    raise RuntimeError("Gmail authentication failed")

sender = service.users().getProfile(userId="me").execute()["emailAddress"]

msg = EmailMessage()
msg["To"] = recipient
msg["From"] = sender
msg["Subject"] = subject
msg.set_content("Attached file sent by Lucy.")

with open(attachment, "rb") as f:
    msg.add_attachment(
        f.read(),
        maintype="application",
        subtype="octet-stream",
        filename=os.path.basename(attachment)
    )

raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
result = service.users().messages().send(
    userId="me",
    body={"raw": raw}
).execute()

message_id = result.get("id")
if not message_id:
    raise RuntimeError("No Gmail message ID returned")

service.users().messages().get(
    userId="me",
    id=message_id,
    format="metadata"
).execute()

print("API_SEND_VERIFIED=True")
print("MESSAGE_ID=" + message_id)
"@

$tmp = Join-Path $env:TEMP "lucy_email_file_to_self.py"
Set-Content -LiteralPath $tmp -Value $py -Encoding UTF8
python $tmp

if ($LASTEXITCODE -ne 0) {
    throw "Email workflow failed"
}

