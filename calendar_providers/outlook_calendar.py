import requests
from msal import ConfidentialClientApplication

class OutlookCalendar:
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

    def send_invite(self, email, event_datetime):
        url = 'https://graph.microsoft.com/v1.0/me/events'
        event = {
            "subject": "Meeting Invitation",
            "start": {"dateTime": event_datetime, "timeZone": "UTC"},
            "end": {"dateTime": event_datetime, "timeZone": "UTC"},
            "attendees": [
                {"emailAddress": {"address": email, "name": email}, "type": "required"}
            ]
        }
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        requests.post(url, json=event, headers=headers)
