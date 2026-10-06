import argparse
from collections import defaultdict

from entity_extractor import EntityExtractor
from split_dataset import DEV_PATH, TEST_PATH, load_jsonl

# this file is for week 3's evaluation
# It scores EntityExtractor against the labeled test set from the same week

# ============================================================
# ------------------Config------------------------------------
# ============================================================

# maps labels in the jsonl files to keys returned by extract_all
NUMERIC_FIELDS = {
    "BEDROOMS": "bedrooms",
    "BATHROOMS": "bathrooms",
    "PRICE": "price",
    "SQFT": "sqft",
}

# tolerance for comparing bathroom counts such as 2.5
VALUE_TOLERANCE = 1e-6

# ============================================================
# ------------------Gold labels-------------------------------
# ============================================================

# convert a labeled record into the same shape extract_all returns
# using gold as var as data will be used to train AI model down the line
def gold_from_record(record):
    gold = {field: None for field in NUMERIC_FIELDS.values()}
    amenities = set()
    for entity in record["entities"]:
        if entity["label"] == "AMENITY":
            amenities.add(entity["value"])
        elif entity["label"] in NUMERIC_FIELDS:
            gold[NUMERIC_FIELDS[entity["label"]]] = entity["value"]
    gold["amenities"] = amenities
    return gold

# ============================================================
# ------------------Scoring-----------------------------------
# ============================================================

def _values_match(gold, extracted):
    return abs(float(gold) - float(extracted)) < VALUE_TOLERANCE

# score one numeric field; a wrong value counts as both a false positive and a false negative
def score_numeric(gold, extracted):
    if gold is None and extracted is None:
        return {"tp": 0, "fp": 0, "fn": 0}, None
    if gold is None:
        return {"tp": 0, "fp": 1, "fn": 0}, "false_positive"
    if extracted is None:
        return {"tp": 0, "fp": 0, "fn": 1}, "false_negative"
    if _values_match(gold, extracted):
        return {"tp": 1, "fp": 0, "fn": 0}, None
    return {"tp": 0, "fp": 1, "fn": 1}, "wrong_value"

# score amenities as sets of taxonomy ids
def score_amenities(gold, extracted):
    extracted = set(extracted)
    counts = {
        "tp": len(gold & extracted),
        "fp": len(extracted - gold),
        "fn": len(gold - extracted),
    }
    return counts, sorted(extracted - gold), sorted(gold - extracted)

# run the extractor over every record and collect counts plus individual errors
def evaluate(records, extractor):
    totals = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0})
    errors = []

    for record in records:
        gold = gold_from_record(record)
        extracted = extractor.extract_all(record["text"])

        for field in NUMERIC_FIELDS.values():
            counts, error_type = score_numeric(gold[field], extracted[field])
            for key, value in counts.items():
                totals[field][key] += value
            if error_type:
                errors.append({
                    "listing_id": record["listing_id"],
                    "field": field,
                    "error_type": error_type,
                    "gold": gold[field],
                    "extracted": extracted[field],
                })

        counts, extra, missed = score_amenities(gold["amenities"], extracted["amenities"])
        for key, value in counts.items():
            totals["amenities"][key] += value
        for term_id in extra:
            errors.append({"listing_id": record["listing_id"], "field": "amenities",
                           "error_type": "false_positive", "gold": None, "extracted": term_id})
        for term_id in missed:
            errors.append({"listing_id": record["listing_id"], "field": "amenities",
                           "error_type": "false_negative", "gold": term_id, "extracted": None})

    return dict(totals), errors

# ============================================================
# ------------------Metrics and reporting---------------------
# ============================================================

# precision, recall, and f1 from raw counts; empty denominators return 0
def prf(counts):
    tp, fp, fn = counts["tp"], counts["fp"], counts["fn"]
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1

# print per-field scores plus a micro average weighted by entity count
def print_report(totals, split_name, n_records):
    print(f"\nentity extraction results on {split_name} ({n_records} remarks)\n")
    print(f"{'field':<12}{'support':>9}{'precision':>11}{'recall':>9}{'f1':>8}")

    micro = {"tp": 0, "fp": 0, "fn": 0}
    for field, counts in totals.items():
        p, r, f = prf(counts)

        # support is the number of gold entities, which is tp plus fn
        support = counts["tp"] + counts["fn"]
        print(f"{field:<12}{support:>9}{p:>11.3f}{r:>9.3f}{f:>8.3f}")
        for key in micro:
            micro[key] += counts[key]

    p, r, f = prf(micro)
    print(f"{'micro avg':<12}{micro['tp'] + micro['fn']:>9}{p:>11.3f}{r:>9.3f}{f:>8.3f}")

# score the extractor on the chosen split; dev is the default so the test set is not used by accident
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()

    records = load_jsonl(DEV_PATH if args.split == "dev" else TEST_PATH)
    totals, errors = evaluate(records, EntityExtractor())
    print_report(totals, args.split, len(records))


if __name__ == "__main__":
    main()