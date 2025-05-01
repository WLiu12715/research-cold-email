import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

class GmailEmailer:
    def __init__(self, config):
        self.creds = Credentials(
            None,
            refresh_token=config['refresh_token'],
            client_id=config['client_id'],
            client_secret=config['client_secret'],
            token_uri='https://oauth2.googleapis.com/token'
        )
        self.service = build('gmail', 'v1', credentials=self.creds)
        self.sent_label = 'Label_ColdEmailerSent'

    def send_cold_emails(self, to_email, body, subject="Let's connect!"):
        message = MIMEText(body)
        message['to'] = to_email
        message['from'] = 'me'
        message['subject'] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        self.service.users().messages().send(userId='me', body={'raw': raw}).execute()

    def fetch_replies(self):
        # Fetch replies to sent emails
        query = f'label:{self.sent_label} is:inbox'
        results = self.service.users().messages().list(userId='me', q=query).execute()
        messages = results.get('messages', [])
        replies = []
        for msg in messages:
            msg_data = self.service.users().messages().get(userId='me', id=msg['id']).execute()
            payload = msg_data.get('payload', {})
            headers = {h['name']: h['value'] for h in payload.get('headers', [])}
            body = base64.urlsafe_b64decode(payload.get('body', {}).get('data', '')).decode(errors='ignore')
            replies.append({'email': headers.get('From'), 'body': body, 'id': msg['id']})
        return replies

    def send_response(self, reply, response_text):
        message = MIMEText(response_text)
        message['to'] = reply['email']
        message['from'] = 'me'
        message['subject'] = 'Re: Follow up'
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
        self.service.users().messages().send(userId='me', body={'raw': raw}).execute()
