import re
import os
import json

# spelled-out counts
WORD_NUMBERS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}

# words after a square feet mention, that means they're not the home's living area
NON_LIVING_SQFT_WORDS = r'(?:lot|backyard|yard|terrace|patio|deck|garage|adu|casita|guest)'

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAXONOMY_PATH = os.path.join(PROJECT_ROOT, "data", "processed", "taxonomy.json")

# based on the spec I kept only the five feature categories to count as amenities; property_type, condition, and financial_use are excluded 
AMENITY_PREFIXES = {"rs", "kb", "if", "eo", "cl"}

# =============================================================================
# -------------------------Amenity variants------------------------------------
# =============================================================================

# extra phrasings per taxonomy id, matched alongside the canonical term
# hyphen/space differences and plural endings are handled automatically, so they are not listed here
AMENITY_VARIANTS = {

    # rooms and spaces
    "rs_001": ["master suite", "primary bedroom suite"],
    "rs_002": ["master bedroom"],
    "rs_010": ["office"],
    "rs_015": ["full bath"],
    "rs_020": ["mud room"],
    "rs_021": ["sun room"],

    # kitchen and bath
    "kb_001": ["stainless appliances", "stainless steel"],
    "kb_002": ["quartz counters", "quartz"],
    "kb_003": ["granite counters", "granite"],
    "kb_004": ["kitchen island", "island"],
    "kb_013": ["double vanities", "dual vanity", "double vanity"],
    "kb_014": ["double sinks"],

    # interior features
    "if_001": ["hardwood flooring", "hardwood"],
    "if_005": ["lvp", "vinyl plank"],
    "if_006": ["cathedral ceilings"],
    "if_012": ["open concept", "open layout"],
    "if_016": ["double-pane windows", "dual pane", "double pane"],
    "if_017": ["central air", "central ac"],
    "if_024": ["fireplaces"],

    # exterior and outdoor
    "eo_010": ["pool"],
    "eo_017": ["2-car garage", "two car garage"],
    "eo_021": ["spa", "jacuzzi"],
    "eo_027": ["fenced backyard", "fully fenced"],
    "eo_030": ["3-car garage"],
    "eo_033": ["ev charging"],

    # community and location
    "cl_001": ["guard-gated", "gated"],
}

class EntityExtractor:

    def __init__(self, taxonomy_path=TAXONOMY_PATH):

        self.term_names = self._load_amenity_terms(taxonomy_path)

        # precompiled once so extract_amenities stays fast on large datasets
        self._amenity_patterns = self._build_amenity_patterns()

    def _load_amenity_terms(self, path):

        # returns {term_id: term} for the five feature categories only
        with open(path, encoding="utf-8") as f:
            taxonomy = json.load(f)
        return {
            t["id"]: t["term"]
            for t in taxonomy["terms"]
            if t["id"].split("_")[0] in AMENITY_PREFIXES
        }


    # ============================================================
    # -------------------------Numeric entity methods-------------
    # ============================================================

    def extract_bedrooms(self, text):
        patterns = [

            # trailing boundary so "3 brick" is not read as 3 bedrooms
            # optional hyphen so "5-bedroom" matches, used in about 24% of remarks
            r'(\d+)\s*-?\s*(?:bed|br|bedroom)s?\b',

            # kept for raw text; the week 2 cleaner already expands 3bd to 3 bedroom
            r'(\d+)bd',

            # spelled-out counts such as "three bedrooms", reusing the bathroom word map
            r'\b(' + '|'.join(WORD_NUMBERS) + r')\s+(?:bed|bedroom)s?\b'
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = match.group(1).lower()
                return int(WORD_NUMBERS.get(value, value))
        return None

    def extract_price(self, text):
        match = re.search(r'\$?(\d{5,})', text)
        return int(match.group(1)) if match else None

    def extract_bathrooms(self, text):

        # full and half counts such as "2 full and 1 half bathrooms" are combined into 2.5
        split = re.search(
            r'\b(\d+)\s*full\s*(?:bath(?:room)?s?\s*)?(?:and\s*)?(\d+)\s*half\s*bath',
            text,
            re.I,
        )
        if split:
            return int(split.group(1)) + 0.5 * int(split.group(2))

        patterns = [

            # decimals so 2.5 bathrooms returns 2.5, optional hyphen for "3-bath home"
            r'\b(\d+(?:\.\d+)?)\s*-?\s*(?:full\s+)?(?:bathroom|bath|ba)s?\b',
            # spelled-out counts such as "two full bathrooms"
            r'\b(' + '|'.join(WORD_NUMBERS) + r')\s+(?:full\s+)?(?:bathroom|bath)s?\b',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = match.group(1).lower()
                return float(WORD_NUMBERS.get(value, value))
        return None

    def extract_sqft(self, text):

        # week 2 normalizes sqft, sq ft, and sf variants to "N square feet"
        for match in re.finditer(r'\b(\d{3,6})\s*square feet\b', text, re.I):
            following = text[match.end():match.end() + 25]
            preceding = text[max(0, match.start() - 25):match.start()]

            # skip lot, yard, and secondary unit sizes such as "on a 7500 square feet lot"
            if re.match(r'\s*(?:\w+\s+){0,1}' + NON_LIVING_SQFT_WORDS + r'\b', following, re.I):
                continue
            if re.search(r'\b(?:lot|on an?\s+\w*)\s*(?:of\s+)?(?:approximately\s+)?$', preceding, re.I):
                continue
            return int(match.group(1))
        return None

    # ============================================================
    # --------------Amenity detection methods---------------------
    # ============================================================

    def _phrase_to_pattern(self, phrase):

        # "walk-in closet" also matches "walk in closet" and "walk-in closets"
        words = re.split(r'[\s-]+', phrase.lower())
        last = words[-1]

        # plural is optional whether the taxonomy term is singular or plural
        if last.endswith('s') and not last.endswith('ss'):
            words[-1] = re.escape(last[:-1]) + 's?'
        else:
            words[-1] = re.escape(last) + 's?'
        body = r'[\s-]?'.join(
            w if w.endswith('s?') else re.escape(w) for w in words
        )

        # trailing guard also blocks hyphenated words so spa does not match spa-like
        return r'(?<![\w-])' + body + r'(?![\w-])'

    def _build_amenity_patterns(self):

        # each phrase becomes its own pattern so longer phrases can claim text before shorter ones
        entries = []
        for term_id, term in self.term_names.items():
            for phrase in [term] + AMENITY_VARIANTS.get(term_id, []):
                entries.append((len(phrase), term_id, re.compile(self._phrase_to_pattern(phrase), re.I)))

        # longest first so "community pool" is claimed before "pool"
        entries.sort(key=lambda e: e[0], reverse=True)
        return [(term_id, pattern) for _, term_id, pattern in entries]

    def _find_amenity_spans(self, text):

        # returns (start, end, term_id) tuples with no overlapping spans
        claimed = []
        found = []
        for term_id, pattern in self._amenity_patterns:
            for match in pattern.finditer(text):
                start, end = match.span()

                # skip text already claimed by a longer phrase
                if any(start < c_end and end > c_start for c_start, c_end in claimed):
                    continue
                claimed.append((start, end))
                found.append((start, end, term_id))
        return sorted(found)

    def extract_amenities(self, text):

        # one entry per taxonomy id even when the amenity is mentioned more than once
        ids = {term_id for _, _, term_id in self._find_amenity_spans(text)}
        return sorted(ids)

    # ============================================================
    # --------------Combined extraction methods-------------------
    # ============================================================

    def extract_all(self, text):
        return {
            'bedrooms': self.extract_bedrooms(text),
            'bathrooms': self.extract_bathrooms(text),
            'price': self.extract_price(text),
            'sqft': self.extract_sqft(text),
            'amenities': self.extract_amenities(text)
        }


# print extracted entities for a few cleaned remarks as a quick sanity check
def main():
    import pandas as pd

    cleaned_path = os.path.join(PROJECT_ROOT, "data", "processed", "listing_sample_cleaned.csv")
    remarks = pd.read_csv(cleaned_path)["remarks_clean"].fillna("").tolist()

    extractor = EntityExtractor()
    for text in remarks[:5]:
        print(text[:150])
        print(extractor.extract_all(text))
        print()


if __name__ == "__main__":
    main()