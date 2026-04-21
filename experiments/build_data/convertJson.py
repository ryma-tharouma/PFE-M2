import json
import sys
from pathlib import Path

def jsonl_to_json(jsonl_path: str, json_path: str) -> None:
    """
    Convert a JSONL file (one JSON object per line) to a JSON array.

    Args:
        jsonl_path: Path to the input JSONL file.
        json_path: Path to the output JSON file.
    """
    data = []
    with open(jsonl_path, 'r', encoding='utf-8') as infile:
        for line_num, line in enumerate(infile, 1):
            line = line.strip()
            if not line:  # skip empty lines
                continue
            try:
                obj = json.loads(line)
                data.append(obj)
            except json.JSONDecodeError as e:
                print(f"Error parsing line {line_num}: {e}", file=sys.stderr)
                sys.exit(1)
    with open(json_path, 'w', encoding='utf-8') as outfile:
        json.dump(data, outfile, indent=2, ensure_ascii=False)
    print(f"Converted {jsonl_path} -> {json_path} ({len(data)} objects)")

def json_to_jsonl(json_path: str, jsonl_path: str) -> None:
    """
    Convert a JSON array file to JSONL (one JSON object per line).

    Args:
        json_path: Path to the input JSON file (must contain a top-level array).
        jsonl_path: Path to the output JSONL file.
    """
    with open(json_path, 'r', encoding='utf-8') as infile:
        try:
            data = json.load(infile)
        except json.JSONDecodeError as e:
            print(f"Error parsing JSON file: {e}", file=sys.stderr)
            sys.exit(1)

    if not isinstance(data, list):
        print("Error: Input JSON must contain a top-level array.", file=sys.stderr)
        sys.exit(1)

    with open(jsonl_path, 'w', encoding='utf-8') as outfile:
        for obj in data:
            outfile.write(json.dumps(obj, ensure_ascii=False) + '\n')
    print(f"Converted {json_path} -> {jsonl_path} ({len(data)} objects)")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert between JSONL and JSON array formats.")
    parser.add_argument("input", help="Input file path")
    parser.add_argument("output", help="Output file path")
    parser.add_argument("--mode", choices=["tojson", "tojsonl"], required=True,
                        help="Conversion direction: 'tojson' (JSONL -> JSON) or 'tojsonl' (JSON -> JSONL)")

    args = parser.parse_args()

    if args.mode == "tojson":
        jsonl_to_json(args.input, args.output)
    else:  # tojsonl
        json_to_jsonl(args.input, args.output)