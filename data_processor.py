import docx
import json
import re
import tiktoken
import os
from openai import OpenAI
import time

# --- Configuration ---
# Replace these with your actual filenames
INPUT_DOCX = "yyl.docx" 
OUTPUT_JSONL = "training_data.jsonl"
OUTPUT_TXT = "deepseek_context.txt"
SYSTEM_PROMPT = "You are a digital clone of [YOUR_NAME]. Mimic the tone, style, and vocabulary from the training data."

API_KEY = "sk-dc4c6988c52c46d88d8f1d742e099721" # DeepSeek API Key provided by user
MODEL_NAME = "deepseek-chat" # DeepSeek V3 model
BASE_URL = "https://api.deepseek.com"

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# Regex to identify speaker lines (Modify based on your doc format)
# Updated for "Name: Content" format
SPEAKER_PATTERN = r"^([^:]+):\s*(.*)$"

def extract_conversations(docx_path):
    doc = docx.Document(docx_path)
    messages = []
    
    current_speaker = None
    current_text = []
    
    print(f"Reading {docx_path}...")
    
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text: continue
        
        # Check if line is "Name: Content"
        match = re.match(SPEAKER_PATTERN, text)
        if match:
            # If we have accumulated text for previous speaker, save it
            if current_speaker and current_text:
                messages.append({
                    "role": current_speaker,
                    "content": "\n".join(current_text)
                })
            
            # Start new speaker
            current_speaker = match.group(1).strip() # Extract name
            content_part = match.group(2).strip()
            current_text = [content_part] if content_part else []
        else:
            # Append text to current speaker (continuation line)
            if current_speaker:
                current_text.append(text)
    
    # Add last message
    if current_speaker and current_text:
        messages.append({
            "role": current_speaker,
            "content": "\n".join(current_text)
        })
        
    return messages

def export_plain_text(raw_messages, output_path):
    """
    Exports the chat history as a plain text file.
    This is ideal for DeepSeek's long context window (Context Caching/In-Context Learning).
    """
    print(f"Exporting plain text to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        for msg in raw_messages:
            f.write(f"{msg['role']}: {msg['content']}\n\n")

def summarize_chunk(text_chunk, index, total):
    """
    Summarizes a chunk of chat history using DeepSeek API.
    """
    print(f"Summarizing chunk {index}/{total} (length: {len(text_chunk)} chars)...")
    prompt = f"""You are a highly efficient assistant summarizing a chat history segment between 'Ptaclfere' and 'Yy'.
    
Your goal is to COMPRESS this information while retaining maximum value for a digital clone of Yy.
    
INSTRUCTIONS:
1. Filter out trivial greetings, logistics (e.g., "good morning", "eating now"), and repetitive small talk.
2. Extract and Retain:
   - Key life events, shared memories, and relationship milestones.
   - Specific preferences, hobbies, and factual details about Yy.
   - Distinctive speaking styles, catchphrases, and emotional patterns of Yy.
   - Nicknames and inside jokes.
3. Output format: A dense, information-rich summary paragraph or bullet points.
    
CHAT SEGMENT:
{text_chunk}
    
SUMMARY:"""

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3, # Low temp for factual summary
            max_tokens=4000
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error summarizing chunk {index}: {e}")
        return ""

def process_history_smartly(raw_msgs, output_path):
    """
    Pipeline:
    1. Keep last 2000 messages verbatim (for immediate tone).
    2. Summarize the rest in chunks.
    3. Combine Summary + Verbatim Recent.
    """
    
    # 1. Split
    VERBATIM_COUNT = 2000
    if len(raw_msgs) <= VERBATIM_COUNT:
        print("History is short enough. No summarization needed.")
        export_plain_text(raw_msgs, output_path)
        return

    recent_msgs = raw_msgs[-VERBATIM_COUNT:]
    older_msgs = raw_msgs[:-VERBATIM_COUNT]
    
    print(f"Total Messages: {len(raw_msgs)}")
    print(f"Verbatim Recent: {len(recent_msgs)}")
    print(f"Older to Summarize: {len(older_msgs)}")
    
    # 2. Chunk Older Messages
    # Group by messages (e.g., 500 messages per chunk)
    CHUNK_SIZE = 500
    chunks = []
    current_chunk = []
    
    for msg in older_msgs:
        current_chunk.append(f"{msg['role']}: {msg['content']}")
        if len(current_chunk) >= CHUNK_SIZE:
            chunks.append("\n".join(current_chunk))
            current_chunk = []
            
    if current_chunk:
        chunks.append("\n".join(current_chunk))
        
    print(f"Created {len(chunks)} chunks for summarization.")
    
    # 3. Summarize Chunks
    summaries = []
    for i, chunk in enumerate(chunks):
        summary = summarize_chunk(chunk, i+1, len(chunks))
        if summary:
            summaries.append(summary)
        # Avoid rate limits if necessary (DeepSeek is fast usually)
        time.sleep(0.5) 
        
    full_summary = "\n\n".join(summaries)
    
    # 4. Save Combined Context
    print(f"Saving smart context to {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("--- KNOWLEDGE BASE (SUMMARIZED HISTORY) ---\n")
        f.write(full_summary)
        f.write("\n\n--- RECENT CONVERSATION (VERBATIM) ---\n")
        for msg in recent_msgs:
            f.write(f"{msg['role']}: {msg['content']}\n\n")

def estimate_tokens(file_path, is_jsonl=True):
    enc = tiktoken.get_encoding("cl100k_base")
    total_tokens = 0
    with open(file_path, 'r', encoding='utf-8') as f:
        if is_jsonl:
            for line in f:
                data = json.loads(line)
                for msg in data['messages']:
                    total_tokens += len(enc.encode(msg['content']))
        else:
            content = f.read()
            total_tokens = len(enc.encode(content))
            
    return total_tokens

if __name__ == "__main__":
    # 1. Extract
    if not os.path.exists(INPUT_DOCX):
        print(f"Error: {INPUT_DOCX} not found.")
        exit()
        
    raw_msgs = extract_conversations(INPUT_DOCX)
    print(f"Extracted {len(raw_msgs)} message blocks.")
    
    if not raw_msgs:
        print("No messages found! Check the SPEAKER_PATTERN regex.")
        exit()

    # 2. Identify Names
    speakers = list(set(m['role'] for m in raw_msgs))
    print(f"Found speakers: {speakers}")
    
    # 3. Smart Process (Summarize + Verbatim)
    process_history_smartly(raw_msgs, OUTPUT_TXT)
    
    # 4. Check Final Size
    txt_tokens = estimate_tokens(OUTPUT_TXT, is_jsonl=False)
    print(f"Final Smart Context Size: ~{txt_tokens} tokens")
