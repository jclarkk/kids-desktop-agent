from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

import httpx

from kids_agent.config import AppConfig, KidProfile

FilterDirection = Literal["input", "output"]

KID_SAFE_REFUSAL = (
    "I can't help with that. Let's ask a safe question instead, like animals, space, words, or a game!"
)


@dataclass(frozen=True)
class FilterResult:
    ok: bool
    reason: str | None = None
    source: str = "local"


LOCAL_BLOCK_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(kill myself|suicide|self harm|hurt myself)\b", "self_harm"),
    (r"\b(how to kill|murder|stab|shoot|bomb|poison)\b", "violence"),
    (r"\b(sex|porn|nude|naked|onlyfans)\b", "sexual"),
    (r"\b(bypass|disable|turn off|hack)\b.{0,40}\b(parent|pin|control|filter|safety)\b", "bypass"),
    (r"\b(api key|password|credit card|address|phone number)\b", "private_info"),
)

STRICT_EXTRA_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\b(gun|knife|weapon|blood)\b", "strict_violence"),
    (r"\b(secret from (mom|dad|parent|grown[- ]?up))\b", "unsafe_secrecy"),
)


def _local_check(text: str, strictness: str) -> FilterResult:
    normalized = " ".join(text.lower().split())
    patterns = list(LOCAL_BLOCK_PATTERNS)
    if strictness == "strict":
        patterns.extend(STRICT_EXTRA_PATTERNS)
    for pattern, reason in patterns:
        if re.search(pattern, normalized):
            return FilterResult(ok=False, reason=reason, source="local")
    return FilterResult(ok=True)


def _should_call_cloud(config: AppConfig) -> bool:
    if config.ai_mode == "local" or not config.cloud.api_key:
        return False
    # OpenAI exposes /moderations on the same API host. Other OpenAI-compatible
    # routers often don't, so local filtering remains the hard safety floor.
    return config.cloud.provider == "openai" or "api.openai.com" in config.cloud.base_url


async def _cloud_check(config: AppConfig, text: str) -> FilterResult:
    if not _should_call_cloud(config):
        return FilterResult(ok=True, source="cloud_skipped")

    url = f"{config.cloud.base_url.rstrip('/')}/moderations"
    headers = {
        "Authorization": f"Bearer {config.cloud.api_key}",
        "Content-Type": "application/json",
    }
    body = {"model": "omni-moderation-latest", "input": text}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        # Do not block kids because an optional provider moderation endpoint is
        # down; the local gate already ran before this.
        return FilterResult(ok=True, source="cloud_error")

    result = (data.get("results") or [{}])[0]
    if result.get("flagged"):
        categories = result.get("categories") or {}
        reason = next((k for k, v in categories.items() if v), "moderation")
        return FilterResult(ok=False, reason=str(reason), source="cloud")
    return FilterResult(ok=True, source="cloud")


async def screen_text(
    config: AppConfig,
    text: str,
    *,
    kid: KidProfile | None = None,
    direction: FilterDirection,
) -> FilterResult:
    if not text.strip():
        return FilterResult(ok=True)

    strictness = (config.safety.content_strictness or "strict").strip().lower()
    local = _local_check(text, strictness)
    if not local.ok:
        return local

    # Younger kids stay on strict local handling; cloud moderation adds coverage
    # for cloud LLM paths where provider support exists.
    if kid and kid.age <= 5:
        strictness = "strict"
    return await _cloud_check(config, text)
