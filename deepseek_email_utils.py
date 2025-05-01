from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

# You can replace this with the exact DeepSeek R1 model name if available
MODEL_NAME = "facebook/opt-2.7b"

# Load model and tokenizer once (this may take some time and require sufficient RAM/VRAM)
model = AutoModelForCausalLM.from_pretrained(MODEL_NAME)
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

def generate_email(prompt: str, max_new_tokens: int = 256) -> str:
    """Generate an email using DeepSeek LLM."""
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=True, temperature=0.7)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)

def interpret_reply(reply_text: str, max_new_tokens: int = 128) -> str:
    """Summarize or interpret an email reply using DeepSeek LLM."""
    prompt = (
        f"Analyze the following email reply and summarize the sender's intent, tone, and whether they are interested in continuing the conversation:\n\n"
        f"Reply:\n{reply_text}\n\nSummary:"
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=True, temperature=0.7)
    return tokenizer.decode(outputs[0], skip_special_tokens=True)
