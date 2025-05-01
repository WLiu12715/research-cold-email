# Automatic Cold Emailer & Calendar Inviter

This project automates cold emailing, AI-powered reply handling, and calendar invite scheduling for Gmail and Outlook users.

## Features
- Send cold emails automatically
- Read and interpret replies using AI
- Auto-respond and send calendar invites based on replies
- Supports both Gmail and Outlook (email & calendar)
- Fully automated (runs as a background service)

## Setup
1. Clone the repo
2. Install dependencies: `pip install -r requirements.txt`
3. Configure your providers and templates in `config.yaml`
4. Run with `python main.py`

## Structure
- `main.py`: Main service loop
- `config.yaml`: Configuration file
- `email_providers/`: Gmail/Outlook email integrations
- `calendar_providers/`: Calendar invite integrations
- `ai/`: AI reply interpreter
- `templates/`: Email templates
- `db/`: State tracking (SQLite)

## Requirements
- Python 3.8+
- API credentials for Gmail and/or Outlook
- OpenAI API key (for AI reply interpretation)

---

## Disclaimer
Use responsibly and in compliance with email and privacy laws.
