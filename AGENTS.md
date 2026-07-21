# AGENTS.md

Guidance for humans and coding agents working in this repository.

## What this project is

Kids Desktop Agent: Electron avatar UI + Python voice/agent backend. Kids talk via mic/speakers; the agent teaches English and runs **allowlisted** desktop actions. Parents configure everything behind a PIN. Cloud (cheap cascade), local (Ollama), or hybrid backends.

User-facing setup lives in [README.md](README.md). Keep this file accurate when architecture changes.

## Architecture

```
app/                 Electron + React (kid-first: avatar + subtitles + push-to-talk; kid menu; PIN parent settings)
backend/kids_agent/  WebSocket server, engines, skills, OS adapters, vision, identity, games
assets/avatars/      OSS-friendly packs + manifest.json
config/              config.example.json in git — secrets in config.local.json (ignored)
data/                runtime only (gitignored): transcripts, screenshots, kids biometrics, budget, usage
backend/tests/       unit tests (no mic/GPU required)
```

### Runtime flow

1. UI ↔ backend over local WebSocket (`ws://127.0.0.1:8765` by default).
2. User text (or browser STT) → `EngineRouter` (`cloud` / `local` / smart `hybrid`).
3. Hybrid is **local-first**: heuristics pick cloud for hard turns; local errors can escalate once. Route sticks for the whole agent-loop turn (including computer-use resume).
4. `engines/agent_loop.py` runs chat → tools → optional vision follow-up (multi-step).
5. Skills in `skills/registry.py` validate allowlists / computer-use gates **in code**.
6. Desktop control only via `os_adapter/` (`windows.py`, `macos.py`). Never call OS APIs from the LLM.

### Important modules

| Path | Role |
|------|------|
| `server.py` | WebSocket dispatch, parent PIN/session/setup, content filter, computer-use approve/resume, games, onboarding |
| `config.py` | `AppConfig` schema (kids, allowlist, `computer_use`, identity, cloud/local/`hybrid`) |
| `skills/registry.py` | Tool schemas + handlers (`SkillResult`) |
| `computer_use.py` | PIN gate: `off` / `ask` / `session`, emergency stop |
| `vision.py` | Screenshot JPEG downscale, OpenAI/Ollama image messages, click coord mapping |
| `engines/agent_loop.py` | Multi-turn tool + vision loop; pause when PIN needed |
| `engines/cascade_cloud.py` | OpenAI-compatible chat + tools |
| `engines/local_ollama.py` | Ollama chat + tools (+ `images` for vision) |
| `engines/hybrid_policy.py` | Pure hybrid heuristics (`choose_route` / `should_escalate`) |
| `engines/router.py` | Mode routing + per-turn hybrid sticky route; `dialect()` → `openai` \| `ollama` |
| `prompts.py` | Age + English-level system prompt; computer-use vision instructions |
| `identity.py` | Name match, face aHash enroll/match (local files under `data/kids/`) |
| `games.py` / `usage.py` / `budget.py` | Mini-games, daily minutes, soft cloud spend |
| `safety.py` | PIN hash/verify, transcript logger + retention purge |
| `content_filter.py` | Local kid-safety rules + best-effort provider moderation |
| `hardware.py` / `model_catalog.py` | VRAM / Apple unified memory probe + **vision-first** Ollama catalog (Qwen3.5 9B / Gemma4 12B quantized; low-VRAM 4B / E4B) |

### Kid identity & onboarding

- Guided onboarding asks English level with picture buttons (New / Some / More / Not sure).
- Unknown or skipped English level defaults to **beginner** (`normalize_english_level`).
- Beginner mode: ultra-short coach lines, slower TTS rate, stricter tutor vocabulary in the system prompt.
- “Who is playing?”: tap, say-your-name (STT → local name match), soft face-hash.
- Biometrics under `data/kids/<id>/` (gitignored). Parent toggles in `identity` config.
- Face match is a friendly hint (perceptual hash), **not** security-grade auth.

### First-run parent setup (packaged installs)

- When `needs_parent_setup` (no PIN hash yet), `ParentSetupWizard` blocks the kid UI.
- Steps: welcome → PIN → AI mode (cloud / local / hybrid) → cloud API key (OpenRouter / OpenAI / Gemini) and/or Ollama detect/install → daily limit → finish.
- WebSocket `parent_setup` persists PIN (hashed), cloud/local settings, `default_daily_limit_minutes`; computer-use stays `off`.
- NSIS installs the app only; credentials and Ollama are collected on first launch (live `hardware.ollama_ok` probe), not inside the Windows installer pages.
- **Windows Ollama install:** Electron IPC `ollama:install` (`app/electron/ollamaInstall.cjs`) downloads official `OllamaSetup.exe`, runs it silently, waits for the API, optionally pulls the selected model. Manual download remains as fallback.

## Safety invariants (do not break)

1. LLM never gets raw shell / arbitrary process execution.
2. Allowlist checks happen in the skill layer, not only in the system prompt.
3. Computer-use (if enabled) requires parent PIN and a visible UI indicator.
   - Modes: `off` \| `ask` (PIN each action) \| `session` (PIN once for N minutes).
   - Tools: `computer_screenshot`, `computer_click`, `computer_type`.
   - Vision: screenshots → downscaled JPEG → LLM; clicks are **image-pixel** coords, mapped to screen via `VisionFrame.map_click`.
   - Ask-mode pause: agent loop stores messages; `computer_use_approve` resumes with the screenshot attached.
   - Emergency stop: Esc or Stop — no PIN required to halt.
   - Screenshots in `data/screenshots/` (gitignored).
4. Never commit API keys, PIN hashes, transcripts, screenshots, or model weights.
5. No hardcoded personal paths, kid names, or family allowlists in source — use examples only.
6. Unit tests must not call `load_config()` in a way that depends on a developer’s `config.local.json`. Prefer `AppConfig()` with explicit fixtures. Include **negative** cases for safety gates.

## Optional install components (future parent installer)

When building an installer, parents must be able to **opt in/out** of heavy extras. Do not bury this only in pip comments.

- Catalog (human): [`docs/INSTALLER_OPTIONAL_COMPONENTS.md`](docs/INSTALLER_OPTIONAL_COMPONENTS.md)
- Catalog (JSON for the installer UI): [`docs/installer-components.json`](docs/installer-components.json)

| Id | Parent-facing idea | Default |
|----|--------------------|---------|
| `core` | Required app | Always on |
| `kokoro_tts` | Natural voices | On (recommended) |
| `faster_whisper_stt` | Private on-device STT | Off |
| `ollama_local_llm` | Local AI (Ollama + model) | Off |
| `cloud_api_key` | Cloud API key step | Prompt |
| `wake_word` | Hands-free wake word | Off / planned |

**Rule:** any new optional pip/system/external dependency updates those two docs in the same change. Dev-only deps (`requirements-dev.txt`, Playwright) never appear in the parent installer.

## Local config

- Copy `config/config.example.json` → `config/config.local.json`.
- Env overrides: `KDA_API_KEY`, `KDA_WS_HOST`, `KDA_WS_PORT`, `KDA_CONFIG`.
- Useful `computer_use` knobs: `mode`, `session_ttl_minutes`, `vision_max_side`, `vision_jpeg_quality`, `max_agent_steps`.
- Useful `hybrid` knobs: `long_input_words`, `cloud_keywords` (empty → built-in list), `escalate_on_error`.

## How to run

See [README.md](README.md). Typical loop:

1. Backend: `cd backend && .venv\Scripts\activate && python -m kids_agent`
2. App: `cd app && npm run dev`

## How to extend

### Add a skill

1. Add an async handler on `SkillRegistry` (or a small module imported by `registry.py`) returning `SkillResult`.
2. Register it in `_handlers`, expose JSON schema in `tools_schema()` when enabled.
3. Enforce allowlist / parent flags / computer-use gates inside the handler.
4. Add a unit test for the allowlist or gate (accept **and** reject).

### Add an avatar pack

1. Add `assets/avatars/<pack-id>/` with art + `manifest.json` (`id`, genders, voice ids).
2. Keep licenses OSS-compatible; note attribution in the pack README.
3. Backend exposes packs via WebSocket `state.avatar_packs`; kid studio picks character + gender → voice.

### Add a cloud/local engine

1. Implement `VoiceEngine` (`handle_text` / `chat`) under `engines/`.
2. Wire through `engines/router.py`.
3. If tools + vision matter, support the same message shapes as cascade (OpenAI) or Ollama (`images`).
4. Soft cloud budget: `budget.py`.

### Add an OS adapter (e.g. Linux later)

1. Implement `OSAdapter` in `os_adapter/<platform>.py` (including `screenshot` / `click` / `type_text`).
2. Resolve apps via allowlist launch commands — no hardcoded `.exe` in skills.
3. Register in `os_adapter/__init__.py` `get_os_adapter()`.
4. Keep Electron UI OS-agnostic.

**macOS:** `osascript`, `screencapture`, CoreGraphics via ctypes (no pyobjc). Accessibility + Screen Recording required. Apple Silicon unified memory feeds the local catalog.

### WebSocket (high level)

Kid/UI → backend examples: `user_text`, `set_avatar`, `set_kid` / `clear_kid`, `onboard_kid`, `identify_voice` / `identify_face`, `start_game` / `cancel_game`, `parent_unlock` / `parent_save`, `computer_use_approve` / `deny` / `stop` / `start_session`.

Backend → UI: `state`, `assistant_reply`, `avatar_state`, `parent_*_result`, `computer_use_event`, `identify_result`, `onboard_kid_result`.

## Coding conventions

- **Python:** type hints, `async` for I/O, package under `kids_agent/`. Prefer small pure functions for allowlist / vision / PIN logic (easy to test).
- **TypeScript/React:** functional components; keep the avatar window thin — state from WebSocket events.
- **Kid UI contract:** the home screen is avatar + subtitles + push-to-talk only (`App.tsx`, `usePushToTalk.ts`). Everything else lives in `KidMenu.tsx` (no PIN: friend/voice, games, kid switch, talk key) or `ParentPanel.tsx` (PIN). Assistant speech must always render as subtitles (`onSubtitle` in `speak.ts`) for accessibility. Parent settings grow the Electron window via `window.kda.resize` IPC.
- **Overlay z-order:** avatar floats above normal apps (`floating` level via `app/electron/overlayPolicy.cjs`), not above games/fullscreen — never use Electron `screen-saver` always-on-top or macOS `visibleOnFullScreen`.
- **Parent PIN:** dev default is `1234` (`config.py`, `config.example.json`); installed builds must collect a PIN during setup (`docs/installer-components.json` → `parent_pin_setup`). Never ship a default PIN in installers.
- **Commits:** do not commit secrets; keep PRs focused; update this file when architecture changes.

## Tests

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
python -m pytest tests -m e2e -q
```

```bash
cd app
npm run test:e2e:install
npm run test:e2e
```

- Unit: `backend/tests/test_allowlist.py` (safety, allowlist, PIN, vision, agent loop, identity, prompts, games).
- WS e2e: `backend/tests/e2e/` — real `AgentServer` + websockets client; inject `FakeOS` / `StubEngine` via constructor; `conftest` isolates all data paths.
- UI e2e: `app/e2e/` — Playwright + Vite; globalSetup starts backend with `KDA_E2E_STUB_ENGINE=1` and `KDA_CONFIG` under `app/e2e/.fixture/`.
- Prefer isolated `AppConfig()` fixtures — **do not** rely on developer `config.local.json`.
- `config_local_path()` respects `KDA_CONFIG` so saves during e2e stay in the fixture file.
- Cover positive **and** negative paths for gates.
- Do not assert machine-specific GPU/VRAM amounts.
- Env: `KDA_E2E_STUB_ENGINE=1` enables stub LLM + FakeOS in `run_server`; `VITE_WS_URL` points the UI at a non-default WS port for Playwright.

## Known gaps (do not pretend they exist)

- Wake word / VAD not wired (push-to-talk / click).
- Browser STT is the fallback; faster-whisper can transcribe PTT audio when installed (`speech.py`).
- Kokoro neural TTS is used for assistant speech when installed (`tts.py`); otherwise enhanced browser neural voices (`app/src/speak.ts`).
- Windows beta installers are wired via GitHub Releases, but unsigned until code-signing secrets are configured. macOS packaging/notarization is not wired.
- Face ID is soft aHash, not ML embeddings.

## Out of scope for agents unless asked

- Force-push, rewriting git history, or committing `config.local.json`.
- Shipping unconstrained computer-use without PIN gates.
- Writing exploits, malware, or attack tooling.
