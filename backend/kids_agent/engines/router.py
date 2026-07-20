from __future__ import annotations

from typing import Any

from kids_agent.config import AppConfig
from kids_agent.engines.base import EngineResult, VoiceEngine
from kids_agent.engines.cascade_cloud import CascadeCloudEngine
from kids_agent.engines.local_ollama import LocalOllamaEngine


class EngineRouter(VoiceEngine):
    """Routes to cloud, local, or hybrid (cloud LLM with local-ready speech stack)."""

    def __init__(self, config: AppConfig, tools_schema: list[dict[str, Any]]) -> None:
        self.config = config
        self.tools_schema = tools_schema
        self.cloud = CascadeCloudEngine(config, tools_schema)
        self.local = LocalOllamaEngine(config, tools_schema)

    def dialect(self) -> str:
        return "ollama" if self._llm_engine() is self.local else "openai"

    def _llm_engine(self) -> VoiceEngine:
        mode = self.config.ai_mode
        if mode == "local":
            return self.local
        if mode == "hybrid":
            if self.config.cloud.api_key:
                return self.cloud
            return self.local
        return self.cloud

    async def handle_text(self, text: str, *, system_prompt: str) -> EngineResult:
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
