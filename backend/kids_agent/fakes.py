"""Deterministic fakes for e2e / CI (no live LLM, no real OS input)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image

from kids_agent.engines.base import EngineResult, ToolCall, VoiceEngine


class FakeOS:
    """In-memory OS adapter for tests and KDA_E2E_STUB_ENGINE."""

    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []
        self.opened_apps: list[dict[str, Any]] = []
        self.opened_urls: list[str] = []
        self.volumes: list[int] = []

    def open_app(self, launch: dict[str, Any]) -> str:
        self.opened_apps.append(launch)
        return f"opened:{launch.get('command')}"

    def open_url(self, url: str) -> str:
        self.opened_urls.append(url)
        return f"opened:{url}"

    def set_volume(self, level: int) -> str:
        self.volumes.append(level)
        return f"vol:{level}"

    def list_windows(self) -> list[str]:
        return ["E2E Window"]

    def screenshot(self, path: str) -> str:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (800, 400), color=(40, 50, 60)).save(path)
        return "shot ok"

    def click(self, x: int, y: int) -> str:
        self.clicks.append((x, y))
        return f"click {x},{y}"

    def type_text(self, text: str) -> str:
        self.typed.append(text)
        return f"typed:{len(text)}"


class StubEngine(VoiceEngine):
    """Scriptable LLM for e2e. Default: friendly text, no tools."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        # Queue of EngineResult for successive chat() calls; empty → default reply
        self.script: list[EngineResult] = []
        self.default_text = "Hello from stub engine!"

    def dialect(self) -> str:
        return "openai"

    def enqueue(self, *results: EngineResult) -> None:
        self.script.extend(results)

    def enqueue_screenshot_then_done(self) -> None:
        self.enqueue(
            EngineResult(
                assistant_text="Looking at the screen.",
                tool_calls=[ToolCall(id="stub1", name="computer_screenshot", arguments={})],
                raw_assistant_message={
                    "role": "assistant",
                    "content": "Looking at the screen.",
                    "tool_calls": [
                        {
                            "id": "stub1",
                            "type": "function",
                            "function": {"name": "computer_screenshot", "arguments": "{}"},
                        }
                    ],
                },
            ),
            EngineResult(assistant_text="I see the desktop."),
        )

    async def handle_text(self, text: str, *, system_prompt: str) -> EngineResult:
        return await self.chat(
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ]
        )

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools_schema: list[dict[str, Any]] | None = None,
    ) -> EngineResult:
        user = ""
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                user = str(msg["content"])
        self.calls.append(user)
        if self.script:
            return self.script.pop(0)
        return EngineResult(user_transcript=user, assistant_text=self.default_text)
