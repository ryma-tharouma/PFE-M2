import os
import json
import random
from sklearn.model_selection import train_test_split  # optionnel, vous pouvez aussi utiliser random.shuffle


INPUT_DIR = "data/converted"
OUTPUT_TRAIN_DIR = "data/train"
OUTPUT_TEST_DIR = "data/test"
TEST_SIZE = 0.2  
RANDOM_SEED = 42  


os.makedirs(OUTPUT_TRAIN_DIR, exist_ok=True)
os.makedirs(OUTPUT_TEST_DIR, exist_ok=True)


for filename in os.listdir(INPUT_DIR):
    if not filename.endswith(".json"):
        continue

    input_path = os.path.join(INPUT_DIR, filename)
    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    
    if isinstance(data, dict):
        data = [data]
    elif not isinstance(data, list):
        print(f"Format inattendu dans {filename} : {type(data)}. Ignoré.")
        continue


    if len(data) == 0:
        print(f"{filename} est vide. Rien à diviser.")
        continue

  
    train_data, test_data = train_test_split(
        data, test_size=TEST_SIZE, random_state=RANDOM_SEED
    )


    train_path = os.path.join(OUTPUT_TRAIN_DIR, filename)
    test_path = os.path.join(OUTPUT_TEST_DIR, filename)

    with open(train_path, "w", encoding="utf-8") as f:
        json.dump(train_data, f, indent=2, ensure_ascii=False)
    with open(test_path, "w", encoding="utf-8") as f:
        json.dump(test_data, f, indent=2, ensure_ascii=False)

    print(f"{filename} : {len(train_data)} train, {len(test_data)} test")

print("Division terminée.")