import subprocess
import time

def run(cmd, cwd):
    print(f"\n[RUNNING] {cmd} (in {cwd})\n")
    subprocess.run(cmd, cwd=cwd, shell=True, check=True)

GENERATOR_DIR = r"C:\Users\T14s\Desktop\PFE\PFE-Project\experiments\generator"
RETRIEVER_DIR = r"C:\Users\T14s\Desktop\PFE\PFE-Project\experiments\retriever"

GENERATOR_CMD = (
    "python run_generation.py "
    "--config configs.yaml "
    "--turns data/resolved_convos/original_convos_level2.jsonl "
    "--output-dir outputs/"
)

RETRIEVER_CMD = "python run.py --phase evaluate"

# 1. Run generator
print("Starting generator...")
run(GENERATOR_CMD, GENERATOR_DIR)

# 2. Wait 5 minutes
print("Generator finished. Waiting 5 minutes before starting retriever...")
time.sleep(300)  # 300 seconds = 5 minutes

# 3. Run retriever
print("Starting retriever...")
run(RETRIEVER_CMD, RETRIEVER_DIR)

print("All done.")