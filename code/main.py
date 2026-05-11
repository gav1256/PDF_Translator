"""
main.py — Main entry point for the Translator CLI.
Orchestrates the PDF extraction, LLM translation, and multi-format output.
"""

import os
import sys
import shutil
from extractor import extract_text
from translator import call_translation_api
from formatter import save_markdown, save_word

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def main():
    clear_screen()
    print("=" * 60)
    print("      Modular Translation System CLI")
    print("=" * 60)

    # 1. Model Selection
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

    # 2. File Input
    print("\n[2] FILE INPUT:")
    while True:
        pdf_path = input("  Enter the full path to the PDF file: ").strip().strip('"')
        if os.path.exists(pdf_path) and pdf_path.lower().endswith(".pdf"):
            break
        print("  Invalid path or not a PDF file. Please try again.")

    # 3. Interactive Translation Menu
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

    # 4. Additional Specifications
    extra_specs = input("\n[4] Are there any additional translation specifications or context?\n    (Press Enter for none): ").strip()

    # --- EXECUTION ---
    print("\n" + "-" * 60)
    print("  STARTING PIPELINE...")
    print("-" * 60)

    # Step 1: Extraction
    print(f"  [1/4] Extracting text from PDF...")
    try:
        extracted_text = extract_text(pdf_path)
    except Exception as e:
        print(f"  CRITICAL ERROR during extraction: {e}")
        sys.exit(1)

    # Step 2: Translation
    print(f"  [2/4] Calling LLM API ({input_lang} -> {output_lang})...")
    try:
        translated_text = call_translation_api(extracted_text, model_choice, input_lang, output_lang, extra_specs)
    except Exception as e:
        print(f"  CRITICAL ERROR during translation: {e}")
        sys.exit(1)

    # Step 3: Formatting
    print(f"  [3/4] Generating output files (Markdown & Word)...")
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    md_filename = f"{base_name}.md"
    docx_filename = f"{base_name}.docx"
    
    md_path = save_markdown(translated_text, md_filename)
    docx_path = save_word(translated_text, docx_filename, output_lang)

    # Step 4: Organization
    print(f"  [4/4] Organizing files...")
    # Create directory named after the base name
    output_dir = os.path.join(os.getcwd(), "output", base_name)
    os.makedirs(output_dir, exist_ok=True)
    
    # Move files
    try:
        # Move original PDF
        shutil.copy2(pdf_path, os.path.join(output_dir, os.path.basename(pdf_path)))
        # Move MD
        shutil.move(md_path, os.path.join(output_dir, md_filename))
        # Move DOCX
        shutil.move(docx_path, os.path.join(output_dir, docx_filename))
        
        print("\n" + "=" * 60)
        print("  PIPELINE COMPLETE!")
        print("=" * 60)
        print(f"  Results saved in: {output_dir}")
    except Exception as e:
        print(f"  ERROR during file organization: {e}")
        print(f"  Files may still be in the current directory: {os.getcwd()}")

if __name__ == "__main__":
    main()
