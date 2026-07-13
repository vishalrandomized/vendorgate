"""GSTIN structure, state decode, embedded PAN, and Luhn mod-36 checksum."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

GSTIN_REGEX = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
)
# Same pattern but position 14 may be non-Z (soft flag case)
GSTIN_STRUCTURE_LOOSE = re.compile(
    r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][A-Z0-9][0-9A-Z]$"
)
PAN_EMBEDDED = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
C = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


@lru_cache
def load_state_codes() -> dict[str, str]:
    path = Path(__file__).resolve().parents[2] / "data" / "state_codes.json"
    return json.loads(path.read_text())


def expected_checksum(first14: str) -> str:
    total = 0
    for i, ch in enumerate(first14):
        v = C.index(ch)
        factor = 2 if (i % 2 == 1) else 1
        p = v * factor
        total += p // 36 + p % 36
    return C[(36 - total % 36) % 36]


def compute_checksum(first14: str) -> str:
    return expected_checksum(first14)


def make_gstin(state: str, pan: str, entity: str = "1", taxpayer_type: str = "Z") -> str:
    """Build a valid 15-char GSTIN from parts (used by fixtures)."""
    first14 = f"{state}{pan}{entity}{taxpayer_type}"
    return first14 + expected_checksum(first14)


def decode_state(gstin: str) -> str | None:
    if len(gstin) < 2:
        return None
    return load_state_codes().get(gstin[:2].upper())


def validate_gstin_parts(gstin: str) -> dict:
    """
    Return structured validation findings for Gate 3.
    Keys: structure_ok, nonstandard_taxpayer_type, state_ok, state_name,
          pan_ok, checksum_ok, expected_checksum, evidence bits.
    """
    g = (gstin or "").strip().upper()
    out = {
        "normalized": g,
        "structure_ok": bool(GSTIN_REGEX.match(g)),
        "loose_structure_ok": bool(GSTIN_STRUCTURE_LOOSE.match(g)),
        "nonstandard_taxpayer_type": False,
        "state_ok": False,
        "state_name": None,
        "pan_ok": False,
        "checksum_ok": False,
        "expected_checksum": None,
    }
    if len(g) != 15:
        return out

    if out["loose_structure_ok"] and not out["structure_ok"]:
        # position 14 (0-indexed 13) is not Z
        if g[13] != "Z":
            out["nonstandard_taxpayer_type"] = True

    state_name = decode_state(g)
    out["state_name"] = state_name
    out["state_ok"] = state_name is not None

    pan = g[2:12]
    out["pan_ok"] = bool(PAN_EMBEDDED.match(pan))

    try:
        exp = expected_checksum(g[:14])
        out["expected_checksum"] = exp
        out["checksum_ok"] = g[14] == exp
    except ValueError:
        out["checksum_ok"] = False

    return out
