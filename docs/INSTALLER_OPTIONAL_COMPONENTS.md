# Installer optional components (for parents)

This is the **source of truth** for what a future installer should offer.  
Machine-readable twin: [`installer-components.json`](installer-components.json).

When you add an optional dependency (pip, system package, or external app), **update both files** in the same PR, and mention it in `AGENTS.md`.

## Design goals

- Parents choose features in plain language (“Natural voices”), not package names.
- Core app works with **zero** optional installs (cloud key + browser mic/TTS).
- Optional pieces are additive: skip them → clear fallback, no crash.
- Never put **dev/CI** tools (pytest, Playwright) in the parent installer.

## Always installed (core)

| What | Why |
|------|-----|
| Electron + React UI (`app/`) | Avatar window |
| Python backend (`backend/requirements.txt`) | WebSocket agent, skills, safety |
| Pillow, numpy, sounddevice, etc. | Screenshots, audio plumbing |

Fallback without extras: browser speech recognition + enhanced browser/OS neural voices + cloud LLM (if key set).

## Optional components (offer in installer)

### 1. Natural voices — Kokoro TTS — **recommended**

| Field | Value |
|-------|--------|
| **Installer id** | `kokoro_tts` |
| **Parent label** | Natural voices (Kokoro) |
| **Default** | Selected |
| **Size** | ~300MB model on first use + pip wheels |
| **Pip** | `kokoro`, `soundfile`, `misaki[en]` (see `backend/requirements-optional.txt`) |
| **Python** | **3.10–3.12 only** — Kokoro has no 3.13 wheels; installer must use/create a 3.12 runtime when this is selected |
| **System (optional)** | `espeak-ng` / eSpeak — helps some pronunciations |
| **Detect** | `kids_agent.tts.kokoro_available()` |
| **If skipped** | Enhanced browser TTS (`app/src/speak.ts`) |

### 2. Private speech recognition — faster-whisper

| Field | Value |
|-------|--------|
| **Installer id** | `faster_whisper_stt` |
| **Parent label** | Private speech recognition (faster-whisper) |
| **Default** | Off |
| **Size** | Hundreds of MB depending on model |
| **Pip** | `faster-whisper` |
| **Detect** | `import faster_whisper` / speech probe `stt == faster_whisper` |
| **If skipped** | Browser `SpeechRecognition` |
| **Status** | Packaged as optional; **not** the default live STT path yet — still offer so parents can pre-install |

### 3. Local AI brain — Ollama

| Field | Value |
|-------|--------|
| **Installer id** | `ollama_local_llm` |
| **Parent label** | Local AI brain (Ollama) |
| **Default** | Off |
| **Size** | Ollama app + model (often 4–8GB+) |
| **Install** | External: [ollama.com](https://ollama.com), then `ollama pull …` from `model_catalog.py` |
| **Detect** | `http://127.0.0.1:11434/api/tags` / `hardware.ollama_ok` |
| **If skipped** | Cloud or hybrid with API key |

### 4. Cloud AI — API key (not a package)

| Field | Value |
|-------|--------|
| **Installer id** | `cloud_api_key` |
| **Parent label** | Cloud AI (API key) |
| **Default** | Prompt / selected |
| **Install** | Collect provider + key → `config.local.json` / `KDA_API_KEY` |
| **If skipped** | Local Ollama only |

### 5. Wake word — planned

| Field | Value |
|-------|--------|
| **Installer id** | `wake_word` |
| **Parent label** | Wake word (“Hey Sparky”) |
| **Status** | **Not wired** — reserve UI checkbox; do not install packages yet |
| **If skipped** | Click / hold avatar |

## System helpers (secondary checkbox or silent recommend)

| Id | When | Commands |
|----|------|----------|
| `espeak_ng` | With Kokoro | Windows: `winget install eSpeak-NG`; macOS: `brew install espeak`; Linux: `apt install espeak-ng` |

## Not for the parent installer

- `backend/requirements-dev.txt` (pytest, pytest-asyncio)
- Playwright / `app` e2e tooling
- Anything under `node_modules` beyond the shipped app runtime

## Installer UX checklist

1. Show **label + one-sentence summary + size**.
2. Core locked on.
3. Kokoro default **on**; whisper + Ollama default **off**.
4. Ask the parent to define a **PIN** during setup (required step below).
5. After install, show a Ready list from runtime probes (`speech`, `hardware`).
6. Link “Advanced” to this doc for contributors.

## Required setup steps (not optional)

| Id | Step | Notes |
|----|------|-------|
| `parent_pin_setup` | **Choose a parent PIN** | Min 4 digits, stored hashed (`safety.set_pin`). Installed builds must NOT ship a default PIN. Dev default is `1234` (README). |

## Dev install (today, until the GUI installer exists)

```bash
# Core
cd backend && pip install -r requirements.txt

# Speech extras (Kokoro + faster-whisper)
pip install -r requirements-optional.txt

# External: Ollama from https://ollama.com — then pull a catalog model
```

## Maintenance rule

**New optional capability → update:**

1. `docs/installer-components.json`
2. This file
3. `backend/requirements-optional.txt` (if pip)
4. Short note in `README.md` / `AGENTS.md`
