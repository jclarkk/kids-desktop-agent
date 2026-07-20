from __future__ import annotations

import logging
import platform
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

import httpx

log = logging.getLogger("kids_agent.hardware")


@dataclass
class HardwareInfo:
    vram_mb: int | None
    gpu_name: str | None
    ollama_ok: bool
    ollama_models: list[str]
    has_nvidia_smi: bool
    apple_silicon: bool = False
    system_ram_mb: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "vram_mb": self.vram_mb,
            "vram_gb": round(self.vram_mb / 1024, 1) if self.vram_mb else None,
            "gpu_name": self.gpu_name,
            "ollama_ok": self.ollama_ok,
            "ollama_models": self.ollama_models,
            "has_nvidia_smi": self.has_nvidia_smi,
            "apple_silicon": self.apple_silicon,
            "system_ram_mb": self.system_ram_mb,
        }


def detect_nvidia_vram_mb() -> tuple[int | None, str | None]:
    if not shutil.which("nvidia-smi"):
        return None, None
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=5,
        )
        line = out.strip().splitlines()[0]
        mem_s, _, name = line.partition(",")
        return int(float(mem_s.strip())), name.strip()
    except (subprocess.SubprocessError, ValueError, IndexError) as exc:
        log.debug("nvidia-smi failed: %s", exc)
        return None, None


def detect_apple_unified_mb() -> tuple[int | None, str | None, int | None]:
    """Estimate usable unified memory for local models on Apple Silicon / macOS."""
    if platform.system() != "Darwin":
        return None, None, None
    try:
        mem_bytes = int(
            subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True).strip()
        )
        ram_mb = mem_bytes // (1024 * 1024)
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        log.debug("sysctl memsize failed: %s", exc)
        return None, None, None

    chip = "Apple"
    try:
        chip = subprocess.check_output(
            ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
        ).strip() or chip
    except (subprocess.SubprocessError, OSError):
        pass

    # Leave headroom for macOS + Electron; Ollama uses Metal on unified memory.
    usable = max(2048, ram_mb - 4096)
    label = f"{chip} (unified ~{ram_mb}MB RAM)"
    return usable, label, ram_mb


def detect_vram_mb() -> tuple[int | None, str | None]:
    nvidia_mb, nvidia_name = detect_nvidia_vram_mb()
    if nvidia_mb is not None:
        return nvidia_mb, nvidia_name
    apple_mb, apple_name, _ram = detect_apple_unified_mb()
    if apple_mb is not None:
        return apple_mb, apple_name
    return None, None


async def probe_ollama(base_url: str = "http://127.0.0.1:11434") -> tuple[bool, list[str]]:
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags")
            resp.raise_for_status()
            models = [m.get("name", "") for m in (resp.json().get("models") or []) if m.get("name")]
            return True, models
    except httpx.HTTPError:
        return False, []


async def detect_hardware(ollama_base_url: str = "http://127.0.0.1:11434") -> HardwareInfo:
    vram_mb, gpu_name = detect_vram_mb()
    apple_mb, apple_name, ram_mb = detect_apple_unified_mb()
    ollama_ok, models = await probe_ollama(ollama_base_url)
    apple = platform.system() == "Darwin" and apple_mb is not None
    return HardwareInfo(
        vram_mb=vram_mb,
        gpu_name=gpu_name or apple_name,
        ollama_ok=ollama_ok,
        ollama_models=models,
        has_nvidia_smi=bool(shutil.which("nvidia-smi")),
        apple_silicon=apple,
        system_ram_mb=ram_mb,
    )


# Keep sync helper for tests
def detect_vram_sync() -> dict[str, Any]:
    vram_mb, gpu_name = detect_vram_mb()
    return {
        "vram_mb": vram_mb,
        "vram_gb": round(vram_mb / 1024, 1) if vram_mb else None,
        "gpu_name": gpu_name,
        "has_nvidia_smi": bool(shutil.which("nvidia-smi")),
        "platform": platform.system().lower(),
    }
