#!/usr/bin/env python3
import argparse
import yaml
import sys
import os
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Retrieval Experiment Runner")
    parser.add_argument("--phase", choices=["build", "evaluate", "all"], required=True)
    parser.add_argument("--config", type=str, default="config.yaml")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    sys.path.insert(0, str(base_dir))

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Ensure directories exist
    os.makedirs(cfg["paths"]["apps_dir"], exist_ok=True)
    os.makedirs(cfg["paths"]["results_dir"], exist_ok=True)
    
    # Create DB directory for local DBs (Qdrant), skip for URIs (Milvus)
    db_path = cfg["database"]["path"]
    if not db_path.startswith("http"):
        os.makedirs(db_path, exist_ok=True)

    phases = ["build", "evaluate"] if args.phase == "all" else [args.phase]

    for phase in phases:
        print(f"\n{'='*60}")
        print(f"🚀 PHASE: {phase.upper()}")
        print(f"{'='*60}")

        if phase == "build":
            from src.builder import run_build
            run_build(cfg)
        elif phase == "evaluate":
            from src.evaluator import run_evaluate
            run_evaluate(cfg)

        print(f"✅ Phase '{phase}' complete.\n")

if __name__ == "__main__":
    main()