# PDF Translator

A powerful tool to extract text from PDF files, translate it using various LLM providers (Gemini, OpenAI, Claude, Llama), and format the output into clean documents.

## Features
- **Multi-LLM Support**: Toggle between Gemini, OpenAI, Claude, and Meta Llama.
- **Text Extraction**: Robust extraction from complex PDF layouts.
- **Bilingual Output**: Generates structured bilingual text.
- **Batch Processing**: Easily run via command line or batch scripts.

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

## Project Structure
- `code/`: Main Python logic (extractor, translator, formatter).
- `RUN_TRANSLATOR.bat`: Convenient script to launch the tool.
- `.env`: Sensitive configuration (ignored by git).
