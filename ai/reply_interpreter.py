import openai

class AIReplyInterpreter:
    def __init__(self, api_key):
        openai.api_key = api_key

    def interpret(self, reply):
        prompt = f"""
You are an AI assistant for an automated cold email outreach tool.
Analyze the following email reply and decide:
1. Should we respond? If so, what should we say?
2. Should we offer a calendar invite? If so, suggest a date/time if available.

Reply:
{reply['body']}

Respond with a JSON object like:
{{"type": "respond", "response": "..."}}
OR
{{"type": "invite", "datetime": "YYYY-MM-DDTHH:MM:SSZ"}}
"""
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            max_tokens=256,
            temperature=0.2
        )
        import json
        content = response['choices'][0]['message']['content']
        try:
            return json.loads(content)
        except Exception:
            return {"type": "respond", "response": "Thank you for your reply!"}
