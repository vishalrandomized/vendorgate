from app.validation.gstin import expected_checksum, make_gstin, validate_gstin_parts


def test_valid_gstin_passes_all_parts():
    parts = validate_gstin_parts("27AAPFU0939F1ZV")

    assert parts["normalized"] == "27AAPFU0939F1ZV"
    assert parts["structure_ok"] is True
    assert parts["loose_structure_ok"] is True
    assert parts["state_ok"] is True
    assert parts["state_name"] == "Maharashtra"
    assert parts["pan_ok"] is True
    assert parts["checksum_ok"] is True


def test_make_gstin_uses_expected_checksum_vector():
    first14 = "29ABCDE1234F1Z"

    assert expected_checksum("27AAPFU0939F1Z") == "V"
    assert expected_checksum(first14) == "W"
    assert make_gstin("29", "ABCDE1234F") == "29ABCDE1234F1ZW"


def test_bad_state_code_fails_state_only():
    gstin = make_gstin("98", "AAPFU0939F")
    parts = validate_gstin_parts(gstin)

    assert parts["loose_structure_ok"] is True
    assert parts["state_ok"] is False
    assert parts["pan_ok"] is True
    assert parts["checksum_ok"] is True


def test_bad_pan_fails_embedded_pan():
    first14 = "27A1PFU0939F1Z"
    gstin = first14 + expected_checksum(first14)
    parts = validate_gstin_parts(gstin)

    assert parts["loose_structure_ok"] is False
    assert parts["state_ok"] is True
    assert parts["pan_ok"] is False
    assert parts["checksum_ok"] is True


def test_bad_checksum_fails_checksum():
    gstin = "27AAPFU0939F1ZA"
    parts = validate_gstin_parts(gstin)

    assert parts["loose_structure_ok"] is True
    assert parts["expected_checksum"] == "V"
    assert parts["checksum_ok"] is False


def test_bad_length_fails_structure():
    parts = validate_gstin_parts("27AAPFU0939F1Z")

    assert parts["structure_ok"] is False
    assert parts["loose_structure_ok"] is False
