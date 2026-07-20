/**
 * Starts the Kids Desktop Agent backend with stub engine + isolated config for UI e2e.
 */
import { spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(__dirname, "../..");
const backend = path.resolve(root, "backend");
const fixtureDir = path.resolve(__dirname, ".fixture");
const cfgPath = path.join(fixtureDir, "config.local.json");
const pidPath = path.join(fixtureDir, "backend.pid");
const WS_PORT = Number(process.env.KDA_WS_PORT || 18765);

const config = {
  parent_pin: "1234",
  ai_mode: "cloud",
  websocket: { host: "127.0.0.1", port: WS_PORT },
  cloud: {
    provider: "openrouter",
    api_key: "e2e-stub",
    base_url: "https://openrouter.ai/api/v1",
    chat_model: "google/gemini-2.5-flash",
    daily_budget_usd: 5.0,
    presets: {},
  },
  local: {
    llm_model: "stub",
    ollama_base_url: "http://127.0.0.1:11434",
  },
  avatar: {
    pack_id: "starter",
    character_id: "sparky",
    gender: "neutral",
    wake_word: "Hey Sparky",
  },
  kids: [
    {
      id: "kid_a",
      name: "Maya",
      age: 6,
      english_level: "beginner",
      daily_limit_minutes: 60,
      onboarding_complete: true,
      preferred_avatar: "sparky",
      preferred_gender: "neutral",
    },
  ],
  active_kid_id: "kid_a",
  allowlist: {
    apps: [],
    websites: [],
    skills_enabled: ["open_app", "open_website", "set_volume", "start_timer", "list_windows"],
  },
  computer_use: { mode: "off", session_ttl_minutes: 15 },
  safety: { log_transcripts: false, content_strictness: "strict" },
  identity: {
    require_who_is_playing: false,
    voice_name_match: true,
    face_match: false,
    allow_tap_select: true,
  },
};

function waitPort(port: number, host = "127.0.0.1", timeoutMs = 45000) {
  const start = Date.now();
  return new Promise<void>((resolve, reject) => {
    const tryOnce = () => {
      const socket = net.connect({ port, host }, () => {
        socket.end();
        resolve();
      });
      socket.on("error", () => {
        socket.destroy();
        if (Date.now() - start > timeoutMs) {
          reject(new Error(`Port ${port} not open after ${timeoutMs}ms`));
        } else {
          setTimeout(tryOnce, 250);
        }
      });
    };
    tryOnce();
  });
}

function stopPid(pid: number) {
  if (process.platform === "win32") {
    spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    try {
      process.kill(pid, "SIGTERM");
    } catch {
      /* gone */
    }
  }
}

export default async function globalSetup() {
  fs.mkdirSync(fixtureDir, { recursive: true });
  fs.writeFileSync(cfgPath, JSON.stringify(config, null, 2));

  const py =
    process.platform === "win32"
      ? path.join(backend, ".venv", "Scripts", "python.exe")
      : path.join(backend, ".venv", "bin", "python");

  const child: ChildProcess = spawn(py, ["-m", "kids_agent"], {
    cwd: backend,
    env: {
      ...process.env,
      KDA_CONFIG: cfgPath,
      KDA_WS_HOST: "127.0.0.1",
      KDA_WS_PORT: String(WS_PORT),
      KDA_E2E_STUB_ENGINE: "1",
    },
    stdio: "ignore",
    windowsHide: true,
  });

  if (!child.pid) {
    throw new Error("Failed to start kids_agent for Playwright e2e");
  }
  fs.writeFileSync(pidPath, String(child.pid));

  try {
    await waitPort(WS_PORT);
  } catch (err) {
    stopPid(child.pid);
    throw err;
  }

  return () => {
    stopPid(child.pid!);
  };
}
