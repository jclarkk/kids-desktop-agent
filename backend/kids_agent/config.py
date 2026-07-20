from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def app_data_root() -> Path:
    """Writable runtime root.

    Dev mode defaults to the repository. Packaged Electron sets KDA_DATA_DIR /
    KDA_CONFIG so installs never write into app resources.
    """

    env_path = os.environ.get("KDA_DATA_DIR")
    if env_path:
        return Path(env_path)
    return repo_root() / "data"


def assets_root() -> Path:
    env_path = os.environ.get("KDA_ASSETS_DIR")
    if env_path:
        return Path(env_path)
    return repo_root() / "assets"


class WebSocketConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765


class CloudConfig(BaseModel):
    provider: str = "openrouter"
    api_key: str = ""
    base_url: str = "https://openrouter.ai/api/v1"
    chat_model: str = "google/gemini-2.5-flash"
    stt_provider: str = "openai_compatible"
    tts: str = "local_kokoro"
    daily_budget_usd: float = 2.0
    presets: dict[str, str] = Field(default_factory=dict)


class LocalConfig(BaseModel):
    llm_runtime: str = "ollama"
    llm_model: str = "qwen2.5:14b-instruct-q4_K_M"
    ollama_base_url: str = "http://127.0.0.1:11434"
    gpu_layers: str | int = "auto"
    stt_model: str = "small"
    tts_voice_male: str = "am_michael"
    tts_voice_female: str = "af_heart"
    tts_voice_neutral: str = "af_bella"
    allow_offload: bool = True


class AvatarConfig(BaseModel):
    pack_id: str = "starter"
    character_id: str = "sparky"
    gender: Literal["boy", "girl", "neutral"] = "neutral"
    wake_word: str = "Hey Sparky"


class KidProfile(BaseModel):
    id: str
    name: str
    age: int = 7
    preferred_avatar: str = "sparky"
    preferred_gender: Literal["boy", "girl", "neutral"] = "neutral"
    daily_limit_minutes: int = 60
    # beginner = hardly any English; default when unknown / skipped
    english_level: Literal["beginner", "elementary", "intermediate"] = "beginner"
    onboarding_complete: bool = False
    voice_enrolled: bool = False
    face_enrolled: bool = False
    magic_word: str = ""  # optional passphrase for voice confirm


class AllowlistApp(BaseModel):
    id: str
    label: str
    windows: dict[str, Any] = Field(default_factory=dict)
    macos: dict[str, Any] = Field(default_factory=dict)


class AllowlistWebsite(BaseModel):
    id: str
    label: str
    url: str


class AllowlistConfig(BaseModel):
    apps: list[AllowlistApp] = Field(default_factory=list)
    websites: list[AllowlistWebsite] = Field(default_factory=list)
    skills_enabled: list[str] = Field(default_factory=list)


class ComputerUseConfig(BaseModel):
    mode: Literal["off", "ask", "session"] = "off"
    session_ttl_minutes: int = 15
    vision_max_side: int = 1280
    vision_jpeg_quality: int = 75
    max_agent_steps: int = 6


class SafetyConfig(BaseModel):
    log_transcripts: bool = True
    transcript_retention_days: int = 14
    content_strictness: str = "strict"


class AudioConfig(BaseModel):
    sample_rate: int = 16000
    wake_word_enabled: bool = False
    barge_in: bool = True


class IdentityConfig(BaseModel):
    """Local-only kid recognition. Not security-grade — a friendly who-is-playing helper."""

    require_who_is_playing: bool = True
    voice_name_match: bool = True
    face_match: bool = True
    face_match_threshold: int = 14
    allow_tap_select: bool = True


class AppConfig(BaseModel):
    # Dev/run-from-source default; the installer must prompt for a real PIN.
    parent_pin: str = "1234"
    parent_pin_hash: str | None = None
    ai_mode: Literal["cloud", "local", "hybrid"] = "cloud"
    websocket: WebSocketConfig = Field(default_factory=WebSocketConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    local: LocalConfig = Field(default_factory=LocalConfig)
    avatar: AvatarConfig = Field(default_factory=AvatarConfig)
    kids: list[KidProfile] = Field(default_factory=list)
    active_kid_id: str | None = None
    allowlist: AllowlistConfig = Field(default_factory=AllowlistConfig)
    computer_use: ComputerUseConfig = Field(default_factory=ComputerUseConfig)
    safety: SafetyConfig = Field(default_factory=SafetyConfig)
    audio: AudioConfig = Field(default_factory=AudioConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)

    def voice_for_gender(self, gender: str | None = None) -> str:
        from kids_agent.avatars import resolve_voice

        g = gender or self.avatar.gender
        return resolve_voice(
            self.avatar.pack_id,
            self.avatar.character_id,
            g,
            fallback_male=self.local.tts_voice_male,
            fallback_female=self.local.tts_voice_female,
            fallback_neutral=self.local.tts_voice_neutral,
        )

    def settings_for_parent(self) -> dict[str, Any]:
        data = self.model_dump()
        key = data.get("cloud", {}).get("api_key") or ""
        if key:
            data["cloud"]["api_key"] = ("*" * max(0, len(key) - 4)) + key[-4:]
            data["cloud"]["api_key_set"] = True
        else:
            data["cloud"]["api_key_set"] = False
        # Never send pin material to the UI
        data.pop("parent_pin", None)
        data.pop("parent_pin_hash", None)
        data["pin_is_hashed"] = bool(self.parent_pin_hash)
        return data


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def config_local_path() -> Path:
    env_path = os.environ.get("KDA_CONFIG")
    if env_path:
        return Path(env_path)
    return repo_root() / "config" / "config.local.json"


def load_config(path: str | Path | None = None) -> AppConfig:
    root = repo_root()
    env_path = os.environ.get("KDA_CONFIG")
    candidates: list[Path] = []
    if path:
        candidates.append(Path(path))
    if env_path:
        candidates.append(Path(env_path))
    candidates.extend(
        [
            config_local_path(),
            root / "config" / "config.example.json",
        ]
    )

    data: dict[str, Any] = {}
    loaded_config = False
    for candidate in candidates:
        if candidate.is_file():
            data = _load_json(candidate)
            loaded_config = True
            break

    cfg = AppConfig.model_validate(data)
    if os.environ.get("KDA_PACKAGED") == "1" and not loaded_config:
        # Installed builds must collect a parent PIN before use. Dev mode keeps
        # the documented 1234 fallback through config.example.json / defaults.
        cfg.parent_pin = ""
        cfg.parent_pin_hash = None

    api_key = os.environ.get("KDA_API_KEY") or cfg.cloud.api_key
    cfg.cloud.api_key = api_key

    if host := os.environ.get("KDA_WS_HOST"):
        cfg.websocket.host = host
    if port := os.environ.get("KDA_WS_PORT"):
        cfg.websocket.port = int(port)

    return cfg


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    target = path or config_local_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = config.model_dump()
    with target.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return target
