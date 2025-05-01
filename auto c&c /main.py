import os
import yaml
import schedule
import time
from email_providers import gmail, outlook
from calendar_providers import google_calendar, outlook_calendar
from ai import reply_interpreter

CONFIG_PATH = 'config.yaml'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)

def main_job(config):
    provider = config['provider']
    if provider == 'gmail':
        emailer = gmail.GmailEmailer(config['gmail'])
        calendar = google_calendar.GoogleCalendar(config['gmail'])
    else:
        emailer = outlook.OutlookEmailer(config['outlook'])
        calendar = outlook_calendar.OutlookCalendar(config['outlook'])
    ai = reply_interpreter.AIReplyInterpreter(config['openai']['api_key'])

    # 1. Send cold emails
    prompt = get_dynamic_prompt()
    email_text = generate_email(prompt)
    emailer.send_cold_emails(email_text)

    # 2. Check for replies
    replies = emailer.fetch_replies()
    for reply in replies:
        action = interpret_reply(reply)
        if action['type'] == 'respond':
            emailer.send_response(reply, action['response'])
        elif action['type'] == 'invite':
            calendar.send_invite(reply['email'], action['datetime'])

if __name__ == '__main__':
    config = load_config()
    interval = config.get('scheduling', {}).get('interval_minutes', 10)
    schedule.every(interval).minutes.do(main_job, config)
    print(f"[INFO] Automatic cold emailer running every {interval} minutes.")
    while True:
        schedule.run_pending()
        time.sleep(5)
