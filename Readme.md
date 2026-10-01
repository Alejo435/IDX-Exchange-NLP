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

