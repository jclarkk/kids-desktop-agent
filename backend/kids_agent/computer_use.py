from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from kids_agent.config import AppConfig, app_data_root
from kids_agent.os_adapter.base import OSAdapter
from kids_agent.safety import verify_pin
from kids_agent.vision import VisionFrame, prepare_screenshot_for_llm

ActionName = Literal["computer_screenshot", "computer_click", "computer_type"]


@dataclass
class PendingAction:
    id: str
    name: ActionName
    arguments: dict[str, Any]
    created_at: float = field(default_factory=time.time)


@dataclass
class ExecuteResult:
    ok: bool
    message: str
    needs_approval: bool = False
    pending_id: str | None = None
    screenshot_path: str | None = None
    vision: VisionFrame | None = None


class ComputerUseGate:
    """PIN-gated desktop control: screenshot / click / type (+ vision frames)."""

    def __init__(self, config: AppConfig, os_adapter: OSAdapter) -> None:
        self.config = config
        self.os = os_adapter
        self.session_until: float | None = None
        self.pending: PendingAction | None = None
        self.last_vision: VisionFrame | None = None
        self.last_result: ExecuteResult | None = None

    def screenshots_dir(self) -> Path:
        path = app_data_root() / "screenshots"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def mode(self) -> str:
        return self.config.computer_use.mode

    def enabled(self) -> bool:
        return self.mode() != "off"

    def session_active(self) -> bool:
        if self.session_until is None:
            return False
        if time.time() > self.session_until:
            self.session_until = None
            return False
        return True

    def status(self) -> dict[str, Any]:
        remaining = None
        if self.session_active() and self.session_until is not None:
            remaining = max(0, int(self.session_until - time.time()))
        pending = None
        if self.pending:
            pending = {
                "id": self.pending.id,
                "name": self.pending.name,
                "arguments": self.pending.arguments,
            }
        vision = None
        if self.last_vision:
            vision = {
                "vision_w": self.last_vision.vision_w,
                "vision_h": self.last_vision.vision_h,
                "screen_w": self.last_vision.screen_w,
                "screen_h": self.last_vision.screen_h,
            }
        return {
            "mode": self.mode(),
            "enabled": self.enabled(),
            "session_active": self.session_active(),
            "session_remaining_sec": remaining,
            "pending": pending,
            "driving": self.session_active() or self.pending is not None,
            "last_vision": vision,
        }

    def emergency_stop(self) -> str:
        self.session_until = None
        self.pending = None
        return "Computer control stopped."

    def start_session(self, pin: str) -> tuple[bool, str]:
        if not self.enabled():
            return False, "Computer use is turned off. A parent can enable it in Settings."
        if self.mode() != "session":
            return False, "Session mode is not enabled. Use Ask each time, or change Settings."
        if not verify_pin(self.config, pin):
            return False, "Incorrect PIN."
        ttl = max(1, int(self.config.computer_use.session_ttl_minutes)) * 60
        self.session_until = time.time() + ttl
        self.pending = None
        return True, f"Computer control on for {ttl // 60} minutes. Press Esc or Stop anytime."

    def deny_pending(self) -> str:
        if not self.pending:
            return "Nothing waiting."
        self.pending = None
        return "Parent said no. Computer action cancelled."

    def approve_pending(self, pin: str) -> ExecuteResult:
        if not self.pending:
            return ExecuteResult(ok=False, message="Nothing waiting to approve.")
        if not verify_pin(self.config, pin):
            return ExecuteResult(
                ok=False,
                message="Incorrect PIN.",
                needs_approval=True,
                pending_id=self.pending.id,
            )
        action = self.pending
        self.pending = None
        if self.mode() == "session":
            ttl = max(1, int(self.config.computer_use.session_ttl_minutes)) * 60
            self.session_until = time.time() + ttl
        result = self._run(action.name, action.arguments)
        self.last_result = result
        return result

    async def request(self, name: ActionName, arguments: dict[str, Any]) -> ExecuteResult:
        if not self.enabled():
            result = ExecuteResult(
                ok=False,
                message="Computer use is off. Ask a parent to turn it on in Settings.",
            )
            self.last_result = result
            return result
        if self.mode() == "session" and self.session_active():
            result = self._run(name, arguments)
            self.last_result = result
            return result
        self.pending = PendingAction(
            id=uuid.uuid4().hex[:10],
            name=name,
            arguments=arguments,
        )
        label = {
            "computer_screenshot": "take a screenshot",
            "computer_click": "click the screen",
            "computer_type": "type on the keyboard",
        }.get(name, name)
        result = ExecuteResult(
            ok=False,
            message=f"Waiting for a parent to approve: {label}. Enter the parent PIN.",
            needs_approval=True,
            pending_id=self.pending.id,
        )
        self.last_result = result
        return result

    def _run(self, name: ActionName, arguments: dict[str, Any]) -> ExecuteResult:
        try:
            if name == "computer_screenshot":
                path = (
                    self.screenshots_dir()
                    / f"shot_{int(time.time())}_{uuid.uuid4().hex[:6]}.png"
                )
                info = self.os.screenshot(str(path))
                vision = prepare_screenshot_for_llm(
                    path,
                    max_side=self.config.computer_use.vision_max_side,
                    jpeg_quality=self.config.computer_use.vision_jpeg_quality,
                )
                self.last_vision = vision
                return ExecuteResult(
                    ok=True,
                    message=(
                        f"{info} Vision frame {vision.vision_w}x{vision.vision_h} "
                        f"(screen {vision.screen_w}x{vision.screen_h}). "
                        "Click using image pixel coordinates."
                    ),
                    screenshot_path=str(path),
                    vision=vision,
                )
            if name == "computer_click":
                x = int(arguments.get("x", -1))
                y = int(arguments.get("y", -1))
                if x < 0 or y < 0:
                    return ExecuteResult(
                        ok=False, message="I need positive x and y click coordinates."
                    )
                if self.last_vision:
                    sx, sy = self.last_vision.map_click(x, y)
                    msg = self.os.click(sx, sy)
                    return ExecuteResult(
                        ok=True,
                        message=f"{msg} (mapped from image {x},{y} → screen {sx},{sy})",
                    )
                return ExecuteResult(ok=True, message=self.os.click(x, y))
            if name == "computer_type":
                text = str(arguments.get("text") or "")
                cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
                if not cleaned.strip():
                    return ExecuteResult(ok=False, message="Nothing to type.")
                if len(cleaned) > 200:
                    cleaned = cleaned[:200]
                return ExecuteResult(ok=True, message=self.os.type_text(cleaned))
            return ExecuteResult(ok=False, message="Unknown computer action.")
        except Exception as exc:  # noqa: BLE001
            return ExecuteResult(ok=False, message=f"Computer action failed: {exc}")
