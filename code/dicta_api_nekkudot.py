import os
import sys
import re
import json
import urllib.request
import unicodedata
import time

# Ensure UTF-8 output for Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# API Configuration
DICTA_API_URL = 'https://nakdan-2-0.loadbalancer.dicta.org.il/api'
BATCH_SIZE_CHARS = 3000 # Send up to 3000 characters per request

def strip_niqqud(text: str) -> str:
    """Remove all Hebrew vowel points (niqqud), cantillation marks, and normalize punctuation."""
    text = unicodedata.normalize('NFC', text)
    text = text.replace('\u05F3', "'").replace('\u05F4', '"')
    return ''.join(
        ch for ch in text
        if unicodedata.category(ch) != 'Mn'
    )

def is_mostly_hebrew(text: str) -> bool:
    """Detects if a line is likely Hebrew source text."""
    if not text.strip():
        return False
    heb_chars = len(re.findall(r'[\u0590-\u05FF]', text))
    eng_chars = len(re.findall(r'[a-zA-Z]', text))
    return heb_chars > eng_chars and heb_chars > 0

def call_dicta_api(text: str, genre: str = "rabbinic") -> list | None:
    """Sends text to Dicta Nakdan API and returns the tokenized results."""
    payload = {
        "task": "nakdan",
        "data": text,
        "genre": genre,
        "addmorph": True,
        "keepqq": False,
        "nodageshdefective": False,
        "bylayer": False
    }
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(DICTA_API_URL, data=data, headers={'Content-Type': 'application/json'})
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.loads(response.read().decode('utf-8'))
        except Exception as e:
            if attempt < max_retries - 1:
                print(f"    [Dicta API] Attempt {attempt+1} failed: {e}. Retrying...")
                time.sleep(2)
            else:
                print(f"    [Dicta API] Final Error: {e}")
                return None

def process_batch(batch_text: str) -> str:
    """Sends a batch of text to the API and reconstructs it with Consonant Lock."""
    if not batch_text.strip():
        return batch_text
        
    tokens = call_dicta_api(batch_text)
    if not tokens:
        return batch_text

    result_parts = []
    for item in tokens:
        original_word = item.get('word', '')
        
        if item.get('sep'):
            # Separator or newline
            result_parts.append(original_word)
        elif item.get('options'):
            # Word with vocalization
            best_vocalized = item['options'][0][0].replace('|', '')
            
            # Consonant-Lock Guard
            if strip_niqqud(best_vocalized) == strip_niqqud(original_word):
                result_parts.append(best_vocalized)
            else:
                result_parts.append(original_word)
        else:
            result_parts.append(original_word)

    return ''.join(result_parts)

def apply_nekkudot_to_text(text: str) -> str:
    """Applies nekkudot in large batches to Hebrew sections within a text string."""
    print(f"  [Dicta API] Processing nekkudot...")
    lines = text.splitlines(keepends=True)
    new_content = []
    current_batch = []
    current_batch_len = 0
    
    def flush_batch():
        nonlocal current_batch, current_batch_len
        if not current_batch:
            return
        
        batch_str = "".join(current_batch)
        vocalized = process_batch(batch_str)
        new_content.append(vocalized)
        
        current_batch = []
        current_batch_len = 0

    for line in lines:
        clean_line = line.strip()
        
        # We only batch Hebrew lines. Headers, separators, and English lines are flushed.
        if not clean_line or clean_line.startswith('#') or clean_line.startswith('---') or not is_mostly_hebrew(clean_line):
            flush_batch()
            new_content.append(line)
        else:
            current_batch.append(line)
            current_batch_len += len(line)
            if current_batch_len >= BATCH_SIZE_CHARS:
                flush_batch()
                
    flush_batch() # Final flush
    print(f"  [Dicta API] Finished vocalization.")
    return "".join(new_content)

def apply_nekkudot_to_file(filepath: str):
    """Reads a file and applies nekkudot in large batches to Hebrew sections."""
    if not os.path.exists(filepath):
        print(f"  ✗ Error: File not found: {filepath}")
        return

    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()

    print(f"  [Dicta API] Processing {os.path.basename(filepath)}...")
    vocalized_text = apply_nekkudot_to_text(text)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(vocalized_text)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        apply_nekkudot_to_file(sys.argv[1])
    else:
        print("Usage: python dicta_api_nekkudot.py <path_to_md>")
