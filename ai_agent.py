import os
from openai import OpenAI

# --- Configuration ---
API_KEY = "sk-dc4c6988c52c46d88d8f1d742e099721" # DeepSeek API Key provided by user
MODEL_NAME = "deepseek-chat" # DeepSeek V3 model
BASE_URL = "https://api.deepseek.com"
CONTEXT_FILE = "deepseek_context.txt"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# Load context once
try:
    with open(CONTEXT_FILE, "r", encoding="utf-8") as f:
        print(f"Loading context from {CONTEXT_FILE}...")
        LONG_CONTEXT = f.read()
        print(f"Loaded {len(LONG_CONTEXT)} chars of context.")
except FileNotFoundError:
    print(f"[Warning] {CONTEXT_FILE} not found. Running without history context.")
    LONG_CONTEXT = ""

def chat_with_agent(user_input, history=[]):
    """
    Simple chat function maintaining history context.
    """
    # System Prompt with Long Context Injection
    system_prompt = f"""You are a digital clone of 'Yy'.
Your task is to roleplay as Yy and chat with 'Ptaclfere' (the user).
Below is a large collection of your past chat history. 
Mimic Yy's tone, vocabulary, sentence length, and emoji usage EXACTLY based on this history.
Do not act like an AI. Act like a real person.

--- BEGIN CHAT HISTORY ---
{LONG_CONTEXT}
--- END CHAT HISTORY ---

Now, reply to the latest message from Ptaclfere.
"""

    messages = [
        {"role": "system", "content": system_prompt}
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": user_input})
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=1.3, # DeepSeek V3 works well with high temp for creativity
            max_tokens=500
        )
        
        reply = response.choices[0].message.content
        return reply
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    print(f"--- Chatting with {MODEL_NAME} (DeepSeek API) ---")
    print("Type 'exit' to quit.")
    
    chat_history = []
    
    while True:
        user_in = input("\nYou: ")
        if user_in.lower() in ['exit', 'quit']:
            break
            
        ai_out = chat_with_agent(user_in, chat_history)
        print(f"Agent: {ai_out}")
        
        # Update history
        chat_history.append({"role": "user", "content": user_in})
        chat_history.append({"role": "assistant", "content": ai_out})
        
        # DeepSeek has a large context window, but we already filled most of it with history.
        # Keep short-term memory limited to avoid overflow if context is near 60k.
        if len(chat_history) > 20: 
            chat_history = chat_history[-20:]
