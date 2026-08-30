"""
reformat.py — Re-render an existing translation .md into Word, with the
formatting chosen interactively.

Nothing is re-translated and nothing is overwritten: the settings you pick are
encoded into the output file name and into the .docx Title property, so each
variant sits beside the original.

    py code/reformat.py                       # pick from output/
    py code/reformat.py "C:\\path\\to\\file.md"  # or paste / drag a path
"""

import os
import re
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from formatter import (FormatOptions, save_word, save_word_columns,
                       _blocks, _pair_runs, _parse_line_type)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")

HEBREW_FONTS = ["David", "Frank Ruehl CLM", "Narkisim", "Times New Roman", "Arial"]
LATIN_FONTS = ["Calibri", "Times New Roman", "Garamond", "Georgia", "Arial"]
SIZES = [9, 10, 11, 12, 14, 16]
SPACINGS = [1.0, 1.15, 1.5, 2.0]
MARGINS = [0.5, 0.7, 1.0, 1.25]

LAYOUT_LABELS = {
    "mono": "Translation only",
    "stacked": "Both languages, stacked paragraphs",
    "columns": "Both languages, side-by-side columns",
}


# ── input helpers ────────────────────────────────────────────────────────────

def ask(prompt, default=None):
    """input() that survives a closed stdin and treats Ctrl-C as 'quit'."""
    try:
        raw = input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    return raw or (default if default is not None else "")


def clean_path(raw):
    """Strip the quotes cmd.exe leaves on a pasted or dragged path."""
    raw = raw.strip().strip('"').strip("'").strip()
    return os.path.expandvars(os.path.expanduser(raw))


def pick_from_cycle(label, values, current, fmt=str):
    """Numbered chooser; blank keeps the current value."""
    print(f"\n  {label}:")
    for i, v in enumerate(values, 1):
        mark = " (current)" if v == current else ""
        print(f"    {i}) {fmt(v)}{mark}")
    raw = ask("  Choice (blank = keep): ")
    if raw.isdigit() and 1 <= int(raw) <= len(values):
        return values[int(raw) - 1]
    return current


# ── locating the markdown ────────────────────────────────────────────────────

def find_md_files():
    """Every .md under output/, newest first."""
    found = []
    if os.path.isdir(OUTPUT_DIR):
        for root, _dirs, files in os.walk(OUTPUT_DIR):
            for f in files:
                if f.lower().endswith(".md"):
                    found.append(os.path.join(root, f))
    return sorted(found, key=os.path.getmtime, reverse=True)


def resolve_md(raw):
    """Accept a .md path, a .docx path, or the folder that holds them."""
    path = clean_path(raw)
    if not path:
        return None
    if os.path.isdir(path):
        mds = [f for f in os.listdir(path) if f.lower().endswith(".md")]
        if len(mds) == 1:
            return os.path.join(path, mds[0])
        print(f"  ! {'No' if not mds else 'More than one'} .md file in that folder.")
        return None
    if path.lower().endswith(".docx"):
        alt = os.path.splitext(path)[0] + ".md"
        if os.path.isfile(alt):
            return alt
    if os.path.isfile(path):
        return path
    print(f"  ! Not found: {path}")
    return None


def choose_md():
    if len(sys.argv) > 1 and sys.argv[1].strip():
        md = resolve_md(sys.argv[1])
        if md:
            return md

    files = find_md_files()
    if files:
        print("\n  Documents in output/ (newest first):\n")
        for i, f in enumerate(files[:15], 1):
            print(f"    {i}) {os.path.basename(os.path.dirname(f))}")
    while True:
        raw = ask("\n  Paste the .md path, or pick a number: ")
        if not raw:
            continue
        if raw.isdigit() and files and 1 <= int(raw) <= min(len(files), 15):
            return files[int(raw) - 1]
        md = resolve_md(raw)
        if md:
            return md


# ── inspecting the markdown ──────────────────────────────────────────────────

_HEB_RE = re.compile(r'[֐-׿]')
_LAT_RE = re.compile(r'[A-Za-z]')
MIN_LETTERS = 20        # below this a block is a marker, not prose
BILINGUAL_RATIO = 0.20  # minority share of prose blocks that means "both languages"


def _prose_blocks(text):
    """
    (block, is_hebrew) for blocks carrying real prose.

    Short blocks are skipped deliberately: footnote markers like '[1]' and bare
    page numbers hold no letters of either script, and counting them as English
    was enough to make an all-Hebrew document look bilingual.
    """
    out = []
    for b in _blocks(text):
        if re.match(r'^#{1,6}\s', b):
            continue
        heb, lat = len(_HEB_RE.findall(b)), len(_LAT_RE.findall(b))
        if heb + lat >= MIN_LETTERS:
            out.append((b, heb > lat))
    return out


def _content_blocks(text):
    """The blocks save_word_columns will actually pair — headings excluded."""
    out = []
    for b in _blocks(text):
        line_type, _level, _clean = _parse_line_type(b)
        if line_type not in ('page_break', 'heading'):
            out.append(b)
    return out


def _unpaired_share(blocks, source_hebrew):
    """How much of the document would end up with an empty column."""
    pairs = _pair_runs(blocks, source_hebrew, not source_hebrew)
    if not pairs:
        return 1.0
    lonely = sum(1 for s, t in pairs if not s.strip() or not t.strip())
    return lonely / len(pairs)


def inspect(text):
    """
    Returns (is_bilingual, source_lang, target_lang).

    Which language is the source decides how the columns pair up, and reading
    it off the first block is unreliable — a stray '(Delivered in the Holy
    Tongue)' can lead the file.  So both directions are run through the real
    pairing function and the one that leaves fewer empty columns wins.
    """
    prose = _prose_blocks(text)
    if not prose:
        return False, "Hebrew", "English"

    heb = sum(1 for _b, is_heb in prose if is_heb)
    bilingual = min(heb, len(prose) - heb) / len(prose) >= BILINGUAL_RATIO

    if not bilingual:
        # Monolingual: only the target language matters for rendering.
        return (False, "English", "Hebrew") if prose[0][1] else (False, "Hebrew", "English")

    content = _content_blocks(text)
    hebrew_first = _unpaired_share(content, True) <= _unpaired_share(content, False)
    return (True, "Hebrew", "English") if hebrew_first else (True, "English", "Hebrew")


# ── naming ───────────────────────────────────────────────────────────────────

def describe(layout, opts, defaults=FormatOptions()):
    """Short tags for everything that differs from the standard look."""
    tags = [{"mono": "translation only",
             "stacked": "stacked",
             "columns": "side-by-side"}[layout]]
    if opts.body_pt != defaults.body_pt:
        tags.append(f"{opts.body_pt:g}pt")
    if opts.hebrew_font != defaults.hebrew_font:
        tags.append(opts.hebrew_font)
    if opts.latin_font != defaults.latin_font:
        tags.append(opts.latin_font)
    if opts.line_spacing != defaults.line_spacing:
        tags.append(f"{opts.line_spacing:g} spacing")
    if opts.margin_in != defaults.margin_in:
        tags.append(f'{opts.margin_in:g}in margins')
    if not opts.show_bsd:
        tags.append("no bsd")
    elif opts.bsd_side != defaults.bsd_side:
        tags.append("bsd left")
    if not opts.show_page_numbers:
        tags.append("no page numbers")
    if opts.justify:
        tags.append("justified")
    if layout == "columns" and opts.swap_columns:
        tags.append("source left")
    return ", ".join(tags)


def build_output_path(md_path, description):
    base = os.path.splitext(os.path.basename(md_path))[0]
    safe = re.sub(r'[<>:"/\\|?*]', "-", description)
    return os.path.join(os.path.dirname(md_path), f"{base} ({safe}).docx")


# ── the settings menu ────────────────────────────────────────────────────────

def settings_menu(layout, opts, source_lang, target_lang, bilingual):
    on = lambda b: "on" if b else "off"
    while True:
        print("\n" + "=" * 60)
        print("  FORMATTING OPTIONS")
        print("=" * 60)
        print(f"    1) Layout ............. {LAYOUT_LABELS[layout]}")
        print(f"    2) Languages .......... {source_lang} -> {target_lang}")
        print(f"    3) Body text size ..... {opts.body_pt:g} pt")
        print(f"    4) Hebrew font ........ {opts.hebrew_font}")
        print(f"    5) Latin font ......... {opts.latin_font}")
        print(f"    6) Line spacing ....... {opts.line_spacing:g}")
        print(f"    7) Page margins ....... {opts.margin_in:g} in")
        print(f"    8) Bs\"d header ........ {on(opts.show_bsd)}"
              + (f" ({opts.bsd_side})" if opts.show_bsd else ""))
        print(f"    9) Page numbers ....... {on(opts.show_page_numbers)}")
        print(f"   10) Justify body text .. {on(opts.justify)}")
        if layout == "columns":
            order = ("source | translation" if opts.swap_columns
                     else "translation | source")
            print(f"   11) Column order ....... {order}")
        print(f"\n  Saves as: ...({describe(layout, opts)}).docx")
        print("\n  [Enter] generate     [q] quit")

        choice = ask("\n  Change which setting? ").lower()

        if choice in ("q", "quit", "exit"):
            return None, None, None, None
        if choice == "":
            return layout, opts, source_lang, target_lang

        if choice == "1":
            print("\n  Layout:")
            print("    1) Translation only")
            print("    2) Both languages, stacked paragraphs")
            print("    3) Both languages, side-by-side columns")
            raw = ask("  Choice (blank = keep): ")
            picked = {"1": "mono", "2": "stacked", "3": "columns"}.get(raw)
            if picked == "columns" and not bilingual:
                print("\n  ! This .md holds only one language, so a side-by-side")
                print("    layout would leave the source column empty.")
                if ask("    Use it anyway? (y/N): ").lower() not in ("y", "yes"):
                    picked = None
            if picked:
                layout = picked
        elif choice == "2":
            print("\n  Languages:")
            print("    1) Hebrew -> English")
            print("    2) English -> Hebrew")
            print("    3) Enter them myself")
            raw = ask("  Choice (blank = keep): ")
            if raw == "1":
                source_lang, target_lang = "Hebrew", "English"
            elif raw == "2":
                source_lang, target_lang = "English", "Hebrew"
            elif raw == "3":
                s = ask("  Source language: ")
                t = ask("  Target language: ")
                if s and t:
                    source_lang, target_lang = s, t
        elif choice == "3":
            opts.body_pt = pick_from_cycle("Body text size", SIZES, opts.body_pt,
                                           lambda v: f"{v} pt")
        elif choice == "4":
            opts.hebrew_font = pick_from_cycle("Hebrew font", HEBREW_FONTS, opts.hebrew_font)
        elif choice == "5":
            opts.latin_font = pick_from_cycle("Latin font", LATIN_FONTS, opts.latin_font)
        elif choice == "6":
            opts.line_spacing = pick_from_cycle(
                "Line spacing", SPACINGS, opts.line_spacing,
                lambda v: {1.0: "1.0 (single)", 1.5: "1.5", 2.0: "2.0 (double)"}.get(v, f"{v:g}"))
        elif choice == "7":
            opts.margin_in = pick_from_cycle(
                "Page margins", MARGINS, opts.margin_in,
                lambda v: f'{v:g} in' + {0.5: "  (narrow)", 0.7: "  (standard)",
                                         1.0: "  (wide)"}.get(v, ""))
        elif choice == "8":
            if not opts.show_bsd:
                opts.show_bsd = True
            elif opts.bsd_side == "right":
                opts.bsd_side = "left"
            else:
                opts.show_bsd, opts.bsd_side = False, "right"
        elif choice == "9":
            opts.show_page_numbers = not opts.show_page_numbers
        elif choice == "10":
            opts.justify = not opts.justify
        elif choice == "11" and layout == "columns":
            opts.swap_columns = not opts.swap_columns
        else:
            print("  Not an option.")


# ── rendering ────────────────────────────────────────────────────────────────

def render(text, out_path, layout, opts, source_lang, target_lang):
    if layout == "columns":
        save_word_columns(text, out_path, source_lang, target_lang, opts=opts)
    elif layout == "stacked":
        save_word(text, out_path, target_lang, bilingual=True, opts=opts)
    else:
        save_word(text, out_path, target_lang, opts=opts)


def main():
    print("=" * 60)
    print("  Regenerate Word document from Markdown")
    print("=" * 60)

    md_path = choose_md()
    with open(md_path, encoding="utf-8") as f:
        text = f.read()

    bilingual, source_lang, target_lang = inspect(text)
    print(f"\n  Document: {os.path.basename(md_path)}")
    print(f"  Detected: {'both languages present' if bilingual else 'single language'}"
          f" ({source_lang} -> {target_lang})")

    layout = "columns" if bilingual else "mono"
    opts = FormatOptions()

    while True:
        layout, opts, source_lang, target_lang = settings_menu(
            layout, opts, source_lang, target_lang, bilingual)
        if layout is None:
            print("\n  Nothing generated.")
            return

        description = describe(layout, opts)
        out_path = build_output_path(md_path, description)
        opts.doc_title = (f"{os.path.splitext(os.path.basename(md_path))[0]} "
                          f"({description})")

        print(f"\n  Generating: {os.path.basename(out_path)}")
        try:
            render(text, out_path, layout, opts, source_lang, target_lang)
            print(f"  Done -> {out_path}")
        except PermissionError:
            print("  ! Could not write the file. It is probably open in Word —")
            print("    close it and try again.")
        except Exception as e:
            print(f"  ! Failed: {e}")

        if ask("\n  Generate another version of this document? (y/N): ").lower() \
                not in ("y", "yes"):
            return
        # Reset the tags so the next variant is named for its own settings.
        opts.doc_title = ""


if __name__ == "__main__":
    main()
