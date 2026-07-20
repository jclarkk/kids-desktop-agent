# Contributing

Thanks for helping build a safer, open kid-friendly desktop agent.

## Before you start

1. Read [AGENTS.md](AGENTS.md) (architecture + safety invariants).
2. Never commit secrets, transcripts, screenshots, or model weights.
3. Use `config/config.example.json` — keep real keys in ignored `config.local.json`.

## Setup

Follow [README.md](README.md) quick start.

## Pull requests

- Keep changes focused (one skill / one engine / one UI concern).
- Update docs (`README`, `AGENTS.md`, example config) when you change behavior parents or contributors need to know.
- Add or update tests for allowlist / skill validation when touching those paths.
- Describe how you tested (especially anything involving mic, speakers, or desktop control).

## Safety-sensitive changes

PRs that weaken allowlists, PIN gates, or add shell/exec powers need clear justification and should default to **off** or parent-gated.

## Code of conduct

Be respectful. This project is aimed at families and kids — keep discussion and demos appropriate. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing, you agree your contributions are licensed under the MIT License (and that any new avatar assets you add are clearly licensed for redistribution).
