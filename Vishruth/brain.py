import requests, json

def generate_response(user_message):
    url = "http://localhost:11434/api/generate"

    data = {
        "model" : "llama3",
        "prompt": f"You are helpful assistant for the Google Developer Students Group of IIT Indore. The User says: {user_message}",
        "stream": False
    }

    response = requests.post(url, data = json.dumps(data))

    if response.status_code == 200:
        print("Successfully generated responose")
        return response.json()["response"]
    else:
        print(f"Local AI Error: {response.text}")
        return "My local brain is resting!"