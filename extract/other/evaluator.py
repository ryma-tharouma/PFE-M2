import os
import re
import csv
import json
import sys
import logging
import time
from pathlib import Path
import numpy as np
import fitz


# ==================== PATHS ====================

BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
REFERENCE_DIR = os.path.join(BASE_DIR, "docs_exports_hardcoded")

CANDIDATES = {
    "Docling":     os.path.join(BASE_DIR, "docs_exports_docling"),
    "PyMuPDF4LLM": os.path.join(BASE_DIR, "docs_exports_PyMuPDF4LLM"),
}

RESULTS_DIR = os.path.join(BASE_DIR, "evaluation_results")


# ==================== LOGGER ====================

def _setup_loggers(pdf_base: str) -> tuple[logging.Logger, logging.Logger]:
    """
    Two loggers per run:
      - metrics logger  : one line per metric value  → {pdf_base}_metrics.log
      - diff logger     : detailed title/breadcrumb diffs  → {pdf_base}_diff.log
    """
    os.makedirs(os.path.join(RESULTS_DIR, "logs"), exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    def _make(name: str, filepath: str) -> logging.Logger:
        logger = logging.getLogger(f"{name}.{pdf_base}.{timestamp}")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        fmt = logging.Formatter("%(asctime)s | %(levelname)-8s | %(message)s")
        fh  = logging.FileHandler(filepath, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(logging.Formatter("%(message)s"))
        ch.setLevel(logging.INFO)
        logger.addHandler(ch)
        return logger

    log_dir   = os.path.join(RESULTS_DIR, "logs")
    metrics_log = _make("metrics", os.path.join(log_dir, f"{pdf_base}_metrics_{timestamp}.log"))
    diff_log    = _make("diff",    os.path.join(log_dir, f"{pdf_base}_diff_{timestamp}.log"))

    return metrics_log, diff_log


# ==================== JSON LOADER ====================

def _load_json(path: str) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(data, list):
        return {"sections": data, "toc": []}
    return data


def _sections(data: dict) -> list[dict]:
    return data.get("sections", [])


# ==================== NORMALIZATION ====================

def _norm(text: str) -> str:
    """Lowercase + collapse whitespace for comparison."""
    return re.sub(r'\s+', ' ', str(text).strip().lower())


def _title_set(sections: list[dict]) -> set[str]:
    return {_norm(s["title"]) for s in sections if s.get("title")}


def _breadcrumb_set(sections: list[dict]) -> set[str]:
    return {_norm(s["breadcrumb"]) for s in sections if s.get("breadcrumb")}


# ==================== COVERAGE METRICS ====================

def _coverage(data: dict, pdf_path: str) -> dict:
    secs          = _sections(data)
    pages_covered = {s.get("page", 0) for s in secs if s.get("page", 0) > 0}
    doc           = fitz.open(pdf_path)
    total_pages   = max(len(doc) - 1, 1)   # -1 for cover page
    doc.close()

    contents  = [s.get("content", "") for s in secs]
    avg_len   = int(np.mean([len(c) for c in contents])) if contents else 0
    total_ch  = sum(len(c) for c in contents)
    caps_linked = sum(
        1 for s in secs
        for c in (s.get("captions") or [])
        if isinstance(c, dict) and c.get("image_path")
    )

    return {
        "nb_sections":     len(secs),
        "pages_covered":   len(pages_covered),
        "total_pages":     total_pages,
        "coverage_%":      round(len(pages_covered) / total_pages * 100, 1),
        "avg_content_len": avg_len,
        "total_chars":     total_ch,
        "captions_linked": caps_linked,
        "H1_count":        sum(1 for s in secs if s.get("level") == 1),
        "H2_count":        sum(1 for s in secs if s.get("level") == 2),
        "H3_count":        sum(1 for s in secs if s.get("level") == 3),
    }


# ==================== TITLE METRICS ====================

def _title_metrics(cand: dict, ref: dict, diff_log: logging.Logger,
                   method: str) -> dict:
    ref_t  = _title_set(_sections(ref))
    cand_t = _title_set(_sections(cand))

    if not ref_t or not cand_t:
        return {"Title_Precision": None, "Title_Recall": None, "Title_F1": None,
                "Title_matched": 0, "Title_missing": 0, "Title_extra": 0}

    matched  = ref_t & cand_t
    missing  = ref_t - cand_t    # in reference but NOT in candidate
    extra    = cand_t - ref_t    # in candidate but NOT in reference

    P = len(matched) / len(cand_t)
    R = len(matched) / len(ref_t)
    F = 2 * P * R / (P + R) if (P + R) > 0 else 0

    # ── Detailed diff log ──────────────────────────────────────────
    diff_log.info(f"")
    diff_log.info(f"{'='*70}")
    diff_log.info(f"[{method}] TITLE DIFF")
    diff_log.info(f"{'='*70}")
    diff_log.info(f"  Matched  : {len(matched)}")
    diff_log.info(f"  Missing  : {len(missing)}  (in hardcoded but NOT in {method})")
    diff_log.info(f"  Extra    : {len(extra)}   (in {method} but NOT in hardcoded)")

    diff_log.debug(f"\n  --- MISSING TITLES ({len(missing)}) ---")
    for t in sorted(missing):
        diff_log.debug(f"    ✗ MISSING  : {t}")

    diff_log.debug(f"\n  --- EXTRA TITLES ({len(extra)}) ---")
    for t in sorted(extra):
        diff_log.debug(f"    + EXTRA    : {t}")

    diff_log.debug(f"\n  --- MATCHED TITLES ({len(matched)}) ---")
    for t in sorted(matched):
        diff_log.debug(f"    ✓ MATCHED  : {t}")

    return {
        "Title_Precision": round(P, 4),
        "Title_Recall":    round(R, 4),
        "Title_F1":        round(F, 4),
        "Title_matched":   len(matched),
        "Title_missing":   len(missing),
        "Title_extra":     len(extra),
    }


# ==================== BREADCRUMB METRICS ====================

def _breadcrumb_metrics(cand: dict, ref: dict, diff_log: logging.Logger,
                        method: str) -> dict:
    ref_b  = _breadcrumb_set(_sections(ref))
    cand_b = _breadcrumb_set(_sections(cand))

    if not ref_b or not cand_b:
        return {"Breadcrumb_Precision": None, "Breadcrumb_Recall": None,
                "Breadcrumb_F1": None, "Breadcrumb_missing": 0, "Breadcrumb_extra": 0}

    matched = ref_b & cand_b
    missing = ref_b - cand_b
    extra   = cand_b - ref_b

    P = len(matched) / len(cand_b)
    R = len(matched) / len(ref_b)
    F = 2 * P * R / (P + R) if (P + R) > 0 else 0

    diff_log.info(f"")
    diff_log.info(f"[{method}] BREADCRUMB DIFF")
    diff_log.info(f"  Matched  : {len(matched)}")
    diff_log.info(f"  Missing  : {len(missing)}")
    diff_log.info(f"  Extra    : {len(extra)}")

    diff_log.debug(f"\n  --- MISSING BREADCRUMBS ({len(missing)}) ---")
    for b in sorted(missing):
        diff_log.debug(f"    ✗ MISSING  : {b}")

    diff_log.debug(f"\n  --- EXTRA BREADCRUMBS ({len(extra)}) ---")
    for b in sorted(extra):
        diff_log.debug(f"    + EXTRA    : {b}")

    return {
        "Breadcrumb_Precision": round(P, 4),
        "Breadcrumb_Recall":    round(R, 4),
        "Breadcrumb_F1":        round(F, 4),
        "Breadcrumb_missing":   len(missing),
        "Breadcrumb_extra":     len(extra),
    }


# ==================== HIERARCHY QUALITY ====================

def _hierarchy_metrics(cand: dict, diff_log: logging.Logger,
                       method: str) -> dict:
    secs = _sections(cand)
    if not secs:
        return {"Hierarchy_Score": None, "Hierarchy_errors": 0}

    errors      = 0
    error_detail = []

    for s in secs:
        lvl   = s.get("level", 1)
        title = s.get("title", "")
        crumb = s.get("breadcrumb", "")
        par   = s.get("parent", "")
        g_ttl = s.get("global_title", "")

        # H3 must have a parent
        if lvl == 3 and not par:
            errors += 1
            error_detail.append(f"H3 has no parent: '{title}'")

        # H2/H3 must have a breadcrumb
        if lvl > 1 and not crumb:
            errors += 1
            error_detail.append(f"H{lvl} has no breadcrumb: '{title}'")

        # global_title must be set for H2/H3
        if lvl > 1 and not g_ttl:
            errors += 1
            error_detail.append(f"H{lvl} has no global_title: '{title}'")

        # Breadcrumb must contain the title itself
        if crumb and _norm(title) not in _norm(crumb):
            errors += 1
            error_detail.append(f"Title not in breadcrumb: '{title}' | crumb='{crumb}'")

        # Title too short
        if len(title.strip()) < 3:
            errors += 1
            error_detail.append(f"Title too short: '{title}'")

    score = max(0.0, round(1 - errors / (len(secs) * 5), 4))

    if error_detail:
        diff_log.info(f"")
        diff_log.info(f"[{method}] HIERARCHY ERRORS ({errors})")
        for e in error_detail[:50]:   # cap at 50 to avoid flooding
            diff_log.debug(f"    ⚠  {e}")
        if len(error_detail) > 50:
            diff_log.debug(f"    … and {len(error_detail) - 50} more errors")

    return {
        "Hierarchy_Score":  score,
        "Hierarchy_errors": errors,
    }


# ==================== ROUGE-L ====================

def _rouge_l(hyp: str, ref: str) -> dict:
    try:
        from rouge_score import rouge_scorer
        scorer = rouge_scorer.RougeScorer(['rougeL'], use_stemmer=False)
        s      = scorer.score(ref, hyp)
        return {
            "ROUGE_L_P": round(s['rougeL'].precision, 4),
            "ROUGE_L_R": round(s['rougeL'].recall,    4),
            "ROUGE_L_F": round(s['rougeL'].fmeasure,  4),
        }
    except ImportError:
        return {"ROUGE_L_P": None, "ROUGE_L_R": None, "ROUGE_L_F": None}


# ==================== BERTSCORE ====================

def _bertscore(hyp: str, ref: str) -> dict:
    try:
        from bert_score import score as bscore

        def _chunks(text: str, max_len: int = 512) -> list[str]:
            sents, cur = [], ""
            for line in text.split('\n'):
                if not line.strip():
                    continue
                if len(cur) + len(line) > max_len:
                    if cur:
                        sents.append(cur.strip())
                    cur = line
                else:
                    cur += " " + line
            if cur:
                sents.append(cur.strip())
            return sents[:30]

        rc = _chunks(ref)
        hc = _chunks(hyp)
        n  = min(len(rc), len(hc))
        if n == 0:
            return {"BERTScore_P": None, "BERTScore_R": None, "BERTScore_F1": None}

        P, R, F = bscore(hc[:n], rc[:n], lang="fr", verbose=False)
        return {
            "BERTScore_P":  round(float(P.mean()), 4),
            "BERTScore_R":  round(float(R.mean()), 4),
            "BERTScore_F1": round(float(F.mean()), 4),
        }
    except ImportError:
        return {"BERTScore_P": None, "BERTScore_R": None, "BERTScore_F1": None}
    except Exception as e:
        return {"BERTScore_P": None, "BERTScore_R": None, "BERTScore_F1": None}


# ==================== CONTENT EXTRACTION ====================

def _full_content(data: dict) -> str:
    parts = []
    for s in _sections(data):
        if s.get("title"):
            parts.append(s["title"])
        if s.get("content"):
            parts.append(s["content"])
    return "\n".join(parts)


# ==================== CSV WRITER ====================

CSV_FIELDS = [
    "pdf",
    "method",
    # Coverage
    "nb_sections", "pages_covered", "total_pages", "coverage_%",
    "avg_content_len", "total_chars", "captions_linked",
    "H1_count", "H2_count", "H3_count",
    # Titles
    "Title_Precision", "Title_Recall", "Title_F1",
    "Title_matched", "Title_missing", "Title_extra",
    # Breadcrumbs
    "Breadcrumb_Precision", "Breadcrumb_Recall", "Breadcrumb_F1",
    "Breadcrumb_missing", "Breadcrumb_extra",
    # Hierarchy
    "Hierarchy_Score", "Hierarchy_errors",
    # NLP
    "ROUGE_L_P", "ROUGE_L_R", "ROUGE_L_F",
    "BERTScore_P", "BERTScore_R", "BERTScore_F1",
    # Meta
    "eval_time_s",
]


def _append_csv(csv_path: str, row: dict) -> None:
    write_header = not os.path.exists(csv_path)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(row)


# ==================== MAIN EVALUATE ====================

def evaluate(pdf_path: str) -> dict:
    """
    Compare Docling and PyMuPDF4LLM against the hardcoded reference.

    Outputs:
      evaluation_results/
        ├── evaluation_summary.csv          ← one row per (pdf, method)
        └── logs/
              ├── {pdf}_metrics_{ts}.log    ← INFO: metric values
              └── {pdf}_diff_{ts}.log       ← DEBUG: missing/extra titles & breadcrumbs
    """
    pdf_name  = os.path.basename(pdf_path)
    pdf_base  = os.path.splitext(pdf_name)[0]
    os.makedirs(RESULTS_DIR, exist_ok=True)

    metrics_log, diff_log = _setup_loggers(pdf_base)

    metrics_log.info(f"=== Evaluation start: {pdf_name} ===")

    # Reference
    ref_path = os.path.join(REFERENCE_DIR, f"{pdf_base}.json")
    if not os.path.exists(ref_path):
        metrics_log.error(f"Reference not found: {ref_path}")
        return {}

    ref_data    = _load_json(ref_path)
    ref_content = _full_content(ref_data)
    ref_secs    = _sections(ref_data)

    metrics_log.info(f"Reference: {len(ref_secs)} sections  |  {len(ref_content)} chars")

    csv_path    = os.path.join(RESULTS_DIR, "evaluation_summary.csv")
    all_results = {}

    for method, export_dir in CANDIDATES.items():
        json_path = os.path.join(export_dir, f"{pdf_base}.json")

        metrics_log.info(f"")
        metrics_log.info(f"--- {method} ---")

        if not os.path.exists(json_path):
            metrics_log.warning(f"  JSON not found: {json_path}")
            continue

        t0        = time.time()
        cand_data = _load_json(json_path)
        cand_secs = _sections(cand_data)
        cand_content = _full_content(cand_data)

        metrics_log.info(f"  Sections : {len(cand_secs)}")
        metrics_log.info(f"  Chars    : {len(cand_content)}")

        # ── Metrics ───────────────────────────────────────────────
        cov   = _coverage(cand_data, pdf_path)
        titles = _title_metrics(cand_data, ref_data, diff_log, method)
        crumbs = _breadcrumb_metrics(cand_data, ref_data, diff_log, method)
        hier   = _hierarchy_metrics(cand_data, diff_log, method)
        rouge  = _rouge_l(cand_content, ref_content)
        bert   = _bertscore(cand_content, ref_content)

        elapsed = round(time.time() - t0, 2)

        row = {
            "pdf":    pdf_name,
            "method": method,
            **cov,
            **titles,
            **crumbs,
            **hier,
            **rouge,
            **bert,
            "eval_time_s": elapsed,
        }

        all_results[method] = row
        _append_csv(csv_path, row)

        # ── Log summary ───────────────────────────────────────────
        metrics_log.info(f"  Coverage     : {cov['coverage_%']}%  ({cov['pages_covered']}/{cov['total_pages']} pages)")
        metrics_log.info(f"  Sections     : {cov['nb_sections']}  (H1={cov['H1_count']} H2={cov['H2_count']} H3={cov['H3_count']})")
        metrics_log.info(f"  Title F1     : {titles['Title_F1']}  (P={titles['Title_Precision']} R={titles['Title_Recall']})")
        metrics_log.info(f"  Title match  : {titles['Title_matched']} matched | {titles['Title_missing']} missing | {titles['Title_extra']} extra")
        metrics_log.info(f"  Breadcrumb F1: {crumbs['Breadcrumb_F1']}  (P={crumbs['Breadcrumb_Precision']} R={crumbs['Breadcrumb_Recall']})")
        metrics_log.info(f"  Hierarchy    : {hier['Hierarchy_Score']}  ({hier['Hierarchy_errors']} errors)")
        metrics_log.info(f"  ROUGE-L F    : {rouge['ROUGE_L_F']}")
        metrics_log.info(f"  BERTScore F1 : {bert['BERTScore_F1']}")
        metrics_log.info(f"  Time         : {elapsed}s")

    # ── Final comparison ──────────────────────────────────────────────
    if len(all_results) == 2:
        methods = list(all_results.keys())
        m1, m2  = methods[0], methods[1]
        metrics_log.info(f"")
        metrics_log.info(f"=== COMPARISON SUMMARY ===")
        metrics_log.info(f"{'Metric':<25} {m1:<15} {m2:<15} {'Winner'}")
        metrics_log.info(f"{'-'*65}")

        compare_keys = [
            ("Title_F1",        "↑ higher is better"),
            ("Breadcrumb_F1",   "↑ higher is better"),
            ("Hierarchy_Score", "↑ higher is better"),
            ("ROUGE_L_F",       "↑ higher is better"),
            ("BERTScore_F1",    "↑ higher is better"),
            ("coverage_%",      "↑ higher is better"),
        ]

        for key, note in compare_keys:
            v1 = all_results[m1].get(key)
            v2 = all_results[m2].get(key)
            if v1 is None or v2 is None:
                winner = "N/A"
            elif v1 > v2:
                winner = m1
            elif v2 > v1:
                winner = m2
            else:
                winner = "TIE"
            v1_str = f"{v1:.4f}" if isinstance(v1, float) else str(v1)
            v2_str = f"{v2:.4f}" if isinstance(v2, float) else str(v2)
            metrics_log.info(f"  {key:<23} {v1_str:<15} {v2_str:<15} → {winner}")

    metrics_log.info(f"")
    metrics_log.info(f"CSV    : {csv_path}")
    metrics_log.info(f"=== Evaluation complete ===")

    return all_results


# ==================== ENTRY POINT ====================

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py -3.11 evaluator.py docs_import/mon_manuel.pdf")
        print("")
        print("Outputs:")
        print("  evaluation_results/evaluation_summary.csv")
        print("  evaluation_results/logs/{pdf}_metrics_{ts}.log")
        print("  evaluation_results/logs/{pdf}_diff_{ts}.log")
        sys.exit(1)

    results = evaluate(sys.argv[1])

    if results:
        print("\n" + "="*65)
        print("FINAL SCORES")
        print("="*65)
        for method, row in results.items():
            print(f"\n  {method}")
            print(f"    Title F1      : {row.get('Title_F1')}")
            print(f"    Breadcrumb F1 : {row.get('Breadcrumb_F1')}")
            print(f"    Hierarchy     : {row.get('Hierarchy_Score')}")
            print(f"    ROUGE-L F     : {row.get('ROUGE_L_F')}")
            print(f"    BERTScore F1  : {row.get('BERTScore_F1')}")
            print(f"    Coverage      : {row.get('coverage_%')}%")