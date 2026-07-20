from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from kids_agent.config import AppConfig
from kids_agent.engines.base import EngineResult, ToolCall, VoiceEngine


SYSTEM_FALLBACK = (
    "You are a friendly English-teaching desktop helper for children ages 4–7. "
    "Use short, simple sentences. Be warm and encouraging. "
    "You may call tools only when the child clearly asks to open something or change volume. "
    "Never invent tools. If you cannot help safely, say so gently."
)


def _parse_tool_calls(message: dict[str, Any]) -> list[ToolCall]:
    tool_calls: list[ToolCall] = []
    for raw in message.get("tool_calls") or []:
        fn = raw.get("function") or {}
        args_raw = fn.get("arguments") or "{}"
        try:
            args = json.loads(args_raw) if isinstance(args_raw, str) else dict(args_raw)
        except json.JSONDecodeError:
            args = {}
        tool_calls.append(
            ToolCall(
                id=raw.get("id") or str(uuid.uuid4()),
                name=fn.get("name") or "",
                arguments=args,
                raw=raw,
            )
        )
    return tool_calls


class CascadeCloudEngine(VoiceEngine):
    """Cheap path: text (or future STT) → OpenAI-compatible chat with tools → text (TTS later)."""

    def __init__(self, config: AppConfig, tools_schema: list[dict[str, Any]]) -> None:
        self.config = config
        self.tools_schema = tools_schema

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.config.cloud.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.cloud.provider == "openrouter":
            headers["HTTP-Referer"] = "https://github.com/jclarkk/kids-desktop-agent"
            headers["X-Title"] = "Kids Desktop Agent"
        return headers

    async def handle_text(self, text: str, *, system_prompt: str) -> EngineResult:
        messages = [
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

        if not self.config.cloud.api_key:
            return EngineResult(
                user_transcript=user_text,
                assistant_text=(
                    "I need an API key before I can chat. "
                    "A parent can add one in Settings (OpenRouter, OpenAI, or Gemini)."
                ),
                error="missing_api_key",
            )

        schema = tools_schema if tools_schema is not None else self.tools_schema
        body: dict[str, Any] = {
            "model": self.config.cloud.chat_model,
            "messages": messages,
        }
        if schema:
            body["tools"] = schema
            body["tool_choice"] = "auto"

        url = f"{self.config.cloud.base_url.rstrip('/')}/chat/completions"
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(url, headers=self._headers(), json=body)
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            return EngineResult(
                user_transcript=user_text,
                assistant_text="Sorry, I had trouble thinking just now. Please try again.",
                error=str(exc),
            )

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        if isinstance(content, list):
            content = " ".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        tool_calls = _parse_tool_calls(message)

        if not content and tool_calls:
            names = ", ".join(t.name for t in tool_calls)
            content = f"Okay — I'll try: {names}."

        return EngineResult(
            user_transcript=user_text,
            assistant_text=str(content).strip() or "Okay!",
            tool_calls=tool_calls,
            raw_assistant_message=message,
        )
