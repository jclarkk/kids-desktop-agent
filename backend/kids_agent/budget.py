from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from kids_agent.config import AppConfig, app_data_root


def budget_path() -> Path:
    return app_data_root() / "budget.json"


class BudgetTracker:
    """Soft daily USD counter for cloud calls (estimated)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.path = budget_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"day": str(date.today()), "spent_usd": 0.0}
        try:
            with self.path.open(encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            data = {"day": str(date.today()), "spent_usd": 0.0}
        if data.get("day") != str(date.today()):
            data = {"day": str(date.today()), "spent_usd": 0.0}
        return data

    def _save(self, data: dict[str, Any]) -> None:
        with self.path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def status(self) -> dict[str, Any]:
        data = self._load()
        limit = float(self.config.cloud.daily_budget_usd)
        spent = float(data.get("spent_usd") or 0)
        return {
            "day": data.get("day"),
            "spent_usd": round(spent, 4),
            "limit_usd": limit,
            "remaining_usd": round(max(0.0, limit - spent), 4),
            "over_budget": spent >= limit if limit > 0 else False,
        }

    def can_spend(self) -> bool:
        st = self.status()
        if st["limit_usd"] <= 0:
            return True
        return not st["over_budget"]

    def add_estimate(self, usd: float) -> dict[str, Any]:
        data = self._load()
        data["spent_usd"] = float(data.get("spent_usd") or 0) + max(0.0, usd)
        self._save(data)
        return self.status()
