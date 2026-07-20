from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kids_agent.config import AppConfig, app_data_root


def pin_hash(pin: str, salt: str | None = None) -> str:
    """Return salt$sha256hex. Salt is generated when omitted."""
    salt = salt or secrets.token_hex(8)
    digest = hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_pin(config: AppConfig, pin: str) -> bool:
    if config.parent_pin_hash:
        try:
            salt, _digest = config.parent_pin_hash.split("$", 1)
        except ValueError:
            return False
        return secrets.compare_digest(pin_hash(pin, salt), config.parent_pin_hash)
    # Legacy plaintext (example config / first run)
    return secrets.compare_digest(pin, config.parent_pin)


def set_pin(config: AppConfig, new_pin: str) -> None:
    config.parent_pin_hash = pin_hash(new_pin)
    config.parent_pin = ""  # clear plaintext once hashed


class TranscriptLogger:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.enabled = config.safety.log_transcripts
        self.path = app_data_root() / "transcripts" / "session.jsonl"
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, role: str, text: str, **extra: object) -> None:
        if not self.enabled or not text:
            return
        row = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "text": text,
            **extra,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def purge_old(self) -> int:
        days = max(1, int(self.config.safety.transcript_retention_days))
        if not self.path.is_file():
            return 0
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        kept: list[str] = []
        removed = 0
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                ts = datetime.fromisoformat(str(row.get("ts")))
            except (ValueError, json.JSONDecodeError, TypeError):
                kept.append(line)
                continue
            if ts < cutoff:
                removed += 1
            else:
                kept.append(line)
        self.path.write_text(("\n".join(kept) + "\n") if kept else "", encoding="utf-8")
        return removed

    def clear(self) -> None:
        if self.path.is_file():
            self.path.unlink()
