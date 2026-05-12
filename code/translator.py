"""
translator.py — Modular LLM API interface.
Supports Gemini, OpenAI, Claude, and MetaAI.
"""

import os
import requests
from dotenv import load_dotenv

# Load .env once at the module level
load_dotenv()

from config import SYSTEM_PROMPT_PASS1, SYSTEM_PROMPT_PASS2

def _call_gemini(text, system_prompt, api_key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite", # Using flash for speed/cost as default
        contents=[text],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.1,
        )
    )
    return response.text.strip()

def _call_openai(text, system_prompt, api_key):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        temperature=0.1
    )
    return response.choices[0].message.content.strip()

def _call_claude(text, system_prompt, api_key):
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=8192,
        system=system_prompt,
        messages=[{"role": "user", "content": text}],
        temperature=0.1
    )
    return response.content[0].text.strip()

def _call_meta(text, system_prompt, api_key):
    """
    Using a standard Llama API endpoint (e.g., via Groq or similar if available, 
    but for now following the generic MetaAI request structure).
    """
    # Note: MetaAI doesn't have a direct "API key for a website" usually, 
    # but Llama models are available via many providers. 
    # We'll use a placeholder structure for a typical Llama provider.
    endpoint = "https://api.llama-api.com/chat/completions" # Placeholder
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    payload = {
        "model": "llama3-70b-8192",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.1
    }
    response = requests.post(endpoint, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"].strip()

def _get_api_config(model_choice):
    """Internal helper to get model metadata and API key."""
    config = {
        1: ("Gemini", "GEMINI_API_KEY", _call_gemini),
        2: ("OpenAI", "OPENAI_API_KEY", _call_openai),
        3: ("Claude", "ANTHROPIC_API_KEY", _call_claude),
        4: ("MetaAI", "META_API_KEY", _call_meta)
    }
    name, env_key, func = config.get(model_choice, (None, None, None))
    if not func:
        raise ValueError("Invalid model choice.")
    api_key = os.getenv(env_key)
    if not api_key:
        raise ValueError(f"API key for {name} ({env_key}) not found in .env file.")
    return name, api_key, func

def run_pass1(text, model_choice, input_lang, output_lang, extra_specs=""):
    """
    Runs Pass 1 (Drafting) for all chunks.
    Returns (combined_draft, chunk_data) where chunk_data is a list of (orig_chunk, draft_chunk).
    """
    name, api_key, func = _get_api_config(model_choice)
    prompt1 = SYSTEM_PROMPT_PASS1.format(source_lang=input_lang, target_lang=output_lang)
    if extra_specs:
        prompt1 += f"\n\nAdditional Specifications: {extra_specs}"

    # Implementation of a simple chunker to avoid token limits
    MAX_CHUNK_SIZE = 50000
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = ""
    for p in paragraphs:
        if len(current_chunk) + len(p) < MAX_CHUNK_SIZE:
            current_chunk += ("\n\n" if current_chunk else "") + p
        else:
            if current_chunk:
                chunks.append(current_chunk)
            current_chunk = p
    if current_chunk:
        chunks.append(current_chunk)

    chunk_data = []
    results = []
    print(f"\n  [Translator] Running Pass 1 ({len(chunks)} chunks) via {name}...")
    for i, chunk in enumerate(chunks):
        print(f"    - Chunk {i+1}/{len(chunks)}... (Drafting)", end="", flush=True)
        try:
            draft = func(chunk, prompt1, api_key)
            chunk_data.append((chunk, draft))
            results.append(draft)
            print(" Done")
        except Exception as e:
            print(f" Failed: {e}")
            results.append(f"\n[ERROR PASS 1 CHUNK {i+1}: {e}]\n")
            chunk_data.append((chunk, None))
            
    return "\n\n".join(results), chunk_data

def run_pass2(chunk_data, model_choice, input_lang, output_lang, extra_specs=""):
    """
    Runs Pass 2 (Reconstruction) using matched chunk data.
    Returns combined_final_text.
    """
    name, api_key, func = _get_api_config(model_choice)
    prompt2 = SYSTEM_PROMPT_PASS2.format(source_lang=input_lang, target_lang=output_lang)
    if extra_specs:
        prompt2 += f"\n\nAdditional Specifications: {extra_specs}"

    results = []
    print(f"\n  [Translator] Running Pass 2 ({len(chunk_data)} chunks) via {name}...")
    for i, (orig_chunk, draft_chunk) in enumerate(chunk_data):
        if not draft_chunk:
            results.append(f"\n[SKIPPED PASS 2 CHUNK {i+1}: Pass 1 failed]\n")
            continue
            
        print(f"    - Chunk {i+1}/{len(chunk_data)}... (Reconstructing)", end="", flush=True)
        try:
            pass2_input = f"--- ORIGINAL FRAGMENTS ---\n{orig_chunk}\n\n--- DRAFT TRANSLATION ---\n{draft_chunk}"
            reconstructed = func(pass2_input, prompt2, api_key)
            results.append(reconstructed)
            print(" Done")
        except Exception as e:
            print(f" Failed: {e}")
            results.append(f"\n[ERROR PASS 2 CHUNK {i+1}: {e}]\n")
            
    return "\n\n".join(results)
