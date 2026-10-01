
import html
import re
import unicodedata
from collections import Counter

import pandas as pd

# text cleaning and normalization pipeline for mls remarks and search queries

class TextCleaner:

    def __init__(self):

        self.abbrev_map = {
            # rooms
            'br': 'bedroom',
            'brs': 'bedrooms',
            'bd': 'bedroom',
            'bdrm': 'bedroom',
            'bdrms': 'bedrooms',
            'mbr': 'master bedroom',
            'mstr': 'master',
            'ba': 'bathroom',
            'bth': 'bathroom',
            'lr': 'living room',
            'fr': 'family room',
            'kit': 'kitchen',
            'rm': 'room',
            'bsmt': 'basement',
            'ofc': 'office',
            'gar': 'garage',
            'fp': 'fireplace',
            'hw': 'hardwood',
            'hdwd': 'hardwood',
            'ss': 'stainless steel',
            'appl': 'appliances',
            'appls': 'appliances',
            'cntr': 'counter',
            'a/c': 'air conditioning',
            'w/d': 'washer and dryer',
            'w/i': 'walk-in',
            'scr': 'screened',
            'encl': 'enclosed',
            'flr': 'floor',
            'pkg': 'parking',
            'sqft': 'square feet',
            'w/': 'with',
            'w/o': 'without',
            'approx': 'approximately',
            'lg': 'large',
            'updt': 'updated',
            'blt': 'built',
            'yr': 'year',
            'yrs': 'years',
            'nr': 'near',
            'pvt': 'private',
            'hoa': 'homeowners association',
        }

        # precompiled once so clean_text stays fast on large datasets
        self._abbrev_pattern = self._build_abbrev_pattern()

    def _build_abbrev_pattern(self):
        # longest keys first so w/o matches before w/ and bdrms before bdrm
        keys = sorted(self.abbrev_map.keys(), key=len, reverse=True)
        parts = []
        for k in keys:
            # keys ending in a letter need a trailing boundary so br does not match bright
            # keys ending in a slash like w/ must also match w/pool, so no trailing boundary
            tail = r'(?!\w)' if k[-1].isalnum() else ''
            parts.append(re.escape(k) + tail)
        # lookbehind blocks a preceding letter but allows a digit so 3br and 2ba still match
        return re.compile(r'(?<![^\W\d])(' + '|'.join(parts) + r')', flags=re.I)
    
    # ============================================================
    # Character level normalization
    # ============================================================

    def remove_html(self, text):

        # strip tags first so decoded entities like &lt; are not mistaken for tags
        text = re.sub(r'<[a-zA-Z/!][^>]*>', ' ', text)

        # drop unclosed tags left by truncated mls exports
        text = re.sub(r'<[a-zA-Z/][^>]*$', ' ', text)

        # decode entities such as &amp; and &nbsp;
        text = html.unescape(text)
        return text

    def normalize_unicode(self, text):

        # replace characters that would otherwise be lost or mangled by accent stripping
        replacements = {
            '\u2018': "'", '\u2019': "'",   # smart single quotes
            '\u201c': '"', '\u201d': '"',   # smart double quotes
            '\u2013': '-', '\u2014': '-',   # en and em dashes
            '\u2026': '...',                # ellipsis
            '\u00a0': ' ',                  # non-breaking space
            '\u200b': '', '\ufeff': '',     # zero-width space and byte order mark
            '\u00b2': ' sq',                # superscript two, so ft² becomes ft sq
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        # decompose accented characters and drop the combining marks
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(c for c in text if not unicodedata.combining(c))
        return text

    # ============================================================
    # Numeric normalization
    # ============================================================

    def _strip_number_commas(self, text):

        # 2,000 -> 2000 and 1,250,000 -> 1250000 without touching list commas like "pool, spa"
        return re.sub(r'(?<=\d),(?=\d{3}\b)', '', text)

    def normalize_prices(self, text):

        text = self._strip_number_commas(text)

        # 450k -> 450000
        # correction: decimal support so 1.5k is not split, boundaries so words like 4kids are skipped
        # lookahead skips non-price uses such as 4k tv
        text = re.sub(
            r'\b(\d+(?:\.\d+)?)k\b(?!\s*(?:tv|display|monitor|resolution))',
            lambda m: str(int(round(float(m.group(1)) * 1000))),
            text,
            flags=re.I,
        )
        # 1.2m -> 1200000
        # correction: boundaries so tokens like 2mbr or 10min are not converted
        text = re.sub(
            r'\b(\d+(?:\.\d+)?)m\b',
            lambda m: str(int(round(float(m.group(1)) * 1000000))),
            text,
            flags=re.I,
        )
        return text

    def normalize_measurements(self, text):
        text = self._strip_number_commas(text)
        
        # square footage variants: sqft, sq ft, sq. ft., sq feet, sf, and ft sq from the unicode step
        # longer alternatives come first so regex alternation does not stop at a shorter match
        sqft_units = r'(?:square\s*feet|square\s*foot|sq\.?\s*feet|sq\.?\s*ft|sqft|ft\s*sq|sf)'
        text = re.sub(
            r'\b(\d+(?:\.\d+)?)\s*' + sqft_units + r'\b',
            r'\1 square feet',
            text,
            flags=re.I,
        )
        # acreage variants: 1.5 acres, 2 acre, .5 ac
        text = re.sub(
            r'(\d*\.?\d+)\s*(?:acres?|ac)\b',
            r'\1 acres',
            text,
            flags=re.I,
        )
        return text

    # ============================================================
    # Word level normalization
    # ============================================================

    def expand_abbreviations(self, text):
        def _replace(match):
            key = match.group(1)
            expansion = self.abbrev_map[key.lower()]

            # 3br -> 3 bedroom
            if match.start() > 0 and match.string[match.start() - 1].isdigit():
                expansion = ' ' + expansion

            # w/pool -> with pool
            if key.endswith('/'):
                expansion = expansion + ' '
            return expansion

        return self._abbrev_pattern.sub(_replace, text)

    # ============================================================
    # Formatting cleanup
    # ============================================================

    def normalize_punctuation(self, text):

        # drop decorative runs common in mls marketing such as ***price reduced***
        text = re.sub(r'[*~=_#]{2,}', ' ', text)

        # collapse repeated terminal punctuation
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\?{2,}', '?', text)
        text = re.sub(r'\.{4,}', '...', text)
        text = re.sub(r'-{2,}', '-', text)

        # remove space before punctuation
        text = re.sub(r'\s+([,.!?;:])', r'\1', text)

        # ensure a space after commas and semicolons joined to the next word
        text = re.sub(r'([,;])(?=[A-Za-z])', r'\1 ', text)
        return text

    def normalize_whitespace(self, text):
        # collapse tabs, newlines, and repeated spaces into a single space
        return re.sub(r'\s+', ' ', text).strip()

    # ============================================================
    # Full pipeline for cleaning text 
    # ============================================================

    def clean_text(self, text):

        # guard against null remarks 
        if not isinstance(text, str):
            if text is None or pd.isna(text):
                return ''
            text = str(text)

        text = self.remove_html(text)
        text = self.normalize_unicode(text)
        text = self.normalize_prices(text)
        text = self.normalize_measurements(text)
        text = self.expand_abbreviations(text)
        text = self.normalize_punctuation(text)
        text = self.normalize_whitespace(text)
        return text.strip()

    # ============================================================
    # Data profiling
    # ============================================================

    def profile_column(self, df, column_name):

        # analyze what is actually in the remarks column before cleaning

        col = df[column_name].astype('string')
        return {
            'null_rate': col.isnull().mean(),
            'avg_length': col.str.len().mean(),
            'common_terms': self._extract_top_ngrams(col),
            # correction: na=False so null rows count as no match instead of returning NaN
            'price_mentions': int(col.str.contains(r'\$\d', na=False).sum()),
            # correction: match real tags so text like "< 1 mile" is not counted as html
            'has_html': int(col.str.contains(r'<[a-zA-Z/!][^>]*>', na=False).sum()),
            'common_abbreviations': self._detect_abbreviations(col),
        }

    def _tokenize(self, text):

        # lowercase tokens that keep slashes so w/ and a/c survive as single tokens
        return re.findall(r"[a-z0-9/']+", text.lower())

    def _extract_top_ngrams(self, series, top_n=20):

        # filler words that would otherwise dominate the counts
        stopwords = {
            'a', 'an', 'and', 'the', 'of', 'to', 'in', 'is', 'for', 'with',
            'on', 'at', 'this', 'that', 'it', 'or', 'from', 'by', 'are',
            'be', 'has', 'have', 'all', 'your', 'you', 'as', 'home',
        }
        unigrams = Counter()
        bigrams = Counter()
        for text in series.dropna():
            tokens = [t for t in self._tokenize(text) if t not in stopwords]
            unigrams.update(tokens)
            bigrams.update(zip(tokens, tokens[1:]))
        return {
            'unigrams': unigrams.most_common(top_n),
            'bigrams': [(' '.join(pair), count) for pair, count in bigrams.most_common(top_n)],
        }

    def _detect_abbreviations(self, series, top_n=20, min_count=3):

        known = Counter()
        candidates = Counter()
        known_keys = set(self.abbrev_map.keys())

        for text in series.dropna():

            # count matches of mapped abbreviations using the same pattern the cleaner uses
            known.update(m.lower() for m in self._abbrev_pattern.findall(text))

            # flag short tokens that look like shorthand but have no mapping yet
            for token in self._tokenize(text):
                if token in known_keys or token.isdigit() or len(token) > 5:
                    continue
                no_vowels = token.isalpha() and len(token) >= 2 and not re.search(r'[aeiouy]', token)
                if no_vowels or '/' in token:
                    candidates[token] += 1
        return {
            'known': known.most_common(top_n),

            # tokens seen at least min_count times are worth reviewing for the dictionary
            'unknown_candidates': [(t, c) for t, c in candidates.most_common(top_n) if c >= min_count],
        }
