"""
formatter.py — Handles output generation for Markdown and Word (.docx).
Implements strict styling for Word:
- Top-right header: בס"ד
- Centered footer: Page numbers
- RTL/Right-aligned if output is Hebrew
"""

import os
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

def save_word(text, output_path, output_lang):
    """
    Saves text to a Word document with specific styling.
    """
    doc = Document()
    
    # 1. Setup Section (Margins and RTL)
    section = doc.sections[0]
    section.top_margin = Inches(0.7)
    section.bottom_margin = Inches(0.7)
    section.left_margin = Inches(0.7)
    section.right_margin = Inches(0.7)
    
    is_hebrew = "hebrew" in output_lang.lower()
    
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
    paragraphs = text.split('\n\n')
    for p_text in paragraphs:
        if not p_text.strip():
            continue
        p = doc.add_paragraph()
        
        # Alignment and RTL
        if is_hebrew:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            _set_rtl(p)
        else:
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT
            
        run = p.add_run(p_text.strip())
        run.font.name = "David" if is_hebrew else "Calibri"
        run.font.size = Pt(11)
        if is_hebrew:
            run.font.rtl = True

    doc.save(output_path)
    return output_path
