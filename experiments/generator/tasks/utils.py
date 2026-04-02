import csv
import json
import re
from pathlib import Path
from typing import Iterable

from tqdm import tqdm


def read_configs(path: Path):
    """Read configs.jsonl (one JSON per line)."""
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def read_csv_inputs(path: Path):
    """Read CSV inputs and yield dict rows."""
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            yield row


def read_json_inputs(path: Path, key: str | None = None):
    """Read JSON inputs. If key is provided, iterate data[key], else data itself."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if key is not None:
        data = data[key]
    for item in data:
        yield item


def safe_name(s: str) -> str:
    """Make string safe for filenames."""
    return re.sub(r"[^a-zA-Z0-9._-]", "_", s)


def make_output_path(out_dir: Path, cfg: dict):
    """Build output filename using model_name, prompt_file, config_id."""
    fname = f"{safe_name(cfg['model_name'])}__{safe_name(cfg['prompt_file'])}__{safe_name(cfg['config_id'])}.csv"
    return out_dir / fname


def progress_configs(configs: Iterable[dict]):
    """Progress bar for configs."""
    return tqdm(list(configs), desc="Configs", unit="cfg")


def progress_rows(rows: Iterable[dict], cfg_id: str):
    """Progress bar for rows under a config."""
    return tqdm(rows, desc=f"Rows ({cfg_id})", unit="row", leave=False)