"""OpenSanctions screening client with SQLite fallback cache."""
from __future__ import annotations

import json
from typing import Any

import httpx
from sqlmodel import Session

from app.config import get_settings
from app.models import SanctionsCache, utcnow
from app.validation.names import normalize

OPENSANCTIONS_MATCH_URL = "https://api.opensanctions.org/match/default"


def _cached_payload(cache: SanctionsCache | None) -> dict[str, Any] | None:
    if cache is None:
        return None
    try:
        return json.loads(cache.response_json)
    except json.JSONDecodeError:
        return None


def _summarize_response(raw: dict[str, Any]) -> dict[str, Any]:
    results = raw.get("responses", {}).get("q", {}).get("results", []) or []
    if not results:
        return {
            "top_score": 0.0,
            "top_caption": None,
            "datasets": [],
            "raw": raw,
        }

    top = max(results, key=lambda item: float(item.get("score") or 0.0))
    datasets = top.get("datasets") or []
    if isinstance(datasets, dict):
        datasets = list(datasets.keys())

    return {
        "top_score": float(top.get("score") or 0.0),
        "top_caption": top.get("caption"),
        "datasets": datasets,
        "raw": raw,
    }


def severity_guidance(score: float) -> str:
    """Human-readable guidance; Gate 5 owns final severity mapping."""
    if score >= 0.85:
        return "hard_fail"
    if score >= 0.50:
        return "manual_review"
    return "pass"


def _from_cache(cache: SanctionsCache | None, error: str) -> dict[str, Any]:
    cached = _cached_payload(cache)
    if cached is not None:
        return {
            **_summarize_response(cached),
            "source": "cache",
            "error": error,
            "fetched_at": cache.fetched_at.isoformat(),
        }
    return {
        "top_score": 0.0,
        "top_caption": None,
        "datasets": [],
        "raw": None,
        "source": "unavailable",
        "error": error,
    }


async def screen_company(legal_name: str, session: Session) -> dict:
    """Screen a company name against OpenSanctions.

    Returns top match evidence plus source: live, cache, or unavailable.
    """
    settings = get_settings()
    normalized_name = normalize(legal_name)
    cache = session.get(SanctionsCache, normalized_name)

    if not normalized_name:
        return {
            "top_score": 0.0,
            "top_caption": None,
            "datasets": [],
            "raw": None,
            "source": "unavailable",
            "error": "Legal name is empty",
        }

    if not settings.opensanctions_api_key:
        return _from_cache(cache, "OpenSanctions API key is not configured")

    body = {
        "queries": {
            "q": {
                "schema": "Company",
                "properties": {"name": [legal_name]},
            }
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                OPENSANCTIONS_MATCH_URL,
                headers={"Authorization": f"ApiKey {settings.opensanctions_api_key}"},
                json=body,
            )
            response.raise_for_status()
            raw = response.json()
    except httpx.HTTPError as exc:
        return _from_cache(cache, str(exc))

    cache_row = SanctionsCache(
        normalized_name=normalized_name,
        response_json=json.dumps(raw),
        fetched_at=utcnow(),
    )
    session.merge(cache_row)
    session.commit()

    return {**_summarize_response(raw), "source": "live"}
