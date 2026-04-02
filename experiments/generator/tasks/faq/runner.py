import csv
import json
import argparse
import sys
from pathlib import Path

# add experiments/generator and tasks to sys.path
BASE_DIR = Path(__file__).resolve().parents[2]  # .../experiments/generator
TASKS_DIR = BASE_DIR / "tasks"
sys.path.extend([str(BASE_DIR), str(TASKS_DIR)])

from generator import Generator, GenParams, Sample  # noqa: E402
from utils import (
    read_configs,
    progress_configs,
    progress_rows,
)  # noqa: E402


def read_jsonl_inputs(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="tasks/faq/data/inputs.jsonl")
    ap.add_argument("--configs", default="tasks/faq/configs.jsonl")
    ap.add_argument("--output", default="tasks/faq/data/output.csv")
    ap.add_argument("--batch-size", type=int, default=None, help="number of rows to process")
    ap.add_argument("--start", type=int, default=0, help="row offset")
    args = ap.parse_args()

    inputs = list(read_jsonl_inputs(Path(args.inputs)))
    if args.start:
        inputs = inputs[args.start:]
    if args.batch_size:
        inputs = inputs[: args.batch_size]

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not output_path.exists()

    prompt_dir = Path(__file__).parent / "prompts"

    with output_path.open("a", encoding="utf-8", newline="") as out_f:
        writer = csv.DictWriter(
            out_f,
            fieldnames=[
                "input_id",
                "question",
                "total_ms",
                "config_id",
                "model_name",
                "prompt_file",
            ],
        )
        if write_header:
            writer.writeheader()

        for cfg in progress_configs(read_configs(Path(args.configs))):
            gen = Generator(
                model_name=cfg["model_name"],
                prompt=cfg["prompt_file"],
                prompt_dir=prompt_dir,
                **cfg.get("model_kwargs", {}),
            )
            gen_params = GenParams(**cfg.get("gen_params", {}))

            for row in progress_rows(inputs, cfg["config_id"]):
                title = (row.get("title") or "").strip()
                breadcrumb = (row.get("breadcrumb") or "").strip()
                content = (row.get("content") or "").strip()
                if not content and not title:
                    continue

                context = f"Breadcrumb: {breadcrumb}\nContent: {content}".strip()
                sample = Sample(
                    query=title,
                    history="",
                    context=context,
                )
                response, _ttft, total = gen.generate_one(sample, gen_params, stream=False)

                writer.writerow({
                    "input_id": row["id"],
                    "question": response,
                    "total_ms": round(total, 5),
                    "config_id": cfg["config_id"],
                    "model_name": cfg["model_name"],
                    "prompt_file": cfg["prompt_file"],
                })


if __name__ == "__main__":
    main()