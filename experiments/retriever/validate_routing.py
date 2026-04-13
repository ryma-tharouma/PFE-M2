# validate_routing.py
import json
from src.routing_validator import run_routing_validation

# 1. Load thresholds learned from Dev set
with open("data/results/phase_A1_base/summary_results.json", "r", encoding="utf-8") as f:
    thresholds = json.load(f)["optimized_thresholds"]

# 2. Run validation on a specific config's test results
# (Change mode/aggregation to match the CSV you want to validate)
run_routing_validation(
    detailed_csv_path="data/results/phase_A1_base/qdrant_dense_flat_max_none_detailed.csv",
    ground_truth_path="data/conversations/test_turns.jsonl",
    thresholds=thresholds,
    output_dir="data/results/phase_A1_base/"
)