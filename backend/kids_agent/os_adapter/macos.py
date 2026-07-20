from __future__ import annotations

import logging
import platform
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Any

from kids_agent.os_adapter.base import OSAdapter

log = logging.getLogger("kids_agent.os.macos")


def _run_osascript(source: str, timeout: float = 12.0) -> tuple[bool, str]:
    """Run AppleScript; return (ok, stdout_or_error)."""
    try:
        completed = subprocess.run(
            ["osascript", "-e", source],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    out = (completed.stdout or "").strip()
    err = (completed.stderr or "").strip()
    if completed.returncode != 0:
        return False, err or out or f"osascript exit {completed.returncode}"
    return True, out


def _escape_as(text: str) -> str:
    """Escape a string for embedding in AppleScript double quotes."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


class MacOSAdapter(OSAdapter):
    """Desktop control for macOS via AppleScript + CoreGraphics (no pyobjc).

    Click/type/list-windows need Accessibility permission for the terminal or
    Electron app running the agent (System Settings → Privacy & Security → Accessibility).
    Screenshots may need Screen Recording permission.
    """

    def open_app(self, launch: dict[str, Any]) -> str:
        command = launch.get("command")
        if not command:
            return "No macOS launch command configured for this app."
        args = list(launch.get("args") or [])
        cmd = str(command)

        # Common allowlist shapes: open -a TextEdit, or a .app path
        if cmd.endswith(".app") and not args:
            argv = ["open", "-a", cmd]
        elif cmd == "open" or cmd.endswith("/open"):
            argv = [cmd, *args]
        else:
            argv = [cmd, *args]

        try:
            subprocess.Popen(argv, shell=False)
        except OSError as exc:
            return f"Could not open app ({exc})."
        return f"Opened via {' '.join(argv)}"

    def open_url(self, url: str) -> str:
        webbrowser.open(url)
        return f"Opened {url}"

    def set_volume(self, level: int) -> str:
        level = max(0, min(100, int(level)))
        ok, detail = _run_osascript(f"set volume output volume {level}")
        if not ok:
            return f"Could not set volume ({detail})."
        return f"Volume set to {level}%"

    def list_windows(self) -> list[str]:
        script = """
tell application "System Events"
  set titles to {}
  set procs to every process whose background only is false
  repeat with p in procs
    try
      repeat with w in (windows of p)
        set t to name of w as text
        if t is not "" then set end of titles to t
      end repeat
    end try
  end repeat
end tell
set AppleScript's text item delimiters to linefeed
return titles as text
"""
        ok, detail = _run_osascript(script)
        if not ok:
            log.debug("list_windows failed: %s", detail)
            return []
        titles = [line.strip() for line in detail.splitlines() if line.strip()]
        # de-dupe preserving order
        seen: set[str] = set()
        unique: list[str] = []
        for t in titles:
            if t not in seen:
                seen.add(t)
                unique.append(t)
        return unique[:30]

    def screenshot(self, path: str) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Native screencapture: no flash (-x), PNG
        try:
            completed = subprocess.run(
                ["screencapture", "-x", str(target)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"Screenshot failed ({exc})."
        if completed.returncode != 0 or not target.is_file():
            # Fallback: Pillow ImageGrab
            try:
                from PIL import ImageGrab

                image = ImageGrab.grab()
                image.save(target)
                w, h = image.size
                return f"Screenshot saved ({w}x{h}). Origin is top-left (0,0)."
            except Exception as exc:  # noqa: BLE001
                err = (completed.stderr or completed.stdout or str(exc)).strip()
                return f"Screenshot failed ({err}). Grant Screen Recording if prompted."
        try:
            from PIL import Image

            with Image.open(target) as image:
                w, h = image.size
            return f"Screenshot saved ({w}x{h}). Origin is top-left (0,0)."
        except Exception:  # noqa: BLE001
            return f"Screenshot saved to {target.name}."

    def click(self, x: int, y: int) -> str:
        x, y = int(x), int(y)
        if self._click_quartz(x, y):
            return f"Clicked at ({x}, {y})."
        # Accessibility fallback
        ok, detail = _run_osascript(
            f'tell application "System Events" to click at {{{x}, {y}}}'
        )
        if ok:
            return f"Clicked at ({x}, {y})."
        return (
            f"Click failed ({detail}). "
            "Allow Accessibility for the app running the agent "
            "(System Settings → Privacy & Security → Accessibility)."
        )

    def type_text(self, text: str) -> str:
        cleaned = "".join(ch for ch in text if ch.isprintable() or ch in "\n\t")
        if not cleaned:
            return "Nothing to type."
        if len(cleaned) > 200:
            cleaned = cleaned[:200]

        # Prefer Quartz unicode keyboard events when available
        if self._type_quartz(cleaned):
            return f"Typed {len(cleaned)} characters."

        # AppleScript keystroke (needs Accessibility). Handle newlines as return.
        parts = cleaned.split("\n")
        for i, part in enumerate(parts):
            if part:
                ok, detail = _run_osascript(
                    'tell application "System Events" to keystroke '
                    f'"{_escape_as(part)}"'
                )
                if not ok:
                    return (
                        f"Type failed ({detail}). "
                        "Allow Accessibility for the app running the agent."
                    )
            if i < len(parts) - 1:
                ok, detail = _run_osascript(
                    'tell application "System Events" to key code 36'
                )
                if not ok:
                    return f"Type failed on return ({detail})."
            time.sleep(0.02)
        return f"Typed {len(cleaned)} characters."

    def _click_quartz(self, x: int, y: int) -> bool:
        if platform.system() != "Darwin":
            return False
        try:
            import ctypes
            import ctypes.util

            path = ctypes.util.find_library("CoreGraphics")
            if not path:
                path = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            cg = ctypes.CDLL(path)

            class CGPoint(ctypes.Structure):
                _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]

            kCGEventLeftMouseDown = 1
            kCGEventLeftMouseUp = 2
            kCGHIDEventTap = 0
            kCGMouseButtonLeft = 0

            cg.CGEventCreateMouseEvent.restype = ctypes.c_void_p
            cg.CGEventCreateMouseEvent.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint32,
                CGPoint,
                ctypes.c_uint32,
            ]
            cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
            cg.CFRelease.argtypes = [ctypes.c_void_p]

            pt = CGPoint(float(x), float(y))
            for etype in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
                event = cg.CGEventCreateMouseEvent(None, etype, pt, kCGMouseButtonLeft)
                if not event:
                    return False
                cg.CGEventPost(kCGHIDEventTap, event)
                cg.CFRelease(event)
                time.sleep(0.02)
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("Quartz click failed: %s", exc)
            return False

    def _type_quartz(self, text: str) -> bool:
        if platform.system() != "Darwin":
            return False
        try:
            import ctypes
            import ctypes.util

            path = ctypes.util.find_library("CoreGraphics")
            if not path:
                path = "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics"
            cg = ctypes.CDLL(path)

            kCGHIDEventTap = 0
            kCGEventFlagMask = 0

            cg.CGEventCreateKeyboardEvent.restype = ctypes.c_void_p
            cg.CGEventCreateKeyboardEvent.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint16,
                ctypes.c_bool,
            ]
            cg.CGEventKeyboardSetUnicodeString.argtypes = [
                ctypes.c_void_p,
                ctypes.c_ulong,
                ctypes.c_void_p,
            ]
            cg.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
            cg.CFRelease.argtypes = [ctypes.c_void_p]

            for ch in text:
                if ch == "\n":
                    for down in (True, False):
                        event = cg.CGEventCreateKeyboardEvent(None, 36, down)
                        if not event:
                            return False
                        cg.CGEventPost(kCGHIDEventTap, event)
                        cg.CFRelease(event)
                    time.sleep(0.01)
                    continue
                if ch == "\t":
                    for down in (True, False):
                        event = cg.CGEventCreateKeyboardEvent(None, 48, down)
                        if not event:
                            return False
                        cg.CGEventPost(kCGHIDEventTap, event)
                        cg.CFRelease(event)
                    time.sleep(0.01)
                    continue

                buf = ctypes.create_unicode_buffer(ch)
                for down in (True, False):
                    event = cg.CGEventCreateKeyboardEvent(None, 0, down)
                    if not event:
                        return False
                    cg.CGEventKeyboardSetUnicodeString(event, 1, buf)
                    set_flags = getattr(cg, "CGEventSetFlags", None)
                    if set_flags:
                        set_flags.argtypes = [ctypes.c_void_p, ctypes.c_uint64]
                        set_flags(event, kCGEventFlagMask)
                    cg.CGEventPost(kCGHIDEventTap, event)
                    cg.CFRelease(event)
                time.sleep(0.01)
            return True
        except Exception as exc:  # noqa: BLE001
            log.debug("Quartz type failed: %s", exc)
            return False
