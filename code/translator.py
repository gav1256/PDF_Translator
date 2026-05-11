"""
translator.py — Modular LLM API interface.
Supports Gemini, OpenAI, Claude, and MetaAI.
"""

import os
import requests
from dotenv import load_dotenv

# Load .env once at the module level
load_dotenv()

def _build_system_prompt(input_lang, output_lang, extra_specs=""):
    """
    Constructs the system prompt dynamically.
    """
    specs = f" {extra_specs}" if extra_specs else ""
    return (
        f"You are an expert translator, translating {input_lang} to {output_lang} "
        f"to keep the flow and nuance of the original text. "
        f"DO NOT add additional ideas, commentary, or explanations.{specs}"
    )

def _call_gemini(text, system_prompt, api_key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash", # Using flash for speed/cost as default
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

def call_translation_api(text, model_choice, input_lang, output_lang, extra_specs=""):
    """
    Orchestrates the translation call based on the model choice.
    """
    system_prompt = _build_system_prompt(input_lang, output_lang, extra_specs)
    
    # Map selection to internal functions and env keys
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

    # Implementation of a simple chunker to avoid token limits
    # Max ~4000 characters per chunk for safety across all models
    MAX_CHUNK_SIZE = 4000
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
    
    results = []
    print(f"\n  [Translator] Processing {len(chunks)} chunks via {name}...")
    for i, chunk in enumerate(chunks):
        print(f"    - Chunk {i+1}/{len(chunks)}...", end="", flush=True)
        try:
            translated = func(chunk, system_prompt, api_key)
            results.append(translated)
            print(" Done")
        except Exception as e:
            print(f" Failed: {e}")
            results.append(f"\n[ERROR TRANSLATING CHUNK {i+1}: {e}]\n")
            
    return "\n\n".join(results)
