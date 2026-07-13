from app.validation.names import BAND_LOW, PASS_THRESHOLD, normalize, similarity


def test_legal_suffix_normalization_keeps_core_name_close():
    score = similarity("Meridian Trading Private Limited", "MERIDIAN TRADING PVT LTD")

    assert score >= PASS_THRESHOLD


def test_name_similarity_pass_threshold_is_inclusive():
    assert PASS_THRESHOLD == 0.85
    assert similarity("ACME SUPPLY", "ACME SUPPLY") >= PASS_THRESHOLD


def test_name_similarity_band_vector_lands_in_llm_band():
    score = similarity("Meridian Enterprises", "MERIDIAN LOGISTICS")

    assert BAND_LOW <= score < PASS_THRESHOLD


def test_name_similarity_below_band_for_different_entities():
    score = similarity("Meridian Trading", "Blue River Foods")

    assert score < BAND_LOW


def test_normalize_strips_known_suffixes_and_punctuation():
    assert normalize("Meridian Trading Pvt. Ltd.") == "MERIDIAN TRADING"
