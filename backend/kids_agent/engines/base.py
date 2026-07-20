from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class EngineResult:
    user_transcript: str = ""
    assistant_text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    audio_pcm16_b64: str | None = None
    error: str | None = None
    raw_assistant_message: dict[str, Any] | None = None


class VoiceEngine(ABC):
    """Shared interface for cloud cascade, realtime, and local engines."""

    @abstractmethod
    async def handle_text(self, text: str, *, system_prompt: str) -> EngineResult:
        raise NotImplementedError

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools_schema: list[dict[str, Any]] | None = None,
    ) -> EngineResult:
        """Multi-turn chat used by the vision/tool agent loop. Override in engines."""
        # Fallback: only last user text
        text = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content")
                if isinstance(content, str):
                    text = content
                elif isinstance(content, list):
                    text = " ".join(
                        str(p.get("text", "")) for p in content if isinstance(p, dict)
                    )
                break
        return await self.handle_text(text, system_prompt="")

    async def handle_audio(
        self, pcm16: bytes, *, sample_rate: int, system_prompt: str
    ) -> EngineResult:
        """Optional: engines may override for STT. Default rejects."""
        return EngineResult(error="Audio input not implemented for this engine yet")
