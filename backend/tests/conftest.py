from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import websockets

from kids_agent.config import AppConfig, save_config
from kids_agent.fakes import FakeOS, StubEngine
from kids_agent.safety import set_pin
from kids_agent.server import AgentServer
from tests.e2e.helpers import WsClient


@pytest.fixture
def isolated_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point all runtime paths at a temp directory so e2e never touches config.local.json."""
    cfg_path = tmp_path / "config.local.json"
    monkeypatch.setenv("KDA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr("kids_agent.config.config_local_path", lambda: cfg_path)
    monkeypatch.setattr(
        "kids_agent.server.save_config",
        lambda config, path=None: save_config(config, path or cfg_path),
    )
    monkeypatch.setattr("kids_agent.identity.kids_data_root", lambda: tmp_path / "kids")
    monkeypatch.setattr("kids_agent.budget.budget_path", lambda: tmp_path / "budget.json")
    monkeypatch.setattr("kids_agent.usage.usage_path", lambda: tmp_path / "usage.json")
    (tmp_path / "kids").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "screenshots").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data" / "transcripts").mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def base_config(isolated_data: Path) -> AppConfig:
    cfg = AppConfig(
        kids=[
            {
                "id": "kid_a",
                "name": "Maya",
                "age": 6,
                "english_level": "beginner",
                "daily_limit_minutes": 60,
                "onboarding_complete": True,
            }
        ],
        active_kid_id="kid_a",
        allowlist={
            "apps": [
                {
                    "id": "editor",
                    "label": "Editor",
                    "windows": {"command": "editor.exe"},
                    "macos": {"command": "open", "args": ["-a", "TextEdit"]},
                }
            ],
            "websites": [{"id": "wiki", "label": "Wiki", "url": "https://example.test/"}],
            "skills_enabled": [
                "open_app",
                "open_website",
                "set_volume",
                "start_timer",
                "list_windows",
            ],
        },
        identity={
            "require_who_is_playing": True,
            "voice_name_match": True,
            "face_match": False,
            "allow_tap_select": True,
        },
    )
    set_pin(cfg, "1234")
    cfg.computer_use.mode = "off"
    cfg.ai_mode = "cloud"
    cfg.cloud.api_key = "test-key-not-used"
    cfg.cloud.daily_budget_usd = 5.0
    save_config(cfg, isolated_data / "config.local.json")
    return cfg


@pytest.fixture
def fake_os() -> FakeOS:
    return FakeOS()


@pytest.fixture
def stub_engine() -> StubEngine:
    return StubEngine()


@pytest.fixture
async def e2e_server(
    base_config: AppConfig,
    fake_os: FakeOS,
    stub_engine: StubEngine,
    isolated_data: Path,
):
    server = AgentServer(base_config, os_adapter=fake_os, engine=stub_engine)
    server._hardware = {
        "vram_mb": 8192,
        "vram_gb": 8.0,
        "gpu_name": "E2E GPU",
        "ollama_ok": False,
        "ollama_models": [],
        "has_nvidia_smi": False,
    }
    async with websockets.serve(server.handle, "127.0.0.1", 0) as ws_server:
        sock = ws_server.sockets[0]
        port = sock.getsockname()[1]
        yield {
            "server": server,
            "url": f"ws://127.0.0.1:{port}",
            "config": base_config,
            "fake_os": fake_os,
            "stub_engine": stub_engine,
            "data": isolated_data,
        }


@pytest.fixture
async def ws_client(e2e_server: dict[str, Any]):
    async with websockets.connect(e2e_server["url"]) as ws:
        client = WsClient(ws)
        client.initial_state = await client.recv_until("state")
        yield client
