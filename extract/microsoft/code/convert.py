import json
import os
from pathlib import Path
import re


def parse_applies_to(applies_to_str: str) -> list:
    """Parse 'applies_to' string into a list of values"""
    if not applies_to_str or not isinstance(applies_to_str, str):
        return []
    
    # Split by comma and strip whitespace
    values = [v.strip() for v in applies_to_str.split(',')]
    # Filter out empty strings
    return [v for v in values if v]


def find_symptom_section(sections: list) -> dict:
    """Find and return the symptom section if it exists"""
    for section in sections:
        header = section.get("header", "").lower()
        if any(keyword in header for keyword in ["symptôme", "symptom", "problème", "problem", "issue", "error", "erreur"]):
            return section
    return None


def format_section(header: str, content: str) -> str:
    """Format a section with header and content"""
    return f"## {header}\n\n{content}"


def build_problem(title: str, symptom_section: dict) -> str:
    """Build problem field from title and symptom section"""
    problem = f"# {title}\n\n"
    
    if symptom_section:
        problem += format_section(symptom_section.get("header"), symptom_section.get("content", ""))
    
    return problem.strip()


def build_answer(preamble: str, sections: list, symptom_section: dict) -> str:
    """Build answer field from preamble and all sections except symptom"""
    answer_parts = []
    
    # Add preamble if it exists
    if preamble and preamble.strip():
        answer_parts.append(preamble)
    
    # Add all sections except symptom and title
    for section in sections:
        header = section.get("header", "").lower()
        
        # Skip symptom sections
        if any(keyword in header for keyword in ["symptôme", "symptom", "problème", "problem", "issue", "error", "erreur"]):
            continue
        
        # Add the section
        answer_parts.append(format_section(section.get("header"), section.get("content", "")))
    
    return "\n\n".join(answer_parts).strip()


def build_full_text(title: str, applies_to_list: list, problem: str, answer: str) -> str:
    """Build full_text field by combining title, applies_to, problem, and answer"""
    applies_to_str = ", ".join(applies_to_list) if applies_to_list else "None"
    
    full_text = f"Title: {title}\n"
    full_text += f"Applies to: {applies_to_str}\n\n"
    full_text += f"Problem:\n{problem}\n\n"
    full_text += f"Answer:\n{answer}"
    
    return full_text.strip()


def convert_article(article: dict) -> dict:
    """Convert a single article to the new format"""
    
    article_id = article.get("article_id")
    title = article.get("title", "")
    applies_to = article.get("applies_to", "")
    preamble = article.get("preamble", "")
    sections = article.get("sections", [])
    fetched_url = article.get("fetched_url", "")
    
    # Parse applies_to into list
    applies_to_list = parse_applies_to(applies_to)
    
    # Find symptom section
    symptom_section = find_symptom_section(sections)
    
    # Build problem and answer fields
    problem = build_problem(title, symptom_section)
    answer = build_answer(preamble, sections, symptom_section)
    
    # Build full_text field
    full_text = build_full_text(title, applies_to_list, problem, answer)
    
    converted = {
        "section_id": article_id,
        "title": title,
        "applies_to": applies_to_list,
        "problem": problem,
        "answer": answer,
        "full_text": full_text,             
        "source": fetched_url,
        "source_type": "faq"
    }
    
    return converted


def main():
    source_dir = Path("data/scraped")
    output_dir = Path("data/converted")
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    if not source_dir.exists():
        print(f"✗ Source directory {source_dir} not found")
        return
    
    json_files = list(source_dir.glob("*.json"))
    
    if not json_files:
        print(f"✗ No JSON files found in {source_dir}")
        return
    
    print(f"\n{'='*100}")
    print(f"  Converting {len(json_files)} app(s) from {source_dir} to {output_dir}")
    print(f"{'='*100}\n")
    
    for json_file in sorted(json_files):
        app_name = json_file.stem
        print(f"   Processing {app_name}...")
        
        try:
            # Read source JSON
            with open(json_file, 'r', encoding='utf-8') as f:
                articles = json.load(f)
            
            if not articles:
                print(f"    ✗ No articles found in {json_file}")
                continue
            
            # Convert articles
            converted_articles = []
            for article in articles:
                try:
                    converted = convert_article(article)
                    converted_articles.append(converted)
                except Exception as e:
                    print(f"    ⚠️ Error converting article: {e}")
                    continue
            
            # Write converted JSON
            output_file = output_dir / f"{app_name}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(converted_articles, f, ensure_ascii=False, indent=2)
            
            print(f"    ✓ {len(converted_articles)} articles converted → {output_file}")
        
        except Exception as e:
            print(f"    ✗ Error processing {app_name}: {e}")
    
    print(f"\n{'='*100}")
    print(f"  ✓ Conversion complete!")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()