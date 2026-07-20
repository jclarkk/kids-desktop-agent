from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class OSAdapter(ABC):
    @abstractmethod
    def open_app(self, launch: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def open_url(self, url: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def set_volume(self, level: int) -> str:
        raise NotImplementedError

    @abstractmethod
    def list_windows(self) -> list[str]:
        raise NotImplementedError

    @abstractmethod
    def screenshot(self, path: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def click(self, x: int, y: int) -> str:
        raise NotImplementedError

    @abstractmethod
    def type_text(self, text: str) -> str:
        raise NotImplementedError
