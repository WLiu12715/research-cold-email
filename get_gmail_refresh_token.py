from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
import json

SCOPES = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/calendar.events',
]

def main():
    client_id = input('Paste your client_id: ').strip()
    client_secret = input('Paste your client_secret: ').strip()
    creds_data = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    }
    # Write to a temporary file
    with open('temp_client_secret.json', 'w') as f:
        json.dump(creds_data, f)
    flow = InstalledAppFlow.from_client_secrets_file('temp_client_secret.json', SCOPES)
    creds = flow.run_local_server(port=0)
    print('\nYour refresh token:')
    print(creds.refresh_token)
    print('\nYour client_id:', client_id)
    print('Your client_secret:', client_secret)
    print('\nPaste these into your config.yaml under gmail:')

if __name__ == '__main__':
    main()
