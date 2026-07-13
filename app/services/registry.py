"""Mock GST registry lookup backed by local JSON data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings


class MockGstRegistry:
    def __init__(self, path: Path | None = None):
        settings = get_settings()
        self.path = path or settings.data_dir / "mock_gst_registry.json"
        self._records = self._load()

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}

        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        if isinstance(data, dict):
            records = data.get("records", data)
            if isinstance(records, dict):
                return {
                    str(gstin).upper(): record
                    for gstin, record in records.items()
                    if isinstance(record, dict)
                }
            if isinstance(records, list):
                return {
                    str(record.get("gstin", "")).upper(): record
                    for record in records
                    if isinstance(record, dict) and record.get("gstin")
                }

        if isinstance(data, list):
            return {
                str(record.get("gstin", "")).upper(): record
                for record in data
                if isinstance(record, dict) and record.get("gstin")
            }

        return {}

    def lookup(self, gstin: str) -> dict:
        record = self._records.get((gstin or "").strip().upper())
        if not record:
            return {"found": False, "status": None, "legal_name": None}

        return {
            "found": True,
            "status": record.get("status"),
            "legal_name": record.get("legal_name") or record.get("legalName"),
        }
