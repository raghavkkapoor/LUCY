import os
import sys
import json
import base64
import mimetypes
import subprocess
from pathlib import Path
from email.message import EmailMessage

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request, AuthorizedSession
from google.auth.exceptions import RefreshError

ROOT = Path(r"C:\Users\ragha\Downloads\LUCY\LucyPython")
CRED = ROOT / "cred.json"
OAUTH_HELPER = ROOT / "LUCY_ABILITIES" / "gmail-service" / "gmail_oauth.py"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]

API = "https://gmail.googleapis.com/gmail/v1"
TIMEOUT = 8

payload = json.loads(os.environ["LUCY_GMAIL_PAYLOAD"])


def start_oauth_detached(reason):
    flags = 0
    if os.name == "nt":
        flags = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        )

    subprocess.Popen(
        [sys.executable, str(OAUTH_HELPER)],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=flags,
        close_fds=True,
    )

    print("GMAIL_AUTH_REQUIRED=True")
    print("OAUTH_STARTED=True")
    print("AUTH_REASON=" + reason)
    print("RETRY_AFTER_AUTH=True")
    sys.exit(2)


def load_credentials():
    if not CRED.exists():
        start_oauth_detached("CREDENTIAL_FILE_MISSING")

    try:
        creds = Credentials.from_authorized_user_file(str(CRED), SCOPES)
    except Exception as exc:
        start_oauth_detached("CREDENTIAL_FILE_INVALID:" + type(exc).__name__)

    if creds.valid:
        return creds

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            CRED.write_text(creds.to_json(), encoding="utf-8")

            if creds.valid:
                print("GMAIL_TOKEN_REFRESHED=True")
                return creds

        except RefreshError:
            start_oauth_detached("REFRESH_TOKEN_REJECTED")
        except Exception as exc:
            print("GMAIL_REFRESH_FAILED=True")
            print("ERROR_TYPE=" + type(exc).__name__)
            sys.exit(3)

    start_oauth_detached("NO_USABLE_REFRESH_TOKEN")


def request_json(session, method, url, **kwargs):
    try:
        response = session.request(
            method,
            url,
            timeout=TIMEOUT,
            **kwargs
        )
    except Exception as exc:
        print("GMAIL_NETWORK_ERROR=True")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("ERROR=" + str(exc))
        sys.exit(4)

    if response.status_code == 401:
        start_oauth_detached("GMAIL_RETURNED_401")

    if not response.ok:
        print("GMAIL_API_ERROR=True")
        print("HTTP_STATUS=" + str(response.status_code))
        print("RESPONSE=" + response.text[:2000])
        sys.exit(5)

    if not response.content:
        return {}

    return response.json()


def decode_b64(data):
    if not data:
        return ""

    try:
        padded = data + "=" * (-len(data) % 4)
        return base64.urlsafe_b64decode(padded).decode(
            "utf-8",
            errors="replace"
        )
    except Exception:
        return ""


def header(headers, name):
    wanted = name.lower()

    for item in headers or []:
        if item.get("name", "").lower() == wanted:
            return item.get("value", "")

    return ""


def extract_body(part):
    plain = []
    html = []

    def walk(node):
        mime = node.get("mimeType", "")
        data = node.get("body", {}).get("data")

        if data:
            text = decode_b64(data)

            if mime == "text/plain":
                plain.append(text)
            elif mime == "text/html":
                html.append(text)

        for child in node.get("parts", []) or []:
            walk(child)

    walk(part)

    if plain:
        return "\n".join(plain)

    if html:
        return "\n".join(html)

    return decode_b64(part.get("body", {}).get("data"))


def output_message(message):
    part = message.get("payload", {})
    headers = part.get("headers", [])

    obj = {
        "id": message.get("id", ""),
        "thread_id": message.get("threadId", ""),
        "labels": message.get("labelIds", []),
        "from": header(headers, "From"),
        "to": header(headers, "To"),
        "cc": header(headers, "Cc"),
        "subject": header(headers, "Subject"),
        "date": header(headers, "Date"),
        "body": extract_body(part),
    }

    print(json.dumps(obj, ensure_ascii=False))


creds = load_credentials()
session = AuthorizedSession(creds)

action = payload["action"].lower()

# Profile is also useful for Send because Gmail needs the authenticated sender.
profile = request_json(
    session,
    "GET",
    API + "/users/me/profile"
)

sender = profile.get("emailAddress", "")

if action == "whoami":
    print("GMAIL_AUTHENTICATED=True")
    print("EMAIL=" + sender)
    print("TRANSPORT=DIRECT_REST")
    print("DISCOVERY_BUILD_USED=False")

elif action == "send":
    recipient = (payload.get("to") or "").strip()

    if not recipient:
        print("GMAIL_ARGUMENT_ERROR=True")
        print("ERROR=SEND_REQUIRES_TO")
        sys.exit(6)

    msg = EmailMessage()
    msg["To"] = recipient
    msg["From"] = sender
    msg["Subject"] = payload.get("subject") or ""
    msg.set_content(payload.get("body") or "")

    attachments = payload.get("attachments") or []

    for item in attachments:
        path = Path(item).expanduser().resolve()

        if not path.is_file():
            print("GMAIL_ARGUMENT_ERROR=True")
            print("ERROR=ATTACHMENT_NOT_FOUND")
            print("PATH=" + str(path))
            sys.exit(7)

        mime, _ = mimetypes.guess_type(str(path))

        if mime and "/" in mime:
            maintype, subtype = mime.split("/", 1)
        else:
            maintype, subtype = "application", "octet-stream"

        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name
        )

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")

    result = request_json(
        session,
        "POST",
        API + "/users/me/messages/send",
        json={"raw": raw}
    )

    message_id = result.get("id", "")

    if not message_id:
        print("GMAIL_SEND_VERIFIED=False")
        sys.exit(8)

    print("GMAIL_SEND_VERIFIED=True")
    print("MESSAGE_ID=" + message_id)
    print("TO=" + recipient)
    print("ATTACHMENT_COUNT=" + str(len(attachments)))

elif action in ("search", "latest"):
    max_results = max(
        1,
        min(int(payload.get("max_results") or 10), 100)
    )

    query_parts = []

    if action == "search" and payload.get("query"):
        query_parts.append(payload["query"])

    if payload.get("unread_only"):
        query_parts.append("is:unread")

    if payload.get("inbox_only"):
        query_parts.append("in:inbox")

    query = " ".join(query_parts).strip()

    params = {
        "maxResults": max_results
    }

    if query:
        params["q"] = query

    listing = request_json(
        session,
        "GET",
        API + "/users/me/messages",
        params=params
    )

    messages = listing.get("messages", [])

    print("GMAIL_QUERY=" + query)
    print("RESULT_COUNT=" + str(len(messages)))

    for item in messages:
        message = request_json(
            session,
            "GET",
            API + "/users/me/messages/" + item["id"],
            params={"format": "full"}
        )

        output_message(message)

else:
    print("GMAIL_ARGUMENT_ERROR=True")
    print("ERROR=UNKNOWN_ACTION")
    sys.exit(9)
