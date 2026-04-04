import asyncio
import os
from dotenv import load_dotenv
from flask import Flask, request, jsonify
from orchestar import process_message, speech_to_text, text_to_speech
import requests
import nest_asyncio
nest_asyncio.apply()

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
                sender_number = ctx.get("from")
                user_text = ""

                if not _should_respond(ctx):
                    continue

                if ctx["type"] == "audio" and ctx["media_id"]:
                    print(f"Audio processing from {sender_number}")
                    try:
                        media_url = _get_whatsapp_media_url(ctx["media_id"])
                        input_audio = f"in_{ctx['id']}.ogg"
                        _download_media(media_url, input_audio)
                        
                        user_text = speech_to_text(input_audio)

                        ai_reply_text=asyncio.run(process_message(sender_number, user_text))

                        output_audio=f"out_{ctx['id']}.mp3"
                        text_to_speech(ai_reply_text, output_audio)

                        _send_whatsapp_voice(sender_number, output_audio)

                        os.remove(input_audio)
                        os.remove(output_audio)

                    except Exception as e:
                        print(f"Media Download Error: {e}")
                else:
                    user_text = ctx.get("text", "").replace("@bot", "").strip()

                if user_text:
                    try:
                        print(f"User Sent: {user_text}")
                        reply = asyncio.run(process_message(sender_number, user_text))
                        _send_whatsapp(sender_number, reply)
                    except Exception as e:
                        print(f"AI/Send Error: {e}")
                        _send_whatsapp(sender_number, "I'm having trouble thinking right now.")

    return "ok", 200

def _build_context(msg: dict, value: dict) -> dict:
    """Extracts essential metadata from the WhatsApp JSON payload. It also extracts essential metadata, now including audio support."""
    msg_type=msg.get("type")
    return {
        "id":         msg.get("id"),
        "from":       msg.get("from"),
        "type":       msg_type,
        "text":       msg.get("text", {}).get("body", ""),
        "media_id":   msg.get("audio", {}).get("id") if msg_type=="audio" else None,
        "reply_to":   msg.get("context", {}).get("id"),          
        "is_mention": "@bot" in msg.get("text", {}).get("body", "") or "@bot" in msg.get("audio", {}).get("caption", ""),
        "is_group":   value.get("metadata", {}).get("display_phone_number") != msg.get("from"),
    }

# Whatsapp doesn't give you the audio file directly. It gives an ID. So, we must exchange that ID for a temproary URL and then download the file.
def _get_whatsapp_media_url(media_id: str) -> str:
    """Fetches the actual download URL for a given media ID"""
    url=f"https://graph.facebook.com/v19.0/{media_id}"
    headers={"Authorization": f"Bearer {WA_TOKEN}"}
    response= requests.get(url, headers=headers)
    return response.json().get("url")

def _download_media(url: str, save_path: str):
    """Download the files from the META temporary URL."""
    headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    response = requests.get(url, headers=headers)
    with open(save_path, "wb") as f:
        f.write(response.content)

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

def _send_whatsapp_voice(to, audio_file_path):
    upload_url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/media"
    headers = {"Authorization": f"Bearer {WA_TOKEN}"}
    
    with open(audio_file_path, 'rb') as f:
        files = {
            'file': (os.path.basename(audio_file_path), f, 'audio/mpeg'),
            'type': (None, 'audio/mpeg'),
            'messaging_product': (None, 'whatsapp'),
        }
        upload_res = requests.post(upload_url, headers=headers, files=files)
        
    media_id = upload_res.json().get("id")

    if media_id:
        send_url = f"https://graph.facebook.com/v19.0/{WA_PHONE_ID}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "audio",
            "audio": {"id": media_id}
        }
        requests.post(send_url, headers=headers, json=payload)

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