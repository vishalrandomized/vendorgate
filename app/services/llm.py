"""Sarvam chat helpers used by pipeline adjudication."""
from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.config import get_settings

SARVAM_CHAT_URL = "https://api.sarvam.ai/v1/chat/completions"
JSON_ONLY_INSTRUCTION = (
    "Respond with a single raw JSON object. No markdown fences, no preamble, "
    "no trailing text."
)


async def chat(messages: list[dict[str, str]], **kwargs: Any) -> dict[str, Any]:
    """Thin wrapper around Sarvam chat completions.

    The model is always read from settings unless explicitly overridden by a caller.
    """
    settings = get_settings()
    if not settings.sarvam_api_key:
        raise RuntimeError("Sarvam API key is not configured")

    payload: dict[str, Any] = {
        "model": kwargs.pop("model", settings.sarvam_model),
        "messages": messages,
        "temperature": kwargs.pop("temperature", 0.1),
    }
    # Prefer explicit disable of reasoning for structured extraction unless overridden.
    if "reasoning_effort" not in kwargs:
        payload["reasoning_effort"] = None
    payload.update(kwargs)

    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.post(
            SARVAM_CHAT_URL,
            headers={"api-subscription-key": settings.sarvam_api_key},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def _json_content(response: dict[str, Any]) -> str:
    message = response.get("choices", [{}])[0].get("message", {}) or {}
    content = message.get("content") or ""
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return content


def _strip_fences(content: str) -> str:
    stripped = (content or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, re.DOTALL | re.I)
    if fenced:
        return fenced.group(1).strip()
    # Defensive: extract first JSON object if model adds preamble
    match = re.search(r"\{.*\}", stripped, re.DOTALL)
    if match:
        return match.group(0).strip()
    return stripped.strip("` \n\t")


async def strict_json(
    system: str,
    user: str,
    schema_hint: str,
    max_retries: int = 1,
) -> dict | None:
    """Ask Sarvam for one JSON object and parse it defensively.

    Parse failures are retried with the parser error appended to the user message.
    HTTP/configuration failures return None so gates can contain failures locally.
    """
    system_prompt = system or ""
    if JSON_ONLY_INSTRUCTION not in system_prompt:
        system_prompt = f"{system_prompt.rstrip()}\n\n{JSON_ONLY_INSTRUCTION}".strip()

    hint = schema_hint if isinstance(schema_hint, str) else json.dumps(schema_hint)
    base_user = f"{user.rstrip()}\n\nSchema hint:\n{hint.strip()}"
    retry_user = base_user

    for attempt in range(max_retries + 1):
        try:
            response = await chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": retry_user},
                ],
                max_tokens=2048,
                reasoning_effort=None,
            )
            return json.loads(_strip_fences(_json_content(response)))
        except json.JSONDecodeError as exc:
            if attempt >= max_retries:
                return None
            retry_user = (
                f"{base_user}\n\nPrevious response could not be parsed as JSON: {exc}. "
                "Return only a valid raw JSON object."
            )
        except (httpx.HTTPError, RuntimeError, KeyError, IndexError, TypeError):
            return None

    return None
