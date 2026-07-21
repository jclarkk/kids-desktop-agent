from __future__ import annotations

from typing import Any, Literal

from kids_agent.config import AppConfig
from kids_agent.engines.base import EngineResult, VoiceEngine
from kids_agent.engines.cascade_cloud import CascadeCloudEngine
from kids_agent.engines.hybrid_policy import Route, choose_route
from kids_agent.engines.local_ollama import LocalOllamaEngine


class EngineRouter(VoiceEngine):
    """Routes to cloud, local, or smart hybrid (local-first with cloud escalate)."""

    def __init__(self, config: AppConfig, tools_schema: list[dict[str, Any]]) -> None:
        self.config = config
        self.tools_schema = tools_schema
        self.cloud = CascadeCloudEngine(config, tools_schema)
        self.local = LocalOllamaEngine(config, tools_schema)
        self._route: Route | None = None

    @property
    def last_route(self) -> Route | None:
        return self._route

    def begin_turn(self, text: str, *, budget_ok: bool = True) -> Route:
        """Choose the engine for this user turn and stick to it until the next begin_turn."""
        mode = self.config.ai_mode
        if mode == "local":
            self._route = "local"
        elif mode == "hybrid":
            self._route = choose_route(text, self.config, budget_ok=budget_ok)
        else:
            self._route = "cloud"
        return self._route

    def force_cloud(self) -> Route:
        """Escalate the current hybrid turn to cloud (e.g. after a local failure)."""
        self._route = "cloud"
        return self._route

    def force_local(self) -> Route:
        """Pin the current turn to local (e.g. resume after PIN with a local dialect)."""
        self._route = "local"
        return self._route

    def dialect(self) -> Literal["openai", "ollama"]:
        return "ollama" if self._llm_engine() is self.local else "openai"

    def _llm_engine(self) -> VoiceEngine:
        mode = self.config.ai_mode
        if mode == "local":
            return self.local
        if mode == "hybrid":
            route = self._route or "local"
            if route == "cloud" and self.config.cloud.api_key:
                return self.cloud
            return self.local
        return self.cloud

    async def handle_text(self, text: str, *, system_prompt: str) -> EngineResult:
        # Direct calls are a fresh turn — re-run routing heuristics.
        if self.config.ai_mode == "hybrid":
            self.begin_turn(text, budget_ok=True)
        return await self._llm_engine().handle_text(text, system_prompt=system_prompt)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools_schema: list[dict[str, Any]] | None = None,
    ) -> EngineResult:
        return await self._llm_engine().chat(messages, tools_schema=tools_schema)

    async def handle_audio(
        self, pcm16: bytes, *, sample_rate: int, system_prompt: str
    ) -> EngineResult:
        return await self._llm_engine().handle_audio(
            pcm16, sample_rate=sample_rate, system_prompt=system_prompt
        )
