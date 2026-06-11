import os
import re
import json
import sys
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
import fitz


# ==================== PATHS ====================

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMPORT_DIR = os.path.join(BASE_DIR, "docs_import")
EXPORT_DIR = os.path.join(BASE_DIR, "docs_exports_PyMuPDF4LLM")
IMAGES_DIR = os.path.join(EXPORT_DIR, "images")


# ==================== EXTRACTION PARAMETERS ====================

MIN_CONTENT  = 40
MIN_IMG_SIZE = 5_000   # bytes — skip decorative / tiny images


# ==================== REGEX ====================

# Caption: keyword + mandatory NUMBER  (Tableau is NEVER a caption)
# Also handles Markdown formatting (*_) that pymupdf4llm may add
RE_CAPTION = re.compile(
    r'^\*{0,2}_?'
    r'(figure|fig\.?|image|capture|écran|schéma|illustration)'
    r'\s+\d+\s*[\s:\-\.]',
    re.IGNORECASE
)

RE_HEADING = re.compile(r'^(#{1,3})\s+(.+)')


# ==================== DATA MODEL ====================

@dataclass
class CaptionImage:
    text:       str   # caption as written in the PDF
    image_path: str   # relative path from EXPORT_DIR
    page:       int   # PDF page (1-based)


@dataclass
class Section:
    title:        str            # deepest title (H2 or H3 — closest to content)
    global_title: str            # H1 chapter grouping
    parent:       str            # immediate parent title
    breadcrumb:   str            # full path: "H1 > H2 > H3"
    level:        int
    page:         int
    content:      str  = ""
    captions:     list = field(default_factory=list)   # list[CaptionImage]
    source:   str  = ""


# ==================== LOGGER ====================

def _setup_logger(pdf_name: str) -> logging.Logger:
    os.makedirs("logs/extractor", exist_ok=True)
    timestamp   = time.strftime("%Y%m%d_%H%M%S")
    log_file    = f"logs/extractor/{pdf_name}_{timestamp}.log"
    logger_name = f"extractor.pymupdf4llm.{pdf_name}.{timestamp}"

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
    Build a clean filename from a caption.
    Identical to hardcoded extractor — same naming convention across all methods.
    'Figure 3 : Écran de connexion'  →  'ecran_de_connexion_03.png'
    """
    # Strip markdown formatting that pymupdf4llm may add
    caption = re.sub(r'[\*\_]+', '', caption).strip()

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


def _extract_page_images(pdf_path: str, pdf_base: str) -> tuple[dict, int]:
    """
    Extract raw images from PDF grouped by page (1-based).
    Creates:  IMAGES_DIR / {pdf_base} /
    """
    img_folder = os.path.join(IMAGES_DIR, pdf_base)
    os.makedirs(img_folder, exist_ok=True)

    doc         = fitz.open(pdf_path)
    page_images = {}

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
    """Write image to disk, return relative path from EXPORT_DIR."""
    full_path = os.path.join(img_info["folder"], filename)
    with open(full_path, "wb") as f:
        f.write(img_info["data"])
    img_info["saved"] = True
    img_info["path"]  = full_path
    return os.path.relpath(full_path, EXPORT_DIR)


# ==================== PDF → MARKDOWN CHUNKS ====================

def _pdf_to_chunks(pdf_path: str, logger: logging.Logger) -> tuple[list, list]:
    """
    Convert PDF to page chunks via pymupdf4llm.
    Also extract TOC from PDF bookmarks (fallback: reconstruct from headings).
    """
    try:
        import pymupdf4llm
    except ImportError:
        raise ImportError(
            "PyMuPDF4LLM not installed.\n"
            "Run: pip install pymupdf4llm"
        )

    logger.info("Converting PDF → Markdown (PyMuPDF4LLM)...")
    chunks = pymupdf4llm.to_markdown(
        pdf_path,
        show_progress = False,
        margins       = (36, 36, 36, 36),
        page_chunks   = True,
    )

    # TOC from bookmarks
    doc     = fitz.open(pdf_path)
    pdf_toc = doc.get_toc()
    doc.close()

    if pdf_toc:
        toc_entries = [
            {"title": t.strip(), "page": p, "level": l}
            for l, t, p in pdf_toc if t.strip()
        ]
    else:
        # Reconstruct from heading lines in chunks
        toc_entries = []
        for chunk in chunks:
            page = chunk.get("metadata", {}).get("page_number", 0)
            for line in chunk.get("text", "").splitlines():
                m = RE_HEADING.match(line)
                if m:
                    lvl   = len(m.group(1))
                    title = re.sub(r'[\*\_]+', '', m.group(2)).strip()
                    if title and not title.isdigit() and len(title) > 2:
                        toc_entries.append({"title": title, "page": page, "level": lvl})

    logger.info(f"Pages: {len(chunks)}  |  TOC entries: {len(toc_entries)}")
    return chunks, toc_entries


# ==================== CHUNKS → SECTIONS ====================

def _chunks_to_sections(
    chunks:      list,
    page_images: dict,
    source:  str,
    logger:      logging.Logger,
) -> list[Section]:
    """
    Walk markdown lines from pymupdf4llm chunks and build sections.

    Hierarchy logic identical to hardcoded extractor:
      # H1 → global_title context
      ## H2 → real section  (title = this H2)
      ### H3 → real section  (title = this H3)

    Breadcrumb = full path from root.
    Images linked to captions found on the same page.
    """
    sections: list[Section] = []
    headings  = {1: "", 2: "", 3: ""}
    current:  Optional[Section] = None
    img_index = 0

    def _save():
        nonlocal current
        if current and len(current.content.strip()) >= MIN_CONTENT:
            sections.append(current)
        current = None

    def _breadcrumb(level: int, title: str) -> str:
        parts = [headings[l] for l in range(1, level) if headings.get(l)]
        parts.append(title)
        return " > ".join(parts)

    for chunk in chunks:
        page_num = chunk.get("metadata", {}).get("page_number", 0)
        text     = chunk.get("text", "")

        for line in text.splitlines():
            # ── Heading
            h = RE_HEADING.match(line)
            if h:
                lvl   = len(h.group(1))
                title = re.sub(r'[\*\_]+', '', h.group(2)).strip()

                if not title or title.isdigit() or len(title) < 3:
                    continue

                _save()
                headings[lvl] = title
                for l in range(lvl + 1, 4):
                    headings[l] = ""

                if lvl == 1:
                    current = Section(
                        title        = title,
                        global_title = title,
                        parent       = "",
                        breadcrumb   = title,
                        level        = 1,
                        page         = page_num,
                        source   = source,
                    )
                elif lvl == 2:
                    current = Section(
                        title        = title,
                        global_title = headings[1] or title,
                        parent       = headings[1] or "",
                        breadcrumb   = _breadcrumb(2, title),
                        level        = 2,
                        page         = page_num,
                        source   = source,
                    )
                else:  # H3
                    current = Section(
                        title        = title,
                        global_title = headings[1] or title,
                        parent       = headings[2] or headings[1] or "",
                        breadcrumb   = _breadcrumb(3, title),
                        level        = 3,
                        page         = page_num,
                        source   = source,
                    )
                continue

            if current is None:
                continue

            stripped = line.strip()
            if not stripped:
                continue

            # Skip horizontal rules
            if re.match(r'^[-*_]{3,}$', stripped):
                continue

            # Caption → link to image
            if RE_CAPTION.match(stripped):
                clean_cap = re.sub(r'[\*\_]+', '', stripped).strip()
                img_index += 1
                image_rel_path = ""

                for candidate in [page_num, page_num - 1, page_num + 1]:
                    for img_info in page_images.get(candidate, []):
                        if not img_info["saved"]:
                            ext   = img_info.get("ext", "png")
                            fname = _caption_to_filename(clean_cap, img_index, ext)
                            image_rel_path = _save_image(img_info, fname)
                            logger.info(f"  Image: {fname}  (p.{candidate})")
                            break
                    if image_rel_path:
                        break

                current.captions.append(CaptionImage(
                    text=clean_cap, image_path=image_rel_path, page=page_num
                ))
                continue

            # Normal content
            current.content += line + "\n"

    _save()

    # Save leftover images (no caption linked)
    for page_num, imgs in page_images.items():
        for img_info in imgs:
            if not img_info["saved"]:
                img_index += 1
                ext   = img_info.get("ext", "png")
                fname = f"page_{page_num:03d}_img_{img_index:02d}.{ext}"
                _save_image(img_info, fname)

    logger.info(f"Images saved: {img_index} total")
    return sections


# ==================== CONTENT CLEANUP ====================

def _clean_content(text: str) -> str:
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = re.sub(r'^\d{1,3}\s*$', '', text, flags=re.MULTILINE)
    return '\n'.join(line.rstrip() for line in text.splitlines()).strip()


# ==================== EXPORT ====================

def extract_pdf_to_json(pdf_path: str) -> str:
    """
    Extract PDF → JSON using PyMuPDF4LLM (Markdown-based).

    Output JSON is identical in structure to hardcoded extractor:
      section_id, title, global_title, parent, breadcrumb,
      level, page, content, captions[{text, image_path, page}], source

    Images saved to:  docs_exports_PyMuPDF4LLM/images/{pdf_base}/

    Returns path to generated JSON.
    """
    pdf_name  = os.path.basename(pdf_path)
    base_name = os.path.splitext(pdf_name)[0]
    logger    = _setup_logger(base_name)

    logger.info(f"=== Extraction start (PyMuPDF4LLM): {pdf_name} ===")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    start = time.time()

    # 1. Extract images first
    logger.info("Extracting images from PDF...")
    page_images, n_detected = _extract_page_images(pdf_path, base_name)
    logger.info(f"Images detected: {n_detected}")

    # 2. Convert to markdown chunks
    chunks, toc_entries = _pdf_to_chunks(pdf_path, logger)

    # 3. Build sections
    logger.info("Building sections...")
    sections = _chunks_to_sections(chunks, page_images, pdf_name, logger)
    for sec in sections:
        sec.content = _clean_content(sec.content)

    # 4. Build JSON — same structure as hardcoded
    sections_out = [
        {
            "section_id":   f"sec_{idx + 1:05d}",   # sec_00001, sec_00002, …
            "title":        s.title,
            "global_title": s.global_title,
            "parent":       s.parent,
            "breadcrumb":   s.breadcrumb,
            "level":        s.level,
            "page":         s.page,
            "content":      s.content,
            "captions": [
                {"text": c.text, "image_path": c.image_path, "page": c.page}
                for c in s.captions
            ],
            "source": s.source,
            "source_type": "manuel"
        }
        for idx, s in enumerate(sections)
    ]



    out_path = os.path.join(EXPORT_DIR, f"{base_name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sections_out, f, ensure_ascii=False, indent=2)

    # 5. Stats
    elapsed    = time.time() - start
    h_counts   = {l: sum(1 for s in sections_out if s["level"] == l) for l in (1, 2, 3)}
    caps_total = sum(len(s["captions"]) for s in sections_out)
    caps_linked = sum(1 for s in sections_out for c in s["captions"] if c["image_path"])
    pages_hit  = sorted({s["page"] for s in sections_out})

    logger.info(f"JSON       : {out_path}")
    logger.info(f"Images dir : {IMAGES_DIR}/{base_name}/")
    logger.info(f"Time       : {elapsed:.2f}s")
    logger.info(f"Headings   : H1={h_counts[1]}  H2={h_counts[2]}  H3={h_counts[3]}")
    logger.info(f"Sections   : {len(sections_out)}  |  Captions: {caps_total} ({caps_linked} linked)")
    logger.info(f"Pages      : {pages_hit[:15]}{'...' if len(pages_hit) > 15 else ''}")

    logger.info("Hierarchy preview:")
    for s in sections_out[:15]:
        indent = "  " * (s["level"] - 1)
        logger.info(f"  {indent}[{s['section_id']}] H{s['level']} p.{s['page']:3d} | {s['title'][:50]}")
        logger.info(f"  {indent}  breadcrumb: {s['breadcrumb'][:65]}")

    # 6. DOCX
    try:
        from json_to_docx import convert_json_to_docx
        convert_json_to_docx(out_path)
    except ImportError:
        logger.warning("json_to_docx.py not found — skipping DOCX generation")

    logger.info("=== Extraction complete ===")
    return out_path


# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py extractor_pymupdf4llm.py docs_import/mon_manuel.pdf")
        sys.exit(1)
    extract_pdf_to_json(sys.argv[1])