import sys
import os
from pathlib import Path
import pandas as pd
import pytest

parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(parent_dir)

from scripts.text_cleaning import TextCleaner

cleaner = TextCleaner() 

def test_price_normalization(): 
    
    assert '450000' in cleaner.normalize_prices('priced at 450k') 
    assert '1200000' in cleaner.normalize_prices('$1.2m home') 

def test_profiling(): 

    profile = cleaner.profile_column(df, 'remarks') 
    assert 'null_rate' in profile 
    assert 'avg_length' in profile