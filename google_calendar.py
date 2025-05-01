from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

class GoogleCalendar:
    def __init__(self, config):
        self.creds = Credentials(
            None,
            refresh_token=config['refresh_token'],
            client_id=config['client_id'],
            client_secret=config['client_secret'],
            token_uri='https://oauth2.googleapis.com/token'
        )
        self.service = build('calendar', 'v3', credentials=self.creds)

    def send_invite(self, email, event_datetime):
        event = {
            'summary': 'Meeting Invitation',
            'start': {'dateTime': event_datetime, 'timeZone': 'UTC'},
            'end': {'dateTime': event_datetime, 'timeZone': 'UTC'},
            'attendees': [{'email': email}],
        }
        self.service.events().insert(calendarId='primary', body=event).execute()
