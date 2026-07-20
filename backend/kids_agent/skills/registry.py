from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from kids_agent.computer_use import ActionName, ComputerUseGate, ExecuteResult
from kids_agent.config import AppConfig
from kids_agent.os_adapter.base import OSAdapter

SkillHandler = Callable[[dict[str, Any]], Awaitable["SkillResult"]]


@dataclass
class SkillResult:
    message: str
    ok: bool = True
    needs_approval: bool = False
    screenshot_path: str | None = None
    execute: ExecuteResult | None = None
    timer_seconds: int | None = None
    timer_label: str | None = None


class SkillRegistry:
    def __init__(
        self,
        config: AppConfig,
        os_adapter: OSAdapter,
        computer_use: ComputerUseGate | None = None,
    ) -> None:
        self.config = config
        self.os = os_adapter
        self.computer_use = computer_use
        self._handlers: dict[str, SkillHandler] = {
            "open_app": self.open_app,
            "open_website": self.open_website,
            "set_volume": self.set_volume,
            "start_timer": self.start_timer,
            "list_windows": self.list_windows,
            "computer_screenshot": self.computer_screenshot,
            "computer_click": self.computer_click,
            "computer_type": self.computer_type,
        }

    def enabled(self, name: str) -> bool:
        if name.startswith("computer_"):
            return bool(self.computer_use and self.computer_use.enabled())
        return name in self.config.allowlist.skills_enabled

    def tools_schema(self) -> list[dict[str, Any]]:
        schemas: list[dict[str, Any]] = []
        if self.enabled("open_app"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "open_app",
                        "description": "Open an allowlisted desktop application by id.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "app_id": {
                                    "type": "string",
                                    "description": "Allowlisted app id, e.g. notepad",
                                }
                            },
                            "required": ["app_id"],
                        },
                    },
                }
            )
        if self.enabled("open_website"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "open_website",
                        "description": "Open an allowlisted website by id.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "site_id": {"type": "string"},
                            },
                            "required": ["site_id"],
                        },
                    },
                }
            )
        if self.enabled("set_volume"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "set_volume",
                        "description": "Set system volume 0-100.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "level": {"type": "integer", "minimum": 0, "maximum": 100},
                            },
                            "required": ["level"],
                        },
                    },
                }
            )
        if self.enabled("start_timer"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "start_timer",
                        "description": "Start a fun countdown timer in seconds.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "seconds": {"type": "integer", "minimum": 1, "maximum": 3600},
                                "label": {"type": "string"},
                            },
                            "required": ["seconds"],
                        },
                    },
                }
            )
        if self.enabled("list_windows"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "list_windows",
                        "description": "List open window titles.",
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
        if self.enabled("computer_screenshot"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "computer_screenshot",
                        "description": (
                            "Capture the primary screen and look at it (vision). "
                            "Requires parent PIN approval or an active computer-use session. "
                            "Prefer allowlisted open_app/open_website when possible. "
                            "After the screenshot, you will receive the image — then use "
                            "computer_click with image pixel coordinates if needed."
                        ),
                        "parameters": {"type": "object", "properties": {}},
                    },
                }
            )
        if self.enabled("computer_click"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "computer_click",
                        "description": (
                            "Click using pixel coordinates from the latest screenshot IMAGE "
                            "(0,0 top-left of the attached image). Requires PIN / session."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "x": {"type": "integer", "minimum": 0},
                                "y": {"type": "integer", "minimum": 0},
                            },
                            "required": ["x", "y"],
                        },
                    },
                }
            )
        if self.enabled("computer_type"):
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": "computer_type",
                        "description": (
                            "Type text with the keyboard (max 200 chars). "
                            "Requires parent PIN / active computer-use session."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "text": {"type": "string"},
                            },
                            "required": ["text"],
                        },
                    },
                }
            )
        return schemas

    async def run(self, name: str, arguments: dict[str, Any]) -> SkillResult:
        if not self.enabled(name):
            return SkillResult(message="That action is turned off by a parent.", ok=False)
        handler = self._handlers.get(name)
        if not handler:
            return SkillResult(message="I don't know how to do that yet.", ok=False)
        return await handler(arguments)

    async def open_app(self, arguments: dict[str, Any]) -> SkillResult:
        app_id = str(arguments.get("app_id", "")).strip()
        app = next((a for a in self.config.allowlist.apps if a.id == app_id), None)
        if not app:
            return SkillResult(
                message="That app is not on the allowlist. Ask a parent to add it.",
                ok=False,
            )
        import platform

        system = platform.system().lower()
        launch = app.windows if system == "windows" else app.macos
        return SkillResult(message=self.os.open_app(launch))

    async def open_website(self, arguments: dict[str, Any]) -> SkillResult:
        site_id = str(arguments.get("site_id", "")).strip()
        site = next((s for s in self.config.allowlist.websites if s.id == site_id), None)
        if not site:
            return SkillResult(
                message="That website is not on the allowlist. Ask a parent to add it.",
                ok=False,
            )
        return SkillResult(message=self.os.open_url(site.url))

    async def set_volume(self, arguments: dict[str, Any]) -> SkillResult:
        try:
            level = int(arguments.get("level", 50))
        except (TypeError, ValueError):
            return SkillResult(message="I need a volume number from 0 to 100.", ok=False)
        return SkillResult(message=self.os.set_volume(level))

    async def start_timer(self, arguments: dict[str, Any]) -> SkillResult:
        try:
            seconds = int(arguments.get("seconds", 0))
        except (TypeError, ValueError):
            return SkillResult(message="I need a number of seconds for the timer.", ok=False)
        if seconds < 1 or seconds > 3600:
            return SkillResult(message="Timers can be between 1 second and 1 hour.", ok=False)
        label = str(arguments.get("label") or "Timer")
        return SkillResult(
            message=f"Started timer '{label}' for {seconds} seconds.",
            timer_seconds=seconds,
            timer_label=label,
        )

    async def list_windows(self, arguments: dict[str, Any]) -> SkillResult:
        titles = self.os.list_windows()
        if not titles:
            return SkillResult(message="I don't see any windows right now.")
        return SkillResult(message="Open windows: " + "; ".join(titles))

    async def _computer(self, name: ActionName, arguments: dict[str, Any]) -> SkillResult:
        if not self.computer_use:
            return SkillResult(message="Computer use is not available.", ok=False)
        result = await self.computer_use.request(name, arguments)
        return SkillResult(
            message=result.message,
            ok=result.ok,
            needs_approval=result.needs_approval,
            screenshot_path=result.screenshot_path,
            execute=result,
        )

    async def computer_screenshot(self, arguments: dict[str, Any]) -> SkillResult:
        return await self._computer("computer_screenshot", arguments)

    async def computer_click(self, arguments: dict[str, Any]) -> SkillResult:
        return await self._computer("computer_click", arguments)

    async def computer_type(self, arguments: dict[str, Any]) -> SkillResult:
        return await self._computer("computer_type", arguments)
