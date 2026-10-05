from app.rag.normalization import TextNormalizer


def test_tn_001_normalizes_windows_and_legacy_line_endings() -> None:
    text = "first\r\nsecond\rthird"

    assert TextNormalizer().normalize(text) == "first\nsecond\nthird"


def test_tn_002_trims_outer_whitespace_and_bounds_blank_lines() -> None:
    text = " \n\nFirst paragraph\n\n\n\nSecond paragraph\n\n "

    assert TextNormalizer().normalize(text) == "First paragraph\n\nSecond paragraph"


def test_tn_003_is_deterministic_and_preserves_internal_whitespace() -> None:
    text = "SELECT  id, name\nFROM users"
    normalizer = TextNormalizer()

    assert normalizer.normalize(text) == text
    assert normalizer.normalize(text) == normalizer.normalize(text)
