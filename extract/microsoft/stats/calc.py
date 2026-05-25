import json
import os
from pathlib import Path
from collections import defaultdict
import tiktoken
from transformers import AutoTokenizer

# Initialize BGE-M3 tokenizer
tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")

# Initialize tiktoken for reference (optional)
try:
    enc = tiktoken.get_encoding("cl100k_base")
except:
    enc = None


def count_tokens(text: str) -> int:
    """Count tokens using BGE-M3 tokenizer"""
    if not text or not isinstance(text, str):
        return 0
    tokens = tokenizer.encode(text)
    return len(tokens)


def calculate_stats(values: list) -> dict:
    """Calculate min, q1, q2 (median), q3, max, mean for a list of values"""
    if not values:
        return {
            "min": 0,
            "q1": 0,
            "q2": 0,
            "q3": 0,
            "max": 0,
            "mean": 0,
            "count": 0
        }
    
    values = sorted(values)
    count = len(values)
    
    # Calculate quartiles
    def percentile(data, p):
        n = len(data)
        i = (p / 100) * (n - 1)
        lower = int(i)
        upper = lower + 1
        weight = i - lower
        
        if upper >= n:
            return data[lower]
        return data[lower] * (1 - weight) + data[upper] * weight
    
    return {
        "min": int(values[0]),
        "q1": int(percentile(values, 25)),
        "q2": int(percentile(values, 50)),  # median
        "q3": int(percentile(values, 75)),
        "max": int(values[-1]),
        "mean": int(sum(values) / count),
        "count": count
    }


def extract_app_stats(json_file: str) -> dict:
    """Extract statistics from a single app JSON file"""
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            articles = json.load(f)
    except Exception as e:
        print(f"  ✗ Error reading {json_file}: {e}")
        return None
    
    if not articles:
        print(f"  ✗ No articles found in {json_file}")
        return None
    
    # Initialize tracking lists
    section_counts = []  # number of sections per article
    tokens_per_section = []  # tokens in each section
    tokens_in_titles = []  # tokens in section titles
    tokens_in_symptoms = []  # tokens in "symptom" sections
    tokens_titles_symptoms = []  # tokens in both titles and symptoms combined
    tokens_non_title_symptom = []  # tokens in all sections except title and symptoms
    
    article_count = 0
    
    for article in articles:
        if isinstance(article, dict) and "sections" in article:
            article_count += 1
            sections = article.get("sections", [])
            
            # Number of sections per article
            section_counts.append(len(sections))
            
            article_title_tokens = 0
            article_symptom_tokens = 0
            
            for section in sections:
                header = section.get("header", "").lower()
                content = section.get("content", "")
                
                # Count tokens in each section
                section_tokens = count_tokens(content)
                tokens_per_section.append(section_tokens)
                
                # Count tokens in titles
                title_tokens = count_tokens(section.get("header", ""))
                tokens_in_titles.append(title_tokens)
                article_title_tokens += title_tokens
                
                # Check if section is related to symptoms
                is_symptom = any(keyword in header for keyword in [
                    "symptôme", "symptom", "problème", "problem", "issue", "error", "erreur"
                ])
                
                if is_symptom:
                    symptom_tokens = count_tokens(content)
                    tokens_in_symptoms.append(symptom_tokens)
                    article_symptom_tokens += section_tokens
                else:
                    # Tokens in non-symptom sections
                    tokens_non_title_symptom.append(section_tokens)
            
            # Combined tokens for titles and symptoms
            if article_title_tokens + article_symptom_tokens > 0:
                tokens_titles_symptoms.append(article_title_tokens + article_symptom_tokens)
    
    if article_count == 0:
        print(f"  ✗ No valid articles found in {json_file}")
        return None
    
    # Calculate statistics for each metric
    stats = {
        "app": Path(json_file).stem,
        "articles": article_count,
        "sections_per_article": calculate_stats(section_counts),
        "tokens_per_section": calculate_stats(tokens_per_section),
        "tokens_in_titles": calculate_stats(tokens_in_titles),
        "tokens_in_symptoms": calculate_stats(tokens_in_symptoms),
        "tokens_titles_symptoms": calculate_stats(tokens_titles_symptoms),
        "tokens_non_title_symptom": calculate_stats(tokens_non_title_symptom),
    }
    
    return stats


def main():
    data_dir = Path("data/scraped")
    
    if not data_dir.exists():
        print(f"✗ Directory {data_dir} not found")
        return
    
    json_files = list(data_dir.glob("*.json"))
    
    if not json_files:
        print(f"✗ No JSON files found in {data_dir}")
        return
    
    print(f"\n{'='*100}")
    print(f"  Analyzing {len(json_files)} app(s) from {data_dir}")
    print(f"{'='*100}\n")
    
    all_stats = []
    
    for json_file in sorted(json_files):
        print(f"  📊 Processing {json_file.stem}...")
        stats = extract_app_stats(str(json_file))
        
        if stats:
            all_stats.append(stats)
            print(f"    ✓ {stats['articles']} articles analyzed")
    
    # Display results
    print(f"\n{'='*100}")
    print(f"  STATISTICS SUMMARY")
    print(f"{'='*100}\n")
    
    for stats in all_stats:
        app_name = stats["app"].upper()
        articles = stats["articles"]
        
        print(f"\n  📱 {app_name}")
        print(f"  {'-'*96}")
        print(f"    Articles: {articles}\n")
        
        # Sections per article
        print(f"    Sections per Article:")
        s = stats["sections_per_article"]
        print(f"      min={s['min']:<5} q1={s['q1']:<5} q2={s['q2']:<5} q3={s['q3']:<5} max={s['max']:<5} mean={s['mean']:<5} (n={s['count']})")
        
        # Tokens per section
        print(f"\n    Tokens per Section:")
        s = stats["tokens_per_section"]
        print(f"      min={s['min']:<5} q1={s['q1']:<5} q2={s['q2']:<5} q3={s['q3']:<5} max={s['max']:<5} mean={s['mean']:<5} (n={s['count']})")
        
        # Tokens in titles
        print(f"\n    Tokens in Titles:")
        s = stats["tokens_in_titles"]
        print(f"      min={s['min']:<5} q1={s['q1']:<5} q2={s['q2']:<5} q3={s['q3']:<5} max={s['max']:<5} mean={s['mean']:<5} (n={s['count']})")
        
        # Tokens in symptoms
        print(f"\n    Tokens in Symptoms:")
        s = stats["tokens_in_symptoms"]
        print(f"      min={s['min']:<5} q1={s['q1']:<5} q2={s['q2']:<5} q3={s['q3']:<5} max={s['max']:<5} mean={s['mean']:<5} (n={s['count']})")
        
        # Tokens in titles + symptoms
        print(f"\n    Tokens in Titles + Symptoms:")
        s = stats["tokens_titles_symptoms"]
        print(f"      min={s['min']:<5} q1={s['q1']:<5} q2={s['q2']:<5} q3={s['q3']:<5} max={s['max']:<5} mean={s['mean']:<5} (n={s['count']})")
        
        # Tokens in non-title/symptom sections
        print(f"\n    Tokens in Non-Title/Symptom Sections:")
        s = stats["tokens_non_title_symptom"]
        print(f"      min={s['min']:<5} q1={s['q1']:<5} q2={s['q2']:<5} q3={s['q3']:<5} max={s['max']:<5} mean={s['mean']:<5} (n={s['count']})")
    
    # Save detailed stats to JSON
    output_file = "stats/statistics.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*100}")
    print(f"  ✓ Detailed statistics saved to {output_file}")
    print(f"{'='*100}\n")


if __name__ == "__main__":
    main()