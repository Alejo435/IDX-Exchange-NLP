import argparse
import csv
import os
import re
from collections import Counter, defaultdict

from entity_extractor import EntityExtractor, WORD_NUMBERS
from evaluate_extractor import NUMERIC_FIELDS, evaluate
from split_dataset import DEV_PATH, LABELED_DIR, TEST_PATH, load_jsonl

# error analysis for week 3 spec requirements
# groups extractor errors into failure patterns ranked by frequency

# ============================================================
# ------------------Config------------------------------------
# ============================================================

# characters of remark text shown on each side of an error
CONTEXT_CHARS = 60

# number of example errors printed per failure pattern
EXAMPLES_PER_PATTERN = 2

# labels in the jsonl files keyed by extract_all field name
FIELD_LABELS = {field: label for label, field in NUMERIC_FIELDS.items()}

# ============================================================
# ------------------Context helpers---------------------------
# ============================================================

# short single-line window of text around a span
def _snippet(text, start, end):
    left = max(0, start - CONTEXT_CHARS)
    right = min(len(text), end + CONTEXT_CHARS)
    return " ".join(text[left:right].split())

# character span of the labeled value for a numeric field
def gold_span(record, field):
    label = FIELD_LABELS[field]
    for entity in record["entities"]:
        if entity["label"] == label:
            return entity["start"], entity["end"]
    return None

# character span of a labeled amenity
def amenity_span(record, term_id):
    for entity in record["entities"]:
        if entity["label"] == "AMENITY" and entity["value"] == term_id:
            return entity["start"], entity["end"]
    return None

# first place an extracted number appears; counts must be followed by a bed or bath word
def extracted_position(text, value, field):
    if value is None:
        return None
    number = str(int(value)) if float(value).is_integer() else str(value)
    pattern = r'(?<![\d.])' + re.escape(number) + r'(?![\d])'
    if field in ("bedrooms", "bathrooms"):
        pattern += r'\s*-?\s*(?:full\s+)?(?:bed|br|bath|ba)'
    match = re.search(pattern, text, re.I)
    return (match.start(), match.end()) if match else None

# character span where the extractor matched an extracted amenity
def extracted_amenity_span(extractor, text, term_id):
    for start, end, found_id in extractor._find_amenity_spans(text):
        if found_id == term_id:
            return start, end
    return None

# ============================================================
# ------------------Pattern rules-----------------------------
# ============================================================

# assign a numeric error to a failure pattern using the labeled span and the extracted value
def classify_numeric(error, record):
    text = record["text"]
    field, kind = error["field"], error["error_type"]
    span = gold_span(record, field)
    gold_text = text[span[0]:span[1]].lower() if span else ""
    pos = extracted_position(text, error["extracted"], field)
    has_dollar = bool(pos) and text[max(0, pos[0] - 1):pos[0]] == "$"

    if field == "price":
        if kind == "wrong_value":
            return "earlier dollar amount taken instead of the listing price"
        if kind == "false_positive":
            return "dollar amount that is not the listing price" if has_dollar else "number without $ such as a zip code or lot size"

    if kind == "false_negative":
        words = "|".join(WORD_NUMBERS)
        if field == "sqft" and "square feet" not in gold_text:
            return "sqft unit form not normalized by the week 2 cleaner"
        if re.search(r'\b(?:' + words + r')-', gold_text):
            return "hyphenated spelled-out count"
        if re.search(r'1/2|one-half|a-half', gold_text):
            return "fractional bath phrasing"
        if re.search(r'^\S+\s+(?!bed|bath|full)\w+', gold_text):
            return "words between the count and the noun"
        return "other missed count"

    if kind == "false_positive":
        if field == "sqft":
            return "lot, shop, or secondary unit size taken as living area"
        return "count stated for part of the home or a second unit"

    if kind == "wrong_value":
        return "first mention is not the main home value"
    return "other"

# assign an amenity error to a failure pattern; known confusions are checked first
def classify_amenity(error, gold_ids):
    term = error["extracted"] or error["gold"]
    if error["error_type"] == "false_positive":
        if term == "eo_010" and "cl_002" in gold_ids:
            return "community pool read as a private pool"
        if term == "eo_021" and ("cl_002" in gold_ids or "kb_024" in gold_ids):
            return "community or bath spa read as a hot tub"
        return "matched phrase used in another sense or a hypothetical"
    if term.startswith("cl_"):
        return "missed community or location phrasing"
    return "missed feature phrasing not in variants"

# ============================================================
# ------------------Analysis----------------------------------
# ============================================================

# attach a pattern and a text window to every error from evaluate
def analyze(records, errors, extractor):
    by_id = {r["listing_id"]: r for r in records}
    gold_amenities = {
        r["listing_id"]: {e["value"] for e in r["entities"] if e["label"] == "AMENITY"}
        for r in records
    }
    rows = []
    for error in errors:
        record = by_id[error["listing_id"]]
        text = record["text"]
        if error["field"] == "amenities":
            pattern = classify_amenity(error, gold_amenities[error["listing_id"]])

            # missed amenities use the labeled span, extra ones use where the extractor matched
            if error["gold"]:
                span = amenity_span(record, error["gold"])
            else:
                span = extracted_amenity_span(extractor, text, error["extracted"])
        else:
            pattern = classify_numeric(error, record)
            span = gold_span(record, error["field"]) or extracted_position(text, error["extracted"], error["field"])

        # fall back to the start of the remark if no span is found
        context = _snippet(text, *span) if span else text[:2 * CONTEXT_CHARS]
        rows.append({**error, "pattern": pattern, "context": context})
    return rows

# print patterns ranked by count with a few examples each, then the most missed and extra amenities
def print_summary(rows, split_name):
    print(f"\nerror patterns on {split_name}, ranked by count\n")
    counts = Counter((r["field"], r["pattern"]) for r in rows)
    examples = defaultdict(list)
    for r in rows:
        examples[(r["field"], r["pattern"])].append(r)

    for rank, ((field, pattern), n) in enumerate(counts.most_common(), start=1):
        print(f"{rank:>2}. [{field}] {pattern}: {n}")
        for r in examples[(field, pattern)][:EXAMPLES_PER_PATTERN]:
            print(f"      gold={r['gold']} extracted={r['extracted']} | ...{r['context']}...")

    # amenity patterns are broad, so the specific taxonomy ids show where to add variants
    amenity_rows = [r for r in rows if r["field"] == "amenities"]
    for kind in ("false_negative", "false_positive"):
        top = Counter(r["gold"] or r["extracted"] for r in amenity_rows if r["error_type"] == kind)
        print(f"\nmost frequent amenity {kind}s: " + ", ".join(f"{t} ({n})" for t, n in top.most_common(10)))

# save every error with its pattern so individual cases can be reviewed in a spreadsheet
def save_rows(rows, path):
    fields = ["listing_id", "field", "error_type", "pattern", "gold", "extracted", "context"]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

# analyze errors on the chosen split and save them to data/labeled
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=["dev", "test"], default="dev")
    args = parser.parse_args()

    records = load_jsonl(DEV_PATH if args.split == "dev" else TEST_PATH)
    extractor = EntityExtractor()
    _, errors = evaluate(records, extractor)
    rows = analyze(records, errors, extractor)
    print_summary(rows, args.split)

    out_path = os.path.join(LABELED_DIR, f"errors_{args.split}.csv")
    save_rows(rows, out_path)
    print(f"\nsaved {len(rows)} errors to {out_path}")


if __name__ == "__main__":
    main()