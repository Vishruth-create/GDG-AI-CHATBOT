import asyncio
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from orchestar import process_message
import requests

load_dotenv()

app = Flask(__name__)

WA_TOKEN = os.getenv("Whatsapp_acess_token")
WA_PHONE_ID = os.getenv("Whatsapp_phone_no_id")
VERIFY_TOKEN = os.getenv("Whatsapp_verify_token")

@app.get("/webhook")
def verify():
    """Handle WhatsApp Webhook verification."""
    if (request.args.get("hub.mode") == "subscribe"
            and request.args.get("hub.verify_token") == VERIFY_TOKEN):
        return request.args.get("hub.challenge"), 200
    return "Forbidden", 403

@app.post("/webhook")
def webhook():
    """Handle incoming messages from WhatsApp."""
    data = request.get_json(silent=True) or {}
    
    if data.get("object") != "whatsapp_business_account":
        return "ok", 200

    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            messages = value.get("messages", [])

            for msg in messages:
                ctx = _build_context(msg, value)
                message_id = msg.get("id")
                sender_number = ctx.get("from")
                
                print(f"\n--- New Message Received ({message_id}) ---")

                if not _should_respond(ctx):
                    print(f"[webhook] Filtered: Ignoring message {message_id}")
                    continue

                user_text = ctx.get("text", "").replace("@bot", "").strip()
                if not user_text:
                    continue

                print(f"User Sent: {user_text}")

                try:
                    print(f"[webhook] Calling AI (orchestar)...")
                    reply = asyncio.run(process_message(sender_number, user_text))
                    
                    print(f"[webhook] AI Reply: {reply}")
                    _send_whatsapp(sender_number, reply)

                except Exception as e:
                    error_msg = "System Error: I'm having trouble connecting to my brain right now."
                    print(f"[webhook] CRITICAL ERROR: {e}")
                    _send_whatsapp(sender_number, error_msg)

    return "ok", 200

def _build_context(msg: dict, value: dict) -> dict:
    """Extracts essential metadata from the WhatsApp JSON payload."""
    return {
        "id":         msg.get("id"),
        "from":       msg.get("from"),
        "text":       msg.get("text", {}).get("body", ""),
        "reply_to":   msg.get("context", {}).get("id"),          
        "is_mention": "@bot" in msg.get("text", {}).get("body", ""),
        "is_group":   value.get("metadata", {}).get("display_phone_number") != msg.get("from"),
    }

def _should_respond(ctx: dict) -> bool:
    """Logic to decide if the bot should reply (DM vs Group)."""
    if not ctx["is_group"]:   return True   
    if ctx["is_mention"]:     return True   
    if ctx["reply_to"]:       return True   
    return False                            

def _send_whatsapp(to: str, text: str):
    """Sends a text message via the WhatsApp Graph API."""
    url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json"
    }

    for chunk in _split(text, 4000):
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {"body": chunk, "preview_url": False},
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"[WhatsApp] ERROR {response.status_code}: {response.text}")
        except Exception as e:
            print(f"[WhatsApp] Connection Error: {e}")


def _split(text: str, limit: int) -> list[str]:
    """Splits long text into chunks, ideally at newlines."""
    if len(text) <= limit:
        return [text]
    chunks, remaining = [], text
    while remaining:
        cut = limit
        nl = remaining.rfind("\n", 0, limit)
        if nl > limit * 0.7:
            cut = nl + 1
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()
    return chunks


if __name__ == "__main__":
    port = int(os.getenv("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=True)