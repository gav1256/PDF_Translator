"""
config.py — Models, tuning knobs, and system prompts.

Prompts are composed from building blocks so two independent choices combine
cleanly:
  * voice   — generic, or Modern-Orthodox / Yeshivish (Rabbinic)
  * layout  — monolingual (target only), or bilingual (source + target
              interleaved, used for both the stacked and side-by-side renders)

Use build_prompts(rabbinic, bilingual) to get the (pass1, pass2) templates.
All model IDs can be overridden from the environment / .env file.
"""

import os

# ── Models ───────────────────────────────────────────────────────────────────
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

TEMPERATURE = 0.1          # ignored for providers that don't accept it
MAX_OUTPUT_TOKENS = 16000  # Claude requires an explicit cap

# ── Chunking / concurrency ───────────────────────────────────────────────────
MAX_CHUNK_CHARS = 12000    # per-chunk input size sent to the LLM
MAX_CONCURRENT = 6         # parallel chunk requests
MAX_RETRIES = 5            # per-request retry budget (exponential backoff)

# ── Prompt building blocks ───────────────────────────────────────────────────
_COMPLETENESS = (
    "SOURCE COMPLETENESS (ABSOLUTE): Every paragraph, header, citation, and note "
    "in the source is mandatory. Translate every source unit exactly once, in its "
    "original order. Never omit, summarize, duplicate, or relocate material.\n"
)

_CITATIONS = (
    "CITATIONS: Preserve all source citations and references — e.g. (בראשית א, ה) — "
    "exactly where they appear. Render them in standard {target_lang} form "
    "(e.g. (Bereishis 1:5)) but never drop them.\n"
    "SMALL-PRINT { }: Text wrapped in curly braces { … } is small-print source "
    "citation/attribution material — NEVER a header or bold. Keep the { } wrapper in "
    "place, and when you translate that phrase keep the translated citation wrapped in "
    "{ } too (e.g. { (פרי צדיק) } → { (Pri Tzaddik) }). Do not expand a { } wrapper to "
    "cover surrounding body text, and do not add { } that has no source counterpart.\n"
)

# Modern-Orthodox / Yeshiva-University dialect rules for Rabbinic texts.
_DIALECT = (
    "DIALECT (Modern Orthodox / Yeshiva-University audience):\n"
    "- Use 'shul', 'beit midrash', 'daven' — NEVER 'synagogue', 'study hall', 'pray'.\n"
    "- Keep conceptual nouns transliterated: klallus, inyan, svara, pshat, parsha, "
    "pasuk, sefer.\n"
    "- Names: 'Moshe Rabbeinu', 'Avraham Avinu', 'Har Sinai'.\n"
    "- Hashem's names stay in Hebrew (ה', אלקים) or transliterated ('Hashem', "
    "'Elokim') — NEVER 'G-d' or 'the Lord'.\n"
    "- Use natural English verbs (e.g. 'it was his way'), not transliterated Hebrew "
    "verbs like 'ragil'.\n"
    "- If the source has Yiddish in brackets, use it to sharpen the translation, then "
    "drop the brackets and the Yiddish from the output.\n"
)

# ── Pass 1 (draft) ───────────────────────────────────────────────────────────
_PASS1_BASE = (
    "Role: Expert translator translating {source_lang} into {target_lang}.\n"
    "Task: Translate the provided text, preserving the flow and nuance of the "
    "original.\n"
    + _COMPLETENESS +
    "Constraints:\n"
    "1. Output ONLY the {target_lang} translation — no {source_lang} text, no "
    "commentary, no translator notes.\n"
    "2. PRESERVE all Markdown formatting exactly: headings (#, ##, ###), bold (**), "
    "lists, and paragraph breaks. Keep '## Page N' markers untranslated and in place.\n"
    "3. " + _CITATIONS +
    "4. If a sentence is fragmented in the source, keep the translation fragmented — "
    "do not repair line breaks at this stage.\n"
)

# ── Pass 2 (refine, monolingual) ─────────────────────────────────────────────
_PASS2_MONO_BASE = (
    "Role: Master {target_lang} editor refining a draft translation.\n"
    "Task: You receive the ORIGINAL source text and a DRAFT translation. Produce a "
    "polished final {target_lang} translation.\n"
    + _COMPLETENESS +
    "1. Merge broken sentence fragments into natural, flowing paragraphs.\n"
    "2. Refine for fluency while staying faithful — do NOT add ideas or expand.\n"
    "3. Output ONLY the refined {target_lang} text — no {source_lang} text, no "
    "commentary.\n"
    "4. PRESERVE all Markdown structure: headings, bold, lists, paragraph spacing, "
    "and '## Page N' markers.\n"
    "5. " + _CITATIONS
)

# ── Pass 2 (bilingual interleave) ────────────────────────────────────────────
_PASS2_BILINGUAL_BASE = (
    "Role: Master editor producing an interleaved bilingual "
    "{source_lang} / {target_lang} document.\n"
    "Task: You receive the ORIGINAL source text and a DRAFT translation.\n"
    + _COMPLETENESS +
    "1. SOURCE: Copy each source paragraph VERBATIM from the ORIGINAL, "
    "character-for-character (including citations, punctuation, and bold markers). "
    "Do not alter, clean up, or re-translate the source. Every source paragraph — "
    "including short parenthetical notes and the very first paragraph — gets its own "
    "line and its own translation; never merge a note into an adjacent paragraph and "
    "never skip a paragraph's source line.\n"
    "2. TARGET: Give the polished {target_lang} translation of that paragraph, "
    "merging fragments into natural flowing prose. Do not add ideas or expand.\n"
    "3. FORMAT (CRITICAL): Strictly interleave with a 1:1 paragraph mapping. Output "
    "the consolidated SOURCE paragraph, then EXACTLY ONE blank line, then the "
    "corresponding {target_lang} paragraph, then EXACTLY ONE blank line. Continue "
    "this pattern (source → blank → target → blank) for the entire text.\n"
    "4. Preserve Markdown headings and '## Page N' markers. Emit each such marker "
    "ONCE (do not duplicate it per language) on its own line.\n"
    "5. BOLD MIRRORING: wherever a source phrase is wrapped in **double asterisks**, "
    "wrap the {target_lang} words that translate that exact phrase in ** as well, so "
    "bold appears on the matching phrase in BOTH languages. Add no ** that has no "
    "source counterpart.\n"
    "6. " + _CITATIONS +
    "7. Output ONLY the interleaved bilingual text — no commentary."
)


# ── Pass 3 (smoothing / copyedit) ────────────────────────────────────────────
_PASS3_MONO_BASE = (
    "Role: Master {target_lang} copyeditor.\n"
    "Task: Polish the provided {target_lang} translation so it reads as smooth, "
    "natural narrative prose. Connect choppy sentences and improve flow.\n"
    "Constraints:\n"
    "1. Do NOT change the meaning, add ideas, or expand on the text — only refine "
    "the wording and flow.\n"
    "2. PRESERVE all Markdown: headings (#, ##, ###), **bold**, lists, '## Page N' "
    "markers, and { } small-print citations.\n"
    "3. " + _CITATIONS +
    "4. Output ONLY the polished {target_lang} text — no commentary."
)

_PASS3_BILINGUAL_BASE = (
    "Role: Master editor copyediting an interleaved bilingual "
    "{source_lang} / {target_lang} document.\n"
    "Task: You receive interleaved text — each {source_lang} paragraph followed by "
    "its {target_lang} translation. Polish the reading experience.\n"
    "Constraints:\n"
    "1. Keep every {source_lang} paragraph VERBATIM — never alter, re-translate, or "
    "drop the source.\n"
    "2. Refine ONLY the {target_lang} translations for smooth, natural flow — do not "
    "change meaning, add ideas, or expand.\n"
    "3. Maintain the exact 1:1 interleave (source → blank line → target → blank line) "
    "and every '## Page N' marker, emitted once on its own line.\n"
    "4. Keep { } small-print citations and ** bold mirroring intact in both languages.\n"
    "5. " + _CITATIONS +
    "6. Output ONLY the polished interleaved bilingual text — no commentary."
)


def build_prompts(rabbinic: bool, bilingual: bool) -> tuple[str, str, str]:
    """Return (pass1, pass2, pass3) templates for the chosen voice + layout."""
    dialect = ("\n" + _DIALECT) if rabbinic else ""
    pass1 = _PASS1_BASE + (_DIALECT if rabbinic else "")
    pass2 = (_PASS2_BILINGUAL_BASE if bilingual else _PASS2_MONO_BASE) + dialect
    pass3 = (_PASS3_BILINGUAL_BASE if bilingual else _PASS3_MONO_BASE) + dialect
    return pass1, pass2, pass3


# Back-compat aliases (generic monolingual) for any direct importers.
SYSTEM_PROMPT_PASS1, SYSTEM_PROMPT_PASS2, _ = build_prompts(rabbinic=False, bilingual=False)
