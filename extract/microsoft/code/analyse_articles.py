import json
import os
from collections import defaultdict
from pathlib import Path


def analyze_json_file(file_path):
    """Analyze a single JSON file and extract header statistics"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None
    
    if not isinstance(data, list):
        return None
    
    total_articles = len(data)
    
    # Track header combinations
    header_combinations = defaultdict(int)
    articles_with_resolution = 0
    
    # Resolution-related keywords
    resolution_keywords = {"résolution", "contournement", "résolution rapide", "workaround", "solution"}
    
    for article in data:
        if not isinstance(article, dict):
            continue
        
        sections = article.get("sections", [])
        if not sections:
            continue
        
        # Extract headers from this article
        headers = tuple(sorted(set(
            sec.get("header", "").lower().strip() 
            for sec in sections 
            if sec.get("header")
        )))
        
        if headers:
            header_combinations[headers] += 1
        
        # Check if article has resolution-related section
        has_resolution = any(
            any(keyword in sec.get("header", "").lower() for keyword in resolution_keywords)
            for sec in sections
        )
        if has_resolution:
            articles_with_resolution += 1
    
    return {
        "total_articles": total_articles,
        "articles_with_resolution": articles_with_resolution,
        "header_combinations": dict(header_combinations)
    }


def main():
    scraped_dir = Path("data/scraped")
    
    if not scraped_dir.exists():
        print(f"Directory {scraped_dir} not found!")
        return
    
    json_files = sorted(scraped_dir.glob("*.json"))
    
    if not json_files:
        print(f"No JSON files found in {scraped_dir}")
        return
    
    # Create output directory
    os.makedirs("analysis", exist_ok=True)
    output_file = Path("analysis/articles_analysis.txt")
    
    all_stats = {}
    
    with open(output_file, "w", encoding="utf-8") as f:
        f.write(f"\n{'='*80}\n")
        f.write(f"  ARTICLE ANALYSIS REPORT\n")
        f.write(f"{'='*80}\n\n")
        
        for file_path in json_files:
            file_name = file_path.stem
            
            stats = analyze_json_file(file_path)
            if stats is None:
                f.write(f"{file_name.upper()}\n")
                f.write(f"{'-'*80}\n")
                f.write(f"  ✗ Could not parse file\n\n")
                continue
            
            all_stats[file_name] = stats
            
            total = stats["total_articles"]
            with_resolution = stats["articles_with_resolution"]
            
            f.write(f"{file_name.upper()}\n")
            f.write(f"{'-'*80}\n")
            f.write(f"  📊 Total articles: {total}\n")
            f.write(f"  ✓ Articles with Resolution/Contournement/Résolution rapide: {with_resolution} ({with_resolution/total*100:.1f}%)\n\n")
            
            f.write(f"  Section Header Combinations (count):\n")
            combinations = stats["header_combinations"]
            
            # Sort by count (descending)
            sorted_combos = sorted(combinations.items(), key=lambda x: x[1], reverse=True)
            
            for headers, count in sorted_combos:
                f.write(f"    [{count:3d}x] {' → '.join(headers)}\n")
            
            f.write("\n")
        
        # Summary
        f.write(f"{'='*80}\n")
        f.write(f"  SUMMARY\n")
        f.write(f"{'='*80}\n\n")
        
        total_all_articles = sum(s["total_articles"] for s in all_stats.values())
        total_all_resolution = sum(s["articles_with_resolution"] for s in all_stats.values())
        
        f.write(f"{'Category':<20} {'Articles':<15} {'With Resolution':<20} {'Percentage':<15}\n")
        f.write(f"{'-'*70}\n")
        
        for file_name in sorted(all_stats.keys()):
            stats = all_stats[file_name]
            total = stats["total_articles"]
            with_res = stats["articles_with_resolution"]
            pct = (with_res / total * 100) if total > 0 else 0
            
            f.write(f"{file_name:<20} {total:<15} {with_res:<20} {pct:>6.1f}%\n")
        
        f.write(f"{'-'*70}\n")
        pct_all = (total_all_resolution / total_all_articles * 100) if total_all_articles > 0 else 0
        f.write(f"{'TOTAL':<20} {total_all_articles:<15} {total_all_resolution:<20} {pct_all:>6.1f}%\n")
        f.write(f"\n{'='*80}\n\n")
    
    # Also print to console
    with open(output_file, "r", encoding="utf-8") as f:
        content = f.read()
        print(content)
    
    print(f"✓ Analysis saved to: {output_file}")


if __name__ == "__main__":
    main()