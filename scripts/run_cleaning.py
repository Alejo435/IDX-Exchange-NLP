import difflib
import pandas as pd
from pathlib import Path
from text_cleaning import TextCleaner

# runs cleaning pipeline specified in week 2 on data\processed\listing_sample.csv

# ============================================================
# Paths and configuration
# ============================================================

# resolve paths from the project root so the script works from any working directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_PATH = PROJECT_ROOT / 'data' / 'processed' / 'listing_sample.csv'
CLEANED_PATH = PROJECT_ROOT / 'data' / 'processed' / 'listing_sample_cleaned.csv'
REPORTS_DIR = PROJECT_ROOT / 'reports'
PROFILE_REPORT_PATH = REPORTS_DIR / 'profiling_report.md'
EXAMPLES_REPORT_PATH = REPORTS_DIR / 'before_after_examples.md'

TEXT_COLUMN = 'remarks'
CLEAN_COLUMN = 'remarks_clean'

# ============================================================
# Data loading
# ============================================================

def load_sample(path=INPUT_PATH, column=TEXT_COLUMN):
    if not path.exists():
        raise FileNotFoundError(f'week 1 sample not found at {path}')
    df = pd.read_csv(path)
    if column not in df.columns:
        raise KeyError(f"column '{column}' not found, available columns: {list(df.columns)}")
    return df


# ============================================================
# Profiling report
# ============================================================

def _format_counts(pairs):

    # renders [(term, count), ...] as a markdown table body
    if not pairs:
        return ['| (none) | 0 |']
    return [f'| {term} | {count} |' for term, count in pairs]


def write_profiling_report(profile, df, path=PROFILE_REPORT_PATH, column=TEXT_COLUMN):
    path.parent.mkdir(parents=True, exist_ok=True)
    total = len(df)
    abbrevs = profile['common_abbreviations']

    lines = [
        '# Data Profiling Report',
        '',
        f'Source: `{INPUT_PATH.relative_to(PROJECT_ROOT)}`, column `{column}`',
        '',
        '## Summary',
        '',
        '| Metric | Value |',
        '|---|---|',
        f'| Total listings | {total} |',
        f"| Null rate | {profile['null_rate']:.2%} |",
        f"| Average length (chars) | {profile['avg_length']:.1f} |",
        f"| Listings with HTML tags | {profile['has_html']} ({profile['has_html'] / total:.2%}) |",
        f"| Listings with price mentions | {profile['price_mentions']} ({profile['price_mentions'] / total:.2%}) |",
        '',
        '## Known Abbreviations Found',
        '',
        '| Abbreviation | Count |',
        '|---|---|',
        *_format_counts(abbrevs['known']),
        '',
        '## Unmapped Abbreviation Candidates',
        '',
        'Short tokens without vowels or containing slashes that have no mapping yet.',
        '',
        '| Token | Count |',
        '|---|---|',
        *_format_counts(abbrevs['unknown_candidates']),
        '',
        '## Top Terms',
        '',
        '| Unigram | Count |',
        '|---|---|',
        *_format_counts(profile['common_terms']['unigrams']),
        '',
        '| Bigram | Count |',
        '|---|---|',
        *_format_counts(profile['common_terms']['bigrams']),
        '',
    ]
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path

# ============================================================
# Cleaning
# ============================================================

def clean_dataset(df, cleaner, path=CLEANED_PATH):

    # keep the original column next to the cleaned one for side by side review
    cleaned = df.copy()
    cleaned[CLEAN_COLUMN] = cleaned[TEXT_COLUMN].apply(cleaner.clean_text)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned.to_csv(path, index=False)
    return cleaned


# ============================================================
# Before and After example creating
# ============================================================

def _change_score(before, after):

    # 0 means identical, values near 1 mean the text changed heavily
    return 1 - difflib.SequenceMatcher(None, before, after).ratio()


def _count_non_ascii(series):
    return int(series.astype('string').str.contains(r'[^\x00-\x7f]', na=False).sum())


def write_before_after_examples(cleaned, cleaner, before_profile, path=EXAMPLES_REPORT_PATH, n_examples=15):

    path.parent.mkdir(parents=True, exist_ok=True)
    after_profile = cleaner.profile_column(cleaned, CLEAN_COLUMN)

    # total abbreviation occurrences rather than distinct terms
    abbrev_before = sum(c for _, c in before_profile['common_abbreviations']['known'])
    abbrev_after = sum(c for _, c in after_profile['common_abbreviations']['known'])

    # rank non-null listings by how much cleaning changed them
    rows = cleaned[cleaned[TEXT_COLUMN].notna()].copy()
    rows['change_score'] = [
        _change_score(b, a) for b, a in zip(rows[TEXT_COLUMN].astype(str), rows[CLEAN_COLUMN])
    ]
    top = rows.sort_values('change_score', ascending=False).head(n_examples)

    lines = [
        '# Before/After Cleaning Examples',
        '',
        '## Dataset Level Improvements',
        '',
        '| Metric | Before | After |',
        '|---|---|---|',
        f"| Listings with HTML tags | {before_profile['has_html']} | {after_profile['has_html']} |",
        f'| Mapped abbreviation occurrences (top 20 terms) | {abbrev_before} | {abbrev_after} |',
        f'| Listings with non-ASCII characters | {_count_non_ascii(cleaned[TEXT_COLUMN])} '
        f'| {_count_non_ascii(cleaned[CLEAN_COLUMN])} |',
        f"| Average length (chars) | {before_profile['avg_length']:.1f} | {after_profile['avg_length']:.1f} |",
        '',
        f'## Top {len(top)} Most Changed Listings',
        '',
    ]
    for i, (_, row) in enumerate(top.iterrows(), start=1):

        # fenced blocks keep raw html in the before text from rendering
        lines += [
            f"### Example {i} (change score {row['change_score']:.2f})",
            '',
            '**Before**',
            '```text',
            str(row[TEXT_COLUMN]),
            '```',
            '**After**',
            '```text',
            row[CLEAN_COLUMN],
            '```',
            '',
        ]
    path.write_text('\n'.join(lines), encoding='utf-8')
    return path

def main():
    cleaner = TextCleaner()
    df = load_sample()

    # profile first to understand what needs cleaning, usage from the spec
    profile = cleaner.profile_column(df, TEXT_COLUMN)
    print(f"HTML tags found in {profile['has_html']} listings")
    print(f"Common abbreviations: {profile['common_abbreviations']}")
    write_profiling_report(profile, df)

    cleaned = clean_dataset(df, cleaner)
    write_before_after_examples(cleaned, cleaner, profile)

    print(f'profiling report: {PROFILE_REPORT_PATH}')
    print(f'cleaned dataset: {CLEANED_PATH}')
    print(f'before/after examples: {EXAMPLES_REPORT_PATH}')


if __name__ == '__main__':
    main()