import csv
import json
import argparse
import re
from pathlib import Path
from generator import Generator, GenParams, Sample

def read_configs(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)

def read_inputs(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            yield row

def safe_name(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]", "_", s)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", required=True, help="CSV with id,history,context,query")
    ap.add_argument("--configs", required=True, help="configs.jsonl")
    ap.add_argument("--output", required=True, help="output folder")
    ap.add_argument("--batch-size", type=int, default=None, help="number of rows to process")
    ap.add_argument("--start", type=int, default=0, help="row offset")
    args = ap.parse_args()

    inputs = list(read_inputs(Path(args.inputs)))
    if args.start:
        inputs = inputs[args.start:]
    if args.batch_size:
        inputs = inputs[: args.batch_size]

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    for cfg in read_configs(Path(args.configs)):
        gen = Generator(
            model_name=cfg["model_name"],
            prompt=cfg["prompt_file"],
            **cfg.get("model_kwargs", {}),
        )
        gen_params = GenParams(**cfg.get("gen_params", {}))

        fname = f"{safe_name(cfg['model_name'])}__{safe_name(cfg['prompt_file'])}__{safe_name(cfg['config_id'])}.csv"
        output_path = out_dir / fname
        write_header = not output_path.exists()

        with output_path.open("a", encoding="utf-8", newline="") as out_f:
            writer = csv.DictWriter(
                out_f,
                fieldnames=["input_id", "response", "ttft_ms", "total_ms"],
            )
            if write_header:
                writer.writeheader()

            for row in inputs:
                query = (row.get("query") or "").strip()
                if not query:
                    continue

                sample = Sample(
                    query=query,
                    history=row.get("history", "") or "",
                    context=row.get("context", "") or "",
                )
                response, ttft, total = gen.generate_one(sample, gen_params)

                writer.writerow({
                    "input_id": row["id"],
                    "response": response,
                    "ttft_ms": round(ttft, 5),
                    "total_ms": round(total, 5),
                })

if __name__ == "__main__":
    main()