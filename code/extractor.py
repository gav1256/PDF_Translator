"""
extractor.py — RTL-safe PDF text extraction using PyMuPDF with formatting preservation.

Handles legacy Hebrew font encoding (Windows-1255) and 
preserves logical reading order while detecting headings, bold, italic, 
bullets, and indentation.
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


def _analyze_font_sizes(doc):
    """First pass: collect font-size frequency across the entire document."""
    size_counts = {}  # {font_size: total_char_count}
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] != 0:  # skip images
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    size = round(span["size"], 1)
                    size_counts[size] = size_counts.get(size, 0) + len(span["text"])
    
    if not size_counts:
        return 11.0 # default
    # The most common size (by character count) is "body text"
    body_size = max(size_counts, key=size_counts.get)
    return body_size


def _get_base_margin(doc):
    """Detect the most common left margin (x0) of text blocks."""
    x_counts = {}
    for page in doc:
        blocks = page.get_text("dict")["blocks"]
        for block in blocks:
            if block["type"] == 0:
                x0 = round(block["bbox"][0])
                x_counts[x0] = x_counts.get(x0, 0) + 1
    if not x_counts:
        return 50 # typical
    return max(x_counts, key=x_counts.get)


def extract_text(pdf_path: str) -> str:
    """
    Main extraction entry point with formatting preservation.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    doc = fitz.open(pdf_path)
    body_size = _analyze_font_sizes(doc)
    base_margin = _get_base_margin(doc)
    
    BULLET_CHARS = {'•', '‣', '◦', '–', '·', '▪', '►', '■', '-', '*'}
    all_pages_text = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        # sort=True handles multi-column layouts by ordering blocks top-to-bottom
        blocks = page.get_text("dict", sort=True)["blocks"]
        
        page_content = []
        for block in blocks:
            if block["type"] != 0: # skip images
                continue
            
            block_lines = []
            for line in block["lines"]:
                line_text = ""
                # Get max size in line for heading detection
                spans = line["spans"]
                if not spans:
                    continue
                    
                line_max_size = max(span["size"] for span in spans)
                
                for span in spans:
                    text = span["text"]
                    if not text.strip():
                        line_text += text
                        continue
                    
                    # Fix RTL mojibake issues
                    text = _fix_mojibake(text)
                    
                    # Formatting flags (bold=16, italic=2)
                    is_bold = bool(span["flags"] & 16)
                    is_italic = bool(span["flags"] & 2)
                    
                    if is_bold and is_italic:
                        text = f"***{text}***"
                    elif is_bold:
                        text = f"**{text}**"
                    elif is_italic:
                        text = f"*{text}*"
                    
                    line_text += text
                
                if not line_text.strip():
                    continue

                # Heading detection
                prefix = ""
                if line_max_size >= body_size * 1.6:
                    prefix = "# "
                elif line_max_size >= body_size * 1.25:
                    prefix = "## "
                elif line_max_size >= body_size * 1.1:
                    prefix = "### "
                
                # Bullet / Indent detection
                x0 = line["bbox"][0]
                indent_level = max(0, int((x0 - base_margin) / 20))
                indent_str = "  " * indent_level
                
                stripped = line_text.strip()
                is_bullet = (stripped and stripped[0] in BULLET_CHARS) or re.match(r'^(\d+[.\)]|[a-zA-Z][.\)])\s', stripped)
                
                if is_bullet:
                    # If it's a bullet char but doesn't look like MD, normalize to '-'
                    if stripped[0] in BULLET_CHARS and not (stripped.startswith("- ") or stripped.startswith("* ")):
                         line_text = "- " + line_text.lstrip(stripped[0]).strip()
                
                block_lines.append(f"{indent_str}{prefix}{line_text}")
            
            if block_lines:
                page_content.append("\n".join(block_lines))
        
        if page_content:
            all_pages_text.append(f"## Page {page_num + 1}\n\n" + "\n\n".join(page_content))

    doc.close()
    return "\n\n".join(all_pages_text)
