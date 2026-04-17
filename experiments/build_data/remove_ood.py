import json

input_file = "data/conversations/conv_manuels_level2.jsonl"
output_file = "data/filtered_conv_manuels_level2.jsonl"

with open(input_file, "r", encoding="utf-8") as fin, \
     open(output_file, "w", encoding="utf-8") as fout:

    for i, line in enumerate(fin, start=1):
        raw_line = line  # keep original for debugging
        line = line.strip()

        # Skip empty lines but report them
        if not line:
            print(f"[Line {i}] ⚠️ Empty line")
            continue

        try:
            conv = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"\n❌ JSON Error at line {i}")
            print(f"   → Error: {e}")
            print(f"   → Content: {repr(raw_line[:200])}")  # limit length
            continue

        # Extra safety: check structure
        if "turns" not in conv:
            print(f"\n❌ Missing 'turns' at line {i}")
            print(f"   → Content: {repr(raw_line[:200])}")
            continue

        # Remove OOD turns
        filtered_turns = [
            turn for turn in conv["turns"]
            if turn.get("routing_label") != "ood"
        ]

        # Skip conversations with no remaining turns
        if not filtered_turns:
            continue

        conv["turns"] = filtered_turns

        # Write back as JSONL
        fout.write(json.dumps(conv, ensure_ascii=False) + "\n")

print("Done ✅")