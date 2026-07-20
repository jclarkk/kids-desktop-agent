from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from kids_agent.engines.base import EngineResult, VoiceEngine
from kids_agent.skills.registry import SkillRegistry, SkillResult
from kids_agent.vision import VisionFrame, ollama_image_message, openai_image_message


@dataclass
class AgentLoopResult:
    assistant_text: str
    user_transcript: str = ""
    error: str | None = None
    tool_notes: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    paused_for_approval: bool = False
    messages: list[dict[str, Any]] = field(default_factory=list)
    vision_steps: int = 0


def _assistant_message_for_api(
    result: EngineResult, *, dialect: Literal["openai", "ollama"]
) -> dict[str, Any]:
    if result.raw_assistant_message:
        msg = dict(result.raw_assistant_message)
        # Ensure content is string for tool rounds
        if msg.get("content") is None:
            msg["content"] = result.assistant_text or ""
        return msg
    msg: dict[str, Any] = {
        "role": "assistant",
        "content": result.assistant_text or "",
    }
    if result.tool_calls:
        if dialect == "openai":
            msg["tool_calls"] = [
                t.raw
                or {
                    "id": t.id,
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "arguments": __import__("json").dumps(t.arguments),
                    },
                }
                for t in result.tool_calls
            ]
        else:
            msg["tool_calls"] = [
                {"function": {"name": t.name, "arguments": t.arguments}} for t in result.tool_calls
            ]
    return msg


def _tool_message(
    call_id: str,
    name: str,
    content: str,
    *,
    dialect: Literal["openai", "ollama"],
) -> dict[str, Any]:
    if dialect == "openai":
        return {"role": "tool", "tool_call_id": call_id, "content": content}
    return {"role": "tool", "content": content, "name": name}


def _vision_followup(
    frame: VisionFrame, *, dialect: Literal["openai", "ollama"]
) -> dict[str, Any]:
    if dialect == "ollama":
        return ollama_image_message(frame)
    return openai_image_message(frame)


async def run_agent_loop(
    *,
    engine: VoiceEngine,
    skills: SkillRegistry,
    system_prompt: str,
    user_text: str,
    max_steps: int = 6,
    dialect: Literal["openai", "ollama"] = "openai",
    messages: list[dict[str, Any]] | None = None,
    on_skill: Any = None,
) -> AgentLoopResult:
    """Run chat → tools → (vision image) → chat until done or PIN pause."""
    if messages is None:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ]

    notes: list[str] = []
    recorded_calls: list[dict[str, Any]] = []
    vision_steps = 0
    last_text = ""
    last_error: str | None = None

    steps = max(1, min(12, int(max_steps)))
    for _ in range(steps):
        result = await engine.chat(messages, tools_schema=skills.tools_schema())
        last_text = result.assistant_text
        last_error = result.error
        if result.error and not result.tool_calls:
            return AgentLoopResult(
                assistant_text=result.assistant_text,
                user_transcript=user_text,
                error=result.error,
                tool_notes=notes,
                tool_calls=recorded_calls,
                messages=messages,
                vision_steps=vision_steps,
            )

        if not result.tool_calls:
            return AgentLoopResult(
                assistant_text=last_text or "Okay!",
                user_transcript=user_text,
                error=last_error,
                tool_notes=notes,
                tool_calls=recorded_calls,
                messages=messages,
                vision_steps=vision_steps,
            )

        messages.append(_assistant_message_for_api(result, dialect=dialect))

        paused = False
        for call in result.tool_calls:
            recorded_calls.append({"name": call.name, "arguments": call.arguments})
            skill_result: SkillResult = await skills.run(call.name, call.arguments)
            notes.append(f"{call.name}: {skill_result.message}")
            if on_skill:
                await on_skill(call, skill_result)

            messages.append(
                _tool_message(call.id, call.name, skill_result.message, dialect=dialect)
            )

            vision: VisionFrame | None = None
            if skill_result.execute and skill_result.execute.vision:
                vision = skill_result.execute.vision
            elif (
                skill_result.screenshot_path
                and skills.computer_use
                and skills.computer_use.last_vision
            ):
                vision = skills.computer_use.last_vision

            if vision and skill_result.ok:
                vision_steps += 1
                messages.append(_vision_followup(vision, dialect=dialect))

            if skill_result.needs_approval:
                paused = True
                break

        if paused:
            reply = last_text
            if notes:
                reply = (reply + "\n" + " ".join(notes)).strip()
            return AgentLoopResult(
                assistant_text=reply,
                user_transcript=user_text,
                error=last_error,
                tool_notes=notes,
                tool_calls=recorded_calls,
                paused_for_approval=True,
                messages=messages,
                vision_steps=vision_steps,
            )

    reply = last_text or "Okay!"
    if notes:
        reply = (reply + "\n" + " ".join(notes)).strip()
    return AgentLoopResult(
        assistant_text=reply,
        user_transcript=user_text,
        error=last_error,
        tool_notes=notes,
        tool_calls=recorded_calls,
        messages=messages,
        vision_steps=vision_steps,
    )
