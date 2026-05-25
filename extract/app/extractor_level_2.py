import os
import re
import json
import sys
import logging
import time
from statistics import mode
from dataclasses import dataclass, field
from typing import Optional
import fitz


# ==================== PATHS ====================

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMPORT_DIR = os.path.join(BASE_DIR, "manuels")
EXPORT_DIR = os.path.join(BASE_DIR, "json")
IMAGES_DIR = os.path.join(EXPORT_DIR, "images")   # images/{pdf_base}/img.png


# ==================== SONATRACH TEMPLATE COLORS (RGB) ====================

H1H2_COLORS = {
    (47, 84, 150),   # #2F5496
    (46, 83, 149),   # #2E5395
}

H3_COLORS = {
    (31, 55,  98),   # #1F3762
    (31, 55,  99),   # #1F3763
}

ALL_BLUE       = H1H2_COLORS | H3_COLORS
IGNORED_COLORS = {(4, 98, 193), (5, 99, 193)}   # hyperlinks


# ==================== SIZE THRESHOLDS (pt) ====================

SIZE_H1  = 15.0    # Calibri Light 16pt
SIZE_H2  = 12.0    # Calibri Light 13pt
SIZE_H3  = 11.0    # Calibri Light 12pt
SIZE_TOL =  0.6    # PDF rounding tolerance


# ==================== PYMUPDF FLAGS ====================

F_ITALIC = 2
F_BOLD   = 16


# ==================== EXTRACTION PARAMETERS ====================

MIN_CONTENT     = 20      # minimum chars to keep a section
MIN_IMG_SIZE    = 5_000   # bytes — skip decorative / tiny images
TOC_PAGES_RANGE = (2, 8)  # scan range for TOC if no PDF bookmarks


# ==================== REGEX ====================

# Caption: keyword + mandatory NUMBER  (Tableau is NEVER a caption)
RE_CAPTION = re.compile(
    r'^(figure|fig\.?|image|capture|écran|schéma|illustration)'
    r'\s+\d+\s*[\s:\-\.]',
    re.IGNORECASE
)

RE_TOC_LINE  = re.compile(r'(\.{3,}|\s{4,})\s*\d+\s*$')
RE_PAGE_ONLY = re.compile(r'^\s*\d{1,3}\s*$')

RE_BUL1  = re.compile(r'^[•●◆▪]\s+')
RE_BUL2  = re.compile(r'^[➢➤►▶→‣✓▸]\s+')
RE_SUB_O = re.compile(r'^(\s{2,}|\t)o\s+')
RE_DASH  = re.compile(r'^[-–—]\s+')
RE_NUM   = re.compile(r'^(\(?(?:[0-9]+|[a-zA-Z]|[ivxlIVXL]{1,5})[.\)]\s)')


# ==================== DATA MODEL ====================

@dataclass
class CaptionImage:
    """One figure caption linked to its saved image."""
    text:       str    # caption text as written in the PDF  (e.g. "Figure 3 : Écran principal")
    image_path: str    # relative path from EXPORT_DIR  (e.g. "images/manuel/ecran_03.png")
    page:       int    # PDF page number (1-based)


@dataclass
class Section:
    title:        str
    global_title: str    # H1 chapter grouping
    parent:       str    # immediate parent title
    breadcrumb:   str    # full path: "H1 > H2 > H3"
    level:        int
    page:         int
    content:      str            = ""
    captions:     list           = field(default_factory=list)  # list[CaptionImage]
    source_pdf:   str            = ""


# ==================== LOGGER ====================

def _setup_logger(pdf_name: str) -> logging.Logger:
    os.makedirs("logs/extractor", exist_ok=True)
    timestamp   = time.strftime("%Y%m%d_%H%M%S")
    log_file    = f"logs/extractor/{pdf_name}_{timestamp}.log"
    logger_name = f"extractor.{pdf_name}.{timestamp}"

    logger = logging.getLogger(logger_name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    return logger


# ==================== IMAGE HELPERS ====================

def _caption_to_filename(caption: str, index: int, ext: str = "png") -> str:
    """
    Build a clean filename from a figure caption.
    Identical logic to extractor_docling.caption_to_filename so that
    the two extractors produce the same naming convention.

    Example:
        "Figure 3 : Écran de connexion"  →  "ecran_de_connexion_03.png"
    """
    # Strip the keyword prefix (Figure N :, Image 2 -, …)
    name = re.sub(
        r'^(figure|fig\.?|image|capture|écran|schéma|illustration)\s*\d*[\s:\-\.]+',
        '', caption, flags=re.IGNORECASE
    ).strip() or caption

    name = name.lower()
    for src, dst in [
        ("é","e"),("è","e"),("ê","e"),("à","a"),("â","a"),
        ("ù","u"),("û","u"),("î","i"),("ï","i"),("ô","o"),
        ("ç","c"),("'","_"),("\u2019","_"),
    ]:
        name = name.replace(src, dst)

    name = re.sub(r'[^a-z0-9]+', '_', name).strip('_')
    if len(name) > 60:
        name = name[:60].rstrip('_')

    return f"{name}_{index:02d}.{ext}"


def _extract_page_images(pdf_path: str, pdf_base: str) -> dict[int, list[dict]]:
    """
    Extract all raw images from the PDF grouped by page number (1-based).
    Only images larger than MIN_IMG_SIZE bytes are kept.

    Returns:
        {page_num: [{"ext": str, "data": bytes, "folder": str,
                     "saved": bool, "path": str|None}, …]}
    """
    img_folder = os.path.join(IMAGES_DIR, pdf_base)
    os.makedirs(img_folder, exist_ok=True)

    doc         = fitz.open(pdf_path)
    page_images: dict[int, list[dict]] = {}

    for page_num, page in enumerate(doc, start=1):
        page_images[page_num] = []
        for img in page.get_images(full=True):
            xref       = img[0]
            base_image = doc.extract_image(xref)
            data       = base_image["image"]
            if len(data) < MIN_IMG_SIZE:
                continue
            page_images[page_num].append({
                "ext":    base_image.get("ext", "png"),
                "data":   data,
                "folder": img_folder,
                "saved":  False,
                "path":   None,
            })

    doc.close()
    total = sum(len(v) for v in page_images.values())
    return page_images, total


def _save_image(img_info: dict, filename: str) -> str:
    """
    Write image bytes to disk and mark as saved.
    Returns the relative path from EXPORT_DIR.
    """
    full_path = os.path.join(img_info["folder"], filename)
    with open(full_path, "wb") as f:
        f.write(img_info["data"])
    img_info["saved"] = True
    img_info["path"]  = full_path
    return os.path.relpath(full_path, EXPORT_DIR)


# ==================== COLOR / FLAG HELPERS ====================

def _rgb(c: int) -> tuple:
    if not c:
        return (0, 0, 0)
    return ((c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF)


def _near(rgb: tuple, targets: set, tol: int = 6) -> bool:
    return any(all(abs(rgb[i] - t[i]) <= tol for i in range(3)) for t in targets)


def _line_info(spans: list) -> dict:
    """Summarize visual properties of a line's spans."""
    max_sz  = 0.0
    italic  = bold = h1h2 = h3 = any_blue = False
    all_ign = True

    for s in spans:
        sz  = s.get("size", 0)
        flg = s.get("flags", 0)
        rgb = _rgb(s.get("color", 0))

        if sz > max_sz:
            max_sz = sz
        if flg & F_ITALIC:
            italic = True
        if flg & F_BOLD:
            bold = True

        if _near(rgb, IGNORED_COLORS):
            continue
        all_ign = False

        if _near(rgb, H1H2_COLORS):
            h1h2 = True; any_blue = True
        if _near(rgb, H3_COLORS):
            h3   = True; any_blue = True

    return dict(
        max_size=max_sz,
        is_italic=italic,
        is_bold=bold,
        h1h2=h1h2,
        h3=h3,
        any_blue=any_blue,
        all_ign=all_ign,
    )


# ==================== LINE CLASSIFIER ====================

def _classify(txt: str, spans: list, toc_set: set) -> tuple[str, int]:
    """
    Returns (kind, level).

    H1 : H1H2 color + non-italic + size >= 15pt
    H2 : H1H2 color + non-italic + size >= 12pt
         OR any_blue + italic       + size >= 12pt  (italic subsections)
    H3 : H3 color                  + size >= 11pt
         OR any_blue + italic       + size >= 11pt  (< 12pt)

    Tableau is NEVER a caption — only Figure/Image/Capture/Écran + NUMBER.
    """
    s = txt.strip()
    if not s:
        return "skip", 0

    if RE_PAGE_ONLY.match(s):
        return "skip", 0
    if RE_TOC_LINE.search(s):
        return "skip", 0

    info = _line_info(spans)
    sz   = info["max_size"]

    if RE_CAPTION.match(s):
        return "caption", 0

    if info["all_ign"]:
        return "body", 0

    # H1
    if info["h1h2"] and not info["is_italic"] and sz >= SIZE_H1 - SIZE_TOL:
        return "heading", 1

    # H2
    if sz >= SIZE_H2 - SIZE_TOL:
        if info["h1h2"] and not info["is_italic"]:
            return "heading", 2
        if info["any_blue"] and info["is_italic"]:
            return "heading", 2

    # H3
    if sz >= SIZE_H3 - SIZE_TOL:
        if info["h3"]:
            return "heading", 3
        if info["any_blue"] and info["is_italic"]:
            return "heading", 3

    # TOC fallback
    if s in toc_set and info["any_blue"]:
        return "heading", 2

    # Lists
    if RE_SUB_O.match(txt):
        return "bullet2", 0
    if RE_BUL2.match(s):
        return "bullet2", 0
    if RE_BUL1.match(s) or (s and s[0] in "•●◆▪"):
        return "bullet1", 0
    if RE_DASH.match(s):
        return "bullet1", 0
    if RE_NUM.match(s):
        return "numbered", 0

    return "body", 0


# ==================== DYNAMIC CONTENT START DETECTION ====================

def _detect_content_start(doc) -> int:
    """
    Dynamically find the first real-content page (skips cover / TOC / TOF).

    A page is front-matter if it contains TOC-style lines (text ........ N).
    The first page with an H1 heading AND no TOC lines is the content start.
    Hard fallback: page index 4.
    """
    MAX_FRONTMATTER = 20
    MIN_SCAN_START  =  1   # always skip cover (index 0)

    for pnum in range(MIN_SCAN_START, min(MAX_FRONTMATTER, len(doc))):
        page   = doc[pnum]
        blocks = page.get_text("dict")["blocks"]
        h      = page.rect.height

        has_toc_line   = False
        has_h1_heading = False

        for block in blocks:
            if block["type"] != 0:
                continue
            by, bb = block["bbox"][1], block["bbox"][3]
            if by < h * 0.07 or bb > h * 0.93:
                continue

            for line in block["lines"]:
                spans = line["spans"]
                txt   = "".join(s["text"] for s in spans).strip()
                if not txt:
                    continue

                if RE_TOC_LINE.search(txt):
                    has_toc_line = True

                info = _line_info(spans)
                if (info["h1h2"]
                        and not info["is_italic"]
                        and info["max_size"] >= SIZE_H1 - SIZE_TOL):
                    has_h1_heading = True

        if has_h1_heading and not has_toc_line:
            return pnum

    return 4   # hard fallback


# ==================== TOC EXTRACTION ====================

def _extract_toc(doc, logger: logging.Logger) -> tuple[list, set]:
    entries = []
    toc_set = set()

    pdf_toc = doc.get_toc()
    if pdf_toc:
        for level, title, page in pdf_toc:
            title = title.strip()
            if title:
                entries.append({"title": title, "page": page, "level": level})
                toc_set.add(title)
        logger.info(f"TOC from bookmarks: {len(entries)} entries")
        return entries, toc_set

    p0, p1 = TOC_PAGES_RANGE
    for pnum in range(p0 - 1, min(p1, len(doc))):
        for block in doc[pnum].get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            for line in block["lines"]:
                raw   = "".join(s["text"] for s in line["spans"]).strip()
                clean = re.sub(r'[\.\s]+\d+\s*$', '', raw).strip()
                if clean and len(clean) > 3 and not clean.isdigit():
                    toc_set.add(clean)

    for t in toc_set:
        entries.append({"title": t, "page": 0, "level": 1})

    logger.info(f"TOC scanned (pages {p0}-{p1}): {len(entries)} entries")
    return entries, toc_set


# ==================== SECTION EXTRACTION ====================

def _breadcrumb_for(headings: dict, level: int, title: str) -> str:
    """Build full path from root: 'H1 > H2 > H3'."""
    parts = [headings[l] for l in range(1, level) if headings.get(l)]
    parts.append(title)
    return " > ".join(parts)


def _extract_sections(
    pdf_path: str,
    page_images: dict[int, list[dict]],
    logger: logging.Logger,
) -> tuple[list[Section], list]:
    """
    Main extraction loop.
    page_images is passed in so captions can be linked to their image on the spot.
    """
    doc      = fitz.open(pdf_path)
    pdf_name = os.path.basename(pdf_path)

    toc_entries, toc_set = _extract_toc(doc, logger)

    skip_pages = _detect_content_start(doc)
    logger.info(f"Content starts at page {skip_pages + 1} (0-indexed: {skip_pages})")

    # Body size detection (informational)
    sizes = []
    for pnum, page in enumerate(doc):
        if pnum < skip_pages:
            continue
        h = page.rect.height
        for block in page.get_text("dict")["blocks"]:
            if block["type"] != 0:
                continue
            by, bb = block["bbox"][1], block["bbox"][3]
            if by < h * 0.07 or bb > h * 0.93:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    sizes.append(round(span["size"], 1))

    body_sz = mode(sizes) if sizes else 10.0
    logger.info(f"Detected body size: {body_sz}pt")

    headings: dict[int, str]     = {1: "", 2: "", 3: ""}
    sections: list[Section]      = []
    current:  Optional[Section]  = None
    img_index = 0   # global counter for unique filenames across all captions

    def _save():
        nonlocal current
        if current and len(current.content.strip()) >= MIN_CONTENT:
            sections.append(current)
        current = None

    for pnum, page in enumerate(doc):
        if pnum < skip_pages:
            continue

        h      = page.rect.height
        blocks = page.get_text("dict")["blocks"]
        blocks.sort(key=lambda b: (round(b["bbox"][1] / 5) * 5, b["bbox"][0]))

        for block in blocks:
            if block["type"] != 0:
                continue
            by, bb = block["bbox"][1], block["bbox"][3]
            if by < h * 0.07 or bb > h * 0.93:
                continue

            for line in block["lines"]:
                spans = line["spans"]
                txt   = "".join(s["text"] for s in spans).strip()
                if not txt:
                    continue

                kind, lvl = _classify(txt, spans, toc_set)

                # ── H1
                if kind == "heading" and lvl == 1:
                    _save()
                    headings[1] = txt
                    headings[2] = ""
                    headings[3] = ""
                    current = Section(
                        title        = txt,
                        global_title = txt,
                        parent       = "",
                        breadcrumb   = txt,
                        level        = 1,
                        page         = pnum + 1,
                        source_pdf   = pdf_name,
                    )

                # ── H2
                elif kind == "heading" and lvl == 2:
                    _save()
                    headings[2] = txt
                    headings[3] = ""
                    current = Section(
                        title        = txt,
                        global_title = headings[1] or txt,
                        parent       = headings[1] or "",
                        breadcrumb   = _breadcrumb_for(headings, 2, txt),
                        level        = 2,
                        page         = pnum + 1,
                        source_pdf   = pdf_name,
                    )

                # ── H3
                elif kind == "heading" and lvl == 3:
                    _save()
                    headings[3] = txt
                    current = Section(
                        title        = txt,
                        global_title = headings[1] or txt,
                        parent       = headings[2] or headings[1] or "",
                        breadcrumb   = _breadcrumb_for(headings, 3, txt),
                        level        = 3,
                        page         = pnum + 1,
                        source_pdf   = pdf_name,
                    )

                # ── Caption → link to image on same page (or adjacent pages)
                elif kind == "caption":
                    if current is not None:
                        img_index += 1
                        page_1based = pnum + 1   # caption is on this page

                        filename      = _caption_to_filename(txt, img_index)
                        image_rel_path = ""

                        # Try current page, then page before and after
                        for candidate_page in [page_1based,
                                               page_1based - 1,
                                               page_1based + 1]:
                            for img_info in page_images.get(candidate_page, []):
                                if not img_info["saved"]:
                                    ext      = img_info.get("ext", "png")
                                    fname    = _caption_to_filename(txt, img_index, ext)
                                    image_rel_path = _save_image(img_info, fname)
                                    logger.info(
                                        f"  Image saved: {fname}  (p.{candidate_page})"
                                    )
                                    break
                            if image_rel_path:
                                break

                        current.captions.append(CaptionImage(
                            text       = txt,
                            image_path = image_rel_path,
                            page       = page_1based,
                        ))

                elif kind == "skip":
                    continue

                # ── Content
                elif current is not None:
                    if kind == "bullet1":
                        clean = re.sub(r'^[•●◆▪\-–—]\s*', '', txt)
                        current.content += f"\n• {clean}"

                    elif kind == "bullet2":
                        clean = RE_BUL2.sub('', txt)
                        clean = RE_SUB_O.sub('', clean)
                        clean = re.sub(r'^o\s+', '', clean).strip()
                        current.content += f"\n  o {clean}"

                    elif kind == "numbered":
                        current.content += f"\n{txt}"

                    else:   # body
                        info = _line_info(spans)
                        if info["is_bold"] and not info["any_blue"]:
                            current.content += f"\n**{txt}**"
                        else:
                            last = current.content[-1] if current.content else ""
                            sep  = "\n" if last in ".!?:" else " "
                            current.content = (
                                txt if not current.content
                                else current.content + sep + txt
                            )

    _save()

    # Save any remaining unsaved images (no caption linked) as fallback
    for page_num, imgs in page_images.items():
        for img_info in imgs:
            if not img_info["saved"]:
                img_index += 1
                ext   = img_info.get("ext", "png")
                fname = f"page_{page_num:03d}_img_{img_index:02d}.{ext}"
                _save_image(img_info, fname)

    doc.close()
    logger.info(f"Images saved: {img_index} total")
    return sections, toc_entries



# ==================== TWO-LEVEL GROUPING (TEST) ====================

def _merge_to_two_levels(sections: list) -> list:
    """
    Flatten the hierarchy to only 2 levels for RAG testing:
      - Level 1 (H1) : kept as-is
      - Level 2 (H2) : kept; all its Level 3 children are merged into it

    Level 3 content is appended to the parent L2 section with the H3
    title as a bold separator.  Captions are also merged.
    Level 3 entries are removed from the output.

    section_id is re-numbered on the resulting list.
    Returns a new list — original is not modified.
    """
    import copy
    merged: list = []
    current_l2: dict | None = None

    for sec in sections:
        lvl = sec.get("level", 1)

        if lvl == 1:
            current_l2 = None
            merged.append(copy.deepcopy(sec))

        elif lvl == 2:
            current_l2 = copy.deepcopy(sec)
            merged.append(current_l2)

        elif lvl == 3:
            h3_title   = sec.get("title", "").strip()
            h3_content = sec.get("content", "").strip()
            h3_caps    = sec.get("captions", [])

            if current_l2 is not None:
                # Append H3 as bold sub-header inside L2 content
                if h3_title:
                    current_l2["content"] += f"\n\n**{h3_title}**"
                if h3_content:
                    current_l2["content"] += f"\n{h3_content}"
                current_l2["captions"].extend(copy.deepcopy(h3_caps))
            else:
                # Orphan H3 — promote to level 2
                promoted = copy.deepcopy(sec)
                promoted["level"] = 2
                current_l2 = promoted
                merged.append(current_l2)

    # Re-number section_ids
    for idx, sec in enumerate(merged):
        sec["section_id"] = f"sec_{idx + 1:05d}"

    return merged

# ==================== EXPORT ====================

def extract_pdf_to_json(pdf_path: str) -> str:
    """
    Extract a PDF manual to structured JSON + images.

    Output per PDF:
      docs_exports_hardcoded/
        ├── {base}.json
        └── images/
              └── {base}/
                    ├── ecran_de_connexion_01.png
                    └── liste_utilisateurs_02.png

    Section IDs: sec_00001, sec_00002, … (5-digit zero-padded, per document)

    Returns the path to the generated JSON file.
    """
    pdf_name  = os.path.basename(pdf_path)
    base_name = os.path.splitext(pdf_name)[0]
    logger    = _setup_logger(base_name)

    logger.info(f"=== Extraction start: {pdf_name} ===")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    start = time.time()

    # 1. Extract all images from the PDF first (before text loop)
    logger.info("Extracting images from PDF...")
    page_images, n_images_detected = _extract_page_images(pdf_path, base_name)
    logger.info(f"Images detected: {n_images_detected}")

    # 2. Extract sections (text + captions linked to images)
    sections, toc_entries = _extract_sections(pdf_path, page_images, logger)

    # 3. Build JSON output — plain array of sections (no wrapper, no config, no toc)
    sections_out = [
        {
            "section_id":   f"sec_{idx + 1:05d}",
            "title":        s.title,
            "global_title": s.global_title,
            "parent":       s.parent,
            "breadcrumb":   s.breadcrumb,
            "level":        s.level,
            "page":         s.page,
            "content":      s.content.strip(),
            "captions": [
                {
                    "text":       c.text,
                    "image_path": c.image_path,
                    "page":       c.page,
                }
                for c in s.captions
            ],
            "source_pdf":   s.source_pdf,
            "source_type": "manuel"
        }
        for idx, s in enumerate(sections)
    ]

    out_path = os.path.join(EXPORT_DIR, f"{base_name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sections_out, f, ensure_ascii=False, indent=2)

    # ── Two-level grouped version (for RAG testing) ──────────────────
    sections_2lvl = _merge_to_two_levels(sections_out)
    out_2lvl      = os.path.join(EXPORT_DIR, f"{base_name}_2levels.json")
    with open(out_2lvl, "w", encoding="utf-8") as f:
        json.dump(sections_2lvl, f, ensure_ascii=False, indent=2)
    logger.info(f"2-level JSON : {out_2lvl}  ({len(sections_2lvl)} sections)")

    # 4. Stats
    elapsed    = time.time() - start
    h_counts   = {l: sum(1 for s in sections_out if s["level"] == l) for l in (1, 2, 3)}
    caps_total = sum(len(s["captions"]) for s in sections_out)
    caps_linked = sum(
        1 for s in sections_out for c in s["captions"] if c["image_path"]
    )
    pages_hit  = sorted({s["page"] for s in sections_out})

    logger.info(f"JSON       : {out_path}")
    logger.info(f"Images dir : {IMAGES_DIR}/{base_name}/")
    logger.info(f"Time       : {elapsed:.2f}s")
    logger.info(f"Headings   : H1={h_counts[1]}  H2={h_counts[2]}  H3={h_counts[3]}")
    logger.info(f"Sections   : {len(sections_out)}  |  Captions: {caps_total} ({caps_linked} linked to image)")
    logger.info(f"Pages      : {pages_hit[:15]}{'...' if len(pages_hit) > 15 else ''}")

    # 5. Hierarchy preview (first 15 sections)
    logger.info("Hierarchy preview:")
    for s in sections_out[:15]:
        indent = "  " * (s["level"] - 1)
        logger.info(f"  {indent}H{s['level']} p.{s['page']:3d} | {s['title'][:50]}")
        logger.info(f"  {indent}  breadcrumb: {s['breadcrumb'][:65]}")



    logger.info("=== Extraction complete ===")
    return out_path


# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py -3.11 extractor_hardcoded.py docs_import/mon_manuel.pdf")
        sys.exit(1)
    extract_pdf_to_json(sys.argv[1])