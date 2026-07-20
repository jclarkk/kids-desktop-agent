from __future__ import annotations

"""Optional Kokoro neural TTS. Lazy-loaded; falls back when unavailable."""

import base64
import io
import logging
import re
import threading
from typing import Any

import numpy as np

log = logging.getLogger("kids_agent.tts")

_pipeline = None
_pipeline_lock = threading.Lock()
_pipeline_failed = False

SAMPLE_RATE = 24000
# Breath between Kokoro sentence chunks (samples @ 24kHz)
_PAUSE_SAMPLES = int(SAMPLE_RATE * 0.16)


def kokoro_available() -> bool:
    if _pipeline_failed:
        return False
    try:
        import kokoro  # noqa: F401

        return True
    except ImportError:
        return False


def prepare_tts_text(text: str) -> str:
    """Clean + sentence-split text so Kokoro can apply natural prosody.

    Kokoro splits on newlines by default. Flattening to one line makes speech
    sound flat and robotic — one sentence per line is the intended usage.
    """
    raw = (text or "").strip()
    if not raw:
        return ""

    # Drop tool-dump / markup lines that sound awful when spoken
    lines: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(
            r"^(open_app|open_website|set_volume|computer_|list_windows|start_timer)\b",
            s,
            re.I,
        ):
            continue
        lines.append(s)
    flat = " ".join(lines)

    # Strip markdown / symbols that Kokoro reads awkwardly
    flat = re.sub(r"[*_`#~>]+", " ", flat)
    flat = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", flat)  # [label](url) → label
    flat = re.sub(r"https?://\S+", " ", flat)
    flat = flat.replace("&", " and ")
    flat = re.sub(r"\s+", " ", flat).strip()
    if not flat:
        return ""

    # Ensure terminal punctuation so the last clause isn't clipped flat
    if not re.search(r"[.!?…]$", flat):
        flat += "."

    # Split into spoken sentences; keep punctuation with the clause
    parts = re.findall(r"[^.!?…]+[.!?…]+|[^.!?…]+$", flat)
    sentences: list[str] = []
    for part in parts:
        s = part.strip()
        if not s:
            continue
        # Soften run-on clauses with commas for G2P (light touch)
        s = re.sub(r"\s*;\s*", ", ", s)
        s = re.sub(r"\s*—\s*|\s+-\s+", ", ", s)
        sentences.append(s)

    # One sentence per line → Kokoro split_pattern=r'\n+'
    out = "\n".join(sentences)
    if len(out) > 900:
        # Prefer cutting on a sentence boundary
        cut = out[:900].rsplit("\n", 1)[0]
        out = cut if cut.strip() else out[:900]
    return out


def _trim_silence(pcm: np.ndarray, threshold: float = 0.008) -> np.ndarray:
    if pcm.size < 64:
        return pcm
    abs_pcm = np.abs(pcm)
    mask = abs_pcm > threshold
    if not np.any(mask):
        return pcm
    idx = np.where(mask)[0]
    start = max(0, int(idx[0]) - 48)
    end = min(pcm.size, int(idx[-1]) + 48)
    return pcm[start:end]


def _fade_edges(pcm: np.ndarray, fade_ms: float = 12.0) -> np.ndarray:
    n = int(SAMPLE_RATE * fade_ms / 1000.0)
    if pcm.size < n * 2 or n < 2:
        return pcm
    out = pcm.copy()
    ramp = np.linspace(0.0, 1.0, n, dtype=np.float32)
    out[:n] *= ramp
    out[-n:] *= ramp[::-1]
    return out


def _normalize(pcm: np.ndarray, peak: float = 0.92) -> np.ndarray:
    mx = float(np.max(np.abs(pcm))) if pcm.size else 0.0
    if mx < 1e-6:
        return pcm
    return (pcm * (peak / mx)).astype(np.float32)


def _get_pipeline():
    global _pipeline, _pipeline_failed
    with _pipeline_lock:
        if _pipeline_failed:
            return None
        if _pipeline is not None:
            return _pipeline
        try:
            from kokoro import KPipeline

            _pipeline = KPipeline(lang_code="a")
            log.info("Kokoro TTS pipeline ready")
            return _pipeline
        except Exception as exc:  # noqa: BLE001
            log.warning("Kokoro TTS unavailable: %s", exc)
            _pipeline_failed = True
            return None


def warm_kokoro() -> bool:
    """Load pipeline (and typically the model) so the first kid reply isn't cold."""
    if not kokoro_available():
        return False
    pipe = _get_pipeline()
    if pipe is None:
        return False
    try:
        # Tiny warm-up utterance loads voice pack + weights
        for _ in pipe("Hi.", voice="af_heart", speed=1.0):
            pass
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("Kokoro warm-up failed: %s", exc)
        return False


def synthesize_wav_b64(
    text: str,
    *,
    voice: str = "af_heart",
    speed: float = 1.0,
) -> dict[str, Any] | None:
    """Return {mime, b64, sample_rate} or None if synthesis fails / unavailable."""
    cleaned = prepare_tts_text(text)
    if not cleaned:
        return None

    pipe = _get_pipeline()
    if pipe is None:
        return None

    # Stay near 1.0 — slow rates make Kokoro sound more synthetic
    speed = max(0.88, min(1.15, float(speed)))
    voice_id = (voice or "af_heart").strip() or "af_heart"

    try:
        chunks: list[np.ndarray] = []
        for _gs, _ps, audio in pipe(cleaned, voice=voice_id, speed=speed):
            if audio is None:
                continue
            arr = np.asarray(audio, dtype=np.float32).reshape(-1)
            if arr.size:
                chunks.append(_trim_silence(arr))
        if not chunks:
            return None

        pieces: list[np.ndarray] = []
        for i, chunk in enumerate(chunks):
            if i > 0:
                pieces.append(np.zeros(_PAUSE_SAMPLES, dtype=np.float32))
            pieces.append(chunk)
        pcm = _fade_edges(_normalize(np.concatenate(pieces)))

        import wave

        pcm_i16 = np.clip(pcm * 32767.0, -32768, 32767).astype(np.int16)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm_i16.tobytes())
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
            "mime": "audio/wav",
            "b64": b64,
            "sample_rate": SAMPLE_RATE,
            "voice": voice_id,
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("Kokoro synthesize failed (%s): %s", voice_id, exc)
        return None


def speed_for_english_level(level: str) -> float:
    # Prefer near-natural pace; ultra-slow rates sound machine-like even with Kokoro
    if level == "beginner":
        return 0.96
    if level == "elementary":
        return 0.99
    return 1.02
