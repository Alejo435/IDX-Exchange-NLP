import re
import os
import json

# spelled-out counts
WORD_NUMBERS = {
    'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
}

# one or two descriptive words allowed between a count and its noun, as in "4 spacious bedrooms"
# words that start a new clause are excluded so "2 car garage and bedroom" does not chain together
COUNT_FILLER = r'(?:(?!bed|bath|and\b|with\b|or\b)[a-z]+\s+){1,2}'

# words after a square feet mention, that means they're not the home's living area
NON_LIVING_SQFT_WORDS = r'(?:lot|backyard|yard|terrace|patio|deck|garage|adu|casita|guest)'

# phrases that directly introduce the listing price
PRICE_CUES = r'(?:price of|offered at|listed at|priced at|priced to move at|value at|offers between|market at|only|asking)'

# words around a dollar amount that mark it as something other than the listing price
NON_PRICE_BEFORE = r'\b(?:under|over|more than|below|nearly|approximately|appraised at)\s*$'
NON_PRICE_AFTER = r'^\s*(?:/|in\b|of\b|worth|credit|reduction|price reduction|price improvement|grant|value|annually|per|custom|farmhouse)'

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
    "if_005": ["lvp", "vinyl plank", "luxury vinyl"],
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

    # tuning batch 1: plain phrasings found in the dev error analysis
    "if_003": ["laminate floors", "laminate"],
    "if_020": ["owned solar panels", "paid solar", "paid-off solar", "paid off solar"],
    "if_021": ["solar system"],
    "if_022": ["in-unit washer and dryer"],
    "if_035": ["carpeting", "carpeted"],
    "kb_021": ["wine cooler", "wine fridge"],
    "eo_008": ["indoor-outdoor"],
    "eo_028": ["generous lot", "oversized lot", "expansive lot", "huge lot", "extra-large lot"],
    "cl_004": ["resort-style living", "resort-style community"],
    "cl_006": ["tennis"],
    "cl_010": ["freeway", "highway"],
    "cl_011": ["shopping", "shops"],
    "cl_024": ["biking trails", "bike paths"],
    "cl_025": ["public transit", "transit", "bart", "metro station"],
    "cl_026": ["award-winning schools", "award winning schools"],
    "cl_028": ["parks", "parkland", "local park", "neighborhood park"],
}


# ============================================================
# ------------------Amenity context---------------------------
# ============================================================

# words in the same sentence that mark a pool or spa as a shared community amenity
COMMUNITY_CUES = r'\b(?:community|communities|resort|amenities|clubhouse|hoa|association|residents|complex)\b'

# ids relabeled when community cues appear; None means the shared version is not labeled
COMMUNITY_SWAPS = {"eo_010": "cl_002", "eo_021": None}

# raw regex variants for phrasings with words in between
# lookaheads keep the match to one word so an overlapping term like "two-car garage" still matches
AMENITY_REGEX_VARIANTS = {
    "eo_018": [r'(?<![\w-])attached(?=\s+(?:[\w-]+\s+){1,3}garages?\b)'],
}

# ============================================================
# ------------------EntityExtractor class---------------------------
# ============================================================

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
        words = '|'.join(WORD_NUMBERS)
        patterns = [

            # trailing boundary so "3 brick" is not read as 3 bedrooms
            # optional hyphen so "5-bedroom" also matches
            r'(\d+)\s*-?\s*(?:bed|br|bedroom)s?\b',

            r'(\d+)bd',

            # spelled-out counts, hyphen allowed for "three-bedroom"
            r'\b(' + words + r')[\s-]+(?:bed|bedroom)s?\b',

            # descriptive words in between such as "4 spacious bedrooms"
            r'\b(\d{1,2}|' + words + r')\s+' + COUNT_FILLER + r'(?:bed|bedroom)s?\b',
        ]

        # earliest match in the text wins, not the first pattern in the list
        match = self._earliest_match(patterns, text)
        if match:
            value = match.group(1).lower()
            return int(WORD_NUMBERS.get(value, value))
        return None

    def extract_price(self, text):
        # assumes cleaned text from Week 2
        # an explicit cue like "offered at $X" is trusted first since it names the listing price
        cued = re.search(PRICE_CUES + r'\s*\$(\d{5,})', text, re.I)
        if cued:
            return int(cued.group(1))

        # otherwise take the first $ amount that is not a reduction, credit, upgrade value, rent, or limit
        for match in re.finditer(r'\$(\d{5,})', text):
            before = text[max(0, match.start() - 25):match.start()]
            after = text[match.end():match.end() + 30]
            if re.search(NON_PRICE_BEFORE, before, re.I) or re.search(NON_PRICE_AFTER, after, re.I):
                continue
            return int(match.group(1))
        return None

    def extract_bathrooms(self, text):
        # full and half counts such as "2 full and 1 half bathrooms" are combined into 2.5
        split = re.search(
            r'\b(\d+)\s*full\s*(?:bath(?:room)?s?\s*)?(?:and\s*)?(\d+)\s*half\s*bath',
            text,
            re.I,
        )
        if split:
            return int(split.group(1)) + 0.5 * int(split.group(2))

        words = '|'.join(WORD_NUMBERS)
        patterns = [
            # decimals so 2.5 bathrooms returns 2.5, optional hyphen for "3-bath home"
            r'\b(\d+(?:\.\d+)?)\s*-?\s*(?:full\s+)?(?:bathroom|bath|ba)s?\b',
            # spelled-out counts, hyphen allowed for "two-bath"
            r'\b(' + words + r')[\s-]+(?:full\s+)?(?:bathroom|bath)s?\b',
            # fractional forms such as "2 1/2 bath" and "two-and-a-half bath"
            r'\b(\d{1,2}|' + words + r')(?:\s+1/2|[\s-]+and[\s-]+(?:a|one)[\s-]+half)[\s-]+(?:bathroom|bath)s?\b',
            # descriptive words in between such as "three private baths"
            r'\b(\d{1,2}|' + words + r')\s+' + COUNT_FILLER + r'(?:bathroom|bath)s?\b',
        ]
        match = self._earliest_match(patterns, text)
        if not match:
            return None
        value = match.group(1).lower()
        count = float(WORD_NUMBERS.get(value, value))

        # the fractional pattern captures only the whole number, so the half is added here
        if re.search(r'1/2|half', match.group(0), re.I):
            count += 0.5
        return count

    def _earliest_match(self, patterns, text):
        # run every pattern and keep the match that starts first in the text
        matches = [m for p in patterns for m in [re.search(p, text, re.I)] if m]
        return min(matches, key=lambda m: m.start()) if matches else None

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

        # raw regex variants skip _phrase_to_pattern since they are already patterns
        for term_id, regexes in AMENITY_REGEX_VARIANTS.items():
            for regex in regexes:
                entries.append((len(regex), term_id, re.compile(regex, re.I)))

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

                # the span stays claimed even when dropped so a shorter phrase cannot re-match it
                resolved = self._resolve_community(text, match, term_id)
                if resolved:
                    found.append((start, end, resolved))
        return sorted(found)

    def _sentence_around(self, text, start, end):

        # sentence containing a match, bounded by . ! or ?
        left = max(text.rfind(c, 0, start) for c in '.!?') + 1
        rights = [i for i in (text.find(c, end) for c in '.!?') if i != -1]
        return text[left:min(rights) if rights else len(text)]

    def _resolve_community(self, text, match, term_id):

        # plural "pools" or a community cue in the same sentence means a shared amenity
        if term_id not in COMMUNITY_SWAPS:
            return term_id
        plural = match.group(0).lower().endswith('s')
        if plural or re.search(COMMUNITY_CUES, self._sentence_around(text, *match.span()), re.I):
            return COMMUNITY_SWAPS[term_id]
        return term_id

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