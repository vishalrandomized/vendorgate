"""Day-1 morning smoke: Sarvam 105B strict-JSON extraction ×5."""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

# dotenv may not be installed yet — fall back to manual parse
if not os.getenv("SARVAM_API_KEY"):
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())

API_KEY = os.environ.get("SARVAM_API_KEY", "")
MODEL = os.environ.get("SARVAM_MODEL", "sarvam-105b")
URL = "https://api.sarvam.ai/v1/chat/completions"

SAMPLE = """
GSTIN: 27AABCM1234K1Z5
Legal Name: Meridian Trading Private Limited
Trade Name: Meridian
Principal Place of Business: Plot 14, Industrial Area, Pune, Maharashtra 411001
"""

SYSTEM = (
    "You extract fields from Indian GST registration certificates. "
    "Respond with a single raw JSON object. No markdown fences, no preamble, no trailing text."
)
USER = f"""Document text:
<<<{SAMPLE}>>>
Extract: {{"legal_name": str|null, "trade_name": str|null,
"gstin": str|null, "address_state": str|null,
"confidence": {{"legal_name": 0-1, "gstin": 0-1, "address_state": 0-1}}}}
Use null for anything not present. Confidence reflects how certain you are
the value is transcribed exactly as printed."""


def strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def one_call(client: httpx.AsyncClient, n: int) -> dict:
    resp = await client.post(
        URL,
        headers={
            "api-subscription-key": API_KEY,
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "temperature": 0.1,
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER},
            ],
        },
        timeout=90.0,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(strip_fences(content))
    print(f"[{n}] OK keys={sorted(parsed.keys())}")
    return parsed


async def main() -> int:
    if not API_KEY:
        print("FAIL: SARVAM_API_KEY empty — paste keys into vendorgate/.env")
        return 1
    print(f"model={MODEL}")
    async with httpx.AsyncClient() as client:
        for i in range(1, 6):
            try:
                await one_call(client, i)
            except Exception as e:
                print(f"[{i}] FAIL: {type(e).__name__}: {e}")
                return 1
    print("ALL 5 PASSES")
    return 0


if __name__ == "__main__":
    # Prefer python-dotenv if present; otherwise env already loaded above
    try:
        from dotenv import load_dotenv as _  # noqa: F401
    except ImportError:
        pass
    sys.exit(asyncio.run(main()))
