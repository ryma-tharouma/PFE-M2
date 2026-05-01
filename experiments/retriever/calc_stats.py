import json
from collections import defaultdict, Counter

def analyze_jsonl(filename):
    """
    Analyze JSONL file with conversation data to compute various statistics.
    """
    stats = {
        'total_conversations': 0,
        'total_turns': 0,
        'turns_per_conversation': [],
        'routing_labels': Counter(),
        'query_quality': Counter(),
        'follow_up': Counter(),
        'app_id': Counter()
    }
    
    with open(filename, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                conv = json.loads(line)
                stats['total_conversations'] += 1
                app_id = conv.get('app_id', 'unknown')
                stats['app_id'][app_id] += 1
                
                turns = conv.get('turns', [])
                num_turns = len(turns)
                stats['total_turns'] += num_turns
                stats['turns_per_conversation'].append(num_turns)
                
                for turn in turns:
                    # Routing label (rag/faq/ood)
                    routing = turn.get('routing_label', 'unknown')
                    stats['routing_labels'][routing] += 1
                    
                    # Query quality
                    quality = turn.get('query_quality', 'unknown')
                    stats['query_quality'][quality] += 1
                    
                    # Follow-up
                    is_followup = turn.get('isfollow_up', False)
                    stats['follow_up'][is_followup] += 1
    
    return stats

def compute_derived_stats(stats):
    """
    Compute derived statistics (percentages, averages, etc.)
    """
    derived = {}
    
    # Basic stats
    derived['total_conversations'] = stats['total_conversations']
    derived['total_turns'] = stats['total_turns']
    
    # Turns per conversation stats
    if stats['turns_per_conversation']:
        derived['avg_turns_per_conversation'] = sum(stats['turns_per_conversation']) / len(stats['turns_per_conversation'])
        derived['min_turns_per_conversation'] = min(stats['turns_per_conversation'])
        derived['max_turns_per_conversation'] = max(stats['turns_per_conversation'])
        derived['turns_distribution'] = dict(Counter(stats['turns_per_conversation']))
    else:
        derived['avg_turns_per_conversation'] = 0
        derived['min_turns_per_conversation'] = 0
        derived['max_turns_per_conversation'] = 0
        derived['turns_distribution'] = {}
    
    # Routing labels with percentages
    total_labels = sum(stats['routing_labels'].values())
    derived['routing_labels'] = {}
    for label, count in stats['routing_labels'].items():
        derived['routing_labels'][label] = {
            'count': count,
            'percentage': round((count / total_labels) * 100, 2) if total_labels > 0 else 0
        }
    
    # Query quality with percentages
    total_queries = sum(stats['query_quality'].values())
    derived['query_quality'] = {}
    for quality, count in stats['query_quality'].items():
        derived['query_quality'][quality] = {
            'count': count,
            'percentage': round((count / total_queries) * 100, 2) if total_queries > 0 else 0
        }
    
    # Follow-up stats
    total_followup = stats['follow_up'][True] + stats['follow_up'][False]
    derived['follow_up'] = {
        'follow_up_queries': {
            'count': stats['follow_up'][True],
            'percentage': round((stats['follow_up'][True] / total_followup) * 100, 2) if total_followup > 0 else 0
        },
        'new_queries': {
            'count': stats['follow_up'][False],
            'percentage': round((stats['follow_up'][False] / total_followup) * 100, 2) if total_followup > 0 else 0
        }
    }
    
    # App distribution
    derived['app_distribution'] = {}
    for app_id, count in stats['app_id'].items():
        derived['app_distribution'][app_id] = {
            'count': count,
            'percentage': round((count / stats['total_conversations']) * 100, 2) if stats['total_conversations'] > 0 else 0
        }
    
    return derived

def save_results_to_json(stats, derived_stats, output_filename='analysis_results.json'):
    """
    Save all statistics to a JSON file.
    """
    results = {
        'summary': {
            'total_conversations': stats['total_conversations'],
            'total_turns': stats['total_turns'],
            'avg_turns_per_conversation': derived_stats['avg_turns_per_conversation'],
            'min_turns_per_conversation': derived_stats['min_turns_per_conversation'],
            'max_turns_per_conversation': derived_stats['max_turns_per_conversation']
        },
        'turns_distribution': derived_stats['turns_distribution'],
        'routing_labels': derived_stats['routing_labels'],
        'query_quality': derived_stats['query_quality'],
        'follow_up_analysis': derived_stats['follow_up'],
        'app_distribution': derived_stats['app_distribution'],
        'raw_counts': {
            'routing_labels_raw': dict(stats['routing_labels']),
            'query_quality_raw': dict(stats['query_quality']),
            'follow_up_raw': dict(stats['follow_up']),
            'app_id_raw': dict(stats['app_id']),
            'turns_per_conversation_raw': stats['turns_per_conversation']
        }
    }
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ Results saved to {output_filename}")
    return results

def print_stats(stats, derived_stats):
    """
    Print formatted statistics to console.
    """
    print("=" * 60)
    print("EXCEL/OUTLOOK CONVERSATION ANALYSIS")
    print("=" * 60)
    
    # Basic conversation stats
    print(f"\n📊 BASIC STATISTICS:")
    print(f"   Total conversations: {stats['total_conversations']}")
    print(f"   Total turns: {stats['total_turns']}")
    print(f"   Average turns per conversation: {derived_stats['avg_turns_per_conversation']:.2f}")
    print(f"   Min turns: {derived_stats['min_turns_per_conversation']}")
    print(f"   Max turns: {derived_stats['max_turns_per_conversation']}")
    
    # Distribution of turns per conversation
    print(f"\n📈 TURNS DISTRIBUTION:")
    for turns, count in sorted(derived_stats['turns_distribution'].items()):
        print(f"   {turns} turn(s): {count} conversation(s)")
    
    # Routing labels (RAG/FAQ/OOD/etc)
    print(f"\n🏷️  ROUTING LABELS:")
    for label, data in sorted(derived_stats['routing_labels'].items(), key=lambda x: x[1]['count'], reverse=True):
        print(f"   {label}: {data['count']} ({data['percentage']}%)")
    
    # Query quality
    print(f"\n⭐ QUERY QUALITY:")
    for quality, data in sorted(derived_stats['query_quality'].items(), key=lambda x: x[1]['count'], reverse=True):
        print(f"   {quality}: {data['count']} ({data['percentage']}%)")
    
    # Follow-up vs new queries
    print(f"\n🔄 FOLLOW-UP QUERIES:")
    print(f"   Follow-up queries: {derived_stats['follow_up']['follow_up_queries']['count']} ({derived_stats['follow_up']['follow_up_queries']['percentage']}%)")
    print(f"   New queries: {derived_stats['follow_up']['new_queries']['count']} ({derived_stats['follow_up']['new_queries']['percentage']}%)")
    
    # By app
    print(f"\n📱 BY APPLICATION:")
    for app_id, data in sorted(derived_stats['app_distribution'].items(), key=lambda x: x[1]['count'], reverse=True):
        print(f"   {app_id}: {data['count']} conversations ({data['percentage']}%)")
    
    print("\n" + "=" * 60)

# Main execution
if __name__ == "__main__":
    # Replace with your actual file path
    filename = "data/conversations/original_convos_level3.jsonl"
    output_json = "data/stats/analysis_results_l3.json"
    
    try:
        # Analyze the JSONL file
        stats = analyze_jsonl(filename)
        
        # Compute derived statistics
        derived_stats = compute_derived_stats(stats)
        
        # Print to console
        print_stats(stats, derived_stats)
        
        # Save to JSON file
        save_results_to_json(stats, derived_stats, output_json)
        
        print(f"\n📁 Full analysis saved to: {output_json}")
        
    except FileNotFoundError:
        print(f"❌ Error: File '{filename}' not found!")
        print("Please make sure the file exists in the current directory or provide the full path.")
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing JSON: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")