"""Unit tests for smart hybrid routing (local-first + cloud escalate)."""

from __future__ import annotations

import pytest

from kids_agent.config import AppConfig, CloudConfig, HybridConfig
from kids_agent.engines.base import EngineResult, ToolCall
from kids_agent.engines.hybrid_policy import choose_route, should_escalate
from kids_agent.engines.router import EngineRouter


def _cfg(
    *,
    api_key: str = "test-key",
    long_input_words: int = 40,
    escalate_on_error: bool = True,
    cloud_keywords: list[str] | None = None,
) -> AppConfig:
    return AppConfig(
        ai_mode="hybrid",
        cloud=CloudConfig(api_key=api_key),
        hybrid=HybridConfig(
            long_input_words=long_input_words,
            cloud_keywords=cloud_keywords or [],
            escalate_on_error=escalate_on_error,
        ),
    )


def test_choose_route_easy_stays_local() -> None:
    cfg = _cfg()
    assert choose_route("Hi! Can we play a game?", cfg, budget_ok=True) == "local"
    assert choose_route("Open notepad please", cfg, budget_ok=True) == "local"


def test_choose_route_long_input_goes_cloud() -> None:
    cfg = _cfg(long_input_words=10)
    text = " ".join(["word"] * 12)
    assert choose_route(text, cfg, budget_ok=True) == "cloud"


def test_choose_route_keyword_goes_cloud() -> None:
    cfg = _cfg()
    assert choose_route("Please explain why the sky is blue", cfg) == "cloud"
    assert choose_route("Can you translate this sentence", cfg) == "cloud"


def test_choose_route_math_goes_cloud() -> None:
    cfg = _cfg()
    assert choose_route("What is 12 + 34?", cfg) == "cloud"
    assert choose_route("Please calculate 8 * 7", cfg) == "cloud"


def test_choose_route_no_key_or_over_budget_stays_local() -> None:
    hard = "Please explain why dinosaurs went extinct"
    assert choose_route(hard, _cfg(api_key=""), budget_ok=True) == "local"
    assert choose_route(hard, _cfg(), budget_ok=False) == "local"


def test_choose_route_custom_keywords() -> None:
    cfg = _cfg(cloud_keywords=["super hard"])
    assert choose_route("This is super hard for me", cfg) == "cloud"
    assert choose_route("Please explain why", cfg) == "local"


def test_should_escalate_on_ollama_errors() -> None:
    cfg = _cfg()
    assert should_escalate(
        EngineResult(error="ollama_offline", assistant_text="Ollama isn't running."),
        config=cfg,
        budget_ok=True,
    )
    assert should_escalate(
        EngineResult(error="ollama_missing"),
        config=cfg,
        budget_ok=True,
    )
    assert should_escalate(
        EngineResult(error="HTTP 500 boom"),
        config=cfg,
        budget_ok=True,
    )


def test_should_escalate_empty_answer() -> None:
    cfg = _cfg()
    assert should_escalate(EngineResult(assistant_text=""), config=cfg, budget_ok=True)
    assert not should_escalate(
        EngineResult(
            assistant_text="",
            tool_calls=[ToolCall(id="1", name="open_app", arguments={})],
        ),
        config=cfg,
        budget_ok=True,
    )


def test_should_not_escalate_when_disabled_or_no_budget() -> None:
    cfg = _cfg(escalate_on_error=False)
    assert not should_escalate(
        EngineResult(error="ollama_offline"),
        config=cfg,
        budget_ok=True,
    )
    cfg2 = _cfg()
    assert not should_escalate(
        EngineResult(error="ollama_offline"),
        config=cfg2,
        budget_ok=False,
    )
    assert not should_escalate(
        EngineResult(error="ollama_offline"),
        config=_cfg(api_key=""),
        budget_ok=True,
    )


def test_should_not_escalate_good_local_answer() -> None:
    cfg = _cfg()
    assert not should_escalate(
        EngineResult(assistant_text="Sure! Let's play."),
        config=cfg,
        budget_ok=True,
    )


def test_router_begin_turn_sticky_dialect() -> None:
    cfg = _cfg()
    router = EngineRouter(cfg, tools_schema=[])
    route = router.begin_turn("Hi friend", budget_ok=True)
    assert route == "local"
    assert router.dialect() == "ollama"
    assert router.last_route == "local"

    router.force_cloud()
    assert router.last_route == "cloud"
    assert router.dialect() == "openai"

    router.force_local()
    assert router.last_route == "local"
    assert router.dialect() == "ollama"


def test_router_hard_question_picks_cloud() -> None:
    cfg = _cfg()
    router = EngineRouter(cfg, tools_schema=[])
    assert router.begin_turn("Please explain why the moon has phases", budget_ok=True) == "cloud"
    assert router.dialect() == "openai"


def test_router_cloud_and_local_modes_ignore_heuristics() -> None:
    cloud_cfg = AppConfig(ai_mode="cloud", cloud=CloudConfig(api_key="k"))
    local_cfg = AppConfig(ai_mode="local", cloud=CloudConfig(api_key="k"))
    hard = "Please explain why gravity works"

    cloud_router = EngineRouter(cloud_cfg, tools_schema=[])
    assert cloud_router.begin_turn(hard) == "cloud"
    assert cloud_router.dialect() == "openai"

    local_router = EngineRouter(local_cfg, tools_schema=[])
    assert local_router.begin_turn(hard) == "local"
    assert local_router.dialect() == "ollama"


@pytest.mark.asyncio
async def test_router_chat_uses_selected_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _cfg()
    router = EngineRouter(cfg, tools_schema=[])
    router.begin_turn("hi", budget_ok=True)

    called: list[str] = []

    async def fake_local_chat(messages, *, tools_schema=None):  # type: ignore[no-untyped-def]
        called.append("local")
        return EngineResult(assistant_text="local-ok")

    async def fake_cloud_chat(messages, *, tools_schema=None):  # type: ignore[no-untyped-def]
        called.append("cloud")
        return EngineResult(assistant_text="cloud-ok")

    monkeypatch.setattr(router.local, "chat", fake_local_chat)
    monkeypatch.setattr(router.cloud, "chat", fake_cloud_chat)

    result = await router.chat([{"role": "user", "content": "hi"}])
    assert result.assistant_text == "local-ok"
    assert called == ["local"]

    router.force_cloud()
    result2 = await router.chat([{"role": "user", "content": "hi"}])
    assert result2.assistant_text == "cloud-ok"
    assert called == ["local", "cloud"]
