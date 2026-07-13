"""Name normalization + rapidfuzz similarity (0–1)."""
from __future__ import annotations

import re

from rapidfuzz import fuzz

SUFFIXES = [
    "PRIVATE LIMITED",
    "PVT. LTD.",
    "PVT LTD.",
    "PVT LTD",
    "LIMITED",
    "LTD",
    "LLP",
    "LLC",
    "INC",
    "INCORPORATED",
    "CORP",
    "CORPORATION",
    "CO",
]


def normalize(name: str) -> str:
    s = re.sub(r"[^\w\s]", " ", (name or "").upper())
    s = re.sub(r"\s+", " ", s).strip()
    # longest-first already ordered in SUFFIXES
    for suf in SUFFIXES:
        if s.endswith(" " + suf):
            s = s[: -len(suf)].strip()
            break
        if s == suf:
            s = ""
            break
    return s


def similarity(a: str, b: str) -> float:
    na, nb = normalize(a), normalize(b)
    if not na and not nb:
        return 1.0
    if not na or not nb:
        return 0.0
    return fuzz.token_sort_ratio(na, nb) / 100.0


# Locked thresholds (§8.2). Pass is s >= 0.85 (inclusive).
# EC-1 uses Meridian Enterprises vs MERIDIAN LOGISTICS → band [0.60, 0.85).
PASS_THRESHOLD = 0.85
BAND_LOW = 0.60
