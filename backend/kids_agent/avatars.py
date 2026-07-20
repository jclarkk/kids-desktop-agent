from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from kids_agent.config import assets_root


def avatars_root() -> Path:
    return assets_root() / "avatars"


def load_pack(pack_id: str) -> dict[str, Any] | None:
    manifest = avatars_root() / pack_id / "manifest.json"
    if not manifest.is_file():
        return None
    with manifest.open(encoding="utf-8") as f:
        return json.load(f)


def list_packs() -> list[dict[str, Any]]:
    root = avatars_root()
    if not root.is_dir():
        return []
    packs: list[dict[str, Any]] = []
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        pack = load_pack(path.name)
        if pack:
            packs.append(pack)
    return packs


def resolve_voice(
    pack_id: str,
    character_id: str,
    gender: str,
    *,
    fallback_male: str,
    fallback_female: str,
    fallback_neutral: str,
) -> str:
    pack = load_pack(pack_id)
    if pack:
        for ch in pack.get("characters") or []:
            if ch.get("id") == character_id:
                voices = ch.get("voices") or {}
                if gender in voices:
                    return str(voices[gender])
    if gender == "boy":
        return fallback_male
    if gender == "girl":
        return fallback_female
    return fallback_neutral
