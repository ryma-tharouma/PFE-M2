# run.py
import argparse
import yaml
import os
import sys
from pathlib import Path

def load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def ensure_dirs(cfg: dict):
    exp_name = cfg.get("experiment", {}).get("name", "default")
    results_dir = cfg.get("experiment", {}).get("results_dir", "data/results/")
    
    # Resolve {experiment_name} placeholder
    if "{experiment_name}" in results_dir:
        results_dir = results_dir.format(experiment_name=exp_name)
        cfg["experiment"]["results_dir"] = results_dir
    os.makedirs(results_dir, exist_ok=True)
    cfg["paths"]["resolved_results"] = results_dir  # Easy access for modules

    # Vector DB directory (skip if URI like http://...)
    db_path = cfg.get("database", {}).get("path", "")
    if db_path and not str(db_path).startswith("http"):
        os.makedirs(db_path, exist_ok=True)

    # Ensure input directories exist
    for key in ["apps_dir", "conversations_dir"]:
        if key in cfg.get("paths", {}):
            os.makedirs(cfg["paths"][key], exist_ok=True)

def main():
    parser = argparse.ArgumentParser(description="Config-Driven Retrieval Evaluator")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config file")
    parser.add_argument("--phase", type=str, choices=["build", "evaluate", "all"], required=True,
                        help="Phase to run: build, evaluate, or both")
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)

    phases = ["build", "evaluate"] if args.phase == "all" else [args.phase]

    for phase in phases:
        print(f"\n{'='*60}\n🚀 PHASE: {phase.upper()}\n{'='*60}")
        
        if phase == "build":
            from src.builder import run_build
            run_build(cfg)
        elif phase == "evaluate":
            from src.evaluator import run_evaluate
            run_evaluate(cfg)
            
        print(f"\n✅ Phase '{phase}' complete.\n")

if __name__ == "__main__":
    main()