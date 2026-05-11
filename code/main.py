"""
main.py — Main entry point for the Translator CLI.
Orchestrates the PDF extraction, LLM translation, and multi-format output.
"""

import os
import sys
import re
import shutil
from extractor import extract_text
from translator import call_translation_api
from formatter import save_markdown, save_word

# Resolve paths relative to this script's parent dir (project root)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INPUT_DIR = os.path.join(PROJECT_ROOT, "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")


def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def _get_pdf_list():
    """Returns a sorted list of PDF filenames found in the input/ folder."""
    if not os.path.isdir(INPUT_DIR):
        os.makedirs(INPUT_DIR, exist_ok=True)
    return sorted(
        f for f in os.listdir(INPUT_DIR)
        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(INPUT_DIR, f))
    )


def _select_files(pdf_files):
    """
    Interactive numbered file picker.
    The user can type numbers separated by commas, spaces, or both.
    Typing 0 finalises the selection.
    Duplicates and out-of-range numbers are silently ignored.
    """
    selected_indices = set()

    while True:
        raw = input("\n  Select file(s) by number (0 to confirm): ").strip()
        if not raw:
            continue

        # Split on commas, spaces, or both
        tokens = re.split(r'[\s,]+', raw)

        for token in tokens:
            try:
                num = int(token)
            except ValueError:
                continue  # silently skip non-numeric tokens

            if num == 0:
                # Finalise and return whatever we've collected so far
                if not selected_indices:
                    print("  No files selected. Please pick at least one file.")
                    break  # inner loop — continue outer while
                return [pdf_files[i] for i in sorted(selected_indices)]

            if 1 <= num <= len(pdf_files):
                idx = num - 1
                if idx not in selected_indices:
                    selected_indices.add(idx)
                    print(f"    ✓ Added: {pdf_files[idx]}")
                # else: duplicate — silently ignored
            # else: out of range — silently ignored
        else:
            # The for-loop finished without hitting 0 — show current selection
            if selected_indices:
                print(f"  Currently selected ({len(selected_indices)}): "
                      + ", ".join(pdf_files[i] for i in sorted(selected_indices)))
            continue

    # Should not normally reach here, but guard against it
    return []


def _process_file(pdf_path, model_choice, input_lang, output_lang, extra_specs, file_num, total):
    """Run the full extraction → translation → format → organise pipeline for one file."""
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    prefix = f"  [{file_num}/{total}]"

    print(f"\n{'─' * 60}")
    print(f"{prefix}  Processing: {os.path.basename(pdf_path)}")
    print(f"{'─' * 60}")

    # Step 1: Extraction
    print(f"{prefix}  [1/4] Extracting text from PDF...")
    try:
        extracted_text = extract_text(pdf_path)
    except Exception as e:
        print(f"{prefix}  ✗ CRITICAL ERROR during extraction: {e}")
        return False

    # Step 2: Translation
    print(f"{prefix}  [2/4] Calling LLM API ({input_lang} -> {output_lang})...")
    try:
        translated_text = call_translation_api(
            extracted_text, model_choice, input_lang, output_lang, extra_specs
        )
    except Exception as e:
        print(f"{prefix}  ✗ CRITICAL ERROR during translation: {e}")
        return False

    # Step 3: Formatting
    print(f"{prefix}  [3/4] Generating output files (Markdown & Word)...")
    md_filename = f"{base_name}.md"
    docx_filename = f"{base_name}.docx"

    # Write temp outputs next to the code dir, then move
    md_path = save_markdown(translated_text, md_filename)
    docx_path = save_word(translated_text, docx_filename, output_lang)

    # Step 4: Organisation — each file gets its own output subfolder
    print(f"{prefix}  [4/4] Organizing files...")
    file_output_dir = os.path.join(OUTPUT_DIR, base_name)
    os.makedirs(file_output_dir, exist_ok=True)

    try:
        # Copy original PDF into output
        shutil.copy2(pdf_path, os.path.join(file_output_dir, os.path.basename(pdf_path)))
        # Move generated files
        shutil.move(md_path, os.path.join(file_output_dir, md_filename))
        shutil.move(docx_path, os.path.join(file_output_dir, docx_filename))

        print(f"{prefix}  ✓ Done → {file_output_dir}")
        return True
    except Exception as e:
        print(f"{prefix}  ✗ ERROR during file organization: {e}")
        return False


def main():
    clear_screen()
    print("=" * 60)
    print("      Modular Translation System CLI")
    print("=" * 60)

    # ── 1. Model Selection ──────────────────────────────────────
    print("\n[1] SELECT LLM PROVIDER:")
    print("    1. Gemini")
    print("    2. OpenAI")
    print("    3. Claude")
    print("    4. MetaAI")

    while True:
        try:
            model_choice = int(input("\n  Enter choice (1-4): ").strip())
            if 1 <= model_choice <= 4:
                break
            print("  Invalid choice. Please enter a number between 1 and 4.")
        except ValueError:
            print("  Invalid input. Please enter a number.")

    # ── 2. File Selection from input/ folder ────────────────────
    print("\n[2] FILE INPUT:")
    pdf_files = _get_pdf_list()

    if not pdf_files:
        print(f"  No PDF files found in: {INPUT_DIR}")
        print("  Please place your PDF files in the input/ folder and try again.")
        sys.exit(0)

    print(f"  Found {len(pdf_files)} PDF(s) in input/:\n")
    for i, name in enumerate(pdf_files, 1):
        print(f"    {i}) {name}")

    print("\n  Enter numbers to select files (e.g. 1,2,3 or 1 2 3).")
    print("  Type 0 when done selecting.")

    selected_files = _select_files(pdf_files)

    if not selected_files:
        print("  No files selected. Exiting.")
        sys.exit(0)

    print(f"\n  Final selection ({len(selected_files)} file(s)):")
    for name in selected_files:
        print(f"    • {name}")

    # ── 3. Translation Settings ─────────────────────────────────
    print("\n[3] TRANSLATION SETTINGS:")
    print("    a) Hebrew to English")
    print("    b) English to Hebrew")
    print("    c) Torah/Rabbinic Hebrew to English")
    print("    d) Custom")

    while True:
        lang_choice = input("\n  Enter choice (a-d): ").strip().lower()
        if lang_choice == 'a':
            input_lang, output_lang = "Hebrew", "English"
            break
        elif lang_choice == 'b':
            input_lang, output_lang = "English", "Hebrew"
            break
        elif lang_choice == 'c':
            input_lang, output_lang = "Torah/Rabbinic Hebrew", "English"
            break
        elif lang_choice == 'd':
            input_lang = input("  Enter input language: ").strip()
            output_lang = input("  Enter output language: ").strip()
            if input_lang and output_lang:
                break
        print("  Invalid choice.")

    # ── 4. Additional Specifications ────────────────────────────
    extra_specs = input(
        "\n[4] Are there any additional translation specifications or context?\n"
        "    (Press Enter for none): "
    ).strip()

    # ── EXECUTION ───────────────────────────────────────────────
    total = len(selected_files)
    print("\n" + "=" * 60)
    print(f"  STARTING PIPELINE — {total} file(s)")
    print("=" * 60)

    results = {"ok": [], "fail": []}

    for i, filename in enumerate(selected_files, 1):
        pdf_path = os.path.join(INPUT_DIR, filename)
        success = _process_file(
            pdf_path, model_choice, input_lang, output_lang, extra_specs, i, total
        )
        (results["ok"] if success else results["fail"]).append(filename)

    # ── SUMMARY ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE!")
    print("=" * 60)
    if results["ok"]:
        print(f"  ✓ Succeeded: {len(results['ok'])}")
        for name in results["ok"]:
            print(f"      • {name}")
    if results["fail"]:
        print(f"  ✗ Failed:    {len(results['fail'])}")
        for name in results["fail"]:
            print(f"      • {name}")
    print(f"\n  Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
