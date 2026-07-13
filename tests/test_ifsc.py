from app.validation.ifsc import is_valid_ifsc


def test_canonical_ifsc_passes():
    assert is_valid_ifsc("HDFC0001234") is True


def test_ifsc_validation_normalizes_case_and_spaces():
    assert is_valid_ifsc(" hdfc0001234 ") is True


def test_ifsc_requires_zero_in_fifth_position():
    assert is_valid_ifsc("HDFC1001234") is False


def test_ifsc_rejects_bad_length():
    assert is_valid_ifsc("HDFC000123") is False
