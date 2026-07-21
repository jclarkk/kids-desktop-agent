"""Unit tests for safety-critical and pure logic paths.

Guidelines for this suite:
- Do not call load_config() (may pick up a developer's config.local.json).
- Prefer AppConfig() + explicit allowlists.
- Include negative cases, not only happy paths.
- Avoid asserting on machine-specific hardware values.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path

import pytest
from PIL import Image

from kids_agent.avatars import list_packs, resolve_voice
from kids_agent.budget import BudgetTracker
from kids_agent.computer_use import ComputerUseGate
from kids_agent.config import (
    AllowlistApp,
    AllowlistWebsite,
    AppConfig,
    KidProfile,
    save_config,
)
from kids_agent.engines.agent_loop import run_agent_loop
from kids_agent.engines.base import EngineResult, ToolCall
from kids_agent.games import games_for_age, score_answer, start_game
from kids_agent.hardware import detect_vram_sync
from kids_agent.identity import match_face, match_kid_by_spoken_name, save_face_image
from kids_agent.model_catalog import default_model_for_vram, recommend_for_vram
from kids_agent.prompts import build_system_prompt, normalize_english_level
from kids_agent.safety import set_pin, verify_pin
from kids_agent.skills.registry import SkillRegistry
from kids_agent.usage import UsageTracker
from kids_agent.vision import (
    ollama_image_message,
    openai_image_message,
    prepare_screenshot_for_llm,
)


# --- shared fakes -----------------------------------------------------------------


class FakeOS:
    def __init__(self) -> None:
        self.clicks: list[tuple[int, int]] = []
        self.typed: list[str] = []

    def open_app(self, launch: dict) -> str:
        return f"opened:{launch.get('command')}"

    def open_url(self, url: str) -> str:
        return f"opened:{url}"

    def set_volume(self, level: int) -> str:
        return f"vol:{level}"

    def list_windows(self) -> list[str]:
        return ["Window A"]

    def screenshot(self, path: str) -> str:
        Image.new("RGB", (800, 400), color=(40, 50, 60)).save(path)
        return "shot ok"

    def click(self, x: int, y: int) -> str:
        self.clicks.append((x, y))
        return f"click {x},{y}"

    def type_text(self, text: str) -> str:
        self.typed.append(text)
        return f"typed:{len(text)}"


def _cfg(**kwargs: object) -> AppConfig:
    return AppConfig(**kwargs)  # type: ignore[arg-type]


# --- allowlist / skills -----------------------------------------------------------


def test_open_app_rejects_unknown_id():
    cfg = _cfg(allowlist={"apps": [], "websites": [], "skills_enabled": ["open_app"]})
    reg = SkillRegistry(cfg, FakeOS())  # type: ignore[arg-type]
    result = asyncio.run(reg.open_app({"app_id": "not-real"}))
    assert result.ok is False
    assert "allowlist" in result.message.lower()


def test_open_app_accepts_allowlisted():
    cfg = _cfg(
        allowlist={
            "apps": [
                {
                    "id": "editor",
                    "label": "Editor",
                    "windows": {"command": "editor.exe"},
                    "macos": {"command": "open", "args": ["-a", "TextEdit"]},
                }
            ],
            "websites": [],
            "skills_enabled": ["open_app"],
        }
    )
    os_adapter = FakeOS()
    reg = SkillRegistry(cfg, os_adapter)  # type: ignore[arg-type]
    result = asyncio.run(reg.open_app({"app_id": "editor"}))
    assert result.ok is True
    assert "opened:" in result.message


def test_open_website_rejects_unknown_and_accepts_allowlisted():
    cfg = _cfg(
        allowlist={
            "apps": [],
            "websites": [{"id": "wiki", "label": "Wiki", "url": "https://example.test/"}],
            "skills_enabled": ["open_website"],
        }
    )
    os_adapter = FakeOS()
    reg = SkillRegistry(cfg, os_adapter)  # type: ignore[arg-type]
    bad = asyncio.run(reg.open_website({"site_id": "evil"}))
    assert bad.ok is False
    assert "allowlist" in bad.message.lower()
    good = asyncio.run(reg.open_website({"site_id": "wiki"}))
    assert good.ok is True
    assert "https://example.test/" in good.message


def test_tools_schema_only_lists_enabled_skills():
    cfg = _cfg(allowlist={"skills_enabled": ["open_app", "set_volume"], "apps": [], "websites": []})
    cfg.computer_use.mode = "off"
    reg = SkillRegistry(cfg, FakeOS())  # type: ignore[arg-type]
    names = [t["function"]["name"] for t in reg.tools_schema()]
    assert names == ["open_app", "set_volume"]


def test_disabled_skill_run_is_blocked():
    cfg = _cfg(allowlist={"skills_enabled": ["open_app"], "apps": [], "websites": []})
    reg = SkillRegistry(cfg, FakeOS())  # type: ignore[arg-type]
    result = asyncio.run(reg.run("set_volume", {"level": 10}))
    assert result.ok is False
    assert "turned off" in result.message.lower()


def test_start_timer_returns_timer_metadata():
    cfg = _cfg(allowlist={"skills_enabled": ["start_timer"], "apps": [], "websites": []})
    reg = SkillRegistry(cfg, FakeOS())  # type: ignore[arg-type]
    result = asyncio.run(reg.run("start_timer", {"seconds": 3, "label": "Brush teeth"}))
    assert result.ok is True
    assert result.timer_seconds == 3
    assert result.timer_label == "Brush teeth"


# --- parent PIN / budget / usage --------------------------------------------------


def test_pin_hash_accepts_correct_rejects_wrong():
    cfg = AppConfig()
    set_pin(cfg, "1234")
    assert cfg.parent_pin == ""
    assert cfg.parent_pin_hash
    assert verify_pin(cfg, "1234")
    assert not verify_pin(cfg, "0000")
    assert not verify_pin(cfg, "12345")


def test_pin_legacy_plaintext_still_verifies():
    cfg = AppConfig(parent_pin="2468", parent_pin_hash=None)
    assert verify_pin(cfg, "2468")
    assert not verify_pin(cfg, "0000")


def test_transcript_logger_purges_old_rows(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from kids_agent.safety import TranscriptLogger

    monkeypatch.setenv("KDA_DATA_DIR", str(tmp_path))
    cfg = AppConfig()
    cfg.safety.transcript_retention_days = 14
    logger = TranscriptLogger(cfg)
    old_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    new_ts = datetime.now(timezone.utc).isoformat()
    logger.path.write_text(
        "\n".join(
            [
                json.dumps({"ts": old_ts, "role": "user", "text": "old"}),
                json.dumps({"ts": new_ts, "role": "user", "text": "new"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert logger.purge_old() == 1
    assert "old" not in logger.path.read_text(encoding="utf-8")
    assert "new" in logger.path.read_text(encoding="utf-8")


def test_budget_tracker_blocks_when_over_limit(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.budget.budget_path", lambda: tmp_path / "budget.json")
    cfg = AppConfig()
    cfg.cloud.daily_budget_usd = 0.02
    tracker = BudgetTracker(cfg)
    assert tracker.can_spend()
    tracker.add_estimate(0.01)
    assert tracker.can_spend()
    tracker.add_estimate(0.02)
    assert not tracker.can_spend()


def test_usage_limit_blocks_after_minutes(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.usage.usage_path", lambda: tmp_path / "usage.json")
    cfg = AppConfig(kids=[{"id": "a", "name": "A", "age": 4, "daily_limit_minutes": 1}])
    kid = cfg.kids[0]
    tracker = UsageTracker(cfg)
    assert tracker.can_play(kid)
    tracker.add_minutes(kid, 1.0)
    assert not tracker.can_play(kid)


def test_save_config_roundtrip_isolated(tmp_path):
    cfg = AppConfig()
    cfg.avatar.character_id = "pixel"
    target = tmp_path / "config.local.json"
    save_config(cfg, target)
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["avatar"]["character_id"] == "pixel"


def test_tts_speed_for_english_level():
    from kids_agent.tts import speed_for_english_level

    assert speed_for_english_level("beginner") < speed_for_english_level("intermediate")
    assert 0.88 <= speed_for_english_level("beginner") <= 1.05
    # Near-natural pace — ultra-slow rates sound synthetic
    assert speed_for_english_level("beginner") >= 0.94


def test_kokoro_available_is_bool():
    from kids_agent.tts import kokoro_available

    assert isinstance(kokoro_available(), bool)


def test_prepare_tts_text_splits_sentences():
    from kids_agent.tts import prepare_tts_text

    out = prepare_tts_text("Hello there! How are you today?")
    assert "\n" in out
    assert "Hello there!" in out
    assert "How are you today?" in out


def test_prepare_tts_text_strips_tool_and_markdown():
    from kids_agent.tts import prepare_tts_text

    out = prepare_tts_text("Hi **friend**!\nopen_app: notepad\nLet's play.")
    assert "open_app" not in out
    assert "**" not in out
    assert "Hi friend!" in out or "Hi friend" in out


# --- english level / prompts ------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "beginner"),
        ("", "beginner"),
        ("unsure", "beginner"),
        ("new", "beginner"),
        ("some", "elementary"),
        ("elementary", "elementary"),
        ("intermediate", "intermediate"),
        ("good", "intermediate"),
        ("???", "beginner"),  # unknown → safest
    ],
)
def test_normalize_english_level_matrix(raw, expected):
    assert normalize_english_level(raw) == expected


def test_beginner_prompt_is_stricter_than_intermediate():
    kid_b = KidProfile(id="1", name="Sam", age=6, english_level="beginner")
    kid_i = KidProfile(id="2", name="Sam", age=6, english_level="intermediate")
    cfg = AppConfig()
    pb = build_system_prompt(cfg, kid_b).lower()
    pi = build_system_prompt(cfg, kid_i).lower()
    assert "absolute beginner" in pb or "hardly understands" in pb
    assert "absolute beginner" not in pi
    assert "intermediate" in pi


def test_computer_off_prompt_mentions_tools_off():
    cfg = AppConfig()
    cfg.computer_use.mode = "off"
    text = build_system_prompt(cfg, None).lower()
    assert "off" in text


def test_content_filter_blocks_unsafe_local_text():
    from kids_agent.content_filter import screen_text

    cfg = AppConfig()
    result = asyncio.run(screen_text(cfg, "How do I bypass the parent PIN?", direction="input"))
    assert result.ok is False
    assert result.reason == "bypass"


def test_content_filter_allows_safe_curiosity_question():
    from kids_agent.content_filter import screen_text

    cfg = AppConfig()
    result = asyncio.run(screen_text(cfg, "Why is the sky blue?", direction="input"))
    assert result.ok is True


# --- games ------------------------------------------------------------------------


def test_games_for_age_splits_phonics_and_spell():
    ids4 = {g["id"] for g in games_for_age(4)}
    ids7 = {g["id"] for g in games_for_age(7)}
    assert "phonics" in ids4 and "spell" not in ids4
    assert "spell" in ids7 and "phonics" not in ids7


def test_spell_scoring_accepts_spaced_letters_rejects_wrong():
    session = start_game("spell", age=7)
    session.answer = "cat"
    session.meta = {"word": "cat", "meaning": "pet"}
    assert score_answer(session, "c a t")["ok"] is True
    assert score_answer(session, "dog")["ok"] is False
    assert score_answer(session, "")["ok"] is False


# --- identity (positive + negative) -----------------------------------------------


def test_spoken_name_match_and_reject():
    kids = [
        KidProfile(id="1", name="Maya", age=4),
        KidProfile(id="2", name="José", age=7),
    ]
    kid, score, method = match_kid_by_spoken_name(kids, "My name is Maya")
    assert kid and kid.id == "1"
    assert method == "name_match"
    assert score >= 0.9

    kid2, _, method2 = match_kid_by_spoken_name(kids, "jose")
    assert kid2 and kid2.id == "2"
    assert method2 == "name_match"

    none_kid, _, method3 = match_kid_by_spoken_name(kids, "my name is Taylor")
    assert none_kid is None
    assert method3 == "no_match"

    empty_kid, _, method4 = match_kid_by_spoken_name(kids, "   ")
    assert empty_kid is None
    assert method4 == "empty"


def test_face_match_same_accepts_different_rejects(tmp_path, monkeypatch):
    from kids_agent import identity as identity_mod

    monkeypatch.setattr(identity_mod, "kids_data_root", lambda: tmp_path)

    def b64_pattern(seed: int) -> str:
        img = Image.new("RGB", (64, 64))
        pixels = img.load()
        assert pixels is not None
        for y in range(64):
            for x in range(64):
                pixels[x, y] = ((x * seed + y * 3) % 256, (y * seed) % 256, (x + y + seed) % 256)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return base64.b64encode(buf.getvalue()).decode("ascii")

    enroll = b64_pattern(7)
    save_face_image("maya", enroll)
    kids = [KidProfile(id="maya", name="Maya", age=4, face_enrolled=True)]

    kid, dist, method = match_face(kids, enroll, max_distance=5)
    assert kid and kid.id == "maya"
    assert method == "face_hash"
    assert dist == 0

    other = b64_pattern(91)
    kid2, dist2, method2 = match_face(kids, other, max_distance=5)
    assert kid2 is None
    assert method2 == "no_match"
    assert dist2 > 5


# --- avatars / catalog / hardware smoke -------------------------------------------


def test_starter_pack_has_three_characters():
    packs = list_packs()
    starter = next(p for p in packs if p["id"] == "starter")
    assert {c["id"] for c in starter["characters"]} >= {"sparky", "pixel", "luna"}


def test_resolve_voice_matches_manifest_for_each_gender():
    """Read expected voices from the shipped manifest — not hardcoded guesses."""
    manifest = Path(__file__).resolve().parents[2] / "assets" / "avatars" / "starter" / "manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    luna = next(c for c in data["characters"] if c["id"] == "luna")
    for gender, expected in luna["voices"].items():
        got = resolve_voice(
            "starter",
            "luna",
            gender,
            fallback_male="am_adam",
            fallback_female="af_heart",
            fallback_neutral="af_sarah",
        )
        assert got == expected, f"gender={gender}"


def test_catalog_recommends_default_for_common_vram_tiers():
    from kids_agent.model_catalog import looks_like_vision_model

    for vram in (0, 4096, 8192, 12288, 24576):
        items = recommend_for_vram(vram if vram else None)
        assert items
        assert any("fit" in i for i in items)
        default = next(i for i in items if i.get("selected_default"))
        assert default.get("vision") is True
        assert looks_like_vision_model(default["ollama"])
        assert default.get("quantized") is True

    # Comfortable GPU → Qwen3.5 9B quantized; tight VRAM → 4B / E4B class.
    assert default_model_for_vram(8192) == "qwen3.5:9b-q4_K_M"
    low = default_model_for_vram(4096)
    assert low in ("qwen3.5:4b-q4_K_M", "gemma4:e4b-it-qat")
    assert looks_like_vision_model("qwen3.5:9b-q4_K_M")
    assert looks_like_vision_model("gemma4:12b-it-qat")
    assert looks_like_vision_model("gemma4:e4b-it-qat")
    assert not looks_like_vision_model("qwen2.5:7b-instruct")


def test_detect_vram_sync_returns_stable_keys():
    info = detect_vram_sync()
    assert set(info) >= {"vram_mb", "has_nvidia_smi", "platform"}
    # Do not assert specific GPU values — machine-dependent.


# --- computer use + vision --------------------------------------------------------


def test_computer_use_off_hides_tools_and_blocks_request():
    cfg = AppConfig()
    cfg.computer_use.mode = "off"
    gate = ComputerUseGate(cfg, FakeOS())  # type: ignore[arg-type]
    reg = SkillRegistry(cfg, FakeOS(), gate)  # type: ignore[arg-type]
    names = [t["function"]["name"] for t in reg.tools_schema()]
    assert not any(n.startswith("computer_") for n in names)
    blocked = asyncio.run(gate.request("computer_click", {"x": 1, "y": 1}))
    assert blocked.ok is False
    assert "off" in blocked.message.lower()


def test_ask_mode_wrong_pin_keeps_pending_deny_clears(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    cfg = AppConfig()
    set_pin(cfg, "4321")
    cfg.computer_use.mode = "ask"
    gate = ComputerUseGate(cfg, FakeOS())  # type: ignore[arg-type]

    pending = asyncio.run(gate.request("computer_click", {"x": 10, "y": 20}))
    assert pending.needs_approval
    assert gate.pending is not None

    bad = gate.approve_pending("0000")
    assert not bad.ok
    assert gate.pending is not None

    assert "cancelled" in gate.deny_pending().lower()
    assert gate.pending is None


def test_ask_mode_correct_pin_runs_click(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    os_adapter = FakeOS()
    cfg = AppConfig()
    set_pin(cfg, "4321")
    cfg.computer_use.mode = "ask"
    gate = ComputerUseGate(cfg, os_adapter)  # type: ignore[arg-type]
    asyncio.run(gate.request("computer_click", {"x": 10, "y": 20}))
    good = gate.approve_pending("4321")
    assert good.ok
    assert os_adapter.clicks == [(10, 20)]
    assert gate.pending is None


def test_session_requires_pin_emergency_stop_revokes(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    cfg = AppConfig()
    set_pin(cfg, "9999")
    cfg.computer_use.mode = "session"
    gate = ComputerUseGate(cfg, FakeOS())  # type: ignore[arg-type]

    ok_bad, _ = gate.start_session("0000")
    assert not ok_bad
    assert not gate.session_active()

    ok, _ = gate.start_session("9999")
    assert ok
    typed = asyncio.run(gate.request("computer_type", {"text": "hi"}))
    assert typed.ok

    gate.emergency_stop()
    assert not gate.session_active()
    again = asyncio.run(gate.request("computer_screenshot", {}))
    assert again.needs_approval


def test_type_strips_controls_and_caps_length(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    os_adapter = FakeOS()
    cfg = AppConfig()
    set_pin(cfg, "1111")
    cfg.computer_use.mode = "session"
    gate = ComputerUseGate(cfg, os_adapter)  # type: ignore[arg-type]
    gate.start_session("1111")
    long_text = "a" * 250 + "\x00\x01"
    result = asyncio.run(gate.request("computer_type", {"text": long_text}))
    assert result.ok
    assert len(os_adapter.typed[0]) == 200
    assert "\x00" not in os_adapter.typed[0]


def test_click_maps_from_vision_image_coords(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    os_adapter = FakeOS()
    cfg = AppConfig()
    set_pin(cfg, "1111")
    cfg.computer_use.mode = "session"
    cfg.computer_use.vision_max_side = 400  # 800x400 shot → 400x200 vision
    gate = ComputerUseGate(cfg, os_adapter)  # type: ignore[arg-type]
    gate.start_session("1111")
    shot = asyncio.run(gate.request("computer_screenshot", {}))
    assert shot.ok and shot.vision
    assert shot.vision.vision_w == 400
    assert shot.vision.vision_h == 200
    click = asyncio.run(gate.request("computer_click", {"x": 100, "y": 50}))
    assert click.ok
    # scale 2x → screen (200, 100)
    assert os_adapter.clicks[-1] == (200, 100)


def test_prepare_screenshot_scales_and_maps(tmp_path):
    src = tmp_path / "big.png"
    Image.new("RGB", (2000, 1000), color=(10, 20, 30)).save(src)
    frame = prepare_screenshot_for_llm(src, max_side=1000, jpeg_quality=70)
    assert (frame.screen_w, frame.screen_h) == (2000, 1000)
    assert (frame.vision_w, frame.vision_h) == (1000, 500)
    assert frame.map_click(100, 50) == (200, 100)
    # Clamp to screen bounds
    assert frame.map_click(99999, 99999) == (1999, 999)


def test_vision_message_shapes_openai_and_ollama(tmp_path):
    src = tmp_path / "s.png"
    Image.new("RGB", (64, 48), color=(1, 2, 3)).save(src)
    frame = prepare_screenshot_for_llm(src, max_side=64)
    oa = openai_image_message(frame)
    assert oa["role"] == "user"
    assert oa["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    ol = ollama_image_message(frame)
    assert ol["role"] == "user"
    assert isinstance(ol["images"], list) and ol["images"][0] == frame.b64


def test_agent_loop_injects_vision_and_can_pause(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    cfg = AppConfig()
    set_pin(cfg, "1111")
    cfg.computer_use.mode = "session"
    gate = ComputerUseGate(cfg, FakeOS())  # type: ignore[arg-type]
    gate.start_session("1111")
    reg = SkillRegistry(cfg, FakeOS(), gate)  # type: ignore[arg-type]

    class EngineVisionThenDone:
        def __init__(self) -> None:
            self.n = 0

        async def chat(self, messages, *, tools_schema=None):
            self.n += 1
            if self.n == 1:
                return EngineResult(
                    assistant_text="Looking",
                    tool_calls=[ToolCall(id="1", name="computer_screenshot", arguments={})],
                )
            has_image = any(
                (
                    isinstance(m.get("content"), list)
                    and any(isinstance(p, dict) and p.get("type") == "image_url" for p in m["content"])
                )
                or m.get("images")
                for m in messages
            )
            assert has_image
            return EngineResult(assistant_text="Seen.")

    out = asyncio.run(
        run_agent_loop(
            engine=EngineVisionThenDone(),  # type: ignore[arg-type]
            skills=reg,
            system_prompt="sys",
            user_text="What is on screen?",
            max_steps=4,
            dialect="openai",
        )
    )
    assert out.vision_steps == 1
    assert out.paused_for_approval is False
    assert "Seen" in out.assistant_text


def test_agent_loop_pauses_when_ask_mode_needs_pin(tmp_path, monkeypatch):
    monkeypatch.setattr("kids_agent.computer_use.app_data_root", lambda: tmp_path)
    cfg = AppConfig()
    set_pin(cfg, "1111")
    cfg.computer_use.mode = "ask"
    gate = ComputerUseGate(cfg, FakeOS())  # type: ignore[arg-type]
    reg = SkillRegistry(cfg, FakeOS(), gate)  # type: ignore[arg-type]

    class EngineShot:
        async def chat(self, messages, *, tools_schema=None):
            return EngineResult(
                assistant_text="Need screen",
                tool_calls=[ToolCall(id="1", name="computer_screenshot", arguments={})],
            )

    out = asyncio.run(
        run_agent_loop(
            engine=EngineShot(),  # type: ignore[arg-type]
            skills=reg,
            system_prompt="sys",
            user_text="Look",
            max_steps=3,
            dialect="openai",
        )
    )
    assert out.paused_for_approval is True
    assert gate.pending is not None
    assert out.vision_steps == 0  # image not attached until approved


# --- OS adapter selection / macos helpers -----------------------------------------


def test_macos_escape_and_volume_script(monkeypatch):
    from kids_agent.os_adapter.macos import MacOSAdapter, _escape_as
    from kids_agent.os_adapter.base import OSAdapter
    from kids_agent.os_adapter import macos as macos_mod

    assert isinstance(MacOSAdapter(), OSAdapter)
    assert _escape_as('say "hi"') == 'say \\"hi\\"'

    calls: list[str] = []
    monkeypatch.setattr(macos_mod, "_run_osascript", lambda src, timeout=12.0: (calls.append(src) or True, ""))
    assert "40%" in MacOSAdapter().set_volume(40)
    assert any("output volume 40" in c for c in calls)


def test_get_os_adapter_matches_platform():
    import platform

    from kids_agent.os_adapter import get_os_adapter

    adapter = get_os_adapter()
    system = platform.system().lower()
    if system == "windows":
        from kids_agent.os_adapter.windows import WindowsAdapter

        assert isinstance(adapter, WindowsAdapter)
    elif system == "darwin":
        from kids_agent.os_adapter.macos import MacOSAdapter

        assert isinstance(adapter, MacOSAdapter)
