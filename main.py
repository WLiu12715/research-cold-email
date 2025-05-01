import os
import yaml
import schedule
import time
from deepseek_email_utils import generate_email, interpret_reply
import gmail
import outlook
import google_calendar
import outlook_calendar

CONFIG_PATH = 'config.yaml'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return yaml.safe_load(f)
import requests

def search_semantic_scholar(query, limit=3):
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,abstract,url"
    }
    response = requests.get(url, params=params)
    response.raise_for_status()
    data = response.json()
    return data.get("data", [])

def get_dynamic_prompt():
    print("Who is the recipient? (name): ", end="")
    recipient_name = input().strip()
    to_email = input("What is their email address?: ").strip()
    your_name = input("What is your name?: ").strip()
    your_affiliation = input("What is your affiliation? (e.g., university, lab, etc.): ").strip()

    # Offer to search Semantic Scholar
    print("Would you like to search for a research paper to reference? (y/n): ", end="")
    if input().strip().lower().startswith('y'):
        query = input("Enter keywords, title, or topic to search for: ").strip()
        papers = search_semantic_scholar(query, limit=3)
        if not papers:
            print("No papers found. Please enter details manually.")
            research_interest = input("What specific research, project, or paper are you interested in?: ").strip()
            intrigue_reason = input("Why does this research intrigue you? (one or two sentences): ").strip()
        else:
            print("Select a paper to reference:")
            for i, paper in enumerate(papers):
                print(f"{i+1}. {paper['title']} (by {', '.join([a['name'] for a in paper['authors']])})")
                print(f"   Abstract: {paper.get('abstract', 'No abstract available')}")
                print(f"   URL: {paper['url']}")
            print("0. None of these (enter details manually)")
            choice = input("Enter the number of the paper to use: ").strip()
            try:
                idx = int(choice)
            except ValueError:
                idx = 0
            if idx > 0 and idx <= len(papers):
                paper = papers[idx-1]
                research_interest = paper['title']
                intrigue_reason = paper.get('abstract', '')
                print("You can edit the auto-filled fields below if you want.")
                research_interest = input(f"Research of interest [{research_interest}]: ").strip() or research_interest
                intrigue_reason = input(f"Why it's intriguing [{intrigue_reason[:100]}...]: ").strip() or intrigue_reason
            else:
                research_interest = input("What specific research, project, or paper are you interested in?: ").strip()
                intrigue_reason = input("Why does this research intrigue you? (one or two sentences): ").strip()
    else:
        research_interest = input("What specific research, project, or paper are you interested in?: ").strip()
        intrigue_reason = input("Why does this research intrigue you? (one or two sentences): ").strip()

    goal = input("What is your main goal? (e.g., collaboration, mentorship, joining the lab, etc.): ").strip()
    common_ground = input("Do you share any mutuals or shared interests? (optional): ").strip()

    example_email = (
        "Hello Dr. Chen,\n\n"
        "I'm Ben Kits, a sophomore at Emory University interested in reinforcement learning. I recently read your paper on reward shaping and was fascinated by your novel approach to optimizing sparse rewards.\n\n"
        "I'm currently working on related topics in my coursework and would love to connect to learn more about your methods and discuss possible collaboration.\n\n"
        "If you're available, could we schedule a quick call sometime next week?\n\n"
        "Best regards,\n"
        "Ben"
    )
    prompt = (
        "Write a concise, professional, and warm cold email to a researcher, expressing genuine interest in their work.\n"
        f"From: {your_name} ({your_affiliation})\n"
        f"To: {recipient_name}\n"
        f"Research of interest: {research_interest}\n"
        f"Why it's intriguing: {intrigue_reason}\n"
        f"Goal: {goal}\n"
        + (f"Common ground: {common_ground}\n" if common_ground else "")
        + "\nHere is an example:\n"
        + example_email
        + "\n---\n"
        + f"Now write the email from {your_name} to {recipient_name}. Only output the email, nothing else."
    )
    return prompt, to_email
def main_job(config):
    provider = config['provider']
    if provider == 'gmail':
        emailer = gmail.GmailEmailer(config['gmail'])
        calendar = google_calendar.GoogleCalendar(config['gmail'])
    else:
        emailer = outlook.OutlookEmailer(config['outlook'])
        calendar = outlook_calendar.OutlookCalendar(config['outlook'])

    prompt, to_email = get_dynamic_prompt()
    email_text = generate_email(prompt).strip()
    print("\n--- Generated Email ---\n")
    print(email_text)

    # Fallback for empty or invalid output
    if not email_text or email_text.strip() in {'.', '', '...'}:
        print("[Warning] The generated email was empty or invalid. Here is the raw model output for debugging:")
        print(email_text)

    subject = input("Enter the subject line (or press Enter for default): ").strip() or "Let's connect!"

    # 1. Send cold email
    emailer.send_cold_emails(to_email, email_text, subject)
    print(f"Email sent to {to_email}.")

    # 2. Check for replies
    replies = emailer.fetch_replies()
    for reply in replies:
        summary = interpret_reply(reply)
        print("\n--- Reply Interpretation ---\n")
        print(summary)
        if summary['type'] == 'respond':
            emailer.send_response(reply, summary['response'])
        elif summary['type'] == 'invite':
            calendar.send_invite(reply['email'], summary['datetime'])

if __name__ == '__main__':
    config = load_config()
    print("Welcome to the On-Demand Cold Emailer!")
    while True:
        print("\nMenu:")
        print("1. Send a cold email now")
        print("2. Exit")
        choice = input("Choose an option (1 or 2): ").strip()
        if choice == '1':
            main_job(config)
        elif choice == '2':
            print("Exiting. Goodbye!")
            break
        else:
            print("Invalid choice. Please enter 1 or 2.")
