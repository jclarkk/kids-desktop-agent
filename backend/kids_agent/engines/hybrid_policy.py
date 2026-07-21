"""Pure heuristics for hybrid local-first / cloud-escalate routing.

No I/O — safe to unit test with AppConfig fixtures.
"""

from __future__ import annotations

import re
from typing import Literal

from kids_agent.config import AppConfig
from kids_agent.engines.base import EngineResult

Route = Literal["local", "cloud"]

# Default phrases that suggest the local model may struggle.
DEFAULT_CLOUD_KEYWORDS: tuple[str, ...] = (
    "explain why",
    "explain how",
    "why does",
    "how does",
    "what is the difference",
    "difference between",
    "compare",
    "research",
    "look up",
    "translate",
    "in spanish",
    "in french",
    "in german",
    "in hebrew",
    "in arabic",
    "calculate",
    "solve",
    "math problem",
    "homework",
    "definition of",
    "who invented",
    "when was",
    "history of",
)

_MATH_HINT = re.compile(
    r"(?:\d+\s*[\+\-\*/×÷=]\s*\d+)|(?:what(?:'s| is)\s+\d+\s*[\+\-\*/×÷])",
    re.IGNORECASE,
)


def _word_count(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def choose_route(
    text: str,
    config: AppConfig,
    *,
    budget_ok: bool = True,
) -> Route:
    """Pick local or cloud for one hybrid turn.

    Defaults to local. Escalates to cloud only when an API key is present,
    budget allows, and heuristics say the turn is likely hard.
    """
    if not (config.cloud.api_key or "").strip():
        return "local"
    if not budget_ok:
        return "local"

    hybrid = config.hybrid
    cleaned = (text or "").strip()
    if not cleaned:
        return "local"

    threshold = max(1, int(hybrid.long_input_words))
    if _word_count(cleaned) >= threshold:
        return "cloud"

    lower = cleaned.lower()
    keywords = hybrid.cloud_keywords or list(DEFAULT_CLOUD_KEYWORDS)
    for kw in keywords:
        needle = (kw or "").strip().lower()
        if needle and needle in lower:
            return "cloud"

    if _MATH_HINT.search(cleaned):
        return "cloud"

    return "local"


def should_escalate(
    result: EngineResult | None,
    *,
    config: AppConfig,
    budget_ok: bool = True,
) -> bool:
    """True when a local hybrid turn should be retried on cloud once."""
    if result is None:
        return False
    if not config.hybrid.escalate_on_error:
        return False
    if not (config.cloud.api_key or "").strip():
        return False
    if not budget_ok:
        return False

    err = (result.error or "").strip().lower()
    if err in ("ollama_offline", "ollama_missing"):
        return True
    if err and err not in ("content_filter", "over_budget", "time_limit", "missing_api_key"):
        # Local HTTP / unexpected engine failures
        return True

    text = (result.assistant_text or "").strip()
    if not text and not result.tool_calls:
        return True

    return False
