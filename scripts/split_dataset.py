import json
import os
import random
from collections import defaultdict

# this file is extra for the week 3 dataset split
# it divides the labeled remarks into stratified dev and test sets

# ============================================================
# ------------------Config------------------------------------
# ============================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LABELED_DIR = os.path.join(PROJECT_ROOT, "data", "labeled")
ALL_PATH = os.path.join(LABELED_DIR, "entities_all.jsonl")
DEV_PATH = os.path.join(LABELED_DIR, "entities_dev.jsonl")
TEST_PATH = os.path.join(LABELED_DIR, "entities_test.jsonl")

# 30 percent test gives 75 of 250 remarks
TEST_FRACTION = 0.3

# fixed seed so the split is identical on every run
SEED = 42

# ============================================================
# ------------------Loading and saving------------------------
# ============================================================

# read one labeled record per line
def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]

# write records one per line so the files stay easy to append and diff
def save_jsonl(records, path):
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

# ============================================================
# ------------------Splitting---------------------------------
# ============================================================

# split each sampling group separately so price, numeric, and other remarks appear in both sets
def stratified_split(records, test_fraction=TEST_FRACTION, seed=SEED):
    by_group = defaultdict(list)
    for record in records:
        by_group[record["group"]].append(record)

    rng = random.Random(seed)
    dev, test = [], []

    # sorted keys keep the shuffle order independent of file order
    for group in sorted(by_group):
        items = sorted(by_group[group], key=lambda r: r["listing_id"])
        rng.shuffle(items)
        n_test = round(len(items) * test_fraction)
        test.extend(items[:n_test])
        dev.extend(items[n_test:])
    return dev, test

# create the dev and test files and print their composition
def main():
    records = load_jsonl(ALL_PATH)
    dev, test = stratified_split(records)

    save_jsonl(dev, DEV_PATH)
    save_jsonl(test, TEST_PATH)

    for name, subset in [("dev", dev), ("test", test)]:
        groups = defaultdict(int)
        labels = defaultdict(int)
        for record in subset:
            groups[record["group"]] += 1
            for entity in record["entities"]:
                labels[entity["label"]] += 1
        print(f"{name}: {len(subset)} remarks | groups {dict(groups)} | entities {dict(labels)}")


if __name__ == "__main__":
    main()