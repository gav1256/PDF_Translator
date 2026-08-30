# PDF Translator

A tool to extract text from PDF files (including scrambled right-to-left Hebrew), translate it with an LLM provider (Gemini, OpenAI, or Claude), and format the result into a clean Word document.

## Features
- **RTL-safe extraction**: Reconstructs logical reading order from per-character geometry, fixing stream-order scrambling, split words, and mirrored brackets in Hebrew PDFs — no OCR needed when the PDF has a text layer. Pages with no text layer (scanned images) are detected and reported.
- **Multi-LLM support**: Gemini, OpenAI, or Claude, selected at runtime.
- **Two-pass translation**: a fast concurrent drafting pass, then an optional refinement pass that merges fragments into flowing prose.
- **Formatted output**: Word document with a בס"ד header, page numbers, preserved headings/bold, and RTL/LTR alignment based on the target language.

## Do I need OCR (e.g. GLM)?
Only for **scanned/image-only** PDFs. If the PDF has a real text layer (most digital gilyonos do), the extractor recovers the text deterministically and for free. OCR is a fallback for image-only pages, which the tool flags on extraction.

## Setup
1. Clone the repository.
2. Install dependencies:
   ```bash
   pip install -r code/requirements.txt
   ```
3. Configure your API keys in a `.env` file (see `.env.template` if available, or create one).
4. Run the translator:
   ```bash
   RUN_TRANSLATOR.bat
   ```

A translated PDF is moved out of `input/` into its own folder under `output/`,
so `input/` only ever holds work still to be done.

## Reformatting without re-translating
To try a different look for a document you have already translated, run:

```bash
REGENERATE_DOCX.bat
```

Pick a document from `output/` (or paste/drag its `.md` file onto the .bat) and
choose a layout, fonts, text size, line spacing, margins, page numbers, the
בס"ד header side, and — for side-by-side — which language sits on the left.
Nothing is re-translated and nothing is overwritten: the settings you picked are
written into the file name and the Word Title property, e.g.
`My Document (side-by-side, 12pt, 1.5 spacing).docx`, so variants sit beside
the original.

Side-by-side is offered only for documents whose `.md` actually contains both
languages — a translation-only draft would leave the source column empty.

## Project Structure
- `code/`: Main Python logic (extractor, translator, formatter).
- `RUN_TRANSLATOR.bat`: Convenient script to launch the tool.
- `REGENERATE_DOCX.bat`: Re-render an existing `.md` into Word with different formatting.
- `.env`: Sensitive configuration (ignored by git).
