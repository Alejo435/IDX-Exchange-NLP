import os
import sys
from pathlib import Path

import pandas as pd

# make scripts/ importable without packaging the project
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(parent_dir)

from scripts.text_cleaning import TextCleaner


# ============================================================
# ------------------Shared test data--------------------------
# ============================================================

cleaner = TextCleaner()

# small frame with known nulls, html, prices, and abbreviations for profiling tests
df = pd.DataFrame({
    'remarks': [
        'Beautiful 3br/2ba w/pool<br>Priced at $450k',
        None,
        'Updated kit w/ ss appl, 1,800 sqft',
        '<p>Corner lot near park</p>',
        'Just listed at $1.2m, 4 bdrm',
    ]
})

# ============================================================
# ------------------Price normalization tests-----------------
# ============================================================

def test_price_normalization():
    assert '450000' in cleaner.normalize_prices('priced at 450k')
    assert '1200000' in cleaner.normalize_prices('$1.2m home')


def test_price_uppercase_suffix():
    assert cleaner.normalize_prices('priced at 450K') == 'priced at 450000'


def test_price_decimal_thousands():
    assert cleaner.normalize_prices('deposit of 1.5k') == 'deposit of 1500'


def test_price_with_commas():
    assert cleaner.normalize_prices('$1,250k') == '$1250000'


def test_price_float_rounding():
    assert cleaner.normalize_prices('$1.15m') == '$1150000'


def test_price_range():
    assert cleaner.normalize_prices('$450k-$500k') == '$450000-$500000'


def test_price_ignores_4k_tv():
    assert cleaner.normalize_prices('includes 4k TV') == 'includes 4k TV'


def test_price_ignores_minutes():
    assert cleaner.normalize_prices('10min drive') == '10min drive'


def test_price_ignores_digit_prefixed_abbreviation():
    assert cleaner.normalize_prices('large 2mbr suite') == 'large 2mbr suite'


def test_price_no_numbers_unchanged():
    assert cleaner.normalize_prices('updated kitchen') == 'updated kitchen'

# ============================================================
# ---------------Measurement normalization tests--------------
# ============================================================

def test_sqft_with_comma():
    assert cleaner.normalize_measurements('2,000 sqft') == '2000 square feet'


def test_sqft_no_space_with_comma():
    assert cleaner.normalize_measurements('2,000sqft') == '2000 square feet'


def test_sq_ft_spaced():
    assert cleaner.normalize_measurements('1500 sq ft') == '1500 square feet'


def test_sq_ft_with_periods_keeps_sentence_end():
    assert cleaner.normalize_measurements('1500 sq. ft.') == '1500 square feet.'


def test_sf_shorthand():
    assert cleaner.normalize_measurements('1800sf') == '1800 square feet'


def test_sqft_uppercase():
    assert cleaner.normalize_measurements('1200 SQ FT') == '1200 square feet'


def test_ft_sq_from_superscript():
    # normalize_unicode turns ft² into ft sq before this step runs
    assert cleaner.normalize_measurements('900 ft sq') == '900 square feet'


def test_acres_shorthand():
    assert cleaner.normalize_measurements('0.5 ac lot') == '0.5 acres lot'


def test_sqft_without_number_unchanged():
    assert cleaner.normalize_measurements('great sqft') == 'great sqft'

# ============================================================
# ----------------Abbreviation expansion tests----------------
# ============================================================

def test_abbrev_basic():
    assert cleaner.expand_abbreviations('spacious br') == 'spacious bedroom'


def test_abbrev_uppercase():
    assert cleaner.expand_abbreviations('MBR suite') == 'master bedroom suite'


def test_abbrev_digit_prefixed():
    assert cleaner.expand_abbreviations('3br/2ba') == '3 bedroom/2 bathroom'


def test_abbrev_does_not_match_inside_words():
    assert cleaner.expand_abbreviations('bright room') == 'bright room'
    assert cleaner.expand_abbreviations('finished basement') == 'finished basement'


def test_abbrev_with_no_space():
    assert cleaner.expand_abbreviations('w/pool') == 'with pool'


def test_abbrev_without_before_with():
    assert cleaner.expand_abbreviations('w/o hoa') == 'without homeowners association'


def test_abbrev_with_followed_by_o_word():
    assert cleaner.expand_abbreviations('w/office') == 'with office'


def test_abbrev_plural_longest_match():
    assert cleaner.expand_abbreviations('4 bdrms') == '4 bedrooms'


def test_abbrev_slash_key():
    assert cleaner.expand_abbreviations('central a/c') == 'central air conditioning'


def test_abbrev_adjacent_punctuation():
    assert cleaner.expand_abbreviations('pool, fp.') == 'pool, fireplace.'

# ============================================================
# ------------------Html removal tests------------------------
# ============================================================

def test_html_paragraph_tags():

    # tags become spaces, whitespace cleanup happens later in the pipeline
    assert cleaner.remove_html('<p>Corner lot</p>').strip() == 'Corner lot'


def test_html_break_tag_keeps_words_apart():
    assert cleaner.remove_html('pool<br>spa') == 'pool spa'


def test_html_tag_with_attributes():
    assert cleaner.remove_html('<div class="x">Pool</div>').strip() == 'Pool'


def test_html_entity_ampersand():
    assert cleaner.remove_html('pool &amp; spa') == 'pool & spa'


def test_html_less_than_not_a_tag():
    assert cleaner.remove_html('less than < 1 mile') == 'less than < 1 mile'


def test_html_truncated_tag():
    assert cleaner.remove_html('great view <a href="x').strip() == 'great view'


def test_html_encoded_tag_decoded_not_removed():
    assert cleaner.remove_html('a &lt; b') == 'a < b'

# ============================================================
# ------------------Unicode normalization tests---------------
# ============================================================

def test_unicode_smart_quotes():
    assert cleaner.normalize_unicode('\u201cupdated\u201d') == '"updated"'


def test_unicode_em_dash():
    assert cleaner.normalize_unicode('pool\u2014spa') == 'pool-spa'


def test_unicode_accent_stripping():
    assert cleaner.normalize_unicode('caf\u00e9') == 'cafe'


def test_unicode_zero_width_space():
    assert cleaner.normalize_unicode('po\u200bol') == 'pool'


def test_unicode_non_breaking_space():
    assert cleaner.normalize_unicode('a\u00a0b') == 'a b'


def test_unicode_superscript_square_feet():
    assert cleaner.normalize_unicode('1200 ft\u00b2') == '1200 ft sq'


def test_unicode_ascii_unchanged():
    assert cleaner.normalize_unicode('plain text 123') == 'plain text 123'

# ============================================================
# ---------------Punctuation and whitespace tests-------------
# ============================================================

def test_punct_decorative_runs():
    assert cleaner.normalize_punctuation('***PRICE REDUCED***').strip() == 'PRICE REDUCED'


def test_punct_repeated_exclamation():
    assert cleaner.normalize_punctuation('amazing!!!') == 'amazing!'


def test_punct_repeated_question():
    assert cleaner.normalize_punctuation('really??') == 'really?'


def test_punct_long_ellipsis():
    assert cleaner.normalize_punctuation('wait.....') == 'wait...'


def test_punct_period_before_exclamation():
    assert cleaner.normalize_punctuation('feet.!!!') == 'feet!'


def test_punct_space_before_comma():
    assert cleaner.normalize_punctuation('pool , spa') == 'pool, spa'


def test_punct_missing_space_after_comma():
    assert cleaner.normalize_punctuation('pool,spa') == 'pool, spa'


def test_punct_double_dash():
    assert cleaner.normalize_punctuation('3--car garage') == '3-car garage'


def test_whitespace_collapse():
    assert cleaner.normalize_whitespace('a  \t b\n c') == 'a b c'


def test_whitespace_strip():
    assert cleaner.normalize_whitespace('  padded  ') == 'padded'

# ============================================================
# -----------------Full pipeline tests------------------------
# ============================================================

def test_pipeline_realistic_remark():
    text = 'Gorgeous 3br/2ba w/pool, 2,000 sq. ft.!!! Priced at $450k<br>'
    expected = 'Gorgeous 3 bedroom/2 bathroom with pool, 2000 square feet! Priced at $450000'
    assert cleaner.clean_text(text) == expected


def test_pipeline_collapses_spaces_from_expansion():
    text = 'Updated kit w/ ss appl, 1,800 sqft'
    expected = 'Updated kitchen with stainless steel appliances, 1800 square feet'
    assert cleaner.clean_text(text) == expected


def test_pipeline_html_entities_and_unicode():
    text = '<p>Caf\u00e9 &amp; pool\u2014spa</p>'
    assert cleaner.clean_text(text) == 'Cafe & pool-spa'


def test_pipeline_is_idempotent():
    
    # cleaning already clean text should change nothing
    once = cleaner.clean_text('Updated kit w/ ss appl, 1,800 sqft')
    assert cleaner.clean_text(once) == once


def test_pipeline_none_input():
    assert cleaner.clean_text(None) == ''


def test_pipeline_nan_input():
    assert cleaner.clean_text(float('nan')) == ''


def test_pipeline_non_string_input():
    assert cleaner.clean_text(123) == '123'


def test_pipeline_empty_string():
    assert cleaner.clean_text('') == ''

# ============================================================
# --------------------Data profiling tests--------------------
# ============================================================

def test_profiling():
    profile = cleaner.profile_column(df, 'remarks')
    assert 'null_rate' in profile
    assert 'avg_length' in profile


def test_profiling_null_rate():

    # one null out of five rows
    profile = cleaner.profile_column(df, 'remarks')
    assert profile['null_rate'] == 0.2


def test_profiling_html_count():

    # rows with <br> and <p> tags
    profile = cleaner.profile_column(df, 'remarks')
    assert profile['has_html'] == 2


def test_profiling_price_mentions():

    # rows with $450k and $1.2m
    profile = cleaner.profile_column(df, 'remarks')
    assert profile['price_mentions'] == 2


def test_profiling_detects_known_abbreviations():
    profile = cleaner.profile_column(df, 'remarks')
    known = dict(profile['common_abbreviations']['known'])
    assert known.get('w/') == 2
    assert 'br' in known
    assert 'bdrm' in known


def test_profiling_all_null_column():

    # string dtype cast keeps .str working when every value is null
    empty = pd.DataFrame({'remarks': [None, None]})
    profile = cleaner.profile_column(empty, 'remarks')
    assert profile['null_rate'] == 1.0
    assert profile['has_html'] == 0


if __name__ == '__main__':

    tests = [(name, fn) for name, fn in list(globals().items()) if name.startswith('test_') and callable(fn)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
        except AssertionError:
            failed += 1
            print(f'FAIL {name}')
    print(f'{len(tests) - failed}/{len(tests)} passed')