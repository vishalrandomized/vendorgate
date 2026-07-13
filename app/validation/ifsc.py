"""IFSC format validation."""
from __future__ import annotations

import re

IFSC_REGEX = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")


def is_valid_ifsc(ifsc: str) -> bool:
    return bool(IFSC_REGEX.match((ifsc or "").strip().upper()))
