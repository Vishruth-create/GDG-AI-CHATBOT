import requests, json
import os

ACCESS_TOKEN: str = os.environ["WA_ACCESS_TOKEN"]
PHONE_NUMBER_ID = '917780508094662'
VERSION = 'v22.0'


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