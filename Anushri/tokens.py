import os
from google_auth_oauthlib.flow import InstalledAppFlow
from dotenv import load_dotenv

load_dotenv()

SCOPE= [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly"
]

flow = InstalledAppFlow.from_client_config(
    {
        "installed": {
            "client_id": os.getenv("gmail_client_id"),
            "client_secret": os.getenv("gmail_client_secret"),
            "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob", "http://localhost"],
            "auth_uri":"https://accounts.google.com/o/oauth2/auth",
            "token_uri":"https://oauth2.googleapis.com/token",
        }
    },
    scopes=SCOPE,
)
 
creds = flow.run_local_server(port=0)

print("\n--- AUTHORIZATION SUCCESSFUL ---")
print(f"GMAIL_ACESS_TOKEN={creds.token}")
print(f"GMAIL_REFRESH_TOKEN={creds.refresh_token}")
print("----------------------------------")
input("Copy these to your .env file, then press Enter to exit...")

