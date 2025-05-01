import requests
from msal import ConfidentialClientApplication

class OutlookEmailer:
    def __init__(self, config):
        self.client_id = config['client_id']
        self.client_secret = config['client_secret']
        self.tenant_id = config['tenant_id']
        self.refresh_token = config['refresh_token']
        self.token_url = f'https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token'
        self.app = ConfidentialClientApplication(
            self.client_id,
            authority=f'https://login.microsoftonline.com/{self.tenant_id}',
            client_credential=self.client_secret
        )
        self.token = self._get_token()

    def _get_token(self):
        result = self.app.acquire_token_by_refresh_token(
            refresh_token=self.refresh_token,
            scopes=["https://graph.microsoft.com/.default"]
        )
        return result['access_token']

    def send_cold_emails(self, to_email, body, subject="Let's connect!"):
        url = 'https://graph.microsoft.com/v1.0/me/sendMail'
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": to_email}}]
            },
            "saveToSentItems": "true"
        }
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        requests.post(url, json=payload, headers=headers)

    def fetch_replies(self):
        # Fetch replies to sent emails
        url = 'https://graph.microsoft.com/v1.0/me/messages?$search="in:inbox"'
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.get(url, headers=headers)
        messages = resp.json().get('value', [])
        replies = []
        for msg in messages:
            if msg.get('conversationId'):  # TODO: Filter for replies to cold emails
                replies.append({'email': msg['from']['emailAddress']['address'], 'body': msg['body']['content'], 'id': msg['id']})
        return replies

    def send_response(self, reply, response_text):
        url = f'https://graph.microsoft.com/v1.0/me/sendMail'
        payload = {
            "message": {
                "subject": "Re: Follow up",
                "body": {"contentType": "Text", "content": response_text},
                "toRecipients": [{"emailAddress": {"address": reply['email']}}]
            },
            "saveToSentItems": "true"
        }
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        requests.post(url, json=payload, headers=headers)
