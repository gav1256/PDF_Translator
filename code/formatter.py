"""
formatter.py — Handles output generation for Markdown and Word (.docx).
Implements strict styling for Word by parsing Markdown markers.
- Top-right header: בס"ד
- Centered footer: Page numbers
- RTL/Right-aligned if output is Hebrew
- Support for headings, bold, italic, bullets, and indentation.
"""

import os
import re
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

def save_markdown(text, output_path):
    """
    Saves the raw text to a Markdown file.
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(text)
    return output_path

def _set_rtl(paragraph):
    """
    Helper to set RTL direction on a paragraph.
    """
    pPr = paragraph._p.get_or_add_pPr()
    bidi = OxmlElement('w:bidi')
    bidi.set(qn('w:val'), '1')
    pPr.append(bidi)

def _parse_line_type(line):
    """Returns (line_type, level, clean_text)."""
    # Headings: # H1, ## H2, ### H3
    m = re.match(r'^(#{1,3})\s+(.*)', line)
    if m:
        return ('heading', len(m.group(1)), m.group(2))
    
    # Bullet lists: - item,   - nested item
    m = re.match(r'^(\s*)-\s+(.*)', line)
    if m:
        indent = len(m.group(1)) // 2  # each 2 spaces = 1 indent level
        return ('bullet', indent, m.group(2))
    
    # Numbered lists: 1. item, 2. item
    m = re.match(r'^(\s*)\d+[.\)]\s+(.*)', line)
    if m:
        indent = len(m.group(1)) // 2
        return ('numbered', indent, m.group(2))
    
    # Page markers (skip them in Word output)
    if re.match(r'^##\s+Page\s+\d+', line):
        return ('page_break', 0, '')
    
    # Plain paragraph
    return ('paragraph', 0, line)

def _add_formatted_runs(paragraph, text, is_hebrew, base_font, base_size):
    """Parse **bold**, *italic*, ***bold+italic*** and add as Word runs."""
    # Pattern: ***bold+italic***, **bold**, *italic*, plain
    pattern = r'(\*{3}(.+?)\*{3}|\*{2}(.+?)\*{2}|\*(.+?)\*|([^*]+))'
    
    has_content = False
    for match in re.finditer(pattern, text):
        if match.group(2):      # ***bold+italic***
            run = paragraph.add_run(match.group(2))
            run.bold = True
            run.italic = True
        elif match.group(3):    # **bold**
            run = paragraph.add_run(match.group(3))
            run.bold = True
        elif match.group(4):    # *italic*
            run = paragraph.add_run(match.group(4))
            run.italic = True
        elif match.group(5):    # plain text
            run = paragraph.add_run(match.group(5))
        else:
            continue
        
        has_content = True
        run.font.name = base_font
        run.font.size = base_size
        if is_hebrew:
            run.font.rtl = True
            
    if not has_content and text:
        run = paragraph.add_run(text)
        run.font.name = base_font
        run.font.size = base_size
        if is_hebrew:
            run.font.rtl = True

def save_word(text, output_path, output_lang):
    """
    Saves text to a Word document with specific styling based on Markdown markers.
    """
    doc = Document()
    
    # 1. Setup Section (Margins and RTL)
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    
    is_hebrew = "hebrew" in output_lang.lower()
    base_font = "David" if is_hebrew else "Calibri"
    
    # Set section-level RTL if Hebrew
    if is_hebrew:
        sectPr = section._sectPr
        bidi = OxmlElement('w:bidi')
        bidi.set(qn('w:val'), '1')
        sectPr.append(bidi)

    # 2. Header: "בס"ד" in top-right
    header = section.header
    header_para = header.paragraphs[0]
    header_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header_para.add_run('בס"ד')
    run.font.name = "David"
    run.font.size = Pt(10)
    if is_hebrew:
        _set_rtl(header_para)

    # 3. Footer: Centered Page Numbers
    footer = section.footer
    footer_para = footer.paragraphs[0]
    footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # Add page number field
    fldChar1 = OxmlElement('w:fldChar')
    fldChar1.set(qn('w:fldCharType'), 'begin')
    
    instrText = OxmlElement('w:instrText')
    instrText.set(qn('xml:space'), 'preserve')
    instrText.text = " PAGE "
    
    fldChar2 = OxmlElement('w:fldChar')
    fldChar2.set(qn('w:fldCharType'), 'end')
    
    run_f = footer_para.add_run()
    run_f._r.append(fldChar1)
    run_f._r.append(instrText)
    run_f._r.append(fldChar2)

    # 4. Body Content
    lines = text.split('\n')
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip empty lines (they create paragraph spacing naturally)
        if not line.strip():
            i += 1
            continue
        
        line_type, level, clean_text = _parse_line_type(line)
        
        if line_type == 'page_break':
            # Insert a Word page break
            doc.add_page_break()
            i += 1
            continue
        
        if line_type == 'heading':
            # Heading styles in docx: level 0 = Title, 1 = Heading 1, etc.
            # We use level directly for Heading 1, Heading 2...
            p = doc.add_paragraph(style=f'Heading {level}')
            # Override heading font
            _add_formatted_runs(p, clean_text, is_hebrew, base_font, Pt(20 - level * 2))
            if is_hebrew:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _set_rtl(p)
        
        elif line_type in ('bullet', 'numbered'):
            style = 'List Bullet' if line_type == 'bullet' else 'List Number'
            p = doc.add_paragraph(style=style)
            # Apply indentation for nested items
            if level > 0:
                p.paragraph_format.left_indent = Inches(0.25 * level)
            _add_formatted_runs(p, clean_text, is_hebrew, base_font, Pt(11))
            if is_hebrew:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _set_rtl(p)
        
        else:  # paragraph
            p = doc.add_paragraph()
            _add_formatted_runs(p, clean_text, is_hebrew, base_font, Pt(11))
            if is_hebrew:
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
                _set_rtl(p)
            else:
                p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        
        i += 1

    doc.save(output_path)
    return output_path
