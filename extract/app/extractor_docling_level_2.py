import os
import re
import json
import sys
import logging
import time
from dataclasses import dataclass, field
from typing import Optional
import fitz

# ==================== CACHE (Ubuntu-compatible) ====================

hf_cache     = os.path.expanduser("~/.cache/huggingface")
docling_cache = os.path.expanduser("~/.cache/docling")
os.makedirs(hf_cache,      exist_ok=True)
os.makedirs(docling_cache, exist_ok=True)
os.environ.setdefault("HF_HOME",       hf_cache)
os.environ.setdefault("DOCLING_CACHE", docling_cache)


# ==================== PATHS ====================

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
IMPORT_DIR = os.path.join(BASE_DIR, "manuels")
EXPORT_DIR = os.path.join(BASE_DIR, "json")
IMAGES_DIR = os.path.join(EXPORT_DIR, "images")


# ==================== EXTRACTION PARAMETERS ====================

MIN_CONTENT  = 40      # minimum chars to keep a section
MIN_IMG_SIZE = 5_000   # bytes — skip decorative / tiny images


# ==================== REGEX ====================

# Caption: keyword + mandatory NUMBER  (Tableau is NEVER a caption)
RE_CAPTION = re.compile(
    r'^(figure|fig\.?|image|capture|écran|schéma|illustration)'
    r'\s+\d+\s*[\s:\-\.]',
    re.IGNORECASE
)


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
    tables:       list = field(default_factory=list)
    source:   str  = ""


# ==================== LOGGER ====================

def _setup_logger(pdf_name: str) -> logging.Logger:
    os.makedirs("logs/extractor", exist_ok=True)
    timestamp   = time.strftime("%Y%m%d_%H%M%S")
    log_file    = f"logs/extractor/{pdf_name}_{timestamp}.log"
    logger_name = f"extractor.docling.{pdf_name}.{timestamp}"

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
    'Figure 3 : Écran de connexion'  →  'ecran_de_connexion_03.png'
    """
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


def _extract_page_images(pdf_path: str, pdf_base: str) -> dict:
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


# ==================== DOCLING CONVERSION ====================

def _convert_with_docling(pdf_path: str):
    try:
        from docling.document_converter import DocumentConverter
        from docling.datamodel.pipeline_options import PdfPipelineOptions
        from docling.datamodel.base_models import InputFormat
        from docling.document_converter import PdfFormatOption
    except ImportError:
        raise ImportError("Run: pip install docling")

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr             = False
    pipeline_options.do_table_structure = True

    converter = DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )
    result = converter.convert(pdf_path)
    return result.document


# ==================== TOC ====================

def _extract_toc(pdf_path: str, sections: list) -> list:
    """Priority 1: PDF bookmarks.  Priority 2: reconstruct from sections."""
    doc     = fitz.open(pdf_path)
    pdf_toc = doc.get_toc()
    doc.close()

    if pdf_toc:
        return [
            {"title": t.strip(), "page": p, "level": l}
            for l, t, p in pdf_toc
            if t.strip()
        ]

    # Reconstruct from H1/H2 sections
    return [
        {"title": s.title, "page": s.page, "level": s.level}
        for s in sections
        if s.level <= 2 and s.title
    ]


# ==================== SECTION BUILDER ====================

def _build_sections(
    doc,
    page_images: dict,
    source:  str,
    logger:      logging.Logger,
) -> list[Section]:
    """
    Walk Docling items to build sections.
    Hierarchy logic:
      H1 → global_title context
      H2 → real section  (title = this H2)
      H3 → real section  (title = this H3)
    Breadcrumb = full path from root.
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

    for item, level in doc.iterate_items():
        item_type = type(item).__name__
        page_num  = 0
        try:
            if hasattr(item, "prov") and item.prov:
                page_num = item.prov[0].page_no
        except Exception:
            pass

        # ── HEADING ─────────────────────────────────────────────────
        if item_type == "SectionHeaderItem" or (
            hasattr(item, "label") and
            "heading" in str(getattr(item, "label", "")).lower()
        ):
            text = getattr(item, "text", "").strip()
            lvl  = min(level, 3) if level else 2

            if not text or len(text) < 2:
                continue

            _save()
            headings[lvl] = text
            for l in range(lvl + 1, 4):
                headings[l] = ""

            parent = next(
                (headings[l] for l in range(lvl - 1, 0, -1) if headings.get(l)),
                ""
            )

            if lvl == 1:
                current = Section(
                    title        = text,
                    global_title = text,
                    parent       = "",
                    breadcrumb   = text,
                    level        = 1,
                    page         = page_num,
                    source   = source,
                )
            elif lvl == 2:
                current = Section(
                    title        = text,
                    global_title = headings[1] or text,
                    parent       = headings[1] or "",
                    breadcrumb   = _breadcrumb(2, text),
                    level        = 2,
                    page         = page_num,
                    source   = source,
                )
            else:  # H3
                current = Section(
                    title        = text,
                    global_title = headings[1] or text,
                    parent       = headings[2] or headings[1] or "",
                    breadcrumb   = _breadcrumb(3, text),
                    level        = 3,
                    page         = page_num,
                    source   = source,
                )

        # ── TEXT / DOC ITEM ─────────────────────────────────────────
        elif item_type in ("TextItem", "DocItem") and hasattr(item, "text"):
            if current is None:
                continue
            text = getattr(item, "text", "").strip()
            if not text or len(text) < 5:
                continue

            # Caption detection
            if RE_CAPTION.match(text):
                img_index += 1
                image_rel_path = ""

                for candidate in [page_num, page_num - 1, page_num + 1]:
                    for img_info in page_images.get(candidate, []):
                        if not img_info["saved"]:
                            ext      = img_info.get("ext", "png")
                            fname    = _caption_to_filename(text, img_index, ext)
                            image_rel_path = _save_image(img_info, fname)
                            logger.info(f"  Image: {fname}  (p.{candidate})")
                            break
                    if image_rel_path:
                        break

                current.captions.append(CaptionImage(
                    text=text, image_path=image_rel_path, page=page_num
                ))
            else:
                current.content += text + "\n"

        # ── LIST ITEM ───────────────────────────────────────────────
        elif item_type == "ListItem" and hasattr(item, "text"):
            if current is None:
                continue
            text = getattr(item, "text", "").strip()
            if text:
                current.content += f"• {text}\n"

        # ── TABLE ───────────────────────────────────────────────────
        elif item_type == "TableItem":
            if current is None:
                continue
            try:
                table_md = item.export_to_markdown()
                if table_md and table_md.strip():
                    current.tables.append(table_md)
                    current.content += f"\n{table_md}\n"
            except Exception:
                pass

        # ── PICTURE ─────────────────────────────────────────────────
        elif item_type == "PictureItem":
            if current is None:
                continue
            try:
                cap_text = ""
                if hasattr(item, "caption") and item.caption:
                    cap_text = item.caption.text.strip()
                elif hasattr(item, "captions") and item.captions:
                    cap_text = item.captions[0].text.strip()

                if cap_text and RE_CAPTION.match(cap_text):
                    img_index += 1
                    image_rel_path = ""
                    for img_info in page_images.get(page_num, []):
                        if not img_info["saved"]:
                            ext   = img_info.get("ext", "png")
                            fname = _caption_to_filename(cap_text, img_index, ext)
                            image_rel_path = _save_image(img_info, fname)
                            logger.info(f"  Image: {fname}  (p.{page_num})")
                            break
                    current.captions.append(CaptionImage(
                        text=cap_text, image_path=image_rel_path, page=page_num
                    ))
            except Exception:
                pass

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


# ==================== TWO-LEVEL GROUPING ====================

def _merge_to_two_levels(sections: list) -> list:
    """
    Flatten the hierarchy to only 2 levels:
      - Level 1 (H1) : kept as-is
      - Level 2 (H2) : kept; all its Level 3 children are merged into it

    Level 3 content is appended to the parent L2 section with the H3
    title as a bold separator. Captions are also merged.
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
    Extract PDF → JSON using Docling (RT-DETR + TableFormer).

    Output JSON is identical in structure to hardcoded extractor:
      section_id, title, global_title, parent, breadcrumb,
      level, page, content, captions[{text, image_path, page}],
      tables, source

    Images saved to:  docs_exports_docling/images/{pdf_base}/

    Produces two JSON files:
      - {base}.json          : full 3-level hierarchy
      - {base}_2levels.json  : H3 merged into parent H2

    Returns path to generated JSON (full 3-level).
    """
    pdf_name  = os.path.basename(pdf_path)
    base_name = os.path.splitext(pdf_name)[0]
    logger    = _setup_logger(base_name)

    logger.info(f"=== Extraction start (Docling): {pdf_name} ===")
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    start = time.time()

    # 1. Extract images first
    logger.info("Extracting images from PDF...")
    page_images, n_detected = _extract_page_images(pdf_path, base_name)
    logger.info(f"Images detected: {n_detected}")

    # 2. Run Docling
    logger.info("Running Docling (RT-DETR + TableFormer)...")
    doc = _convert_with_docling(pdf_path)
    logger.info("Docling done")

    # 3. Build sections
    sections = _build_sections(doc, page_images, pdf_name, logger)
    for sec in sections:
        sec.content = _clean_content(sec.content)

    # 4. TOC
    toc_entries = _extract_toc(pdf_path, sections)
    logger.info(f"TOC entries: {len(toc_entries)}")

    # 5. Build JSON — same structure as hardcoded
    sections_out = [
        {
            "section_id":   f"sec_{idx + 1:05d}",
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
            "tables":     s.tables,
            "source_pdf": s.source,
            "source_type": "manuel"
        }
        for idx, s in enumerate(sections)
    ]

    # 6. Write full 3-level JSON
    out_path = os.path.join(EXPORT_DIR, f"{base_name}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(sections_out, f, ensure_ascii=False, indent=2)

    # 7. Write 2-level merged JSON
    sections_2lvl = _merge_to_two_levels(sections_out)
    out_2lvl      = os.path.join(EXPORT_DIR, f"{base_name}_2levels.json")
    with open(out_2lvl, "w", encoding="utf-8") as f:
        json.dump(sections_2lvl, f, ensure_ascii=False, indent=2)
    logger.info(f"2-level JSON : {out_2lvl}  ({len(sections_2lvl)} sections)")

    # 8. Stats
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

    # 9. DOCX (optional)
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
        print("Usage: py extractor_docling.py docs_import/mon_manuel.pdf")
        sys.exit(1)
    extract_pdf_to_json(sys.argv[1])