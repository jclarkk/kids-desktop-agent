from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from kids_agent.config import AppConfig, KidProfile, app_data_root


def usage_path() -> Path:
    return app_data_root() / "usage.json"


class UsageTracker:
    """Per-kid daily minutes (soft time limits)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.path = usage_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"day": str(date.today()), "kids": {}}
        try:
            with self.path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {"day": str(date.today()), "kids": {}}
        if data.get("day") != str(date.today()):
            data = {"day": str(date.today()), "kids": {}}
        data.setdefault("kids", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def status_for(self, kid: KidProfile | None) -> dict[str, Any]:
        if not kid:
            return {
                "kid_id": None,
                "used_minutes": 0,
                "limit_minutes": 0,
                "remaining_minutes": 0,
                "over_limit": False,
            }
        data = self._load()
        used = float((data["kids"].get(kid.id) or {}).get("minutes") or 0)
        limit = int(kid.daily_limit_minutes)
        return {
            "kid_id": kid.id,
            "used_minutes": round(used, 2),
            "limit_minutes": limit,
            "remaining_minutes": round(max(0.0, limit - used), 2),
            "over_limit": used >= limit if limit > 0 else False,
        }

    def can_play(self, kid: KidProfile | None) -> bool:
        st = self.status_for(kid)
        if not kid or st["limit_minutes"] <= 0:
            return True
        return not st["over_limit"]

    def add_minutes(self, kid: KidProfile | None, minutes: float) -> dict[str, Any]:
        if not kid:
            return self.status_for(None)
        data = self._load()
        entry = data["kids"].setdefault(kid.id, {"minutes": 0.0})
        entry["minutes"] = float(entry.get("minutes") or 0) + max(0.0, minutes)
        self._save(data)
        return self.status_for(kid)
