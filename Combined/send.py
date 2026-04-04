import requests, json
import os

ACCESS_TOKEN: str = os.environ["WA_ACCESS_TOKEN"]
PHONE_NUMBER_ID = '917780508094662'
VERSION = 'v22.0'

import base64

WA_PHONE_ID = os.environ["WA_PHONE_NUMBER_ID"]

def send_document(phone_number: str, file_bytes: bytes, filename: str, mime_type: str):
    """Upload media to WhatsApp and send it as a document."""
    upload_url = f"https://graph.facebook.com/v22.0/{WA_PHONE_ID}/media"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
    
    upload_res = requests.post(upload_url, headers=headers, files={
        "file": (filename, file_bytes, mime_type),
        "type": (None, mime_type),
        "messaging_product": (None, "whatsapp"),
    })
    media_id = upload_res.json().get("id")
    if not media_id:
        print(f"[send] Media upload failed: {upload_res.text}")
        return

    send_url = f"https://graph.facebook.com/v22.0/{WA_PHONE_ID}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": phone_number,
        "type": "document",
        "document": {"id": media_id, "filename": filename},
    }
    res = requests.post(send_url, headers={**headers, "Content-Type": "application/json"},
                        data=json.dumps(payload))
    if res.status_code == 200:
        print(f"[send] Document '{filename}' sent to {phone_number}")
    else:
        print(f"[send] Document send failed: {res.status_code} {res.text}")

def send_message(phone_number, text):
    url = f"https://graph.facebook.com/{VERSION}/{PHONE_NUMBER_ID}/messages"
    headers = {
            "Authorization": f"Bearer {ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
    data = {
        "messaging_product" : "whatsapp",
        "to" : phone_number,
        "type" : "text",
        "text" : {
            "body" : text
        }
    }

    response = requests.post(url, headers=headers, data = json.dumps(data))

    if response.status_code == 200:
         print("Messsage sent successfully")
    else:
         print(f'Failed to send message : {response.status_code} + {response.text}')