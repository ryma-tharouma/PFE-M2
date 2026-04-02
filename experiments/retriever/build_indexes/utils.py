import json
import time
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


def iter_jsonl(path: Path) -> Iterable[Dict]:
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def build_section_text(section: Dict) -> str:
    # Customize this to match your content format
    parts = []
    for key in ("title", "breadcrumb", "content"):
        val = section.get(key)
        if val:
            parts.append(str(val))
    return "\n".join(parts)


def normalize(vec: List[float]) -> List[float]:
    # L2 normalize
    norm = sum(x * x for x in vec) ** 0.5
    if norm == 0:
        return vec
    return [x / norm for x in vec]


class Timer:
    def __enter__(self):
        self.start = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.end = time.perf_counter()
        self.ms = (self.end - self.start) * 1000