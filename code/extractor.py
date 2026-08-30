"""
extractor.py — RTL-safe PDF text extraction using per-character geometry.

Many Hebrew PDFs emit glyphs in arbitrary content-stream order with explicit
positioning: word order comes out reversed, words split mid-letter across
"lines", and parentheses/punctuation land in the wrong place.  Stream order is
untrustworthy; character positions are the only source of truth.

Approach (adapted from the RebbeTorahTranslate geometric-reflow extractor,
simplified for general single-column documents):

  1. Read every character on the page via ``page.get_text("rawdict")``
     (decoding legacy cp1255 glyph codes, dropping combining nekkudot and
     private-use glyphs).
  2. Cluster characters into visual rows by baseline y.
  3. Sort each row by x — descending for RTL rows, ascending for LTR rows
     (direction detected per row, so mixed-language documents work).
  4. Derive spaces from horizontal gaps instead of trusting stored spaces.
  5. Re-reverse embedded LTR runs (digits/Latin) inside RTL rows.
  6. Group rows into paragraphs using vertical gaps; mark headings by font
     size and bold runs with ``**`` markdown.

Pages with no text layer (scanned images) are detected and reported so the
caller knows OCR would be required for them.
"""

import os
import re
import unicodedata

import fitz  # PyMuPDF

# Font-size ratio thresholds for markdown heading levels (vs. body size)
HEADING_LEVELS = [(1.6, "# "), (1.25, "## "), (1.1, "### ")]

_BOLD_OPEN = "\x01"
_BOLD_CLOSE = "\x02"
_CITE_OPEN = "\x03"      # small-print source citation / attribution → { … }
_CITE_CLOSE = "\x04"

_HEBREW_RE = re.compile(r'[֐-׿]')
_LTR_RUN_RE = re.compile(r'[A-Za-z0-9]+([ .,:/\-][A-Za-z0-9]+)*')


def _decode_char(ch: str) -> str | None:
    """Decode one raw character; return None if it should be dropped."""
    if '\xe0' <= ch <= '\xfa':          # legacy cp1255 glyph code
        try:
            ch = ch.encode('latin1').decode('windows-1255')
        except UnicodeError:
            pass
    o = ord(ch)
    if o < 0x20 or 0x200B <= o <= 0x200F:   # controls / zero-width marks
        return None
    if 0xE000 <= o <= 0xF8FF:               # private-use-area glyphs
        return None
    if 0x0591 <= o <= 0x05C7:               # combining nekkudot / taamim
        return None
    if 0xFB1D <= o <= 0xFB4F:               # presentation forms → base letter
        ch = ''.join(q for q in unicodedata.normalize('NFKD', ch)
                     if not '֑' <= q <= 'ׇ')
        if not ch:
            return None
    return ch


def _collect_chars(page) -> list[tuple]:
    """Return [(x0, x1, y_mid, size, char, is_bold), ...] for the page."""
    chars = []
    for block in page.get_text("rawdict")["blocks"]:
        if block.get("type") != 0:          # skip images
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                size = span["size"]
                bold = bool(span.get("flags", 0) & 16)
                for c in span.get("chars", []):
                    ch = c["c"]
                    if ch == ' ':           # spaces derived from gaps instead
                        continue
                    ch = _decode_char(ch)
                    if ch is None:
                        continue
                    x0, y0, x1, y1 = c["bbox"]
                    chars.append((x0, x1, (y0 + y1) / 2, size, ch, bold))
    return chars


def _cluster_rows(chars: list[tuple]) -> list[list[tuple]]:
    """Cluster characters into visual rows by baseline y."""
    chars.sort(key=lambda z: z[2])
    rows, row_y = [], None
    for c in chars:
        if row_y is None or c[2] - row_y > 0.55 * c[3]:
            rows.append([])
            row_y = c[2]
        rows[-1].append(c)
    return rows


def _fix_mirrored_brackets(text: str) -> str:
    """
    Some fonts store bracket glyphs visually mirrored, so RTL reordering can
    yield ')א ב('.  Score bracket balance both ways and mirror only when the
    swapped version reads strictly better.
    """
    def violations(t: str) -> int:
        v = depth = 0
        for ch in t:
            if ch in '([':
                depth += 1
            elif ch in ')]':
                if depth == 0:
                    v += 1
                else:
                    depth -= 1
        return v + depth

    swapped = text.translate(str.maketrans('()[]', ')(]['))
    return swapped if violations(swapped) < violations(text) else text


def _render_row(row: list[tuple], cite_max: float = 0.0) -> tuple[str, float, bool]:
    """
    Render one visual row to text.  Characters smaller than `cite_max` are
    wrapped in citation sentinels (→ { … } small-print) and never bolded.
    Returns (text, dominant_font_size, row_is_fully_bold).
    """
    heb = sum(1 for c in row if _HEBREW_RE.match(c[4]))
    is_rtl = heb > len(row) / 2

    row.sort(key=lambda z: -z[0] if is_rtl else z[0])
    out: list[str] = []
    prev_edge = None            # trailing edge of the previous char
    in_bold = False
    in_cite = False
    for x0, x1, _y, size, ch, bold in row:
        if is_rtl:
            gap = prev_edge is not None and prev_edge - x1 > max(1.0, 0.12 * size)
            prev = x0
        else:
            gap = prev_edge is not None and x0 - prev_edge > max(1.0, 0.12 * size)
            prev = x1
        small = size <= cite_max
        want_bold = bold and not small     # small-print citations render non-bold
        # close an open bold run BEFORE the inter-word space and before any
        # citation-state change, so ** never straddles a { } boundary
        if in_bold and not want_bold:
            out.append(_BOLD_CLOSE)
            in_bold = False
        if gap:
            out.append(' ')
        if small != in_cite:
            out.append(_CITE_OPEN if small else _CITE_CLOSE)
            in_cite = small
        if want_bold and not in_bold:
            out.append(_BOLD_OPEN)
            in_bold = True
        out.append(ch)
        prev_edge = prev
    if in_bold:
        out.append(_BOLD_CLOSE)
    if in_cite:
        out.append(_CITE_CLOSE)

    text = ''.join(out)
    if is_rtl:
        # embedded LTR runs come out reversed by the RTL sort — flip them back
        text = _LTR_RUN_RE.sub(lambda m: m.group(0)[::-1], text)
        text = _fix_mirrored_brackets(text)

    sizes: dict[float, int] = {}
    bold_chars = 0
    for c in row:
        sizes[round(c[3], 1)] = sizes.get(round(c[3], 1), 0) + 1
        if c[5]:
            bold_chars += 1
    dominant = max(sizes, key=sizes.get) if sizes else 11.0
    return text.strip(), dominant, bold_chars > len(row) * 0.8


def _finish_markers(text: str) -> str:
    """Convert bold/citation sentinels to markdown and tidy whitespace."""
    # Citation runs → { … } small print
    text = text.replace(_CITE_OPEN, '{').replace(_CITE_CLOSE, '}')
    text = re.sub(r'\}\s*\{', ' ', text)              # merge adjacent runs
    text = re.sub(r'\{\s*', '{ ', text)
    text = re.sub(r'\s*\}', ' }', text)
    text = re.sub(r'\{[\s,.;:]*\}', '', text)         # drop empty / punctuation-only
    # Bold runs → **
    text = re.sub(_BOLD_OPEN + r'\s*' + _BOLD_CLOSE, '', text)      # empty bold
    text = re.sub(_BOLD_CLOSE + r'(\s*)' + _BOLD_OPEN, r'\1', text)  # merge runs
    text = text.replace(_BOLD_OPEN, '**').replace(_BOLD_CLOSE, '**')
    return re.sub(r' +', ' ', text).strip()


def _body_font_size(doc) -> float:
    """The most common font size (by char count) across the document."""
    counts: dict[float, int] = {}
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    size = round(span["size"], 1)
                    counts[size] = counts.get(size, 0) + len(span["text"])
    return max(counts, key=counts.get) if counts else 11.0


def _extract_page(page, body_size: float) -> list[str]:
    """Extract one page as a list of markdown paragraphs."""
    chars = _collect_chars(page)
    if not chars:
        return []

    # citations / attributions are the small print, well below the body size
    cite_max = body_size * 0.92

    rendered = []           # (text, y_mid, size, fully_bold)
    for row in _cluster_rows(chars):
        text, size, fully_bold = _render_row(row, cite_max)
        if text:
            rendered.append((text, row[0][2], size, fully_bold))

    # paragraph grouping: a vertical gap noticeably larger than the typical
    # line spacing starts a new paragraph; heading-sized rows stand alone
    gaps = [rendered[i][1] - rendered[i - 1][1] for i in range(1, len(rendered))]
    typical = sorted(gaps)[len(gaps) // 2] if gaps else 14.0

    def heading_prefix(size: float) -> str:
        for ratio, prefix in HEADING_LEVELS:
            if size >= body_size * ratio:
                return prefix
        return ""

    paragraphs: list[str] = []
    current: list[str] = []
    prev_y = None
    prev_head = None
    for text, y, size, fully_bold in rendered:
        head = heading_prefix(size)
        new_para = (
            prev_y is None
            or y - prev_y > typical * 1.25
            or head != prev_head
        )
        if new_para and current:
            paragraphs.append(" ".join(current))
            current = []
        # a fully-bold body row is usually a sub-header — keep it standalone.
        # (bold is still marked with sentinels here, not '**' yet)
        if not head and fully_bold and _BOLD_OPEN in text:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            paragraphs.append(text)
            prev_y, prev_head = y, head
            continue
        current.append(head + text if not current else text)
        prev_y, prev_head = y, head
    if current:
        paragraphs.append(" ".join(current))

    return [_finish_markers(p) for p in paragraphs if _finish_markers(p)]


def extract_text(pdf_path: str) -> str:
    """
    Extract a PDF as markdown text (headings, bold, page markers), in logical
    reading order.  Raises FileNotFoundError if the file is missing.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        raise ValueError(f"Could not open PDF (corrupt or not a PDF?): {e}") from e
    body_size = _body_font_size(doc)

    pages_md: list[str] = []
    scanned_pages: list[int] = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        paragraphs = _extract_page(page, body_size)
        if not paragraphs:
            if page.get_images():
                scanned_pages.append(page_num + 1)
            continue
        pages_md.append(f"## Page {page_num + 1}\n\n" + "\n\n".join(paragraphs))

    doc.close()

    if scanned_pages:
        print(f"    ⚠ Pages {scanned_pages} have no text layer (scanned images) "
              f"— OCR would be required for them; they were skipped.")

    return "\n\n".join(pages_md)


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(extract_text(sys.argv[1]))
