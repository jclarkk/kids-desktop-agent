from __future__ import annotations

import asyncio
import json
import logging
import shutil
import uuid
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection

from kids_agent.avatars import list_packs
from kids_agent.budget import BudgetTracker
from kids_agent.computer_use import ComputerUseGate
from kids_agent.content_filter import KID_SAFE_REFUSAL, screen_text
from kids_agent.config import (
    AllowlistApp,
    AllowlistWebsite,
    AppConfig,
    KidProfile,
    app_data_root,
    load_config,
    save_config,
)
from kids_agent.engines.agent_loop import run_agent_loop
from kids_agent.engines.router import EngineRouter
from kids_agent.games import GameSession, games_for_age, score_answer, start_game
from kids_agent.hardware import detect_hardware
from kids_agent.identity import (
    kid_identity_status,
    match_face,
    match_kid_by_spoken_name,
    public_kids_with_identity,
    save_face_image,
    save_voice_sample,
)
from kids_agent.model_catalog import recommend_for_vram
from kids_agent.os_adapter import get_os_adapter
from kids_agent.os_adapter.base import OSAdapter
from kids_agent.prompts import build_system_prompt, normalize_english_level
from kids_agent.safety import TranscriptLogger, set_pin, verify_pin
from kids_agent.skills.registry import SkillRegistry
from kids_agent.speech import probe_speech_capabilities, transcribe_audio_b64
from kids_agent.tts import kokoro_available, speed_for_english_level, synthesize_wav_b64
from kids_agent.usage import UsageTracker
from kids_agent.engines.base import VoiceEngine

log = logging.getLogger("kids_agent")

ALL_SKILLS = [
    "open_app",
    "open_website",
    "set_volume",
    "start_timer",
    "list_windows",
]

CLOUD_TURN_ESTIMATE_USD = 0.01
TURN_MINUTES = 0.5


class AgentServer:
    def __init__(
        self,
        config: AppConfig,
        *,
        os_adapter: OSAdapter | None = None,
        engine: VoiceEngine | None = None,
    ) -> None:
        self.config = config
        self.os = os_adapter or get_os_adapter()
        self.computer_use = ComputerUseGate(config, self.os)
        self.skills = SkillRegistry(config, self.os, self.computer_use)
        self._injected_engine = engine
        self.engine: VoiceEngine = engine or EngineRouter(config, self.skills.tools_schema())
        self.transcripts = TranscriptLogger(config)
        self.budget = BudgetTracker(config)
        self.usage = UsageTracker(config)
        if config.active_kid_id and any(k.id == config.active_kid_id for k in config.kids):
            self.active_kid_id = config.active_kid_id
        else:
            self.active_kid_id = config.kids[0].id if config.kids else None
        self._parent_sessions: set[int] = set()
        self._clients: set[ServerConnection] = set()
        self._hardware: dict[str, Any] | None = None
        self._game: GameSession | None = None
        self._paused_agent: dict[str, Any] | None = None
        self._timer_tasks: set[asyncio.Task[None]] = set()
        self.transcripts.purge_old()

    def _rebuild_engine(self) -> None:
        self.computer_use.config = self.config
        self.skills = SkillRegistry(self.config, self.os, self.computer_use)
        if self._injected_engine is not None:
            self.engine = self._injected_engine
        else:
            self.engine = EngineRouter(self.config, self.skills.tools_schema())
        self.transcripts = TranscriptLogger(self.config)
        self.budget = BudgetTracker(self.config)
        self.usage = UsageTracker(self.config)

    def _kid(self) -> KidProfile | None:
        if not self.active_kid_id:
            return None
        return next((k for k in self.config.kids if k.id == self.active_kid_id), None)

    def _needs_parent_setup(self) -> bool:
        return not bool(self.config.parent_pin_hash or self.config.parent_pin)

    def public_state(self) -> dict[str, Any]:
        kid = self._kid()
        age = kid.age if kid else 7
        vram_mb = (self._hardware or {}).get("vram_mb")
        return {
            "type": "state",
            "ai_mode": self.config.ai_mode,
            "needs_parent_setup": self._needs_parent_setup(),
            "avatar": self.config.avatar.model_dump(),
            "voice_id": self.config.voice_for_gender(),
            "avatar_packs": list_packs(),
            "kids": public_kids_with_identity(self.config),
            "active_kid_id": self.active_kid_id,
            "usage": self.usage.status_for(kid),
            "game": self._game.to_dict() if self._game else None,
            "games_available": games_for_age(age),
            "identity": self.config.identity.model_dump(),
            "needs_who_is_playing": bool(
                self.config.identity.require_who_is_playing and not self.active_kid_id
            ),
            "skills_enabled": self.config.allowlist.skills_enabled,
            "has_api_key": bool(self.config.cloud.api_key),
            "chat_model": self.config.cloud.chat_model,
            "local_model": self.config.local.llm_model,
            "cloud_provider": self.config.cloud.provider,
            "daily_budget_usd": self.config.cloud.daily_budget_usd,
            "budget": self.budget.status(),
            "model_presets": self.config.cloud.presets,
            "computer_use_mode": self.config.computer_use.mode,
            "computer_use": self.computer_use.status(),
            "hardware": self._hardware,
            "local_catalog": recommend_for_vram(vram_mb),
            "speech": probe_speech_capabilities().to_dict(),
        }

    async def refresh_hardware(self) -> dict[str, Any]:
        info = await detect_hardware(self.config.local.ollama_base_url)
        self._hardware = info.to_dict()
        return self._hardware

    async def broadcast(self, payload: dict[str, Any]) -> None:
        raw = json.dumps(payload)
        dead: list[ServerConnection] = []
        for client in self._clients:
            try:
                await client.send(raw)
            except Exception:  # noqa: BLE001
                dead.append(client)
        for client in dead:
            self._clients.discard(client)

    async def handle(self, websocket: ServerConnection) -> None:
        log.info("Client connected")
        self._clients.add(websocket)
        try:
            if self._hardware is None:
                try:
                    await self.refresh_hardware()
                except Exception as exc:  # noqa: BLE001
                    log.warning("Hardware probe failed: %s", exc)
                    self._hardware = {"vram_mb": None, "ollama_ok": False, "ollama_models": []}
            await websocket.send(json.dumps(self.public_state()))
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue
                await self.dispatch(websocket, msg)
        finally:
            self._clients.discard(websocket)
            self._parent_sessions.discard(id(websocket))

    async def dispatch(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")
        if mtype == "ping":
            await websocket.send(json.dumps({"type": "pong"}))
            return

        if mtype == "get_state":
            await websocket.send(json.dumps(self.public_state()))
            return

        if mtype == "refresh_hardware":
            await self.refresh_hardware()
            await websocket.send(json.dumps(self.public_state()))
            return

        if mtype == "parent_setup":
            await self._parent_setup(websocket, msg)
            return

        if mtype == "set_avatar":
            gender = msg.get("gender")
            character_id = msg.get("character_id")
            pack_id = msg.get("pack_id")
            if gender in ("boy", "girl", "neutral"):
                self.config.avatar.gender = gender
            if character_id:
                self.config.avatar.character_id = str(character_id)
            if pack_id:
                self.config.avatar.pack_id = str(pack_id)
            try:
                save_config(self.config)
            except OSError as exc:
                log.warning("Could not persist avatar choice: %s", exc)
            await websocket.send(json.dumps(self.public_state()))
            return

        if mtype == "set_kid":
            kid_id = msg.get("kid_id")
            if any(k.id == kid_id for k in self.config.kids):
                self._activate_kid(str(kid_id))
            await websocket.send(json.dumps(self.public_state()))
            return

        if mtype == "clear_kid":
            self.active_kid_id = None
            self.config.active_kid_id = None
            try:
                save_config(self.config)
            except OSError:
                pass
            await websocket.send(json.dumps(self.public_state()))
            return

        if mtype == "onboard_kid":
            if self._needs_parent_setup():
                await websocket.send(
                    json.dumps(
                        {
                            "type": "onboard_kid_result",
                            "ok": False,
                            "error": "Parent setup required before adding a child.",
                        }
                    )
                )
                return
            await self._onboard_kid(websocket, msg)
            return

        if mtype == "enroll_voice":
            await self._enroll_voice(websocket, msg)
            return

        if mtype == "enroll_face":
            await self._enroll_face(websocket, msg)
            return

        if mtype == "identify_voice":
            await self._identify_voice(websocket, msg)
            return

        if mtype == "identify_face":
            await self._identify_face(websocket, msg)
            return

        if mtype == "start_game":
            await self._start_game(websocket, str(msg.get("kind") or "word_of_the_day"))
            return

        if mtype == "cancel_game":
            self._game = None
            await websocket.send(json.dumps(self.public_state()))
            return

        if mtype == "computer_use_stop":
            note = self.computer_use.emergency_stop()
            self._paused_agent = None
            self.transcripts.write("system", note, event="computer_use_stop")
            await self.broadcast({"type": "computer_use_event", "event": "stopped", "message": note})
            await self.broadcast(self.public_state())
            return

        if mtype == "computer_use_start_session":
            ok, note = self.computer_use.start_session(str(msg.get("pin", "")))
            await websocket.send(
                json.dumps({"type": "computer_use_event", "event": "session", "ok": ok, "message": note})
            )
            if ok:
                self.transcripts.write("system", note, event="computer_use_session")
                await self.broadcast(self.public_state())
            return

        if mtype == "computer_use_approve":
            result = self.computer_use.approve_pending(str(msg.get("pin", "")))
            await websocket.send(
                json.dumps(
                    {
                        "type": "computer_use_event",
                        "event": "approve",
                        "ok": result.ok,
                        "message": result.message,
                        "needs_approval": result.needs_approval,
                    }
                )
            )
            if result.ok:
                self.transcripts.write("tool", result.message, skill="computer_use_approve")
                await self._resume_paused_agent(websocket, result)
            elif not result.needs_approval:
                self._paused_agent = None
                await self.broadcast(
                    {
                        "type": "assistant_reply",
                        "user_transcript": "",
                        "text": result.message,
                        "gender": self.config.avatar.gender,
                    }
                )
                await self.broadcast(self.public_state())
            return

        if mtype == "computer_use_deny":
            note = self.computer_use.deny_pending()
            self._paused_agent = None
            await self.broadcast({"type": "computer_use_event", "event": "denied", "message": note})
            await self.broadcast(self.public_state())
            return

        if mtype == "parent_unlock":
            ok = verify_pin(self.config, str(msg.get("pin", "")))
            if ok:
                self._parent_sessions.add(id(websocket))
            await websocket.send(
                json.dumps(
                    {
                        "type": "parent_unlock_result",
                        "ok": ok,
                        "settings": self.config.settings_for_parent() if ok else None,
                        "hardware": self._hardware,
                        "local_catalog": recommend_for_vram((self._hardware or {}).get("vram_mb")),
                        "budget": self.budget.status(),
                    }
                )
            )
            return

        if mtype == "parent_save":
            if id(websocket) not in self._parent_sessions:
                await websocket.send(
                    json.dumps({"type": "parent_save_result", "ok": False, "error": "Unlock first"})
                )
                return
            try:
                self._apply_parent_patch(msg.get("patch") or {})
                save_config(self.config)
                self._rebuild_engine()
                await self.refresh_hardware()
                await websocket.send(
                    json.dumps(
                        {
                            "type": "parent_save_result",
                            "ok": True,
                            "settings": self.config.settings_for_parent(),
                            "budget": self.budget.status(),
                        }
                    )
                )
                await websocket.send(json.dumps(self.public_state()))
            except Exception as exc:  # noqa: BLE001
                await websocket.send(
                    json.dumps({"type": "parent_save_result", "ok": False, "error": str(exc)})
                )
            return

        if mtype == "privacy_clear":
            await self._privacy_clear(websocket, msg)
            return

        if mtype == "user_text":
            await self._handle_user_text(websocket, str(msg.get("text", "")).strip())
            return

        if mtype == "avatar_state":
            await websocket.send(json.dumps({"type": "avatar_state_ack", "state": msg.get("state")}))
            return

        if mtype == "tts_synthesize":
            text = str(msg.get("text") or "").strip()
            kid = self._kid()
            gender = str(msg.get("gender") or (kid.preferred_gender if kid else None) or self.config.avatar.gender)
            voice_id = str(msg.get("voice_id") or self.config.voice_for_gender(gender))
            level = str(msg.get("level") or (kid.english_level if kid else "beginner") or "beginner")
            speech = None
            if text and kokoro_available():
                speech = await asyncio.to_thread(
                    synthesize_wav_b64,
                    text,
                    voice=voice_id,
                    speed=speed_for_english_level(level),
                )
            await websocket.send(
                json.dumps(
                    {
                        "type": "tts_result",
                        "request_id": msg.get("request_id"),
                        "ok": speech is not None,
                        "speech": speech,
                        "voice_id": voice_id,
                        "fallback_browser": speech is None,
                    }
                )
            )
            return

        if mtype == "stt_transcribe":
            audio_b64 = str(msg.get("audio_b64") or "")
            ext = str(msg.get("ext") or "webm")
            try:
                text = await asyncio.to_thread(
                    transcribe_audio_b64,
                    audio_b64,
                    model_name=self.config.local.stt_model,
                    ext=ext,
                )
                await websocket.send(
                    json.dumps(
                        {
                            "type": "stt_result",
                            "ok": bool(text),
                            "text": text,
                            "request_id": msg.get("request_id"),
                        }
                    )
                )
            except Exception as exc:  # noqa: BLE001
                await websocket.send(
                    json.dumps(
                        {
                            "type": "stt_result",
                            "ok": False,
                            "error": str(exc),
                            "request_id": msg.get("request_id"),
                        }
                    )
                )
            return

        await websocket.send(json.dumps({"type": "error", "message": f"Unknown type: {mtype}"}))

    async def _privacy_clear(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        if id(websocket) not in self._parent_sessions:
            await websocket.send(json.dumps({"type": "privacy_clear_result", "ok": False, "error": "Unlock first"}))
            return
        target = str(msg.get("target") or "")
        try:
            if target == "transcripts":
                self.transcripts.clear()
            elif target == "screenshots":
                shutil.rmtree(app_data_root() / "screenshots", ignore_errors=True)
            elif target == "kid_data":
                shutil.rmtree(app_data_root() / "kids", ignore_errors=True)
                for kid in self.config.kids:
                    kid.face_enrolled = False
                    kid.voice_enrolled = False
                save_config(self.config)
            else:
                await websocket.send(
                    json.dumps({"type": "privacy_clear_result", "ok": False, "error": "Unknown target"})
                )
                return
            await websocket.send(json.dumps({"type": "privacy_clear_result", "ok": True, "target": target}))
            await websocket.send(json.dumps(self.public_state()))
        except OSError as exc:
            await websocket.send(json.dumps({"type": "privacy_clear_result", "ok": False, "error": str(exc)}))

    def _start_timer_task(self, seconds: int, label: str) -> None:
        async def run_timer() -> None:
            await self.broadcast(
                {"type": "timer_event", "event": "started", "label": label, "seconds": seconds}
            )
            await asyncio.sleep(seconds)
            await self.broadcast(
                {
                    "type": "timer_event",
                    "event": "done",
                    "label": label,
                    "message": f"{label} is done!",
                }
            )

        task = asyncio.create_task(run_timer())
        self._timer_tasks.add(task)
        task.add_done_callback(lambda done: self._timer_tasks.discard(done))

    async def _parent_setup(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        if not self._needs_parent_setup():
            await websocket.send(
                json.dumps({"type": "parent_setup_result", "ok": False, "error": "Parent PIN already exists."})
            )
            return
        pin = str(msg.get("pin") or "").strip()
        if len(pin) < 4:
            await websocket.send(
                json.dumps({"type": "parent_setup_result", "ok": False, "error": "PIN must be at least 4 digits."})
            )
            return

        ai_mode = str(msg.get("ai_mode") or self.config.ai_mode)
        if ai_mode not in ("cloud", "local", "hybrid"):
            ai_mode = self.config.ai_mode
        needs_cloud = ai_mode in ("cloud", "hybrid")
        needs_local = ai_mode in ("local", "hybrid")

        api_key = str(msg.get("api_key") or "").strip()
        if needs_cloud and not api_key:
            await websocket.send(
                json.dumps(
                    {
                        "type": "parent_setup_result",
                        "ok": False,
                        "error": "Cloud or hybrid mode needs an API key.",
                    }
                )
            )
            return

        # Persist only after validation so a rejected attempt does not set the PIN.
        set_pin(self.config, pin)
        self.config.ai_mode = ai_mode  # type: ignore[assignment]

        if needs_cloud:
            self.config.cloud.api_key = api_key
            provider = str(msg.get("provider") or "").strip()
            if provider:
                self.config.cloud.provider = provider
            base_url = str(msg.get("base_url") or "").strip()
            if base_url:
                self.config.cloud.base_url = base_url
            chat_model = str(msg.get("chat_model") or "").strip()
            if chat_model:
                self.config.cloud.chat_model = chat_model
            try:
                if msg.get("daily_budget_usd") is not None:
                    self.config.cloud.daily_budget_usd = max(0.0, float(msg["daily_budget_usd"]))
            except (TypeError, ValueError):
                pass

        if needs_local:
            llm_model = str(msg.get("llm_model") or "").strip()
            if llm_model:
                self.config.local.llm_model = llm_model
            ollama_url = str(msg.get("ollama_base_url") or "").strip()
            if ollama_url:
                self.config.local.ollama_base_url = ollama_url

        try:
            daily_limit = max(15, min(240, int(msg.get("daily_limit_minutes", 60))))
            self.config.default_daily_limit_minutes = daily_limit
            for kid in self.config.kids:
                kid.daily_limit_minutes = daily_limit
        except (TypeError, ValueError):
            pass

        # Computer-use stays off until a parent explicitly enables it later.
        self.config.computer_use.mode = "off"

        save_config(self.config)
        self._parent_sessions.add(id(websocket))
        self._rebuild_engine()
        await self.refresh_hardware()
        await websocket.send(
            json.dumps(
                {
                    "type": "parent_setup_result",
                    "ok": True,
                    "settings": self.config.settings_for_parent(),
                }
            )
        )
        await websocket.send(json.dumps(self.public_state()))

    async def _start_game(self, websocket: ServerConnection, kind: str) -> None:
        kid = self._kid()
        if not self.usage.can_play(kid):
            await websocket.send(
                json.dumps(
                    {
                        "type": "assistant_reply",
                        "user_transcript": "",
                        "text": "Today's play time is finished. Ask a parent for more time tomorrow!",
                        "error": "time_limit",
                        "usage": self.usage.status_for(kid),
                    }
                )
            )
            return
        try:
            self._game = start_game(kind, age=kid.age if kid else 7)
        except ValueError as exc:
            await websocket.send(json.dumps({"type": "error", "message": str(exc)}))
            return
        await websocket.send(json.dumps(self.public_state()))
        await websocket.send(
            json.dumps(
                {
                    "type": "assistant_reply",
                    "user_transcript": "",
                    "text": self._game.prompt,
                    "voice_id": self.config.voice_for_gender(),
                    "gender": self.config.avatar.gender,
                    "game": self._game.to_dict(),
                }
            )
        )

    def _activate_kid(self, kid_id: str) -> None:
        self.active_kid_id = kid_id
        self.config.active_kid_id = kid_id
        kid = self._kid()
        if kid:
            if kid.preferred_gender in ("boy", "girl", "neutral"):
                self.config.avatar.gender = kid.preferred_gender
            if kid.preferred_avatar:
                self.config.avatar.character_id = kid.preferred_avatar
        try:
            save_config(self.config)
        except OSError as exc:
            log.warning("Could not persist kid: %s", exc)

    async def _onboard_kid(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        # Parent-unlocked OR first kid when list empty
        parent_ok = id(websocket) in self._parent_sessions
        if self.config.kids and not parent_ok:
            await websocket.send(
                json.dumps(
                    {
                        "type": "onboard_kid_result",
                        "ok": False,
                        "error": "Ask a parent to unlock settings to add another child.",
                    }
                )
            )
            return

        name = str(msg.get("name") or "").strip()
        if len(name) < 1:
            await websocket.send(
                json.dumps({"type": "onboard_kid_result", "ok": False, "error": "Name required"})
            )
            return
        try:
            age = int(msg.get("age", 6))
        except (TypeError, ValueError):
            age = 6
        age = max(2, min(18, age))
        gender = msg.get("preferred_gender") or "neutral"
        if gender not in ("boy", "girl", "neutral"):
            gender = "neutral"
        kid_id = str(msg.get("id") or f"kid_{uuid.uuid4().hex[:8]}")
        if any(k.id == kid_id for k in self.config.kids):
            kid_id = f"kid_{uuid.uuid4().hex[:8]}"

        kid = KidProfile(
            id=kid_id,
            name=name,
            age=age,
            preferred_avatar=str(msg.get("preferred_avatar") or "sparky"),
            preferred_gender=gender,
            daily_limit_minutes=int(
                msg.get("daily_limit_minutes") or self.config.default_daily_limit_minutes or 60
            ),
            english_level=normalize_english_level(msg.get("english_level")),  # type: ignore[arg-type]
            onboarding_complete=True,
            magic_word=str(msg.get("magic_word") or "").strip()[:32],
        )
        self.config.kids.append(kid)
        self._activate_kid(kid.id)

        # Optional enrollments in same payload
        if msg.get("face_image_b64"):
            save_face_image(kid.id, str(msg["face_image_b64"]))
            kid.face_enrolled = True
        if msg.get("voice_audio_b64"):
            save_voice_sample(kid.id, str(msg["voice_audio_b64"]), ext=str(msg.get("voice_ext") or "webm"))
            kid.voice_enrolled = True

        save_config(self.config)
        await websocket.send(
            json.dumps(
                {
                    "type": "onboard_kid_result",
                    "ok": True,
                    "kid": kid_identity_status(kid) | kid.model_dump(),
                }
            )
        )
        await websocket.send(json.dumps(self.public_state()))
        await self._reply(
            websocket,
            user="",
            text=(
                f"Hi {kid.name}!"
                if kid.english_level == "beginner"
                else f"Hi {kid.name}! I'm so happy you're here. Let's learn English together."
            ),
        )

    async def _enroll_voice(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        kid_id = str(msg.get("kid_id") or self.active_kid_id or "")
        kid = next((k for k in self.config.kids if k.id == kid_id), None)
        if not kid or not msg.get("audio_b64"):
            await websocket.send(
                json.dumps({"type": "enroll_result", "ok": False, "kind": "voice", "error": "missing"})
            )
            return
        save_voice_sample(kid.id, str(msg["audio_b64"]), ext=str(msg.get("ext") or "webm"))
        kid.voice_enrolled = True
        save_config(self.config)
        await websocket.send(
            json.dumps(
                {
                    "type": "enroll_result",
                    "ok": True,
                    "kind": "voice",
                    "kid_id": kid.id,
                    "status": kid_identity_status(kid),
                }
            )
        )
        await websocket.send(json.dumps(self.public_state()))

    async def _enroll_face(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        kid_id = str(msg.get("kid_id") or self.active_kid_id or "")
        kid = next((k for k in self.config.kids if k.id == kid_id), None)
        if not kid or not msg.get("image_b64"):
            await websocket.send(
                json.dumps({"type": "enroll_result", "ok": False, "kind": "face", "error": "missing"})
            )
            return
        save_face_image(kid.id, str(msg["image_b64"]))
        kid.face_enrolled = True
        save_config(self.config)
        await websocket.send(
            json.dumps(
                {
                    "type": "enroll_result",
                    "ok": True,
                    "kind": "face",
                    "kid_id": kid.id,
                    "status": kid_identity_status(kid),
                }
            )
        )
        await websocket.send(json.dumps(self.public_state()))

    async def _identify_voice(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        if not self.config.identity.voice_name_match:
            await websocket.send(
                json.dumps({"type": "identify_result", "ok": False, "error": "Voice ID is turned off"})
            )
            return
        spoken = str(msg.get("transcript") or "").strip()
        kid, score, method = match_kid_by_spoken_name(self.config.kids, spoken)
        # Optional magic word boost
        if not kid:
            spoken_l = spoken.lower()
            for candidate in self.config.kids:
                if candidate.magic_word and candidate.magic_word.lower() in spoken_l:
                    kid, score, method = candidate, 1.0, "magic_word"
                    break
        if kid:
            self._activate_kid(kid.id)
            await websocket.send(
                json.dumps(
                    {
                        "type": "identify_result",
                        "ok": True,
                        "method": method,
                        "score": score,
                        "kid_id": kid.id,
                        "name": kid.name,
                    }
                )
            )
            await websocket.send(json.dumps(self.public_state()))
            await self._reply(websocket, user=spoken, text=f"Hi {kid.name}! Ready to play?")
        else:
            await websocket.send(
                json.dumps(
                    {
                        "type": "identify_result",
                        "ok": False,
                        "method": method,
                        "score": score,
                        "error": "I didn't catch a name. Try again or tap your picture.",
                    }
                )
            )

    async def _identify_face(self, websocket: ServerConnection, msg: dict[str, Any]) -> None:
        if not self.config.identity.face_match:
            await websocket.send(
                json.dumps({"type": "identify_result", "ok": False, "error": "Face ID is turned off"})
            )
            return
        image_b64 = str(msg.get("image_b64") or "")
        if not image_b64:
            await websocket.send(
                json.dumps({"type": "identify_result", "ok": False, "error": "No camera image"})
            )
            return
        kid, dist, method = match_face(
            self.config.kids,
            image_b64,
            max_distance=int(self.config.identity.face_match_threshold),
        )
        if kid:
            self._activate_kid(kid.id)
            await websocket.send(
                json.dumps(
                    {
                        "type": "identify_result",
                        "ok": True,
                        "method": method,
                        "distance": dist,
                        "kid_id": kid.id,
                        "name": kid.name,
                    }
                )
            )
            await websocket.send(json.dumps(self.public_state()))
            await self._reply(websocket, user="", text=f"Hi {kid.name}! I see you!")
        else:
            await websocket.send(
                json.dumps(
                    {
                        "type": "identify_result",
                        "ok": False,
                        "method": method,
                        "distance": dist,
                        "error": "I couldn't match a face. Tap your name or try better light.",
                    }
                )
            )

    def _apply_parent_patch(self, patch: dict[str, Any]) -> None:
        if "ai_mode" in patch and patch["ai_mode"] in ("cloud", "local", "hybrid"):
            self.config.ai_mode = patch["ai_mode"]

        cloud = patch.get("cloud") or {}
        if "provider" in cloud:
            self.config.cloud.provider = str(cloud["provider"])
        if "base_url" in cloud:
            self.config.cloud.base_url = str(cloud["base_url"])
        if "chat_model" in cloud:
            self.config.cloud.chat_model = str(cloud["chat_model"])
        if "daily_budget_usd" in cloud:
            self.config.cloud.daily_budget_usd = float(cloud["daily_budget_usd"])
        if "api_key" in cloud:
            key = str(cloud["api_key"]).strip()
            if key and "*" not in key:
                self.config.cloud.api_key = key

        local = patch.get("local") or {}
        if "llm_model" in local:
            self.config.local.llm_model = str(local["llm_model"])
        if "ollama_base_url" in local:
            self.config.local.ollama_base_url = str(local["ollama_base_url"])
        if "gpu_layers" in local:
            gl = local["gpu_layers"]
            if gl == "auto" or gl is None:
                self.config.local.gpu_layers = "auto"
            else:
                try:
                    self.config.local.gpu_layers = int(gl)
                except (TypeError, ValueError):
                    self.config.local.gpu_layers = "auto"
        if "allow_offload" in local:
            self.config.local.allow_offload = bool(local["allow_offload"])
        if "stt_model" in local:
            self.config.local.stt_model = str(local["stt_model"])

        if "parent_pin" in patch:
            pin = str(patch["parent_pin"]).strip()
            if len(pin) >= 4:
                set_pin(self.config, pin)

        if "kids" in patch and isinstance(patch["kids"], list):
            kids: list[KidProfile] = []
            for raw in patch["kids"]:
                if not isinstance(raw, dict):
                    continue
                kid_id = str(raw.get("id") or "").strip()
                name = str(raw.get("name") or "").strip()
                if not kid_id or not name:
                    continue
                kids.append(
                    KidProfile(
                        id=kid_id,
                        name=name,
                        age=int(raw.get("age") or 7),
                        preferred_avatar=str(raw.get("preferred_avatar") or "sparky"),
                        preferred_gender=raw.get("preferred_gender") or "neutral",
                        daily_limit_minutes=int(raw.get("daily_limit_minutes") or 60),
                        english_level=normalize_english_level(raw.get("english_level")),  # type: ignore[arg-type]
                        onboarding_complete=bool(raw.get("onboarding_complete", True)),
                        voice_enrolled=bool(raw.get("voice_enrolled", False)),
                        face_enrolled=bool(raw.get("face_enrolled", False)),
                        magic_word=str(raw.get("magic_word") or "")[:32],
                    )
                )
            if kids:
                self.config.kids = kids
                if self.active_kid_id not in {k.id for k in kids}:
                    self.active_kid_id = kids[0].id
                    self.config.active_kid_id = kids[0].id

        identity = patch.get("identity") or {}
        if "require_who_is_playing" in identity:
            self.config.identity.require_who_is_playing = bool(identity["require_who_is_playing"])
        if "voice_name_match" in identity:
            self.config.identity.voice_name_match = bool(identity["voice_name_match"])
        if "face_match" in identity:
            self.config.identity.face_match = bool(identity["face_match"])
        if "allow_tap_select" in identity:
            self.config.identity.allow_tap_select = bool(identity["allow_tap_select"])
        if "face_match_threshold" in identity:
            self.config.identity.face_match_threshold = int(identity["face_match_threshold"])

        allow = patch.get("allowlist") or {}
        if "skills_enabled" in allow:
            enabled = [s for s in allow["skills_enabled"] if s in ALL_SKILLS]
            self.config.allowlist.skills_enabled = enabled
        if "apps" in allow and isinstance(allow["apps"], list):
            apps: list[AllowlistApp] = []
            for raw in allow["apps"]:
                if not isinstance(raw, dict):
                    continue
                app_id = str(raw.get("id") or "").strip()
                if not app_id:
                    continue
                apps.append(
                    AllowlistApp(
                        id=app_id,
                        label=str(raw.get("label") or app_id),
                        windows=dict(raw.get("windows") or {}),
                        macos=dict(raw.get("macos") or {}),
                    )
                )
            self.config.allowlist.apps = apps
        if "websites" in allow and isinstance(allow["websites"], list):
            sites: list[AllowlistWebsite] = []
            for raw in allow["websites"]:
                if not isinstance(raw, dict):
                    continue
                site_id = str(raw.get("id") or "").strip()
                url = str(raw.get("url") or "").strip()
                if not site_id or not url:
                    continue
                sites.append(
                    AllowlistWebsite(
                        id=site_id,
                        label=str(raw.get("label") or site_id),
                        url=url,
                    )
                )
            self.config.allowlist.websites = sites

        cu = patch.get("computer_use") or {}
        if "mode" in cu and cu["mode"] in ("off", "ask", "session"):
            self.config.computer_use.mode = cu["mode"]
            if cu["mode"] == "off":
                self.computer_use.emergency_stop()
        if "session_ttl_minutes" in cu:
            try:
                self.config.computer_use.session_ttl_minutes = max(
                    1, min(120, int(cu["session_ttl_minutes"]))
                )
            except (TypeError, ValueError):
                pass
        if "max_agent_steps" in cu:
            try:
                self.config.computer_use.max_agent_steps = max(
                    1, min(12, int(cu["max_agent_steps"]))
                )
            except (TypeError, ValueError):
                pass
        if "vision_max_side" in cu:
            try:
                self.config.computer_use.vision_max_side = max(
                    256, min(2048, int(cu["vision_max_side"]))
                )
            except (TypeError, ValueError):
                pass

        safety = patch.get("safety") or {}
        if "log_transcripts" in safety:
            self.config.safety.log_transcripts = bool(safety["log_transcripts"])
        if "content_strictness" in safety:
            self.config.safety.content_strictness = str(safety["content_strictness"])

    def _uses_cloud_llm(self) -> bool:
        """True when this turn is billed as cloud (actual route, not mode alone)."""
        mode = self.config.ai_mode
        if mode == "local":
            return False
        route = getattr(self.engine, "last_route", None)
        if mode == "hybrid":
            return route == "cloud" and bool(self.config.cloud.api_key)
        return True

    def _engine_used(self) -> str | None:
        route = getattr(self.engine, "last_route", None)
        if route in ("local", "cloud"):
            return str(route)
        mode = self.config.ai_mode
        if mode == "local":
            return "local"
        if mode == "cloud":
            return "cloud"
        return None

    async def _reply(
        self,
        websocket: ServerConnection,
        *,
        user: str,
        text: str,
        error: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        kid = self._kid()
        gender = (kid.preferred_gender if kid else None) or self.config.avatar.gender
        voice_id = self.config.voice_for_gender(gender)
        level = (kid.english_level if kid else "beginner") or "beginner"

        if text and error is None:
            filtered = await screen_text(self.config, text, kid=kid, direction="output")
            if not filtered.ok:
                log.warning("Blocked assistant output via %s filter: %s", filtered.source, filtered.reason)
                text = KID_SAFE_REFUSAL
                error = "content_filter"

        speech: dict[str, Any] | None = None
        speakable = (text or "").strip()
        # Skip neural TTS for pure error/system beeps that kids shouldn't hear as long speeches
        if speakable and kokoro_available() and error not in ("over_budget",):
            speed = speed_for_english_level(str(level))
            speech = await asyncio.to_thread(
                synthesize_wav_b64,
                speakable,
                voice=voice_id,
                speed=speed,
            )

        payload: dict[str, Any] = {
            "type": "assistant_reply",
            "user_transcript": user,
            "text": text,
            "voice_id": voice_id,
            "gender": gender,
            "error": error,
            "ai_mode": self.config.ai_mode,
            "budget": self.budget.status(),
            "usage": self.usage.status_for(kid),
            "game": self._game.to_dict() if self._game else None,
            "speech": speech,
        }
        if extra:
            payload.update(extra)
        await websocket.send(json.dumps(payload))
        await websocket.send(json.dumps({"type": "avatar_state", "state": "speaking"}))
        await asyncio.sleep(0.05)

    async def _handle_user_text(self, websocket: ServerConnection, text: str) -> None:
        if not text:
            return

        kid = self._kid()
        filtered = await screen_text(self.config, text, kid=kid, direction="input")
        if not filtered.ok:
            log.warning("Blocked user input via %s filter: %s", filtered.source, filtered.reason)
            self.transcripts.write("user", text, blocked=True, reason=filtered.reason)
            await self._reply(
                websocket,
                user=text,
                text=KID_SAFE_REFUSAL,
                error="content_filter",
            )
            return

        if not self.usage.can_play(kid):
            await self._reply(
                websocket,
                user=text,
                text="Today's play time is finished. Ask a parent for more time!",
                error="time_limit",
            )
            return

        # Active mini-game answers are scored locally (no API needed)
        if self._game is not None:
            result = score_answer(self._game, text)
            self.transcripts.write("user", text, game=self._game.kind)
            reply = result["message"]
            if result["ok"]:
                self._game = None
                reply += " Want another game?"
            else:
                reply += f" Hint: {self._game.hint}" if self._game.hint else ""
            self.usage.add_minutes(kid, TURN_MINUTES)
            self.transcripts.write("assistant", reply)
            await self._reply(websocket, user=text, text=reply)
            await websocket.send(json.dumps(self.public_state()))
            return

        budget_ok = self.budget.can_spend()
        # Pure cloud mode hard-blocks when over budget. Hybrid falls back to local.
        if self.config.ai_mode == "cloud" and not budget_ok:
            await self._reply(
                websocket,
                user=text,
                text=(
                    "We've hit today's cloud budget. A parent can raise the limit "
                    "in Settings, or switch to Local mode."
                ),
                error="over_budget",
            )
            return

        await websocket.send(json.dumps({"type": "avatar_state", "state": "thinking"}))
        self.transcripts.write("user", text)
        self._paused_agent = None

        prompt = build_system_prompt(self.config, kid)
        begin_turn = getattr(self.engine, "begin_turn", None)
        if callable(begin_turn):
            begin_turn(text, budget_ok=budget_ok)
        dialect = "ollama" if getattr(self.engine, "dialect", lambda: "openai")() == "ollama" else "openai"

        async def on_skill(call: Any, skill_result: Any) -> None:
            self.transcripts.write("tool", skill_result.message, skill=call.name)
            if getattr(skill_result, "timer_seconds", None):
                self._start_timer_task(
                    int(skill_result.timer_seconds),
                    str(skill_result.timer_label or "Timer"),
                )
            if skill_result.needs_approval:
                await self.broadcast(
                    {
                        "type": "computer_use_event",
                        "event": "pending",
                        "message": skill_result.message,
                        "pending": self.computer_use.status().get("pending"),
                    }
                )
                await self.broadcast(self.public_state())

        loop_result = await run_agent_loop(
            engine=self.engine,
            skills=self.skills,
            system_prompt=prompt,
            user_text=text,
            max_steps=self.config.computer_use.max_agent_steps,
            dialect=dialect,  # type: ignore[arg-type]
            on_skill=on_skill,
        )

        # Hybrid: one automatic cloud retry when local fails and budget allows.
        # Never retry if tools already ran (avoid repeating desktop actions) or
        # if the turn is paused waiting for parent PIN approval.
        if (
            self.config.ai_mode == "hybrid"
            and getattr(self.engine, "last_route", None) == "local"
            and budget_ok
            and not loop_result.paused_for_approval
            and not loop_result.tool_calls
        ):
            from kids_agent.engines.base import EngineResult
            from kids_agent.engines.hybrid_policy import should_escalate

            local_probe = EngineResult(
                assistant_text=loop_result.assistant_text,
                error=loop_result.error,
            )
            if should_escalate(local_probe, config=self.config, budget_ok=budget_ok):
                force_cloud = getattr(self.engine, "force_cloud", None)
                if callable(force_cloud):
                    force_cloud()
                    dialect = (
                        "ollama"
                        if getattr(self.engine, "dialect", lambda: "openai")() == "ollama"
                        else "openai"
                    )
                    loop_result = await run_agent_loop(
                        engine=self.engine,
                        skills=self.skills,
                        system_prompt=prompt,
                        user_text=text,
                        max_steps=self.config.computer_use.max_agent_steps,
                        dialect=dialect,  # type: ignore[arg-type]
                        on_skill=on_skill,
                    )

        # Estimate: one cloud charge per vision/tool round roughly
        if self._uses_cloud_llm() and not loop_result.error:
            steps = max(1, 1 + loop_result.vision_steps)
            self.budget.add_estimate(CLOUD_TURN_ESTIMATE_USD * steps)

        if loop_result.paused_for_approval:
            self._paused_agent = {
                "messages": loop_result.messages,
                "user_text": text,
                "dialect": dialect,
                "route": getattr(self.engine, "last_route", None),
            }

        reply = loop_result.assistant_text
        self.usage.add_minutes(kid, TURN_MINUTES)
        self.transcripts.write("assistant", reply)
        await self._reply(
            websocket,
            user=loop_result.user_transcript or text,
            text=reply,
            error=loop_result.error,
            extra={
                "tool_calls": loop_result.tool_calls,
                "vision_steps": loop_result.vision_steps,
                "engine_used": self._engine_used(),
            },
        )
        await websocket.send(json.dumps(self.public_state()))

    async def _resume_paused_agent(self, websocket: ServerConnection, result: Any) -> None:
        """After PIN approve: append tool outcome (+ vision image) and continue the loop."""
        from kids_agent.vision import ollama_image_message, openai_image_message

        paused = self._paused_agent
        if not paused:
            await self.broadcast(
                {
                    "type": "assistant_reply",
                    "user_transcript": "",
                    "text": result.message,
                    "gender": self.config.avatar.gender,
                }
            )
            await self.broadcast(self.public_state())
            return

        messages: list[dict[str, Any]] = list(paused["messages"])
        dialect = paused.get("dialect") or "openai"
        user_text = str(paused.get("user_text") or "")
        # Keep the same engine/dialect as the paused turn (hybrid sticky route)
        stored_route = paused.get("route")
        if stored_route == "cloud":
            force_cloud = getattr(self.engine, "force_cloud", None)
            if callable(force_cloud):
                force_cloud()
        elif stored_route == "local":
            force_local = getattr(self.engine, "force_local", None)
            if callable(force_local):
                force_local()

        # Replace the last "waiting for PIN" tool stub with the real result if present,
        # otherwise append a fresh tool note + vision user message.
        messages.append(
            {
                "role": "user",
                "content": (
                    f"Parent approved. Result: {result.message}. "
                    "Continue helping the child. Use the screenshot if attached."
                ),
            }
        )
        if result.vision:
            if dialect == "ollama":
                messages.append(ollama_image_message(result.vision))
            else:
                messages.append(openai_image_message(result.vision))

        await websocket.send(json.dumps({"type": "avatar_state", "state": "thinking"}))

        async def on_skill(call: Any, skill_result: Any) -> None:
            self.transcripts.write("tool", skill_result.message, skill=call.name)
            if getattr(skill_result, "timer_seconds", None):
                self._start_timer_task(
                    int(skill_result.timer_seconds),
                    str(skill_result.timer_label or "Timer"),
                )
            if skill_result.needs_approval:
                await self.broadcast(
                    {
                        "type": "computer_use_event",
                        "event": "pending",
                        "message": skill_result.message,
                        "pending": self.computer_use.status().get("pending"),
                    }
                )
                await self.broadcast(self.public_state())

        kid = self._kid()
        prompt = build_system_prompt(self.config, kid)
        # Ensure system prompt still leads if messages were truncated oddly
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": prompt})

        loop_result = await run_agent_loop(
            engine=self.engine,
            skills=self.skills,
            system_prompt=prompt,
            user_text=user_text,
            max_steps=self.config.computer_use.max_agent_steps,
            dialect=dialect,
            messages=messages,
            on_skill=on_skill,
        )

        if self._uses_cloud_llm() and not loop_result.error:
            steps = max(1, 1 + loop_result.vision_steps)
            self.budget.add_estimate(CLOUD_TURN_ESTIMATE_USD * steps)

        if loop_result.paused_for_approval:
            self._paused_agent = {
                "messages": loop_result.messages,
                "user_text": user_text,
                "dialect": dialect,
                "route": getattr(self.engine, "last_route", None),
            }
        else:
            self._paused_agent = None

        reply = loop_result.assistant_text
        if result.message and result.message not in reply:
            reply = f"{result.message}\n{reply}".strip()
        self.usage.add_minutes(kid, TURN_MINUTES)
        self.transcripts.write("assistant", reply)
        await self._reply(
            websocket,
            user=user_text,
            text=reply,
            error=loop_result.error,
            extra={
                "tool_calls": loop_result.tool_calls,
                "vision_steps": loop_result.vision_steps,
                "engine_used": self._engine_used(),
            },
        )
        await self.broadcast(self.public_state())


async def run_server(config: AppConfig | None = None) -> None:
    import os

    config = config or load_config()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    engine = None
    os_adapter = None
    if os.environ.get("KDA_E2E_STUB_ENGINE") == "1":
        from kids_agent.fakes import FakeOS, StubEngine

        engine = StubEngine()
        os_adapter = FakeOS()
        log.info("E2E stub engine + FakeOS enabled (KDA_E2E_STUB_ENGINE=1)")
    else:
        # Warm Kokoro off the event loop so the first spoken reply isn't cold/slow
        from kids_agent.tts import kokoro_available, warm_kokoro

        if kokoro_available():
            log.info("Warming Kokoro TTS…")
            await asyncio.to_thread(warm_kokoro)

    server = AgentServer(config, os_adapter=os_adapter, engine=engine)
    host, port = config.websocket.host, config.websocket.port
    log.info("Starting Kids Desktop Agent on ws://%s:%s", host, port)
    async with websockets.serve(server.handle, host, port):
        await asyncio.Future()


def main() -> None:
    asyncio.run(run_server())
