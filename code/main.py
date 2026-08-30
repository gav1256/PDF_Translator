"""
main.py — Main entry point for the Translator CLI.
Orchestrates the PDF extraction, LLM translation, and multi-format output.
"""

import os
import sys
import re
import shutil
import argparse

# Fix Windows console encoding for Hebrew output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from extractor import extract_text
from translator import (run_pass1, run_pass2, run_pass3,
                        verify_provider, provider_name)
from formatter import save_markdown, save_word, save_word_columns
from config import build_prompts

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


def main():
    parser = argparse.ArgumentParser(description="Modular Translation System CLI")
    parser.add_argument("--multi-pass", action="store_true", help="Run multi-pass reconstruction for formatting")
    args = parser.parse_args()
    
    run_multi_pass = args.multi_pass
    has_multi_pass_flag = "--multi-pass" in sys.argv

    clear_screen()
    print("=" * 60)
    print("      Modular Translation System CLI")
    print("=" * 60)

    # ── 1. Model Selection (with live key verification) ─────────
    print("\n[1] SELECT LLM PROVIDER:")
    print("    1. Gemini")
    print("    2. OpenAI")
    print("    3. Claude")

    while True:
        raw = input("\n  Enter choice (1-3): ").strip()
        try:
            model_choice = int(raw)
        except ValueError:
            print("  Invalid input. Please enter a number.")
            continue
        if not 1 <= model_choice <= 3:
            print("  Invalid choice. Please enter a number between 1 and 3.")
            continue

        print(f"  - Verifying {provider_name(model_choice)} API key...")
        ok, msg = verify_provider(model_choice)
        if ok:
            print(f"  ✓ {msg}")
            break
        # Key missing or invalid — notify and let the user pick another provider.
        print(f"  ✗ {msg}")
        print("    Fix the key in your .env file, or choose a different provider.")

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

    # ── 3. Translation Settings ─────────────────────────────────
    print("\n[3] TRANSLATION SETTINGS:")
    print("    a) Hebrew to English")
    print("    b) English to Hebrew")
    print("    c) Torah/Rabbinic Hebrew to English (Modern-Orthodox / Yeshivish voice)")
    print("    d) Custom")

    rabbinic = False
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
            rabbinic = True
            break
        elif lang_choice == 'd':
            input_lang = input("  Enter input language: ").strip()
            output_lang = input("  Enter output language: ").strip()
            if input_lang and output_lang:
                break
        print("  Invalid choice.")

    # ── 3b. Output Layout (all directions) ──────────────────────
    print("\n[3b] OUTPUT LAYOUT:")
    print("    1) Translation only")
    print(f"    2) {input_lang} + {output_lang}, paragraph after the other (stacked)")
    print(f"    3) {input_lang} + {output_lang}, side-by-side columns")

    while True:
        layout_choice = input("\n  Enter choice (1-3): ").strip()
        if layout_choice in ('1', '2', '3'):
            layout = {'1': 'mono', '2': 'stacked', '3': 'columns'}[layout_choice]
            break
        print("  Invalid choice. Please enter 1, 2, or 3.")

    bilingual = layout in ('stacked', 'columns')
    pass1_prompt, pass2_prompt, pass3_prompt = build_prompts(
        rabbinic=rabbinic, bilingual=bilingual)

    # ── 4. Additional Specifications ────────────────────────────
    extra_specs = input(
        "\n[4] Are there any additional translation specifications or context?\n"
        "    (Press Enter for none): "
    ).strip()

    # ── 5. Nekkudot (Hebrew Vowels) ─────────────────────────────
    add_nekkudot = False
    if "hebrew" in output_lang.lower():
        while True:
            nek_choice = input("\n[5] Add Nekkudot to Hebrew output? (YES/NO): ").strip().upper()
            if nek_choice in ['YES', 'Y']:
                add_nekkudot = True
                break
            elif nek_choice in ['NO', 'N']:
                add_nekkudot = False
                break
            print("  Invalid choice. Please enter YES or NO.")

    # ── 6. Initial Multi-Pass choice ────────────────────────────
    # A bilingual layout REQUIRES pass 2 — that is where the source and target
    # are interleaved — so it runs automatically and the prompt is skipped.
    if bilingual:
        run_multi_pass = True
        print("\n[6] Bilingual layout selected — 2nd pass (interleaving) runs automatically.")
    elif not has_multi_pass_flag:
        while True:
            mp_choice = input("\n[6] Run multi-pass reconstruction for all files? (y/N): ").strip().lower()
            if mp_choice in ['y', 'yes']:
                run_multi_pass = True
                break
            elif mp_choice in ['n', 'no', '']:
                run_multi_pass = False
                break
            print("  Invalid choice. Please enter y or n.")

    # ── 7. Optional 3rd-pass smoothing ──────────────────────────
    do_smoothing = False
    while True:
        sm = input("\n[7] Run 3rd-pass smoothing (polish flow / connect sentences)? (y/N): ").strip().lower()
        if sm in ['y', 'yes']:
            do_smoothing = True
            break
        elif sm in ['n', 'no', '']:
            break
        print("  Invalid choice. Please enter y or n.")

    # ── PHASE 1: Extraction & Pass 1 ────────────────────────────
    print("\n" + "=" * 60)
    print(f"  PHASE 1: DRAFTING ({len(selected_files)} file(s))")
    print("=" * 60)
    
    file_data = {}
    results = {"ok": [], "fail": []}

    for i, filename in enumerate(selected_files, 1):
        pdf_path = os.path.join(INPUT_DIR, filename)
        base_name = os.path.splitext(filename)[0]
        output_dir = os.path.join(OUTPUT_DIR, base_name)
        os.makedirs(output_dir, exist_ok=True)
        
        print(f"\n  [{i}/{len(selected_files)}] Processing: {filename}")
        
        try:
            # 1. Extraction
            print(f"    - Extracting text...")
            extracted_text = extract_text(pdf_path)
            
            # 2. Pass 1
            translated_text, chunk_data = run_pass1(
                extracted_text, model_choice, input_lang, output_lang,
                extra_specs, pass1_prompt=pass1_prompt)

            # If every chunk failed (e.g. auth/quota died mid-run), don't
            # produce a garbage document — mark the file as failed.
            if chunk_data and all(draft is None for _orig, draft in chunk_data):
                raise RuntimeError("all chunks failed in Pass 1 (API error?)")

            # 3. Save Draft MD
            md_path = os.path.join(output_dir, f"{base_name}.md")
            save_markdown(translated_text, md_path)
            
            file_data[filename] = {
                'pdf_path': pdf_path,
                'chunk_data': chunk_data,
                'text': translated_text,
                'output_dir': output_dir,
                'base_name': base_name,
                'md_path': md_path
            }
            results["ok"].append(filename)
        except Exception as e:
            print(f"    ✗ FAILED: {e}")
            results["fail"].append(filename)

    # ── PHASE 2: Review Pause & Selective Pass 2 ────────────────
    files_to_reconstruct = []
    if results["ok"]:
        if run_multi_pass:
            # If globally enabled, all successful files go to pass 2
            files_to_reconstruct = results["ok"]
        else:
            print("\n" + "=" * 60)
            print("  DRAFTS SAVED. Please review the .md files in the output folders.")
            print("=" * 60)
            
            do_pass2 = input("\n[8] Run 2nd Pass (Reconstruction) on any of these files? (y/N): ").strip().lower()
            if do_pass2 in ['y', 'yes']:
                if len(results["ok"]) > 1:
                    print("\n  Select file(s) for 2nd Pass:")
                    for idx, name in enumerate(results["ok"], 1):
                        print(f"    {idx}) {name}")
                    files_to_reconstruct = _select_files(results["ok"])
                else:
                    files_to_reconstruct = results["ok"]

    # Run Pass 2
    if files_to_reconstruct:
        print("\n" + "=" * 60)
        print(f"  PHASE 2: RECONSTRUCTION ({len(files_to_reconstruct)} file(s))")
        print("=" * 60)
        for filename in files_to_reconstruct:
            data = file_data[filename]
            print(f"\n  Reconstructing: {filename}")
            try:
                final_text = run_pass2(
                    data['chunk_data'], model_choice, input_lang, output_lang,
                    extra_specs, pass2_prompt=pass2_prompt)
                data['text'] = final_text
                save_markdown(final_text, data['md_path']) # Overwrite with Pass 2 result
            except Exception as e:
                print(f"    ✗ Pass 2 Failed for {filename}: {e}")

    # ── PHASE 2b: Optional 3rd-pass smoothing ───────────────────
    if do_smoothing and results["ok"]:
        print("\n" + "=" * 60)
        print(f"  PHASE 2b: SMOOTHING ({len(results['ok'])} file(s))")
        print("=" * 60)
        for filename in results["ok"]:
            data = file_data[filename]
            print(f"\n  Smoothing: {filename}")
            try:
                smoothed = run_pass3(
                    data['text'], model_choice, input_lang, output_lang,
                    extra_specs, pass3_prompt=pass3_prompt)
                data['text'] = smoothed
                save_markdown(smoothed, data['md_path'])   # overwrite with smoothed result
            except Exception as e:
                print(f"    ✗ Pass 3 Failed for {filename}: {e}")

    # ── PHASE 3: Finalization (Nekkudot & Word) ─────────────────
    if results["ok"]:
        print("\n" + "=" * 60)
        print(f"  PHASE 3: FINALIZING ({len(results['ok'])} file(s))")
        print("=" * 60)
        for filename in results["ok"]:
            data = file_data[filename]
            text = data['text']
            
            print(f"\n  Finalizing: {filename}")
            
            # 1. Apply Nekkudot if requested
            if add_nekkudot:
                print(f"    - Applying Nekkudot...")
                try:
                    from dicta_api_nekkudot import apply_nekkudot_to_text
                    text = apply_nekkudot_to_text(text)
                    save_markdown(text, data['md_path']) # Update MD with nekkudot
                except Exception as e:
                    print(f"    ✗ Nekkudot failed: {e}")
                
            # 2. Save Word document in the chosen layout
            print(f"    - Generating Word document ({layout})...")
            docx_path = os.path.join(data['output_dir'], f"{data['base_name']}.docx")
            if layout == 'columns':
                save_word_columns(text, docx_path, input_lang, output_lang)
            elif layout == 'stacked':
                save_word(text, docx_path, output_lang, bilingual=True)
            else:
                save_word(text, docx_path, output_lang)
            
            # 3. Move the original PDF out of input/ — a translated file lives
            #    only in its output folder from here on.  Only files that made
            #    it through the pipeline move; failures stay in input/.
            dest_pdf = os.path.join(data['output_dir'], filename)
            try:
                if os.path.exists(dest_pdf):
                    os.remove(dest_pdf)   # re-translation: replace the older copy
                shutil.move(data['pdf_path'], dest_pdf)
                print(f"    ✓ Done → {data['output_dir']}  (PDF moved out of input/)")
            except Exception as e:
                print(f"    ! PDF left in input/ — could not move it: {e}")
                print(f"    ✓ Done → {data['output_dir']}")

    # ── SUMMARY ─────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  PIPELINE COMPLETE!")
    print("=" * 60)
    if results["ok"]:
        print(f"  ✓ Processed: {len(results['ok'])}")
        for name in results["ok"]:
            is_recon = " (2nd Pass applied)" if name in files_to_reconstruct else ""
            print(f"      • {name}{is_recon}")
    if results["fail"]:
        print(f"  ✗ Failed:    {len(results['fail'])}")
        for name in results["fail"]:
            print(f"      • {name}")
    print(f"\n  Output folder: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
