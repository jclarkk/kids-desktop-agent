from __future__ import annotations

from typing import Any


# Recommended Ollama tags for agentic (tool-calling) kids-desktop use.
# Parents can still type any model name; this is the curated catalog.
MODEL_CATALOG: list[dict[str, Any]] = [
    {
        "id": "tinyllama",
        "label": "TinyLlama (CPU / &lt;4GB)",
        "ollama": "tinyllama",
        "min_vram_mb": 0,
        "recommended_vram_mb": 0,
        "notes": "Very small. OK for chat; weak at multi-step tools.",
        "offload_ok": False,
    },
    {
        "id": "llama3.2-3b",
        "label": "Llama 3.2 3B",
        "ollama": "llama3.2:3b",
        "min_vram_mb": 0,
        "recommended_vram_mb": 4096,
        "notes": "Light local chat; limited tool reliability.",
        "offload_ok": True,
    },
    {
        "id": "qwen2.5-7b",
        "label": "Qwen2.5 7B Instruct (6–8GB)",
        "ollama": "qwen2.5:7b-instruct",
        "min_vram_mb": 4096,
        "recommended_vram_mb": 6144,
        "notes": "Good latency and simple tool calls.",
        "offload_ok": True,
    },
    {
        "id": "llama3.1-8b",
        "label": "Llama 3.1 8B Instruct (6–8GB)",
        "ollama": "llama3.1:8b-instruct-q5_K_M",
        "min_vram_mb": 5120,
        "recommended_vram_mb": 8192,
        "notes": "Strong throughput for frequent short tool calls.",
        "offload_ok": True,
    },
    {
        "id": "qwen2.5-14b",
        "label": "Qwen2.5 14B Instruct (10–12GB+) — recommended agent",
        "ollama": "qwen2.5:14b-instruct-q4_K_M",
        "min_vram_mb": 8192,
        "recommended_vram_mb": 12288,
        "notes": "Best tool/schema fidelity in the common gaming-GPU tier.",
        "offload_ok": True,
    },
    {
        "id": "qwen2.5-32b-offload",
        "label": "Qwen2.5 32B (16GB+ or offload)",
        "ollama": "qwen2.5:32b-instruct-q4_K_M",
        "min_vram_mb": 12288,
        "recommended_vram_mb": 20480,
        "notes": "Stronger multi-step skills; enable GPU layer offload if VRAM is tight.",
        "offload_ok": True,
    },
]


def recommend_for_vram(vram_mb: int | None) -> list[dict[str, Any]]:
    """Annotate catalog with fit / recommend / needs_offload for the detected GPU."""
    vram = vram_mb if vram_mb is not None else 0
    cpu_only = vram_mb is None
    out: list[dict[str, Any]] = []
    for row in MODEL_CATALOG:
        item = dict(row)
        # Unescape label for UI (stored escaped for markdown tables historically)
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

    # Mark one default: highest "recommended" that fits, else best "ok", else first cpu/offload
    for prefer in ("recommended", "ok", "cpu", "offload"):
        for item in reversed(out):
            if item["fit"] == prefer:
                item["selected_default"] = True
                return out
    if out:
        out[0]["selected_default"] = True
    return out


def default_model_for_vram(vram_mb: int | None) -> str:
    for item in recommend_for_vram(vram_mb):
        if item.get("selected_default"):
            return str(item["ollama"])
    return "qwen2.5:7b-instruct"
