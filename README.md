# Kids Desktop Agent

A kid-friendly desktop avatar that talks (mic + speakers), teaches English, and can open allowlisted apps/sites — with parent PIN settings and cloud or local AI backends.

> **Status:** Windows beta packaging is wired through GitHub Releases. Computer-use with vision is PIN-gated and off by default. Unsigned beta installers should not be treated as a final consumer release.

## Features

- Always-on-top avatar with kid-selectable character + gender → matching voice
- English conversation via a **cost-aware cascade** (browser STT or optional faster-whisper → cloud/local LLM → **natural TTS**: Kokoro when installed, else enhanced browser neural voices)
- **Kid profiles**: onboarding, English level (`beginner` / `elementary` / `intermediate`), daily time limits
- **Who’s playing?** — tap, say-your-name, or soft camera face-hash (local only; not security-grade)
- English mini-games (word of the day, repeat, phonics/spell by age, I spy)
- Allowlisted skills: open app/site, volume, list windows, real countdown timers
- Optional **PIN-gated computer-use** with vision: screenshot → LLM sees the screen → click/type; Esc/Stop emergency halt
- Parent panel (PIN): providers, models, budget, allowlists, kids, identity, computer-use mode
- Local LLMs via [Ollama](https://ollama.com) (NVIDIA VRAM or Apple Silicon unified memory catalog)

## Quick start (Windows)

### Prerequisites

- Python **3.11 or 3.12** (Kokoro TTS does not support 3.13 yet; use 3.12 if you want natural voices)
- Node.js 20+
- (Optional) OpenRouter / OpenAI / Gemini API key for cloud LLM
- (Optional) NVIDIA GPU + Ollama for local models

### 1. Config

```bash
copy config\config.example.json config\config.local.json
```

Edit `config.local.json` and set `cloud.api_key` (or use env `KDA_API_KEY`). **Never commit** that file.

**Parent PIN:** in dev / run-from-source mode the default PIN is **`1234`** — change it under
Parent settings → Safety & PIN after first unlock (stored hashed). The future installer will
ask the parent to define a PIN during setup instead of shipping a default.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m kids_agent
```

Backend listens on `ws://127.0.0.1:8765` by default.

### 3. App

```bash
cd app
npm install
npm run dev
```

**Talking:** hold the big mic button (or the avatar) to talk — or hold the **Space** key
(push-to-talk; kids can pick a different key in the menu). Assistant speech shows as
**subtitles** under the avatar. Tap ⌨ to type instead, ☰ for the kid menu (friend, voices,
games, grown-up settings).

Wake word is **not** wired yet — push-to-talk / click only.

## Quick start (macOS)

```bash
cp config/config.example.json config/config.local.json
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m kids_agent
```

In another terminal:

```bash
cd app
npm install
npm run dev
```

### macOS permissions (desktop control)

Grant these to **Terminal** (or whatever runs `python -m kids_agent`) and to **Electron** when using computer-use:

1. **Accessibility** — click / type / list windows  
2. **Screen Recording** — screenshots  
3. **Microphone** — speech when using the mic  

Allowlist apps use `macos.command` / `macos.args`, e.g. `"command": "open", "args": ["-a", "TextEdit"]`.

### Apple Silicon + local models

Install Ollama (Metal). The backend estimates usable unified memory from system RAM for the model catalog. Prefer smaller instruct models on 8 GB; 16 GB+ is more comfortable for 7B–14B class.

## Cloud, local, and hybrid

| Mode | Behavior |
|------|----------|
| **Cloud** | OpenAI-compatible chat (OpenRouter / OpenAI / Gemini-compatible base URL) |
| **Local** | Ollama chat API |
| **Hybrid** | Cloud LLM when an API key is set, otherwise local |

Parent settings expose model presets, a soft **daily cloud budget**, content filtering, and a VRAM/unified-memory catalog for local picks.

### Natural voices

See **[docs/INSTALLER_OPTIONAL_COMPONENTS.md](docs/INSTALLER_OPTIONAL_COMPONENTS.md)** for every optional package the future parent installer should offer (Kokoro, faster-whisper, Ollama, API key, wake-word placeholder). Machine-readable: [`docs/installer-components.json`](docs/installer-components.json).

```bash
cd backend
.venv\Scripts\activate
pip install -r requirements-optional.txt
```

Installs **Kokoro** neural TTS and optional **faster-whisper** local STT. When Kokoro is available, assistant replies are synthesized on the backend and played as WAV — much less robotic than stock system voices. First run downloads model weights (~300MB).

Without Kokoro, the UI still prefers Windows/macOS **Natural / Neural / Online** browser voices, splits sentences for natural pacing, and avoids ultra-slow rates that sound machine-like.

## Computer use (optional)

In Parent settings → **Computer use**:

| Mode | Meaning |
|------|---------|
| **Off** | Default — no screenshot/click/type tools |
| **Ask each time** | Every computer action needs the parent PIN |
| **Session** | PIN once; actions allowed for `session_ttl_minutes` (default 15) |

When active, a **Robot driving** banner appears. **Esc** or **Stop** ends control immediately (no PIN).

Vision flow: `computer_screenshot` → image is downscaled and sent to the LLM → `computer_click` uses **image pixel** coordinates (mapped to the screen). Prefer a vision-capable cloud model (e.g. Gemini Flash) or a local vision model in Ollama.

Screenshots are stored under `data/screenshots/` (gitignored).

## Kid experience

- **English level**: onboarding picture buttons (New / Some / More / Not sure). Skip or Not sure → **beginner** (very short language, slower speech).
- Parents can edit each kid’s level, time limit, and preferred avatar in settings.
- Mini-games are age-tuned (e.g. phonics for younger; spelling for older).

## Safety

- Skills only; no raw shell from the LLM. Allowlists are enforced in code.
- Hybrid content filtering: local rules run for every message; OpenAI moderation is used when supported by the configured cloud provider.
- Computer-use requires a parent PIN and a visible UI indicator.
- Soft daily cloud budget; daily play-time limits per kid.
- This project is **not** a substitute for parental supervision.

## Tests

### Backend (unit + WebSocket e2e)

```bash
cd backend
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
python -m pytest tests -m e2e -q   # WebSocket e2e only
```

WS e2e spins up a real `AgentServer` on an ephemeral port with `FakeOS` + `StubEngine` and isolated temp config (never writes your real `config.local.json`).

### UI e2e (Playwright)

```bash
cd app
npm install
npm run test:e2e:install
npm run test:e2e
```

Starts a stub backend on port **18765** (`KDA_E2E_STUB_ENGINE=1`) and Vite with `VITE_WS_URL`. Covers connect, text chat, parent PIN unlock. Mic/camera/real OS clicks stay manual.

### Not covered in CI

Live LLM/API calls, real desktop click/screenshot, browser SpeechRecognition, Electron window packaging smoke.

## Packaging notes

- Dev: `npm run dev` (Vite + Electron).
- CI: GitHub Actions runs backend tests and app typecheck/e2e on PRs.
- Windows beta release: push a `v*` tag or run the release workflow manually. GitHub Actions freezes the Python backend, builds the Electron NSIS installer, and uploads the `.exe` to the GitHub Releases tab.
- Packaged Windows builds store config/data under the app data folder and require parent PIN setup on first launch. The dev default PIN is not used in installed first-run.
- Installers are unsigned until code-signing secrets are configured.

## License

MIT — see [LICENSE](LICENSE). Avatar assets may carry additional notes under `assets/avatars/`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md) for architecture, extension points, and agent guidelines.
