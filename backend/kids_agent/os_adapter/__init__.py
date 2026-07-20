from __future__ import annotations

import platform

from kids_agent.os_adapter.base import OSAdapter

__all__ = ["OSAdapter", "get_os_adapter"]


def get_os_adapter() -> OSAdapter:
    system = platform.system().lower()
    if system == "windows":
        from kids_agent.os_adapter.windows import WindowsAdapter

        return WindowsAdapter()
    if system == "darwin":
        from kids_agent.os_adapter.macos import MacOSAdapter

        return MacOSAdapter()
    raise RuntimeError(f"Unsupported OS: {system}")
