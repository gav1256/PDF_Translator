"""
extractor.py — RTL-safe PDF text extraction using PyMuPDF.

Handles legacy Hebrew font encoding (Windows-1255) and 
preserves logical reading order for standard Unicode Hebrew.
"""

import os
import re
import fitz  # PyMuPDF


def _fix_mojibake(text: str) -> str:
    """
    Decodes legacy Hebrew mojibake characters (0xE0-0xFA) from Windows-1255 
    and reverses them to restore visual LTR extraction to logical RTL.
    """
    def replace_mojibake(match):
        raw_str = match.group(0)
        decoded_chars = []
        for c in raw_str:
            if '\xe0' <= c <= '\xfa':
                try:
                    decoded_chars.append(c.encode('latin1').decode('windows-1255'))
                except UnicodeError:
                    decoded_chars.append(c)
            else:
                decoded_chars.append(c)
        
        # Reverse the decoded substring
        decoded_str = ''.join(decoded_chars)
        reversed_str = decoded_str[::-1]
        
        # Swap bracket directions for RTL
        reversed_str = reversed_str.translate(str.maketrans('()[]{}<>', ')(][}{><'))
        
        # Keep embedded numbers/English in their original order within the reversed block
        def restore_ltr(m):
            return m.group(0)[::-1]
        
        return re.sub(r'[A-Za-z0-9]+', restore_ltr, reversed_str)

    # Match sequences containing mojibake characters
    pattern = r'[ \t\r\n\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e0-9\xe0-\xfa]*[\xe0-\xfa]+[ \t\r\n\x21-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e0-9\xe0-\xfa]*'
    return re.sub(pattern, replace_mojibake, text)


def extract_text(pdf_path: str) -> str:
    """
    Main extraction entry point.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    all_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # sort=True handles multi-column layouts by ordering blocks top-to-bottom
        blocks = page.get_text("blocks", sort=True)
        
        page_content = []
        for block in blocks:
            # block_type 0 is text
            if block[6] == 0:
                text = block[4].strip()
                if text:
                    # Fix RTL mojibake issues
                    fixed_text = _fix_mojibake(text)
                    page_content.append(fixed_text)
        
        if page_content:
            all_text.append(f"## Page {page_num + 1}\n\n" + "\n\n".join(page_content))

    doc.close()
    return "\n\n".join(all_text)
