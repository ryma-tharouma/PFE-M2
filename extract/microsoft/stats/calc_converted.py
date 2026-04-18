import json
import os
from pathlib import Path
from collections import defaultdict
from transformers import AutoTokenizer

# Initialize both tokenizers
bge_tokenizer = AutoTokenizer.from_pretrained("BAAI/bge-m3")
qwen_tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen2.5-0.5B-Instruct")

# Thresholds to track
THRESHOLDS = [1000, 1500, 2000]


def count_tokens_bge(text: str) -> int:
    """Count tokens using BGE-M3 tokenizer"""
    if not text or not isinstance(text, str):
        return 0
    tokens = bge_tokenizer.encode(text)
    return len(tokens)


def count_tokens_qwen(text: str) -> int:
    """Count tokens using Qwen3-0.6B tokenizer"""
    if not text or not isinstance(text, str):
        return 0
    tokens = qwen_tokenizer.encode(text)
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
    """Extract statistics from a single converted app JSON file"""
    
    try:
        with open(json_file, 'r', encoding='utf-8') as f:
            articles = json.load(f)
    except Exception as e:
        print(f"  ✗ Error reading {json_file}: {e}")
        return None
    
    if not articles:
        print(f"  ✗ No articles found in {json_file}")
        return None
    
    # Initialize tracking lists for BGE tokenizer
    bge_problem_tokens = []
    bge_answer_tokens = []
    bge_total_tokens = []
    
    # Initialize tracking lists for Qwen tokenizer
    qwen_problem_tokens = []
    qwen_answer_tokens = []
    qwen_total_tokens = []
    
    # Counters for exceeding thresholds (total tokens)
    bge_exceed = {t: 0 for t in THRESHOLDS}
    qwen_exceed = {t: 0 for t in THRESHOLDS}
    
    article_count = 0
    
    for article in articles:
        if isinstance(article, dict) and "problem" in article and "answer" in article:
            article_count += 1
            
            problem = article.get("problem", "")
            answer = article.get("answer", "")
            
            # BGE tokenization
            bge_problem = count_tokens_bge(problem)
            bge_answer = count_tokens_bge(answer)
            bge_total = bge_problem + bge_answer
            
            bge_problem_tokens.append(bge_problem)
            bge_answer_tokens.append(bge_answer)
            bge_total_tokens.append(bge_total)
            
            # Qwen tokenization
            qwen_problem = count_tokens_qwen(problem)
            qwen_answer = count_tokens_qwen(answer)
            qwen_total = qwen_problem + qwen_answer
            
            qwen_problem_tokens.append(qwen_problem)
            qwen_answer_tokens.append(qwen_answer)
            qwen_total_tokens.append(qwen_total)
            
            # Update exceed counters
            for t in THRESHOLDS:
                if bge_total > t:
                    bge_exceed[t] += 1
                if qwen_total > t:
                    qwen_exceed[t] += 1
    
    if article_count == 0:
        print(f"  ✗ No valid articles found in {json_file}")
        return None
    
    # Calculate statistics for each metric
    stats = {
        "app": Path(json_file).stem,
        "articles": article_count,
        "bge": {
            "problem_tokens": calculate_stats(bge_problem_tokens),
            "answer_tokens": calculate_stats(bge_answer_tokens),
            "total_tokens": calculate_stats(bge_total_tokens),
            "exceed_thresholds": {str(t): c for t, c in bge_exceed.items()}
        },
        "qwen": {
            "problem_tokens": calculate_stats(qwen_problem_tokens),
            "answer_tokens": calculate_stats(qwen_answer_tokens),
            "total_tokens": calculate_stats(qwen_total_tokens),
            "exceed_thresholds": {str(t): c for t, c in qwen_exceed.items()}
        }
    }
    
    return stats


def main():
    data_dir = Path("data/rag_final")
    
    if not data_dir.exists():
        print(f"✗ Directory {data_dir} not found")
        return
    
    json_files = list(data_dir.glob("*.json"))
    
    if not json_files:
        print(f"✗ No JSON files found in {data_dir}")
        return
    
    print(f"\n{'='*120}")
    print(f"  Analyzing {len(json_files)} converted app(s) from {data_dir}")
    print(f"{'='*120}\n")
    
    all_stats = []
    
    for json_file in sorted(json_files):
        print(f"  📊 Processing {json_file.stem}...")
        stats = extract_app_stats(str(json_file))
        
        if stats:
            all_stats.append(stats)
            print(f"    ✓ {stats['articles']} articles analyzed")
    
    # Display results
    print(f"\n{'='*120}")
    print(f"  STATISTICS SUMMARY (CONVERTED DATA)")
    print(f"{'='*120}\n")
    
    for stats in all_stats:
        app_name = stats["app"].upper()
        articles = stats["articles"]
        
        print(f"\n  📱 {app_name}")
        print(f"  {'-'*116}")
        print(f"    Articles: {articles}\n")
        
        # BGE TOKENIZER STATS
        print(f"    BGE-M3 TOKENIZER")
        print(f"    {'-'*116}")
        
        # Problem tokens
        print(f"    Problem Tokens:")
        s = stats["bge"]["problem_tokens"]
        print(f"      min={s['min']:<6} q1={s['q1']:<6} q2={s['q2']:<6} q3={s['q3']:<6} max={s['max']:<6} mean={s['mean']:<6} (n={s['count']})")
        
        # Answer tokens
        print(f"\n    Answer Tokens:")
        s = stats["bge"]["answer_tokens"]
        print(f"      min={s['min']:<6} q1={s['q1']:<6} q2={s['q2']:<6} q3={s['q3']:<6} max={s['max']:<6} mean={s['mean']:<6} (n={s['count']})")
        
        # Total tokens
        print(f"\n    Total Tokens (Problem + Answer):")
        s = stats["bge"]["total_tokens"]
        print(f"      min={s['min']:<6} q1={s['q1']:<6} q2={s['q2']:<6} q3={s['q3']:<6} max={s['max']:<6} mean={s['mean']:<6} (n={s['count']})")
        
        # Exceed thresholds (BGE)
        exceed_bge = stats["bge"]["exceed_thresholds"]
        print(f"\n    Exceed thresholds (total tokens):")
        for t in THRESHOLDS:
            count = exceed_bge[str(t)]
            percent = (count / articles * 100) if articles > 0 else 0
            print(f"      > {t}: {count} articles ({percent:.1f}%)")
        
        # QWEN TOKENIZER STATS
        print(f"\n\n    QWEN3-0.6B TOKENIZER")
        print(f"    {'-'*116}")
        
        # Problem tokens
        print(f"    Problem Tokens:")
        s = stats["qwen"]["problem_tokens"]
        print(f"      min={s['min']:<6} q1={s['q1']:<6} q2={s['q2']:<6} q3={s['q3']:<6} max={s['max']:<6} mean={s['mean']:<6} (n={s['count']})")
        
        # Answer tokens
        print(f"\n    Answer Tokens:")
        s = stats["qwen"]["answer_tokens"]
        print(f"      min={s['min']:<6} q1={s['q1']:<6} q2={s['q2']:<6} q3={s['q3']:<6} max={s['max']:<6} mean={s['mean']:<6} (n={s['count']})")
        
        # Total tokens
        print(f"\n    Total Tokens (Problem + Answer):")
        s = stats["qwen"]["total_tokens"]
        print(f"      min={s['min']:<6} q1={s['q1']:<6} q2={s['q2']:<6} q3={s['q3']:<6} max={s['max']:<6} mean={s['mean']:<6} (n={s['count']})")
        
        # Exceed thresholds (Qwen)
        exceed_qwen = stats["qwen"]["exceed_thresholds"]
        print(f"\n    Exceed thresholds (total tokens):")
        for t in THRESHOLDS:
            count = exceed_qwen[str(t)]
            percent = (count / articles * 100) if articles > 0 else 0
            print(f"      > {t}: {count} articles ({percent:.1f}%)")
        
        # COMPARISON
        print(f"\n\n    TOKENIZER COMPARISON (BGE vs Qwen3-0.6B)")
        print(f"    {'-'*116}")
        
        # Problem tokens comparison
        bge_problem = stats["bge"]["problem_tokens"]["mean"]
        qwen_problem = stats["qwen"]["problem_tokens"]["mean"]
        ratio_problem = (qwen_problem / bge_problem * 100) if bge_problem > 0 else 0
        print(f"    Problem Tokens (mean):")
        print(f"      BGE={bge_problem:<6} Qwen={qwen_problem:<6} Ratio (Qwen/BGE)={ratio_problem:.1f}%")
        
        # Answer tokens comparison
        bge_answer = stats["bge"]["answer_tokens"]["mean"]
        qwen_answer = stats["qwen"]["answer_tokens"]["mean"]
        ratio_answer = (qwen_answer / bge_answer * 100) if bge_answer > 0 else 0
        print(f"\n    Answer Tokens (mean):")
        print(f"      BGE={bge_answer:<6} Qwen={qwen_answer:<6} Ratio (Qwen/BGE)={ratio_answer:.1f}%")
        
        # Total tokens comparison
        bge_total = stats["bge"]["total_tokens"]["mean"]
        qwen_total = stats["qwen"]["total_tokens"]["mean"]
        ratio_total = (qwen_total / bge_total * 100) if bge_total > 0 else 0
        print(f"\n    Total Tokens (mean):")
        print(f"      BGE={bge_total:<6} Qwen={qwen_total:<6} Ratio (Qwen/BGE)={ratio_total:.1f}%")
    
    # Save detailed stats to JSON
    output_file = "stats/statistics_rag_final.json"
    os.makedirs("stats", exist_ok=True)
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_stats, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*120}")
    print(f"  ✓ Detailed statistics saved to {output_file}")
    print(f"{'='*120}\n")


if __name__ == "__main__":
    main()