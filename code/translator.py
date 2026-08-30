"""
translator.py — Multi-provider LLM translation with retries and parallelism.

Providers: Gemini (native SDK, safety filters disabled — needed for religious
Hebrew text), OpenAI, and Claude.  Chunks are translated concurrently with a
bounded thread pool; each request retries with exponential backoff on rate
limits and transient errors.
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

load_dotenv()

import config
from chunker import chunk_text

# Gemini safety config — religious/rabbinic Hebrew can trip generic filters.
_GEMINI_SAFETY = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
]


# ── Provider calls ───────────────────────────────────────────────────────────

def _call_gemini(text, system_prompt, api_key):
    from google import genai
    from google.genai import types
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=config.GEMINI_MODEL,
        contents=[text],
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=config.TEMPERATURE,
            max_output_tokens=config.MAX_OUTPUT_TOKENS,
            safety_settings=_GEMINI_SAFETY,
        ),
    )
    if not response.text:
        raise RuntimeError("Gemini returned no text (possibly filtered)")
    finish = getattr(response.candidates[0], "finish_reason", None) if response.candidates else None
    if finish and str(finish).upper().endswith("MAX_TOKENS"):
        raise RuntimeError("Gemini output truncated (hit max_output_tokens)")
    return response.text.strip()


def _call_openai(text, system_prompt, api_key):
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ],
        temperature=config.TEMPERATURE,
        max_tokens=config.MAX_OUTPUT_TOKENS,
    )
    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenAI returned no text")
    if response.choices[0].finish_reason == "length":
        raise RuntimeError("OpenAI output truncated (hit max_tokens)")
    return content.strip()


def _call_claude(text, system_prompt, api_key):
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)
    # Note: no temperature — removed on current Opus models (400 if sent).
    with client.messages.stream(
        model=config.CLAUDE_MODEL,
        max_tokens=config.MAX_OUTPUT_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": text}],
    ) as stream:
        response = stream.get_final_message()
    parts = [b.text for b in response.content if b.type == "text"]
    if not parts:
        raise RuntimeError(f"Claude returned no text (stop_reason={response.stop_reason})")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude output truncated (hit max_tokens)")
    return "".join(parts).strip()


_PROVIDERS = {
    1: ("Gemini", "GEMINI_API_KEY", _call_gemini),
    2: ("OpenAI", "OPENAI_API_KEY", _call_openai),
    3: ("Claude", "ANTHROPIC_API_KEY", _call_claude),
}


def _get_api_config(model_choice):
    entry = _PROVIDERS.get(model_choice)
    if not entry:
        raise ValueError("Invalid model choice.")
    name, env_key, func = entry
    api_key = os.getenv(env_key)
    if not api_key:
        raise ValueError(f"API key for {name} ({env_key}) not found in .env file.")
    return name, api_key, func


def provider_name(model_choice):
    entry = _PROVIDERS.get(model_choice)
    return entry[0] if entry else "?"


def verify_provider(model_choice):
    """
    Check that the chosen provider's API key is present and valid by making one
    tiny live call.  Returns (ok: bool, message: str) — never raises — so the
    caller can offer a different provider instead of failing mid-run.
    """
    try:
        name, api_key, func = _get_api_config(model_choice)
    except ValueError as e:
        return False, str(e)
    try:
        func("ping", "Reply with the single word: OK.", api_key)
        return True, f"{name} API key OK."
    except Exception as e:
        s = str(e)
        if "401" in s or "invalid" in s.lower() or "authentication" in s.lower():
            return False, f"{name} API key is invalid or missing (authentication failed)."
        return False, f"{name} API check failed: {e}"


# ── Retry wrapper ────────────────────────────────────────────────────────────

def _is_rate_limit(e: Exception) -> bool:
    s = str(e).lower()
    return ("429" in s or "quota" in s or "rate limit" in s or "rate_limit" in s
            or "resource_exhausted" in s or "resource exhausted" in s
            or "overloaded" in s or "529" in s)


def _is_permanent(e: Exception) -> bool:
    """Auth / validation / not-found errors — retrying can never help."""
    s = str(e).lower()
    return any(k in s for k in (
        "401", "403", "invalid api key", "invalid_api_key", "authentication",
        "permission", "not found", "not_found", "invalid model", "400",
    ))


def _call_with_retries(func, text, system_prompt, api_key, label):
    for attempt in range(config.MAX_RETRIES):
        try:
            return func(text, system_prompt, api_key)
        except Exception as e:
            # Never retry permanent errors — fail fast so the user sees the cause.
            if _is_permanent(e) or attempt == config.MAX_RETRIES - 1:
                raise
            wait = 2 ** (attempt + 1) if _is_rate_limit(e) else 2
            print(f"    ⚠ {label}: {e} — retrying in {wait}s "
                  f"({attempt + 1}/{config.MAX_RETRIES})", flush=True)
            time.sleep(wait)


# ── Passes ───────────────────────────────────────────────────────────────────

def _prompt(template, input_lang, output_lang, extra_specs):
    # plain replace (not str.format) so literal { } in the prompt text — used for
    # the small-print citation rules — don't collide with format fields
    prompt = (template.replace("{source_lang}", input_lang)
                      .replace("{target_lang}", output_lang))
    if extra_specs:
        prompt += f"\n\nAdditional specifications: {extra_specs}"
    return prompt


def run_pass1(text, model_choice, input_lang, output_lang, extra_specs="",
              pass1_prompt=None):
    """
    Pass 1 (drafting): chunk the text and translate all chunks concurrently.
    Returns (combined_draft, chunk_data) where chunk_data is [(orig, draft|None)].
    """
    name, api_key, func = _get_api_config(model_choice)
    prompt1 = _prompt(pass1_prompt or config.SYSTEM_PROMPT_PASS1,
                      input_lang, output_lang, extra_specs)

    chunks = chunk_text(text)
    print(f"\n  [Translator] Pass 1: {len(chunks)} chunk(s) via {name} "
          f"(max {config.MAX_CONCURRENT} concurrent)...")

    def translate(idx_chunk):
        idx, chunk = idx_chunk
        label = f"chunk {idx + 1}/{len(chunks)}"
        try:
            draft = _call_with_retries(func, chunk, prompt1, api_key, label)
            print(f"    ✓ {label} drafted")
            return chunk, draft
        except Exception as e:
            print(f"    ✗ {label} FAILED: {e}")
            return chunk, None

    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT) as pool:
        chunk_data = list(pool.map(translate, enumerate(chunks)))

    results = [
        draft if draft is not None else f"\n[ERROR PASS 1 CHUNK {i + 1}]\n"
        for i, (_orig, draft) in enumerate(chunk_data)
    ]
    return "\n\n".join(results), chunk_data


def run_pass2(chunk_data, model_choice, input_lang, output_lang, extra_specs="",
              pass2_prompt=None):
    """
    Pass 2 (refinement or bilingual interleave): give the model each original
    chunk alongside its draft and let it produce the final text. Concurrent.
    """
    name, api_key, func = _get_api_config(model_choice)
    prompt2 = _prompt(pass2_prompt or config.SYSTEM_PROMPT_PASS2,
                      input_lang, output_lang, extra_specs)
    total = len(chunk_data)
    print(f"\n  [Translator] Pass 2: {total} chunk(s) via {name}...")

    def refine(idx_pair):
        idx, (orig, draft) = idx_pair
        label = f"chunk {idx + 1}/{total}"
        if draft is None:
            return f"\n[SKIPPED PASS 2 CHUNK {idx + 1}: Pass 1 failed]\n"
        pass2_input = (
            f"=== ORIGINAL SOURCE TEXT ===\n{orig}\n\n"
            f"=== DRAFT TRANSLATION ===\n{draft}"
        )
        try:
            refined = _call_with_retries(func, pass2_input, prompt2, api_key, label)
            print(f"    ✓ {label} refined")
            return refined
        except Exception as e:
            print(f"    ✗ {label} Pass 2 failed ({e}) — keeping draft")
            return draft

    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT) as pool:
        results = list(pool.map(refine, enumerate(chunk_data)))

    return "\n\n".join(results)


def run_pass3(text, model_choice, input_lang, output_lang, extra_specs="",
              pass3_prompt=None):
    """
    Pass 3 (smoothing / copyedit): polish the pass-2 output for natural flow.
    Operates on the finished text itself (re-chunked), concurrently.
    """
    name, api_key, func = _get_api_config(model_choice)
    prompt3 = _prompt(pass3_prompt or config.SYSTEM_PROMPT_PASS2,
                      input_lang, output_lang, extra_specs)

    chunks = chunk_text(text)
    print(f"\n  [Translator] Pass 3: {len(chunks)} chunk(s) via {name} (smoothing)...")

    def smooth(idx_chunk):
        idx, chunk = idx_chunk
        label = f"chunk {idx + 1}/{len(chunks)}"
        try:
            out = _call_with_retries(func, chunk, prompt3, api_key, label)
            print(f"    ✓ {label} smoothed")
            return out
        except Exception as e:
            print(f"    ✗ {label} Pass 3 failed ({e}) — keeping prior text")
            return chunk

    with ThreadPoolExecutor(max_workers=config.MAX_CONCURRENT) as pool:
        results = list(pool.map(smooth, enumerate(chunks)))

    return "\n\n".join(results)
