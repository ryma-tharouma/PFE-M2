# run.py
import argparse
import yaml
import os
import sys
from pathlib import Path

def load_config(config_path: str) -> dict:
    """Loads YAML config with error handling."""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Error: Config file not found at {config_path}")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ Error: Invalid YAML in {config_path}: {e}")
        sys.exit(1)

def ensure_dirs(cfg: dict):
    """Ensures all required directories exist."""
    exp_name = cfg.get("experiment", {}).get("name", "default")
    results_dir = cfg.get("experiment", {}).get("results_dir", "data/results/")
    
    # Resolve {experiment_name} placeholder
    if "{experiment_name}" in results_dir:
        results_dir = results_dir.format(experiment_name=exp_name)
        cfg["experiment"]["results_dir"] = results_dir
    os.makedirs(results_dir, exist_ok=True)
    cfg["paths"]["resolved_results"] = results_dir

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
    
    #  Routing Workflow Flags
    parser.add_argument("--eval-path", type=str, default=None,
                        help="Override query source path (e.g., data/conversations/test_turns.jsonl)")
    parser.add_argument("--no-auto-optimize", action="store_true",
                        help="Disable threshold auto-optimization (useful for validation runs)")
    
    args = parser.parse_args()

    cfg = load_config(args.config)
    ensure_dirs(cfg)

    # Apply CLI Overrides
    if args.eval_path:
        print(f" Overriding query source with: {args.eval_path}")
        if "evaluation" not in cfg: cfg["evaluation"] = {}
        if "query_sources" not in cfg["evaluation"] or not cfg["evaluation"]["query_sources"]:
            cfg["evaluation"]["query_sources"] = [{"name": "cli_override", "path": args.eval_path}]
        else:
            cfg["evaluation"]["query_sources"][0]["path"] = args.eval_path

    if args.no_auto_optimize:
        print(" Disabling threshold auto-optimization (--no-auto-optimize)")
        cfg["routing"]["auto_optimize"] = False

    phases = ["build", "evaluate"] if args.phase == "all" else [args.phase]

    for phase in phases:
        print(f"\n{'='*60}\n PHASE: {phase.upper()}\n{'='*60}")
        
        if phase == "build":
            from src.builder import run_build
            run_build(cfg)
        elif phase == "evaluate":
            from src.evaluator import run_evaluate
            run_evaluate(cfg)
            
        print(f"\n Phase '{phase}' complete.\n")

if __name__ == "__main__":
    main()