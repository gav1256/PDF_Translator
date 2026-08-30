"""
chunker.py — Split extracted Markdown into LLM-sized chunks.

Groups whole paragraphs up to MAX_CHUNK_CHARS so no paragraph is ever split
across chunks (except pathological single paragraphs larger than the limit,
which are split on sentence boundaries with ** bold markers kept balanced).
"""

import re

from config import MAX_CHUNK_CHARS


def _split_oversized(paragraph: str, limit: int) -> list[str]:
    """Split one huge paragraph on sentence boundaries, keeping ** balanced."""
    sentences = re.split(r'(?<=[.!?])\s+', paragraph)
    pieces: list[str] = []
    buf: list[str] = []
    length = 0
    for sentence in sentences:
        buf.append(sentence)
        length += len(sentence) + 1
        joined = " ".join(buf)
        # only cut when the bold-marker count is even (no ** span straddles)
        if length > limit and joined.count("**") % 2 == 0:
            pieces.append(joined)
            buf, length = [], 0
    if buf:
        pieces.append(" ".join(buf))
    return pieces


def chunk_text(markdown: str, limit: int = MAX_CHUNK_CHARS) -> list[str]:
    """Split markdown into chunks of whole paragraphs, each <= limit chars."""
    paragraphs = [p.strip() for p in re.split(r"\n\n+", markdown) if p.strip()]

    chunks: list[str] = []
    current: list[str] = []
    length = 0

    def flush():
        nonlocal current, length
        if current:
            chunks.append("\n\n".join(current))
            current, length = [], 0

    for para in paragraphs:
        if len(para) > limit:
            flush()
            chunks.extend(_split_oversized(para, limit))
            continue
        if length + len(para) + 2 > limit:
            flush()
        current.append(para)
        length += len(para) + 2
    flush()

    return chunks
