from flask import Flask, request, jsonify
import requests, json
from send import send_message
from brain import generate_response
import threading

app = Flask(__name__)
VERIFICATION_TOKEN = 'GDG_AI_2026_CHATBOT'

def handle_user(prompt, number):
    response = generate_response(prompt)
    send_message(number, response)

# send_message(919414001035, "GDG-Ai here!!")
@app.route('/webhooks', methods = ['GET', 'POST'])
def whatsapp():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        verification_token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if verification_token == VERIFICATION_TOKEN and mode == "subscribe":
            print("Verification succesful")
            return challenge, 200
        return "Verification Failed", 403
    
    if request.method == "POST":
        data = request.get_json()
        # print("Data receieved from whatsapp!!\n\n", data)
        value = data["entry"][0]["changes"][0]["value"]
        if "messages" in value:
            message = value["messages"][0]
            contact = value["contacts"][0]
            if message["type"] == "text":
                    phone_number = message["from"]
                    sender_name = contact["profile"]["name"]
                    message_text = message["text"]["body"]

                    # print("Message Received!!\n")
                    # print(f"Phone number ; {phone_number}")
                    # print(f"Name : {sender_name}")
                    # print(message_text)
                    t = threading.Thread(target=handle_user, args=(message_text, phone_number))
                    t.start()
        return jsonify({"status": "success"}), 200
    
if __name__ == '__main__':
    app.run(debug = True, port = 8000)
        