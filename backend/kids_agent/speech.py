from __future__ import annotations

"""Optional speech backends. Heavy deps are imported lazily."""

import base64
from dataclasses import dataclass
import tempfile
from pathlib import Path
from typing import Any


@dataclass
class SpeechCapabilities:
    stt: str  # none | browser | faster_whisper
    tts: str  # browser | kokoro
    wake_word: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stt": self.stt,
            "tts": self.tts,
            "wake_word": self.wake_word,
            "notes": self.notes,
        }


def probe_speech_capabilities() -> SpeechCapabilities:
    from kids_agent.tts import kokoro_available

    notes: list[str] = []
    stt = "browser"
    tts = "browser"
    try:
        import faster_whisper  # noqa: F401

        stt = "faster_whisper"
    except ImportError:
        notes.append("faster-whisper not installed — using browser speech recognition.")

    if kokoro_available():
        tts = "kokoro"
        notes.append("Kokoro neural TTS available — used for assistant speech when possible.")
    else:
        notes.append(
            "Kokoro not installed — using enhanced browser voices. "
            "For more natural speech: pip install -r requirements-optional.txt"
        )

    notes.append("Wake word (openWakeWord) not wired yet — click/hold avatar to talk.")
    return SpeechCapabilities(stt=stt, tts=tts, wake_word=False, notes=notes)


_WHISPER_MODEL: Any | None = None
_WHISPER_MODEL_NAME: str | None = None


def faster_whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _load_whisper_model(model_name: str) -> Any:
    global _WHISPER_MODEL, _WHISPER_MODEL_NAME
    if _WHISPER_MODEL is not None and _WHISPER_MODEL_NAME == model_name:
        return _WHISPER_MODEL

    from faster_whisper import WhisperModel

    _WHISPER_MODEL = WhisperModel(model_name, device="auto", compute_type="int8")
    _WHISPER_MODEL_NAME = model_name
    return _WHISPER_MODEL


def transcribe_audio_b64(audio_b64: str, *, model_name: str = "small", ext: str = "webm") -> str:
    if not faster_whisper_available():
        raise RuntimeError("faster-whisper is not installed")

    raw = base64.b64decode(audio_b64)
    suffix = f".{ext.lstrip('.') or 'webm'}"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(raw)
        tmp_path = Path(tmp.name)
    try:
        model = _load_whisper_model(model_name)
        segments, _info = model.transcribe(str(tmp_path), language="en", vad_filter=True)
        return " ".join(seg.text.strip() for seg in segments if seg.text.strip()).strip()
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass
