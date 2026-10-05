# NLP 2026

This reposotory contains the code I delevoped for the IDX Exchange 2026 NLP Internship. Below you can find set up instructions as well as descriptions for code added each week

# Setup (TODO)

Will contain set up instructions for docker + additional python libraries

# Weekly Progess

## Week 1: Domain Understanding + Taxonomy

### Environment and Data Setup
- Loaded all three tables into the MySQL container from `docker-compose.yml`
- Initial import didn't run since the SQL files weren't in `data/raw/` at first startup, fixed by resetting the volume
- Sped up the slow import by raising InnoDB's redo log capacity at runtime

### Sample Dataset
**File:** `scripts/data_loading.py` → `data/processed/listing_sample.csv` (1,000 listings)
- `SAMPLE_QUERY` follows the spec's query, with a seeded `RAND()` so the sample is reproducible
- Uses `CHAR_LENGTH` so the length filter counts characters, matching the tests
- `load_listing_sample` reads through a cursor to avoid a pandas warning

### Taxonomy
**Files:** `scripts/taxonomy_builder.py` → `data/processed/taxonomy.json` (211 terms, 8 categories)
- Follows the spec's method: NLTK bigrams, top 200 as the seed
- `count_ngrams` counts per listing and filters stopwords and punctuation so the output is usable
- Curated 102 terms from the seed and added 109 manually, mostly single words bigrams can't capture
- Merged near-duplicates into one term, such as "stainless steel appliances"

### Sample Queries
**File:** `data/processed/sample_queries.csv` (56 queries)
- Balanced classes (19 browsing, 18 researching, 19 high_intent_inquiry)
- Cities come from the database so queries work

### Validation Tests
**File:** `tests/test_week1.py`
- Kept the spec's two tests and added the missing pandas import

## Week 2: Text Cleaning & Normalization

### Text Cleaner
**File:** `scripts/text_cleaning.py`
- `TextCleaner` class with 7 normalization methods: HTML, unicode, prices, measurements, abbreviations, punctuation, whitespace
- `clean_text` keeps the spec's step order, adds HTML removal first and formatting cleanup last
- Null and non-string remarks return an empty string, so the pipeline runs safely on the whole column

### Abbreviation Dictionary
- 42 mappings, starting from the spec's 6 and adding common MLS shorthand (`bdrm`, `ss`, `appl`, `a/c`, `w/d`)
- Skipped ambiguous ones like `dr` (dining room or drive) and `fl` (floor or Florida)
- Longest keys match first so `w/o` doesn't become "witho"
- Matches whole tokens only, so "bright" and "basement" stay unchanged, while compact forms like `3br/2ba` and `w/pool` still expand

### Fixes to the Spec Code
- Price regex: added word boundaries, decimal support (`1.5k`), and rounding to avoid float drift (`1.15m`)
- Skips non-prices like `4k TV` and `10min`
- Commas are removed from numbers first, so `$1,250k` and `2,000 sqft` convert correctly
- Profiling uses `na=False` and a real tag pattern, so nulls and text like "< 1 mile" don't break the counts

### Data Profiling
- `profile_column` returns the spec's keys: null rate, average length, top terms, price mentions, HTML count, abbreviations
- Abbreviation detection uses the same matcher as the cleaner and also flags unmapped shorthand to review

### Pipeline Script
**File:** `scripts/run_cleaning.py`
- Profiles `data/processed/listing_sample.csv`, then cleans it and writes the outputs
- `data/processed/listing_sample_cleaned.csv` keeps `remarks` next to the new `remarks_clean` column
- `reports/profiling_report.md` lists null rate, HTML, prices, abbreviations, and top terms
- `reports/before_after_examples.md` shows before/after metrics and the 15 most changed listings

### Tests
**File:** `tests/test_text_cleaning.py` (67 tests)
- Covers prices, measurements, abbreviations, HTML, unicode, punctuation, the full pipeline, and profiling
- Kept the spec's two tests, defining `cleaner` and `df` at module level so they run

## Week 3: Named Entity Extraction

### Entity Extractor
**File:** `scripts/entity_extractor.py`
- `EntityExtractor` class with regex extraction for bedrooms, bathrooms, price, and square footage, plus `extract_all` returning all five fields as in the spec
- Bathrooms return floats so `2.5 bathrooms` and `2 full and 1 half baths` both give `2.5`
- Sqft skips lot, yard, and secondary unit sizes such as `on a 7500 square feet lot`

### Amenity Detection
- Loads `data/processed/taxonomy.json` and uses only the 5 feature categories: rooms/spaces, kitchen/bath, interior, exterior/outdoor, community/location
- Property type, condition, and financial terms are excluded since they aren't amenities
- Hyphen, spacing, and plural differences match automatically, so `walk in closets` matches `walk-in closet`
- Longer phrases claim text first, so `community pool` isn't also counted as a private pool
- Returns sorted taxonomy IDs, one per amenity even when mentioned more than once

### Fixes to the Spec Code
- Bedroom pattern: added a trailing word boundary so `3 brick` isn't read as 3 bedrooms
- Bedroom pattern: optional hyphen so `5-bedroom` matches (about 24% of remarks use this form)
- Price regex kept as written for the baseline; known false positives (ZIP codes, price reductions, credits) are measured in the evaluation instead of patched blindly

### Labeled Dataset
**Files:** `data/labeled/entities_all.jsonl`, `entities_dev.jsonl`, `entities_test.jsonl`
- 250 remarks with character-level entity spans: 178 bedroom, 160 bathroom, 97 sqft, 11 price, and 2,795 amenity labels
- Stratified sample (seed 42): 60 remarks with `$` amounts, 150 with bed/bath/sqft mentions, 40 with neither, so false positives are measured too
- **Labels were generated with AI assistance due to time constraints (I have a hackthon this weekend and exam later this week).** 
- Labeling rules: main home only (not ADU/guest unit), listing price only (not reductions, credits, HOA, or rent), living area only (not lot size), partial counts by floor left null, hypothetical features ("room for a pool") not labeled

### Dataset Split
**File:** `scripts/split_dataset.py`
- Stratified 70/30 split by sampling group: 175 dev, 75 test
- Fixed seed and sorting by listing ID, so the split is identical on every run regardless of file order
- Tuning uses the dev set only; the test set is run once for the final score