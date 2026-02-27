import pytest
from services.pipeline.resolution.entity_resolver import EntityResolver, normalize_term, normalize_hebrew_term

def test_hebrew_normalization_nikud():
    """Test that Hebrew nikud (vowels) are correctly stripped."""
    with_nikud = "מַעֲרֶכֶת צִיֵּ\"ד"
    without_nikud = normalize_hebrew_term(with_nikud)
    assert without_nikud == "מערכת ציד"

def test_hebrew_normalization_geresh():
    """Test that geresh/gershayim in military acronyms are removed."""
    acronym1 = "קמ\"ן"
    acronym2 = "מפ\"ג"
    assert normalize_hebrew_term(acronym1) == "קמן"
    assert normalize_hebrew_term(acronym2) == "מפג"

def test_auto_language_detection():
    """Test that normalize_term auto-detects English vs Hebrew."""
    assert normalize_term("Air Force") == "air force"
    assert normalize_term("חיל האוויר") == "חיל האוויר"
    assert normalize_term("F-35 אדיר") == "f-35 אדיר"  # Mixed triggers Hebrew path

def test_entity_resolver_exact_match():
    resolver = EntityResolver()
    resolver.register("מערכת צי\"ד", "C-100")
    
    # Exact normalized match
    assert resolver.resolve("מערכת ציד") == "C-100"
    assert resolver.resolve("מַעֲרֶכֶת צִיֵּ\"ד") == "C-100"

def test_entity_resolver_fuzzy_match():
    resolver = EntityResolver()
    resolver.register("קצין מודיעין ראשי", "C-200")
    
    # Slight typo should trigger fuzzy match >= 0.88 threshold
    assert resolver.resolve("קצין מודיען ראשי") == "C-200"

def test_entity_resolver_no_match():
    resolver = EntityResolver()
    resolver.register("אוגדה 36", "C-300")
    
    # Totally different
    assert resolver.resolve("אוגדה 98") is None
