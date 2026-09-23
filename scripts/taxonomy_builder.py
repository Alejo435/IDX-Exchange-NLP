import os
from collections import Counter

import nltk
import pandas as pd
from nltk.corpus import stopwords
from nltk.util import ngrams

# week 1 taxonomy builder: extracts candidate terms from listing remarks to seed the taxonomy

# =============================================================================
# Config.
# =============================================================================

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLE_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "listing_sample.csv")

# using bigrams so N gram size is 2
NGRAM_SIZE = 2

# using top 200 bigrams as taxonomy seed
TOP_K = 200

# output name includes the n-gram size so runs with different sizes do not overwrite each other
CANDIDATES_PATH = os.path.join(
    PROJECT_ROOT, "data", "processed", f"taxonomy_candidates_{NGRAM_SIZE}gram.csv"
)

# negations are kept because phrases like "no hoa" carry meaning
KEEP_WORDS = {"no", "not"}

# =============================================================================
# Resource Setup
# =============================================================================

# download any missing nltk data required for tokenization and stopword filtering
def ensure_nltk_data():
    try:
        nltk.word_tokenize("test")
    except LookupError:
        # the required punkt package depends on the nltk version, so both are fetched
        nltk.download("punkt", quiet=True)
        nltk.download("punkt_tab", quiet=True)

    try:
        stopwords.words("english")
    except LookupError:
        nltk.download("stopwords", quiet=True)

# return the english stopword set excluding KEEP_WORDS
def load_stopwords():

    return set(stopwords.words("english")) - KEEP_WORDS

# =============================================================================
# Loading
# =============================================================================

# load lowercase listing remarks from the week 1 sample CSV
def load_remarks(path=SAMPLE_PATH):

    df = pd.read_csv(path)
    return df["remarks"].dropna().astype(str).str.lower().tolist()

# =============================================================================
# N-gram Counting
# =============================================================================

# return True for alphabetic tokens, allowing internal hyphens such as move-in
def is_word(token):
    return token.replace("-", "").isalpha()

# count how many remarks contain each n-gram
def count_ngrams(remarks, stop_words, n=NGRAM_SIZE):

    freq = Counter()
    for remark in remarks:
        # tokenizing each remark separately prevents n-grams that span two listings
        tokens = nltk.word_tokenize(remark)

        # punctuation and numbers break phrases instead of being skipped over
        grams = {
            " ".join(gram)
            for gram in ngrams(tokens, n)
            if all(is_word(t) for t in gram)
            and gram[0] not in stop_words
            and gram[-1] not in stop_words
        }

        # a set counts each n-gram once per listing so repeated filler words are not inflated
        freq.update(grams)
    return freq

# =============================================================================
# Entry Point
# =============================================================================

# print the top n-grams from the listing sample and save them for review
def main():
   
    ensure_nltk_data()
    remarks = load_remarks()
    freq = count_ngrams(remarks, load_stopwords())

    top = freq.most_common(TOP_K)
    for term, count in top:
        print(f"{term}: {count}")

    # doc_pct shows the share of listings containing each term, which feeds the coverage check
    df = pd.DataFrame(top, columns=["term", "doc_count"])
    df["doc_pct"] = (100 * df["doc_count"] / len(remarks)).round(2)

    os.makedirs(os.path.dirname(CANDIDATES_PATH), exist_ok=True)
    df.to_csv(CANDIDATES_PATH, index=False)
    print(f"\nsaved top {len(top)} of {len(freq)} {NGRAM_SIZE}-grams from {len(remarks)} remarks to {CANDIDATES_PATH}")


if __name__ == "__main__":
    main()