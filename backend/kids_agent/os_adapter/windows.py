from __future__ import annotations

import ctypes
import subprocess
import time
import webbrowser
from ctypes import wintypes
from pathlib import Path
from typing import Any

from kids_agent.os_adapter.base import OSAdapter

user32 = ctypes.windll.user32
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_ABSOLUTE = 0x8000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", INPUT_UNION)]


class WindowsAdapter(OSAdapter):
    def open_app(self, launch: dict[str, Any]) -> str:
        command = launch.get("command")
        if not command:
            return "No Windows launch command configured for this app."
        args = launch.get("args") or []
        subprocess.Popen([command, *args], shell=False)
        return f"Opened {command}"

    def open_url(self, url: str) -> str:
        webbrowser.open(url)
        return f"Opened {url}"

    def set_volume(self, level: int) -> str:
        level = max(0, min(100, level))
        # Scalar volume via Core Audio COM (PowerShell). No extra pip deps.
        script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioEndpointVolume {{
  int NotImpl1(); int NotImpl2(); int NotImpl3();
  int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
  int NotImpl4(); int NotImpl5(); int NotImpl6(); int NotImpl7();
  int GetMasterVolumeLevelScalar(out float pfLevel);
}}
[Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDevice {{
  int Activate(ref Guid iid, int dwClsCtx, IntPtr pActivationParams, out IAudioEndpointVolume ppInterface);
}}
[Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IMMDeviceEnumerator {{
  int NotImpl1();
  int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice ppDevice);
}}
[ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject {{ }}
public class Vol {{
  public static void Set(float level) {{
    var enumerator = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
    IMMDevice device;
    Marshal.ThrowExceptionForHR(enumerator.GetDefaultAudioEndpoint(0, 1, out device));
    Guid iid = typeof(IAudioEndpointVolume).GUID;
    IAudioEndpointVolume vol;
    Marshal.ThrowExceptionForHR(device.Activate(ref iid, 1, IntPtr.Zero, out vol));
    Marshal.ThrowExceptionForHR(vol.SetMasterVolumeLevelScalar(level, Guid.Empty));
  }}
}}
"@
[Vol]::Set(({level} / 100.0))
"""
        try:
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                check=True,
                capture_output=True,
                text=True,
                timeout=15,
            )
            return f"Volume set to {level}%"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return f"Could not set volume ({exc})."

    def list_windows(self) -> list[str]:
        user32 = ctypes.windll.user32
        titles: list[str] = []

        EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd: int, _lparam: int) -> bool:
            if not user32.IsWindowVisible(hwnd):
                return True
            length = user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if title and title not in titles:
                titles.append(title)
            return True

        user32.EnumWindows(EnumWindowsProc(callback), 0)
        return titles[:30]

    def screenshot(self, path: str) -> str:
        from PIL import ImageGrab

        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        image = ImageGrab.grab(all_screens=False)
        image.save(target)
        w, h = image.size
        return f"Screenshot saved ({w}x{h}). Origin is top-left (0,0)."

    def click(self, x: int, y: int) -> str:
        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        x = max(0, min(screen_w - 1, int(x)))
        y = max(0, min(screen_h - 1, int(y)))
        abs_x = int(x * 65535 / max(1, screen_w - 1))
        abs_y = int(y * 65535 / max(1, screen_h - 1))

        def send_mouse(flags: int) -> None:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.union.mi = MOUSEINPUT(abs_x, abs_y, 0, flags, 0, None)
            user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))

        send_mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE)
        time.sleep(0.02)
        send_mouse(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE)
        time.sleep(0.02)
        send_mouse(MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE)
        return f"Clicked at ({x}, {y})."

    def type_text(self, text: str) -> str:
        for ch in text:
            if ch == "\n":
                self._key_vk(0x0D)  # VK_RETURN
                continue
            if ch == "\t":
                self._key_vk(0x09)
                continue
            down = INPUT()
            down.type = INPUT_KEYBOARD
            down.union.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, None)
            up = INPUT()
            up.type = INPUT_KEYBOARD
            up.union.ki = KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, None)
            user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
            user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
            time.sleep(0.01)
        return f"Typed {len(text)} characters."

    def _key_vk(self, vk: int) -> None:
        down = INPUT()
        down.type = INPUT_KEYBOARD
        down.union.ki = KEYBDINPUT(vk, 0, 0, 0, None)
        up = INPUT()
        up.type = INPUT_KEYBOARD
        up.union.ki = KEYBDINPUT(vk, 0, KEYEVENTF_KEYUP, 0, None)
        user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
        user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
