import requests, json

ACCESS_TOKEN = "EAAUqVcv7O68BQ7Ixp3TOHS7E7RLmhipwJTyonQxqOZALxn3gfC9sTsNtl3thmdMphP2rX15If9fKZCXOBhxZCDUAZAsXbom65Cw75GO6JgAO0TuXOWXsL6V3kKFOyB8xmrXeRMGlf1AuZAh9gUMvlyGlDG4KOlOjlDFNEKaKXDhWWIWlVzcwwsUxUdx4w1Fs22AqF7GgHm6kxyhngEmmOLo6za8C7kVKS5UOvon37E7Gfg8ZBvGRQvnbHiDPjvKz1kCbHO30hZCx7wQobz9SY4K1XdnZCgZDZD"
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