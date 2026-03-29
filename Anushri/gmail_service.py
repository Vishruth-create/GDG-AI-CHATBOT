import os
from dotenv import load_dotenv
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

load_dotenv()

def get_gmail_service():
    """Builds the authorized Gmail service object."""
    creds = Credentials(
        token=os.getenv("gmail_acess_token"),
        refresh_token=os.getenv("gmail_refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("gmail_client_id"),
        client_secret=os.getenv("gmail_client_secret"),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("gmail", "v1", credentials=creds)

async def list_inbox(max_results: int, query: str) -> dict:
    service = get_gmail_service()
    result = service.users().messages().list(
        userId="me", q=query, maxResults=min(max_results, 50)
    ).execute()

    messages = result.get("messages", [])
    summaries = []
    for m in messages:
        msg = service.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
        summaries.append({
            "id":      m["id"],
            "from":    headers.get("From", ""),
            "subject": headers.get("Subject", ""),
            "date":    headers.get("Date", ""),
            "snippet": msg.get("snippet", ""),
            "unread":  "UNREAD" in msg.get("labelIds", []),
        })
    return {"emails": summaries}

async def read_email(message_id: str) -> dict:
    service = get_gmail_service()
    msg = service.users().messages().get(
        userId="me", id=message_id, format="full"
    ).execute()
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    body = _extract_body(msg["payload"])
    return {
        "id":        message_id,
        "from":      headers.get("From", ""),
        "to":        headers.get("To", ""),
        "subject":   headers.get("Subject", ""),
        "date":      headers.get("Date", ""),
        "thread_id": msg.get("threadId"),
        "body":      body[:3000],
    }

async def send_email(to: str, subject: str, body: str, cc: str | None = None) -> dict:
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    sender = profile["emailAddress"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw}
    ).execute()
    return {"success": True, "message_id": sent["id"]}

async def reply_email(message_id: str, body: str) -> dict:
    service = get_gmail_service()
    original = service.users().messages().get(
        userId="me", id=message_id, format="metadata",
        metadataHeaders=["From", "Subject", "Message-ID"]
    ).execute()
    headers = {h["name"]: h["value"] for h in original["payload"].get("headers", [])}

    profile = service.users().getProfile(userId="me").execute()
    sender = profile["emailAddress"]

    msg = MIMEMultipart()
    msg["From"] = sender
    msg["To"] = headers.get("From", "")
    msg["Subject"] = "Re: " + headers.get("Subject", "").lstrip("Re: ")
    msg["In-Reply-To"] = headers.get("Message-ID", "")
    msg["References"] = headers.get("Message-ID", "")
    msg.attach(MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    sent = service.users().messages().send(
        userId="me", body={"raw": raw, "threadId": original["threadId"]}
    ).execute()
    return {"success": True, "message_id": sent["id"]}

async def archive_email(message_id: str) -> dict:
    service = get_gmail_service()
    service.users().messages().modify(
        userId="me", id=message_id,
        body={"removeLabelIds": ["INBOX"]}
    ).execute()
    return {"success": True, "archived": message_id}

# --- HELPERS ---

def _extract_body(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore") if data else ""
    for part in payload.get("parts", []):
        text = _extract_body(part)
        if text:
            return text
    return payload.get("snippet", "")