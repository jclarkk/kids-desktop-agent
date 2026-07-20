from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from kids_agent.config import AppConfig
from kids_agent.engines.base import EngineResult, ToolCall, VoiceEngine
from kids_agent.engines.cascade_cloud import SYSTEM_FALLBACK


class LocalOllamaEngine(VoiceEngine):
    """Local LLM via Ollama chat API with tool calling (+ optional vision images)."""

    def __init__(self, config: AppConfig, tools_schema: list[dict[str, Any]]) -> None:
        self.config = config
        self.tools_schema = tools_schema

    @property
    def base_url(self) -> str:
        return self.config.local.ollama_base_url.rstrip("/")

    async def handle_text(self, text: str, *, system_prompt: str) -> EngineResult:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt or SYSTEM_FALLBACK},
            {"role": "user", "content": text},
        ]
        return await self.chat(messages, tools_schema=self.tools_schema)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        *,
        tools_schema: list[dict[str, Any]] | None = None,
    ) -> EngineResult:
        user_text = ""
        for msg in messages:
            if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                user_text = str(msg["content"])

        schema = tools_schema if tools_schema is not None else self.tools_schema
        body: dict[str, Any] = {
            "model": self.config.local.llm_model,
            "messages": messages,
            "stream": False,
        }
        if schema:
            body["tools"] = schema

        options: dict[str, Any] = {}
        gpu_layers = self.config.local.gpu_layers
        if isinstance(gpu_layers, int):
            options["num_gpu"] = gpu_layers
        elif isinstance(gpu_layers, str) and gpu_layers.isdigit():
            options["num_gpu"] = int(gpu_layers)
        if options:
            body["options"] = options

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(f"{self.base_url}/api/chat", json=body)
                if resp.status_code == 404:
                    return EngineResult(
                        user_transcript=user_text,
                        assistant_text=(
                            "I can't find Ollama. Install it from ollama.com, pull a model, "
                            "then pick Local mode in parent settings."
                        ),
                        error="ollama_missing",
                    )
                resp.raise_for_status()
                data = resp.json()
        except httpx.ConnectError:
            return EngineResult(
                user_transcript=user_text,
                assistant_text=(
                    "Ollama isn't running. Start Ollama, then try again "
                    f"(looking at {self.base_url})."
                ),
                error="ollama_offline",
            )
        except httpx.HTTPError as exc:
            return EngineResult(
                user_transcript=user_text,
                assistant_text="Sorry, my local brain had trouble. Please try again.",
                error=str(exc),
            )

        message = data.get("message") or {}
        content = message.get("content") or ""
        tool_calls: list[ToolCall] = []
        for raw in message.get("tool_calls") or []:
            fn = raw.get("function") or {}
            args = fn.get("arguments") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            tid = str(uuid.uuid4())
            tool_calls.append(
                ToolCall(
                    id=tid,
                    name=fn.get("name") or "",
                    arguments=dict(args),
                    raw=raw,
                )
            )

        if not content and tool_calls:
            names = ", ".join(t.name for t in tool_calls)
            content = f"Okay — I'll try: {names}."

        return EngineResult(
            user_transcript=user_text,
            assistant_text=content.strip() or "Okay!",
            tool_calls=tool_calls,
            raw_assistant_message=message,
        )
