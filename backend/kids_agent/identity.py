from __future__ import annotations

import base64
import io
import json
import re
import uuid
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from kids_agent.config import AppConfig, KidProfile, app_data_root


def kids_data_root() -> Path:
    path = app_data_root() / "kids"
    path.mkdir(parents=True, exist_ok=True)
    return path


def kid_dir(kid_id: str) -> Path:
    path = kids_data_root() / kid_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _normalize_name(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return " ".join(text.split())


def match_kid_by_spoken_name(
    kids: list[KidProfile], spoken: str, *, min_ratio: float = 0.72
) -> tuple[KidProfile | None, float, str]:
    """Match STT transcript to a kid name (say-your-name identification)."""
    spoken_n = _normalize_name(spoken)
    if not spoken_n or not kids:
        return None, 0.0, "empty"

    best: KidProfile | None = None
    best_score = 0.0
    for kid in kids:
        name_n = _normalize_name(kid.name)
        if not name_n:
            continue
        # Direct containment helps "my name is Maya"
        if name_n in spoken_n or spoken_n in name_n:
            score = 1.0
        else:
            score = SequenceMatcher(None, name_n, spoken_n).ratio()
            # Also compare against each token
            for token in spoken_n.split():
                score = max(score, SequenceMatcher(None, name_n, token).ratio())
        if score > best_score:
            best_score = score
            best = kid

    if best and best_score >= min_ratio:
        return best, best_score, "name_match"
    return None, best_score, "no_match"


def save_voice_sample(kid_id: str, audio_b64: str, *, ext: str = "webm") -> Path:
    raw = base64.b64decode(audio_b64)
    dest = kid_dir(kid_id) / "voice"
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / f"enroll_{uuid.uuid4().hex[:8]}.{ext.lstrip('.')}"
    path.write_bytes(raw)
    meta = dest / "meta.json"
    samples = []
    if meta.is_file():
        try:
            samples = json.loads(meta.read_text(encoding="utf-8")).get("samples") or []
        except json.JSONDecodeError:
            samples = []
    samples.append({"path": path.name, "bytes": len(raw)})
    meta.write_text(json.dumps({"samples": samples}, indent=2), encoding="utf-8")
    return path


def save_face_image(kid_id: str, image_b64: str) -> Path:
    raw = base64.b64decode(image_b64.split(",")[-1] if "," in image_b64 else image_b64)
    path = kid_dir(kid_id) / "face.jpg"
    path.write_bytes(raw)
    # Store simple perceptual hash for soft matching
    face_hash = average_hash_from_bytes(raw)
    (kid_dir(kid_id) / "face_hash.txt").write_text(face_hash, encoding="utf-8")
    return path


def face_image_data_url(kid_id: str) -> str | None:
    path = kid_dir(kid_id) / "face.jpg"
    if not path.is_file():
        return None
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def average_hash_from_bytes(raw: bytes, size: int = 8) -> str:
    """8x8 aHash as hex — soft local face hint, not cryptographic ID."""
    try:
        from PIL import Image
    except ImportError:
        # Fallback: hash first bytes only (weak)
        import hashlib

        return hashlib.sha256(raw[:4096]).hexdigest()[:16]

    img = Image.open(io.BytesIO(raw)).convert("L").resize((size, size))
    if hasattr(img, "get_flattened_data"):
        pixels = list(img.get_flattened_data())
    else:
        pixels = list(img.getdata())
    avg = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= avg else "0" for p in pixels)
    return f"{int(bits, 2):016x}"


def hamming_hex(a: str, b: str) -> int:
    try:
        x = int(a, 16) ^ int(b, 16)
    except ValueError:
        return 64
    return x.bit_count()


def match_face(
    kids: list[KidProfile], image_b64: str, *, max_distance: int = 14
) -> tuple[KidProfile | None, int, str]:
    raw = base64.b64decode(image_b64.split(",")[-1] if "," in image_b64 else image_b64)
    probe = average_hash_from_bytes(raw)
    best: KidProfile | None = None
    best_dist = 999
    for kid in kids:
        hash_path = kid_dir(kid.id) / "face_hash.txt"
        if not hash_path.is_file():
            continue
        enrolled = hash_path.read_text(encoding="utf-8").strip()
        dist = hamming_hex(probe, enrolled)
        if dist < best_dist:
            best_dist = dist
            best = kid
    if best is not None and best_dist <= max_distance:
        return best, best_dist, "face_hash"
    return None, best_dist if best_dist != 999 else -1, "no_match"


def kid_identity_status(kid: KidProfile) -> dict[str, Any]:
    d = kid_dir(kid.id)
    voice_meta = d / "voice" / "meta.json"
    voice_count = 0
    if voice_meta.is_file():
        try:
            voice_count = len(json.loads(voice_meta.read_text(encoding="utf-8")).get("samples") or [])
        except json.JSONDecodeError:
            voice_count = 0
    return {
        "id": kid.id,
        "voice_samples": voice_count,
        "voice_enrolled": voice_count > 0 or kid.voice_enrolled,
        "face_enrolled": (d / "face.jpg").is_file() or kid.face_enrolled,
        "has_face_preview": (d / "face.jpg").is_file(),
        "onboarding_complete": kid.onboarding_complete,
    }


def public_kids_with_identity(config: AppConfig) -> list[dict[str, Any]]:
    out = []
    for kid in config.kids:
        row = kid.model_dump()
        status = kid_identity_status(kid)
        row.update(status)
        # Small face preview for Who's playing UI (local only)
        if status["has_face_preview"]:
            row["face_preview"] = face_image_data_url(kid.id)
        out.append(row)
    return out
