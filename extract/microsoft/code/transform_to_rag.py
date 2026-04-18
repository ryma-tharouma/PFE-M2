import json
import os
from pathlib import Path
from transformers import AutoTokenizer

# Load Qwen tokenizer once globally
qwen_tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")

MAX_TOKENS = 1000

def count_tokens_qwen(text: str) -> int:
    if not text or not isinstance(text, str):
        return 0
    return len(qwen_tokenizer.encode(text))

def parse_applies_to(applies_to_str):
    if not applies_to_str:
        return []
    return [item.strip() for item in applies_to_str.split(",")]

def get_section_headers(article):
    sections = article.get("sections", [])
    seen = set()
    headers = []
    for sec in sections:
        header = sec.get("header", "").lower().strip()
        if header and header not in seen:
            headers.append(header)
            seen.add(header)
    return tuple(headers)

def is_good_structure(headers):
    good_patterns = [
        ("symptômes", "la cause", "résolution"),
        ("symptômes", "la cause", "contournement"),
        ("symptômes", "la cause", "plus d'informations", "résolution"),
        ("symptômes", "la cause", "plus d'informations", "contournement"),
        ("la cause", "résolution", "symptômes"),
        ("la cause", "contournement", "symptômes"),
        ("la cause", "plus d'informations", "résolution", "symptômes"),
        ("la cause", "plus d'informations", "contournement", "symptômes"),
        ("contournement", "la cause", "symptômes"),
        ("contournement", "la cause", "plus d'informations", "symptômes"),
        ("contournement", "la cause", "résolution", "symptômes"),
        ("contournement", "la cause", "plus d'informations", "résolution", "symptômes"),
    ]
    has_problem = any(k in headers for k in ["symptômes", "la cause"])
    has_solution = any(k in headers for k in ["résolution", "contournement"])
    return headers in good_patterns or (has_problem and has_solution)

def extract_section_content(sections, section_names, markdown=True):
    """
    Extract content from sections whose header contains any of section_names.
    - markdown=True  -> output "## Header\n\nContent"
    - markdown=False -> output "Header:\nContent" (plain text, no markdown)
    """
    parts = []
    for sec in sections:
        header = sec.get("header", "")
        if any(name in header.lower() for name in section_names):
            content = sec.get("content", "")
            if markdown:
                parts.append(f"## {header}\n\n{content}")
            else:
                parts.append(f"{header}:\n{content}")
    return "\n\n".join(parts).strip()

def transform_article(article, section_id):
    title = article.get("title", "")
    applies_to = parse_applies_to(article.get("applies_to", ""))
    sections = article.get("sections", [])
    fetched_url = article.get("fetched_url", "")
    category = article.get("category", "")

    # ----- PROBLEM (plain text, no markdown) -----
    problem = title
    symptomes_plain = extract_section_content(sections, ["symptôme"], markdown=False)
    if symptomes_plain:
        problem += f"\n\nSymptômes:\n{symptomes_plain}"

    # ----- ANSWER (keep markdown headings) -----
    cause_md = extract_section_content(sections, ["cause"], markdown=True)
    resolution_md = extract_section_content(sections, ["résolution", "contournement", "résolution rapide"], markdown=True)
    answer_parts = []
    if cause_md:
        answer_parts.append(cause_md)
    if resolution_md:
        answer_parts.append(resolution_md)
    answer = "\n\n".join(answer_parts)

    # ----- FULL_TEXT (plain text, no markdown, as original) -----
    # Plain versions of answer sections (no '##')
    cause_plain = extract_section_content(sections, ["cause"], markdown=False)
    resolution_plain = extract_section_content(sections, ["résolution", "contournement", "résolution rapide"], markdown=False)
    plain_answer_parts = []
    if cause_plain:
        plain_answer_parts.append(cause_plain)
    if resolution_plain:
        plain_answer_parts.append(resolution_plain)
    plain_answer = "\n\n".join(plain_answer_parts)

    full_text = f"Title: {title}\n"
    full_text += f"Applies to: {', '.join(applies_to)}\n\n"
    full_text += f"Problem:\n{problem}\n\n"
    full_text += f"Answer:\n{plain_answer}"

    return {
        "section_id": section_id,
        "title": title,
        "applies_to": applies_to,
        "problem": problem,
        "answer": answer,
        "full_text": full_text,
        "source": fetched_url,
        "source_type": "faq",
        "category": category,
    }

def transform_articles(input_dir="data/scraped", output_dir="data/rag_final"):
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    print(f"\n🔍 Checking input directory: {input_path.absolute()}")
    if not input_path.exists():
        print("  ✗ Directory does not exist!")
        return

    json_files = sorted(input_path.glob("*.json"))
    print(f"  Found {len(json_files)} JSON files:")
    for f in json_files:
        print(f"    - {f.name}")

    if not json_files:
        print("  ✗ No JSON files found!")
        return

    output_path.mkdir(parents=True, exist_ok=True)
    os.makedirs("analysis", exist_ok=True)

    report_file = Path("analysis/rag_transformation_report.txt")

    with open(report_file, "w", encoding="utf-8") as report:
        report.write(f"\n{'='*80}\n")
        report.write(f"  RAG TRANSFORMATION REPORT\n")
        report.write(f"{'='*80}\n\n")

        total_articles = 0
        total_transformed = 0
        total_filtered_structure = 0
        total_filtered_tokens = 0
        all_categories_results = {}

        for file_path in json_files:
            category = file_path.stem
            print(f"\n📄 Processing {category}.json...")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    articles = json.load(f)
            except Exception as e:
                print(f"  ✗ Error reading file: {e}")
                continue

            print(f"  Loaded {len(articles)} articles")

            transformed_articles = []
            good_structure_count = 0
            bad_structure_count = 0
            token_exceed_count = 0
            structure_breakdown = {}

            section_id = 1
            for idx, article in enumerate(articles, 1):
                try:
                    headers = get_section_headers(article)
                    headers_str = " → ".join(headers)
                    structure_breakdown[headers_str] = structure_breakdown.get(headers_str, 0) + 1

                    if not is_good_structure(headers):
                        bad_structure_count += 1
                        continue
                    good_structure_count += 1

                    transformed = transform_article(article, section_id)

                    if count_tokens_qwen(transformed["full_text"]) > MAX_TOKENS:
                        token_exceed_count += 1
                        continue

                    transformed_articles.append(transformed)
                    section_id += 1

                except Exception as e:
                    print(f"  ✗ Error transforming article {idx}: {e}")
                    continue

            total_articles += len(articles)
            total_transformed += len(transformed_articles)
            total_filtered_structure += bad_structure_count
            total_filtered_tokens += token_exceed_count
            all_categories_results[category] = transformed_articles

            output_file = output_path / f"{category}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(transformed_articles, f, ensure_ascii=False, indent=2)

            print(f"  ✓ Kept (structure): {good_structure_count}")
            print(f"  ✗ Filtered (structure): {bad_structure_count}")
            print(f"  ✗ Filtered (full_text > {MAX_TOKENS} tokens, Qwen): {token_exceed_count}")
            print(f"  → Final kept: {len(transformed_articles)}")

            pct_kept_struct = (good_structure_count / len(articles) * 100) if articles else 0
            pct_kept_total = (len(transformed_articles) / len(articles) * 100) if articles else 0
            report.write(f"\n{category.upper()}\n")
            report.write(f"{'-'*80}\n")
            report.write(f"  Total articles: {len(articles)}\n")
            report.write(f"  ✓ Good structure (kept): {good_structure_count} ({pct_kept_struct:.1f}%)\n")
            report.write(f"  ✗ Bad structure (filtered): {bad_structure_count} ({100-pct_kept_struct:.1f}%)\n")
            report.write(f"  ✗ Exceeds {MAX_TOKENS} tokens (full_text, Qwen): {token_exceed_count}\n")
            report.write(f"  → Final kept after both filters: {len(transformed_articles)} ({pct_kept_total:.1f}%)\n")
            report.write(f"  Output: {output_file}\n\n")

            report.write(f"  Structure breakdown (top 15):\n")
            for struct, count in sorted(structure_breakdown.items(), key=lambda x: x[1], reverse=True)[:15]:
                status = "✓ KEPT" if is_good_structure(tuple(s.strip() for s in struct.split(" → "))) else "✗ FILTERED"
                report.write(f"    [{count:3d}x] {status} - {struct}\n")

        # Summary
        report.write(f"\n{'='*80}\n")
        report.write(f"  SUMMARY\n")
        report.write(f"{'='*80}\n\n")
        report.write(f"{'Category':<15} {'Total':<10} {'Kept':<10} {'Filtered (struct)':<18} {'Filtered (>1000t)':<18} {'%':<10}\n")
        report.write(f"{'-'*80}\n")

        for category in sorted(all_categories_results.keys()):
            json_file = input_path / f"{category}.json"
            with open(json_file) as f:
                orig = json.load(f)
            total = len(orig)
            kept = len(all_categories_results[category])
            filtered = total - kept
            pct = (kept / total * 100) if total > 0 else 0
            report.write(f"{category:<15} {total:<10} {kept:<10} {filtered:<18} {pct:>6.1f}%\n")

        report.write(f"{'-'*80}\n")
        pct_all = (total_transformed / total_articles * 100) if total_articles > 0 else 0
        report.write(f"{'TOTAL':<15} {total_articles:<10} {total_transformed:<10} {total_filtered_structure + total_filtered_tokens:<18} {pct_all:>6.1f}%\n")

        report.write(f"\n✓ RAG-ready articles saved to: {output_dir}/\n\n")
        report.write(f"Filters applied:\n")
        report.write(f"  1. Good structure: must contain both problem ('symptômes' or 'la cause') and solution ('résolution' or 'contournement')\n")
        report.write(f"  2. Maximum token length: full_text (plain text) ≤ {MAX_TOKENS} tokens (using Qwen2.5-0.5B-Instruct tokenizer)\n")
        report.write(f"\nField formatting:\n")
        report.write(f"  - problem: plain text (no markdown) – like original article\n")
        report.write(f"  - answer: markdown (keeps '## ' headings) for readability\n")
        report.write(f"  - full_text: plain text (no markdown) – exactly as original article content\n")
        report.write(f"\n{'='*80}\n\n")

    with open(report_file) as f:
        print("\n" + f.read())

    print(f"\n✓ Report saved to: {report_file}")

if __name__ == "__main__":
    transform_articles()