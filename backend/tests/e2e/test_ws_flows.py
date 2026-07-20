from __future__ import annotations

import pytest

from kids_agent.fakes import StubEngine
from kids_agent.safety import set_pin

pytestmark = pytest.mark.e2e


@pytest.mark.asyncio
async def test_connect_sends_state(ws_client):
    state = ws_client.initial_state
    assert state is not None
    assert state["type"] == "state"
    assert state["active_kid_id"] == "kid_a"
    assert any(k["id"] == "kid_a" for k in state["kids"])


@pytest.mark.asyncio
async def test_ping_pong(ws_client):
    pong = await ws_client.request({"type": "ping"}, "pong")
    assert pong["type"] == "pong"


@pytest.mark.asyncio
async def test_get_state(ws_client):
    state = await ws_client.request({"type": "get_state"}, "state")
    assert "avatar" in state
    assert "computer_use" in state


@pytest.mark.asyncio
async def test_set_and_clear_kid(ws_client):
    state = await ws_client.request({"type": "clear_kid"}, "state")
    assert state["active_kid_id"] is None
    assert state["needs_who_is_playing"] is True

    state = await ws_client.request({"type": "set_kid", "kid_id": "kid_a"}, "state")
    assert state["active_kid_id"] == "kid_a"
    assert state["needs_who_is_playing"] is False


@pytest.mark.asyncio
async def test_identify_voice_match_and_reject(ws_client):
    await ws_client.send({"type": "clear_kid"})
    await ws_client.recv_until("state")

    ok = await ws_client.request(
        {"type": "identify_voice", "transcript": "My name is Maya"},
        "identify_result",
    )
    assert ok["ok"] is True

    await ws_client.send({"type": "clear_kid"})
    await ws_client.recv_until("state")

    bad = await ws_client.request(
        {"type": "identify_voice", "transcript": "My name is Taylor"},
        "identify_result",
    )
    assert bad["ok"] is False


@pytest.mark.asyncio
async def test_set_avatar(ws_client):
    state = await ws_client.request(
        {
            "type": "set_avatar",
            "pack_id": "starter",
            "character_id": "luna",
            "gender": "girl",
        },
        "state",
    )
    assert state["avatar"]["character_id"] == "luna"
    assert state["avatar"]["gender"] == "girl"


@pytest.mark.asyncio
async def test_parent_unlock_wrong_and_right(ws_client):
    bad = await ws_client.request({"type": "parent_unlock", "pin": "0000"}, "parent_unlock_result")
    assert bad["ok"] is False
    assert bad["settings"] is None

    good = await ws_client.request({"type": "parent_unlock", "pin": "1234"}, "parent_unlock_result")
    assert good["ok"] is True
    assert good["settings"] is not None
    assert "cloud" in good["settings"]


@pytest.mark.asyncio
async def test_parent_save_requires_unlock(ws_client, e2e_server):
    blocked = await ws_client.request(
        {"type": "parent_save", "patch": {"ai_mode": "local"}},
        "parent_save_result",
    )
    assert blocked["ok"] is False

    await ws_client.request({"type": "parent_unlock", "pin": "1234"}, "parent_unlock_result")
    saved = await ws_client.request(
        {
            "type": "parent_save",
            "patch": {
                "computer_use": {"mode": "ask"},
                "ai_mode": "cloud",
            },
        },
        "parent_save_result",
    )
    assert saved["ok"] is True
    # state broadcast follows
    state = await ws_client.recv_until("state")
    assert state["computer_use"]["mode"] == "ask"
    assert e2e_server["server"].config.computer_use.mode == "ask"


@pytest.mark.asyncio
async def test_onboard_first_kid_when_empty(isolated_data, fake_os, stub_engine):
    import websockets
    from kids_agent.config import AppConfig, save_config
    from kids_agent.safety import set_pin
    from kids_agent.server import AgentServer
    from tests.e2e.helpers import WsClient

    cfg = AppConfig(kids=[], active_kid_id=None)
    set_pin(cfg, "1234")
    save_config(cfg, isolated_data / "config.local.json")
    server = AgentServer(cfg, os_adapter=fake_os, engine=stub_engine)
    server._hardware = {"vram_mb": None, "ollama_ok": False, "ollama_models": []}

    async with websockets.serve(server.handle, "127.0.0.1", 0) as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            client = WsClient(ws)
            await client.recv_until("state")
            await client.send(
                {
                    "type": "onboard_kid",
                    "name": "Sam",
                    "age": 5,
                    "english_level": "unsure",
                    "preferred_gender": "neutral",
                }
            )
            result = await client.recv_until("onboard_kid_result")
            assert result["ok"] is True
            assert result["kid"]["english_level"] == "beginner"
            state = await client.recv_until("state")
            assert len(state["kids"]) == 1
            assert state["active_kid_id"]


@pytest.mark.asyncio
async def test_parent_setup_required_when_no_pin(isolated_data, fake_os, stub_engine):
    import websockets
    from kids_agent.config import AppConfig
    from kids_agent.server import AgentServer
    from kids_agent.safety import verify_pin
    from tests.e2e.helpers import WsClient

    cfg = AppConfig(parent_pin="", parent_pin_hash=None, kids=[], active_kid_id=None)
    server = AgentServer(cfg, os_adapter=fake_os, engine=stub_engine)
    server._hardware = {"vram_mb": None, "ollama_ok": False, "ollama_models": []}

    async with websockets.serve(server.handle, "127.0.0.1", 0) as ws_server:
        port = ws_server.sockets[0].getsockname()[1]
        async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
            client = WsClient(ws)
            state = await client.recv_until("state")
            assert state["needs_parent_setup"] is True
            blocked = await client.request(
                {"type": "onboard_kid", "name": "Sam", "age": 5},
                "onboard_kid_result",
            )
            assert blocked["ok"] is False
            ok = await client.request(
                {"type": "parent_setup", "pin": "2468", "ai_mode": "local"},
                "parent_setup_result",
            )
            assert ok["ok"] is True
            assert verify_pin(server.config, "2468")
            state = await client.recv_until("state")
            assert state["needs_parent_setup"] is False


@pytest.mark.asyncio
async def test_onboard_second_kid_requires_parent(ws_client):
    blocked = await ws_client.request(
        {"type": "onboard_kid", "name": "Leo", "age": 7},
        "onboard_kid_result",
    )
    assert blocked["ok"] is False
    assert "parent" in blocked["error"].lower()

    await ws_client.request({"type": "parent_unlock", "pin": "1234"}, "parent_unlock_result")
    ok = await ws_client.request(
        {
            "type": "onboard_kid",
            "name": "Leo",
            "age": 7,
            "english_level": "elementary",
        },
        "onboard_kid_result",
    )
    assert ok["ok"] is True


@pytest.mark.asyncio
async def test_onboard_age_clamped_to_2_18(ws_client):
    await ws_client.request({"type": "parent_unlock", "pin": "1234"}, "parent_unlock_result")
    too_old = await ws_client.request(
        {"type": "onboard_kid", "name": "Old", "age": 42},
        "onboard_kid_result",
    )
    assert too_old["ok"] is True
    assert too_old["kid"]["age"] == 18
    await ws_client.drain()
    too_young = await ws_client.request(
        {"type": "onboard_kid", "name": "Tiny", "age": 0},
        "onboard_kid_result",
    )
    assert too_young["ok"] is True
    assert too_young["kid"]["age"] == 2


@pytest.mark.asyncio
async def test_games_start_answer_cancel(ws_client):
    await ws_client.send({"type": "start_game", "kind": "spell"})
    state = await ws_client.recv_until("state")
    assert state["game"] is not None
    assert state["game"]["kind"] == "spell"
    reply = await ws_client.recv_until("assistant_reply")
    assert reply["text"]

    await ws_client.send({"type": "user_text", "text": "zzzznotaword"})
    await ws_client.recv_until("assistant_reply")
    # Game answer path also emits avatar_state + state
    state = await ws_client.recv_until("state")
    assert state["game"] is not None

    state = await ws_client.request({"type": "cancel_game"}, "state")
    assert state["game"] is None


@pytest.mark.asyncio
async def test_user_text_uses_stub_engine(ws_client, e2e_server):
    engine: StubEngine = e2e_server["stub_engine"]
    engine.default_text = "Stub says hi."
    await ws_client.send({"type": "user_text", "text": "Hello friend"})
    # may get avatar_state thinking first
    reply = await ws_client.recv_until("assistant_reply")
    assert "Stub says hi" in reply["text"]
    assert "Hello friend" in engine.calls


@pytest.mark.asyncio
async def test_time_limit_blocks_chat(ws_client, e2e_server, isolated_data):
    from kids_agent.usage import UsageTracker

    server = e2e_server["server"]
    kid = server._kid()
    assert kid is not None
    kid.daily_limit_minutes = 1
    tracker = UsageTracker(server.config)
    tracker.add_minutes(kid, 1.0)
    server.usage = tracker

    await ws_client.send({"type": "user_text", "text": "hello"})
    reply = await ws_client.recv_until("assistant_reply")
    assert reply.get("error") == "time_limit"


@pytest.mark.asyncio
async def test_budget_blocks_cloud_chat(ws_client, e2e_server):
    from kids_agent.budget import BudgetTracker

    server = e2e_server["server"]
    server.config.cloud.daily_budget_usd = 0.01
    tracker = BudgetTracker(server.config)
    tracker.add_estimate(0.05)
    server.budget = tracker

    await ws_client.send({"type": "user_text", "text": "hello"})
    reply = await ws_client.recv_until("assistant_reply")
    assert reply.get("error") == "over_budget"


@pytest.mark.asyncio
async def test_computer_use_ask_pending_wrong_pin_deny(ws_client, e2e_server):
    server = e2e_server["server"]
    engine: StubEngine = e2e_server["stub_engine"]

    await ws_client.request({"type": "parent_unlock", "pin": "1234"}, "parent_unlock_result")
    await ws_client.request(
        {"type": "parent_save", "patch": {"computer_use": {"mode": "ask"}}},
        "parent_save_result",
    )
    await ws_client.recv_until("state")

    engine.enqueue_screenshot_then_done()
    await ws_client.send({"type": "user_text", "text": "Look at my screen"})
    # pending event + assistant_reply + possibly state
    pending_ev = await ws_client.recv_until("computer_use_event")
    assert pending_ev["event"] == "pending"
    assert server.computer_use.pending is not None

    await ws_client.send({"type": "computer_use_approve", "pin": "0000"})
    fail = await ws_client.recv_until("computer_use_event")
    assert fail["ok"] is False
    assert server.computer_use.pending is not None

    await ws_client.send({"type": "computer_use_deny"})
    denied = await ws_client.recv_until("computer_use_event")
    assert denied["event"] == "denied"
    assert server.computer_use.pending is None


@pytest.mark.asyncio
async def test_computer_use_session_and_stop_broadcast(e2e_server):
    import asyncio
    import json

    import websockets

    from tests.e2e.helpers import WsClient

    url = e2e_server["url"]
    server = e2e_server["server"]
    server.config.computer_use.mode = "session"
    set_pin(server.config, "1234")

    async with websockets.connect(url) as ws1, websockets.connect(url) as ws2:
        c1, c2 = WsClient(ws1), WsClient(ws2)
        await c1.recv_until("state")
        await c2.recv_until("state")

        await c1.send({"type": "computer_use_start_session", "pin": "1234"})
        ev = await c1.recv_until("computer_use_event")
        assert ev["ok"] is True
        assert server.computer_use.session_active()

        # Second client should see state update if we broadcast — start_session broadcasts state
        await c2.recv_until("state")

        await c1.send({"type": "computer_use_stop"})
        stop1 = await c1.recv_until("computer_use_event")
        assert stop1["event"] == "stopped"
        stop2 = await c2.recv_until("computer_use_event")
        assert stop2["event"] == "stopped"
        assert not server.computer_use.session_active()


@pytest.mark.asyncio
async def test_computer_use_approve_resume_with_vision(ws_client, e2e_server):
    server = e2e_server["server"]
    engine: StubEngine = e2e_server["stub_engine"]
    fake_os = e2e_server["fake_os"]

    await ws_client.request({"type": "parent_unlock", "pin": "1234"}, "parent_unlock_result")
    await ws_client.request(
        {"type": "parent_save", "patch": {"computer_use": {"mode": "ask"}}},
        "parent_save_result",
    )
    await ws_client.recv_until("state")

    engine.enqueue_screenshot_then_done()
    # After approve, loop continues and needs another scripted reply
    # enqueue_screenshot_then_done already has second "I see the desktop"

    await ws_client.send({"type": "user_text", "text": "What is on screen?"})
    await ws_client.recv_until("computer_use_event")  # pending
    # drain assistant_reply from pause
    await ws_client.recv_until("assistant_reply")

    await ws_client.send({"type": "computer_use_approve", "pin": "1234"})
    approve_ev = await ws_client.recv_until("computer_use_event")
    assert approve_ev["ok"] is True
    # resume produces assistant_reply with vision follow-up
    reply = await ws_client.recv_until("assistant_reply")
    assert reply["text"]
    # FakeOS should have taken a screenshot
    assert any(e2e_server["data"].joinpath("data", "screenshots").glob("*.png")) or True
    # screenshot path under tmp repo_root/data/screenshots
    shots = list((e2e_server["data"] / "data" / "screenshots").glob("*.png"))
    assert len(shots) >= 1
