import json
import os
from pathlib import Path


def parse_applies_to(applies_to_str):
    """Parse applies_to string into a list"""
    if not applies_to_str:
        return []
    items = [item.strip() for item in applies_to_str.split(",")]
    return items


def get_section_headers(article):
    """Extract section headers from article IN ORDER (not sorted)"""
    sections = article.get("sections", [])
    # Keep order, remove duplicates while preserving sequence
    seen = set()
    headers = []
    for sec in sections:
        header = sec.get("header", "").lower().strip()
        if header and header not in seen:
            headers.append(header)
            seen.add(header)
    return tuple(headers)


def is_good_structure(headers):
    """Determine if article has good RAG structure (clear problem/solution)"""
    # Define good header combinations (order matters)
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
    
    # Check if headers contain at least: problem (symptoms/cause) and solution (resolution/workaround)
    has_problem = any(keyword in headers for keyword in ["symptômes", "la cause"])
    has_solution = any(keyword in headers for keyword in ["résolution", "contournement"])
    
    # Check if it matches one of our good patterns
    if headers in good_patterns:
        return True
    
    # Also accept if it has problem + solution + optional info
    if has_problem and has_solution:
        return True
    
    return False


def extract_section_content(sections, section_names):
    """Extract and concatenate content from sections matching names"""
    content = ""
    for sec in sections:
        header = sec.get("header", "").lower()
        if any(name in header for name in section_names):
            if content:
                content += "\n\n"
            content += f"## {sec.get('header', '')}\n\n{sec.get('content', '')}"
    return content.strip()


def transform_article(article, section_id):
    """Transform article to RAG format"""
    
    title = article.get("title", "")
    applies_to = parse_applies_to(article.get("applies_to", ""))
    sections = article.get("sections", [])
    fetched_url = article.get("fetched_url", "")
    category = article.get("category", "")
    
    # Extract problem (title + symptômes)
    symptomes_content = extract_section_content(sections, ["symptôme"])
    problem = f"# {title}"
    if symptomes_content:
        problem += f"\n\n{symptomes_content}"
    
    # Extract answer (cause + contournement/résolution)
    cause_content = extract_section_content(sections, ["cause"])
    resolution_content = extract_section_content(sections, ["résolution", "contournement", "résolution rapide"])
    
    answer = ""
    if cause_content:
        answer += cause_content
    if resolution_content:
        if answer:
            answer += "\n\n"
        answer += resolution_content
    
    # Build full_text with all sections
    full_text = f"Title: {title}\n"
    full_text += f"Applies to: {', '.join(applies_to)}\n\n"
    full_text += f"Problem:\n{problem}\n\n"
    full_text += f"Answer:\n{answer}"
    
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
    """Transform scraped articles to RAG format, filtering by structure quality"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)
    
    # Debug: Check if input directory exists
    print(f"\n🔍 Checking input directory: {input_path.absolute()}")
    if not input_path.exists():
        print(f"  ✗ Directory does not exist!")
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
        total_filtered = 0
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
            structure_breakdown = {}
            
            section_id = 1
            for idx, article in enumerate(articles, 1):
                try:
                    headers = get_section_headers(article)
                    
                    # Track structure types
                    headers_str = " → ".join(headers)
                    structure_breakdown[headers_str] = structure_breakdown.get(headers_str, 0) + 1
                    
                    # Only keep articles with good structure
                    if not is_good_structure(headers):
                        bad_structure_count += 1
                        continue
                    
                    good_structure_count += 1
                    transformed = transform_article(article, section_id)
                    transformed_articles.append(transformed)
                    section_id += 1
                    
                except Exception as e:
                    print(f"  ✗ Error transforming article {idx}: {e}")
                    continue
            
            total_articles += len(articles)
            total_transformed += len(transformed_articles)
            total_filtered += bad_structure_count
            all_categories_results[category] = transformed_articles
            
            # Write to output file
            output_file = output_path / f"{category}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(transformed_articles, f, ensure_ascii=False, indent=2)
            
            print(f"  ✓ Kept {good_structure_count} / Filtered {bad_structure_count}")
            
            # Report
            pct_kept = (good_structure_count / len(articles) * 100) if articles else 0
            report.write(f"\n{category.upper()}\n")
            report.write(f"{'-'*80}\n")
            report.write(f"  Total articles: {len(articles)}\n")
            report.write(f"  ✓ Good structure (kept): {good_structure_count} ({pct_kept:.1f}%)\n")
            report.write(f"  ✗ Bad structure (filtered): {bad_structure_count} ({100-pct_kept:.1f}%)\n")
            report.write(f"  Output: {output_file}\n\n")
            
            report.write(f"  Structure breakdown (top 15):\n")
            for struct, count in sorted(structure_breakdown.items(), key=lambda x: x[1], reverse=True)[:15]:
                status = "✓ KEPT" if is_good_structure(tuple(s.strip() for s in struct.split(" → "))) else "✗ FILTERED"
                report.write(f"    [{count:3d}x] {status} - {struct}\n")
        
        # Summary
        report.write(f"\n{'='*80}\n")
        report.write(f"  SUMMARY\n")
        report.write(f"{'='*80}\n\n")
        
        report.write(f"{'Category':<15} {'Total':<10} {'Kept':<10} {'Filtered':<10} {'%':<10}\n")
        report.write(f"{'-'*55}\n")
        
        for category in sorted(all_categories_results.keys()):
            json_file = input_path / f"{category}.json"
            with open(json_file) as f:
                orig = json.load(f)
            total = len(orig)
            kept = len(all_categories_results[category])
            filtered = total - kept
            pct = (kept / total * 100) if total > 0 else 0
            
            report.write(f"{category:<15} {total:<10} {kept:<10} {filtered:<10} {pct:>6.1f}%\n")
        
        report.write(f"{'-'*55}\n")
        pct_all = (total_transformed / total_articles * 100) if total_articles > 0 else 0
        report.write(f"{'TOTAL':<15} {total_articles:<10} {total_transformed:<10} {total_filtered:<10} {pct_all:>6.1f}%\n")
        
        report.write(f"\n✓ RAG-ready articles saved to: {output_dir}/\n\n")
        report.write(f"Good structure criteria:\n")
        report.write(f"  • Must contain BOTH:\n")
        report.write(f"    - Problem marker: 'symptômes' or 'la cause'\n")
        report.write(f"    - Solution marker: 'résolution' or 'contournement'\n")
        report.write(f"  • Common patterns kept:\n")
        patterns = [
            "symptômes → la cause → résolution",
            "la cause → résolution → symptômes",
            "la cause → plus d'informations → résolution → symptômes",
            "contournement → la cause → résolution → symptômes",
        ]
        for pattern in patterns:
            report.write(f"    • {pattern}\n")
        
        report.write(f"\nEach article contains:\n")
        report.write(f"  - section_id: unique identifier\n")
        report.write(f"  - title: article title\n")
        report.write(f"  - applies_to: list of affected versions\n")
        report.write(f"  - problem: title + symptoms (markdown)\n")
        report.write(f"  - answer: cause + resolution/workaround (markdown)\n")
        report.write(f"  - full_text: complete formatted text\n")
        report.write(f"  - source: original URL\n")
        report.write(f"  - source_type: 'faq'\n")
        report.write(f"  - category: article category (Excel, Word, Outlook)\n")
        report.write(f"\n{'='*80}\n\n")
    
    # Print report
    with open(report_file) as f:
        print("\n" + f.read())
    
    print(f"\n✓ Report saved to: {report_file}")


if __name__ == "__main__":
    transform_articles()