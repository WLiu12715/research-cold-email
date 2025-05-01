import yaml
from gmail import GmailEmailer
from openai import OpenAI

def main():
    # Load config
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    client = OpenAI(api_key=config['openai']['api_key'])

    # Prompt user for inputs
    recipient_email = input("Recipient email: ").strip()
    recipient_name = input("Recipient name (optional): ").strip()
    your_name = input("Your name: ").strip()
    goal = input("What do you want to accomplish with this email? (short): ").strip()
    common_ground = input("What common ground or connection do you share? (optional): ").strip()

    # Compose prompt for OpenAI
    system_prompt = """
You are an expert at writing highly effective, warm, and relatable cold emails. Given the user's goal and any common ground with the recipient, write a concise, friendly, and personalized email. If common ground is provided, weave it in naturally to build rapport. Sign off with the user's name.
"""
    user_prompt = f"""
Recipient: {recipient_name or recipient_email}
Goal: {goal}
Common ground: {common_ground}
Your name: {your_name}
"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        max_tokens=300
    )
    email_body = response.choices[0].message.content.strip()
    print("\n--- Generated Email ---\n")
    print(email_body)
    send = input("\nSend this email? (y/n): ").strip().lower()
    if send == 'y':
        # Send email via Gmail
        emailer = GmailEmailer(config['gmail'])
        subject = "Let's Connect!"
        emailer.send_custom_email(recipient_email, subject, email_body)
        print(f"Email sent to {recipient_email}!")
    else:
        print("Email not sent.")

if __name__ == "__main__":
    main()
