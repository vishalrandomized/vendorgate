"""PAN format helpers (embedded in GSTIN)."""
from __future__ import annotations

import re

PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")


def is_valid_pan(pan: str) -> bool:
    return bool(PAN_REGEX.match((pan or "").strip().upper()))
