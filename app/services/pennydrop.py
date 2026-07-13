"""Mock penny-drop bank verification backed by local JSON directory."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import get_settings

_client: MockPennyDropClient | None = None


class MockPennyDropClient:
    def __init__(self, path: Path | None = None):
        settings = get_settings()
        self.path = path or settings.data_dir / "mock_bank_directory.json"
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
                    str(key): record
                    for key, record in records.items()
                    if isinstance(record, dict)
                }

        return {}

    @staticmethod
    def _key(account_number: str, ifsc: str) -> str:
        return f"{(account_number or '').strip()}|{(ifsc or '').strip().upper()}"

    async def verify(self, account_number: str, ifsc: str) -> dict:
        record = self._records.get(self._key(account_number, ifsc))
        if not record:
            return {"account_exists": False, "active": None, "registered_name": None}

        return {
            "account_exists": True,
            "active": record.get("active"),
            "registered_name": record.get("registered_name"),
        }


async def verify(account_number: str, ifsc: str, beneficiary_name: str | None = None) -> dict:
    """Verify bank account details through the mock bank directory."""
    del beneficiary_name  # lookup is keyed only by account number and IFSC
    global _client
    if _client is None:
        _client = MockPennyDropClient()
    return await _client.verify(account_number, ifsc)
