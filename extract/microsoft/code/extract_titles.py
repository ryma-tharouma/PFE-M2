#!/usr/bin/env python3
"""Extract article_id and title from a Microsoft Learn JSON dump."""

import json
import sys
from pathlib import Path

def extract_ids_and_titles(input_path: str, output_path: str) -> None:
    try:
        # Load input JSON
        with open(input_path, "r", encoding="utf-8") as f:
            articles = json.load(f)

        if not isinstance(articles, list):
            print("⚠️ Warning: Expected a JSON array at the root. Wrapping in a list.")
            articles = [articles]

        # Extract only the fields you need
        extracted = [
            {
                "article_id": article.get("article_id"),
                "title": article.get("title")
            }
            for article in articles
        ]

        # Save to new JSON file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(extracted, f, ensure_ascii=False, indent=2)

        print(f"✅ Successfully extracted {len(extracted)} entries → '{output_path}'")

    except FileNotFoundError:
        print(f"❌ Error: Input file '{input_path}' not found.")
    except json.JSONDecodeError as e:
        print(f"❌ Error: Invalid JSON in '{input_path}': {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")

if __name__ == "__main__":
    # Default paths (edit these or pass via CLI)
    DEFAULT_INPUT = "data/scraped/mot.json"
    DEFAULT_OUTPUT = "data/titles/mot.json"

    if len(sys.argv) == 3:
        inp, out = sys.argv[1], sys.argv[2]
    elif len(sys.argv) == 2:
        inp, out = sys.argv[1], DEFAULT_OUTPUT
    else:
        inp, out = DEFAULT_INPUT, DEFAULT_OUTPUT

    extract_ids_and_titles(inp, out)