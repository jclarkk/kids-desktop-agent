from __future__ import annotations

import re
from typing import Any


# Curated Ollama tags for Kids Desktop Agent.
# Prefer multimodal (vision + tools) models; use quantized tags to fit consumer GPUs.
# Primary: Qwen3.5 9B / Gemma4 12B. Low VRAM: Qwen3.5 4B / Gemma4 E4B.
MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "qwen35-9b-q4",
        "label": "Qwen3.5 9B (Q4) — recommended",
        "ollama": "qwen3.5:9b-q4_K_M",
        "min_vram_mb": 6144,
        "recommended_vram_mb": 8192,
        "vision": True,
        "tools": "good",
        "quantized": True,
        "notes": "Multimodal tutoring + screen vision. ~6.6GB pull; best default on 8GB+ GPUs.",
        "offload_ok": True,
        "use_case": "local_default",
        "family": "qwen3.5",
    },
    {
        "id": "gemma4-12b-qat",
        "label": "Gemma 4 12B (QAT)",
        "ollama": "gemma4:12b-it-qat",
        "min_vram_mb": 6144,
        "recommended_vram_mb": 8192,
        "vision": True,
        "tools": "good",
        "quantized": True,
        "notes": "Strong multimodal alternative (~7.2GB). Good for screenshots + tools.",
        "offload_ok": True,
        "use_case": "local_alt",
        "family": "gemma4",
    },
    {
        "id": "gemma4-12b-q4",
        "label": "Gemma 4 12B (Q4_K_M)",
        "ollama": "gemma4:12b-it-q4_K_M",
        "min_vram_mb": 7168,
        "recommended_vram_mb": 9216,
        "vision": True,
        "tools": "good",
        "quantized": True,
        "notes": "Same size class as QAT; use if QAT tag is unavailable.",
        "offload_ok": True,
        "use_case": "local_alt",
        "family": "gemma4",
    },
    {
        "id": "qwen35-4b-q4",
        "label": "Qwen3.5 4B (Q4) — low VRAM",
        "ollama": "qwen3.5:4b-q4_K_M",
        "min_vram_mb": 0,
        "recommended_vram_mb": 4096,
        "vision": True,
        "tools": "ok",
        "quantized": True,
        "notes": "Light multimodal pick (~3.4GB). Prefer when VRAM is tight or CPU-only.",
        "offload_ok": True,
        "use_case": "local_default_low",
        "family": "qwen3.5",
    },
    {
        "id": "gemma4-e4b-qat",
        "label": "Gemma 4 E4B (QAT) — low VRAM",
        "ollama": "gemma4:e4b-it-qat",
        "min_vram_mb": 4096,
        "recommended_vram_mb": 6144,
        "vision": True,
        "tools": "ok",
        "quantized": True,
        "notes": "Edge multimodal (~6.1GB QAT). Better than full E4B Q4 when memory is limited.",
        "offload_ok": True,
        "use_case": "local_low_alt",
        "family": "gemma4",
    },
    {
        "id": "gemma4-e4b-q4",
        "label": "Gemma 4 E4B (Q4_K_M)",
        "ollama": "gemma4:e4b-it-q4_K_M",
        "min_vram_mb": 6144,
        "recommended_vram_mb": 10240,
        "vision": True,
        "tools": "ok",
        "quantized": True,
        "notes": "Default E4B quant is larger (~9.6GB); prefer the QAT tag when possible.",
        "offload_ok": True,
        "use_case": "local_low_alt",
        "family": "gemma4",
    },
    # Older / emergency fallbacks (still vision-capable).
    {
        "id": "qwen25vl-7b",
        "label": "Qwen2.5-VL 7B (legacy)",
        "ollama": "qwen2.5vl:7b",
        "min_vram_mb": 6144,
        "recommended_vram_mb": 8192,
        "vision": True,
        "tools": "good",
        "quantized": True,
        "notes": "Previous default. Keep if you already pulled it.",
        "offload_ok": True,
        "use_case": "local_legacy",
        "family": "qwen2.5vl",
    },
    {
        "id": "moondream",
        "label": "Moondream (tiny vision)",
        "ollama": "moondream",
        "min_vram_mb": 0,
        "recommended_vram_mb": 2048,
        "vision": True,
        "tools": "weak",
        "quantized": True,
        "notes": "Last-resort tiny vision; weak at tools / tutoring.",
        "offload_ok": False,
        "use_case": "local_emergency",
        "family": "moondream",
    },
]


_VISION_NAME_RE = re.compile(
    r"(?:^|[:/\-_])(?:vl|vision|llava|moondream|minicpm-v|bakllava)(?:$|[:/\-_\d])",
    re.IGNORECASE,
)

# Preference when several models share the same fit bucket (lower = better).
_USE_CASE_RANK = {
    "local_default": 0,
    "local_alt": 1,
    "local_default_low": 2,
    "local_low_alt": 3,
    "local_legacy": 4,
    "local_emergency": 9,
    "chat_only": 10,
}


def looks_like_vision_model(name: str | None) -> bool:
    """Best-effort check that an Ollama tag is multimodal / vision-capable."""
    raw = (name or "").strip().lower()
    if not raw:
        return False
    for row in MODEL_CATALOG:
        tag = str(row["ollama"]).lower()
        if raw == tag:
            return bool(row.get("vision"))
        base = tag.split(":")[0]
        if row.get("vision") and (raw == base or raw.startswith(base + ":")):
            return True
    # Known multimodal families on Ollama (even if not in catalog).
    if raw.startswith("qwen3.5") or raw.startswith("gemma4") or "gemma3" in raw:
        return True
    return bool(_VISION_NAME_RE.search(raw))


def recommend_for_vram(
    vram_mb: int | None,
    *,
    vision_preferred: bool = True,
) -> list[dict[str, Any]]:
    """Annotate catalog with fit / recommend / needs_offload for the detected GPU."""
    vram = vram_mb if vram_mb is not None else 0
    cpu_only = vram_mb is None
    out: list[dict[str, Any]] = []
    for row in MODEL_CATALOG:
        item = dict(row)
        item["label"] = item["label"].replace("&lt;", "<")
        rec = int(item["recommended_vram_mb"])
        vmin = int(item["min_vram_mb"])
        if cpu_only:
            item["fit"] = "cpu" if rec <= 4096 else "offload"
        elif vram >= rec:
            item["fit"] = "recommended"
        elif vram >= vmin:
            item["fit"] = "ok"
        elif item.get("offload_ok"):
            item["fit"] = "offload"
        else:
            item["fit"] = "too_large"
        item["selected_default"] = False
        out.append(item)

    pool = [i for i in out if i.get("vision")] if vision_preferred else out
    if not pool:
        pool = out

    for prefer in ("recommended", "ok", "cpu", "offload"):
        candidates = [
            i for i in pool if i["fit"] == prefer and i.get("use_case") != "local_emergency"
        ]
        if not candidates and prefer in ("cpu", "offload"):
            candidates = [i for i in pool if i["fit"] == prefer]
        if not candidates:
            continue
        ranked = sorted(
            candidates,
            key=lambda i: (
                _USE_CASE_RANK.get(str(i.get("use_case") or ""), 5),
                0 if i.get("quantized") else 1,
                0 if i.get("tools") == "good" else 1,
                0 if i.get("family") == "qwen3.5" else 1,
                int(i.get("recommended_vram_mb") or 0),
            ),
        )
        ranked[0]["selected_default"] = True
        return out

    if pool:
        pool[0]["selected_default"] = True
    elif out:
        out[0]["selected_default"] = True
    return out


def default_model_for_vram(vram_mb: int | None) -> str:
    for item in recommend_for_vram(vram_mb, vision_preferred=True):
        if item.get("selected_default"):
            return str(item["ollama"])
    return "qwen3.5:9b-q4_K_M"


def catalog_entry_for_model(name: str | None) -> dict[str, Any] | None:
    raw = (name or "").strip().lower()
    if not raw:
        return None
    for row in MODEL_CATALOG:
        tag = str(row["ollama"]).lower()
        if raw == tag or raw.startswith(tag.split(":")[0] + ":"):
            return dict(row)
    return None
