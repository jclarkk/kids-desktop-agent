/**
 * Parent-facing Ollama helper for first-run setup.
 * Downloads the official Windows installer and can pull a starter model.
 * Never runs arbitrary shell — only the known OllamaSetup.exe + ollama CLI.
 */

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");
const { pipeline } = require("stream/promises");

const OLLAMA_SETUP_URL = "https://ollama.com/download/OllamaSetup.exe";
const OLLAMA_TAGS_URL = "http://127.0.0.1:11434/api/tags";

function localAppData() {
  return process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
}

function findOllamaExe() {
  const candidates = [
    path.join(localAppData(), "Programs", "Ollama", "ollama.exe"),
    path.join(process.env.ProgramFiles || "C:\\Program Files", "Ollama", "ollama.exe"),
    "ollama",
  ];
  for (const candidate of candidates) {
    if (candidate === "ollama") {
      const which = spawnSync(process.platform === "win32" ? "where" : "which", ["ollama"], {
        encoding: "utf8",
        windowsHide: true,
      });
      if (which.status === 0 && which.stdout.trim()) {
        return which.stdout.trim().split(/\r?\n/)[0];
      }
      continue;
    }
    if (fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function httpGetJson(url, timeoutMs = 2500) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: timeoutMs }, (res) => {
      let body = "";
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if (res.statusCode && res.statusCode >= 200 && res.statusCode < 300) {
          try {
            resolve(JSON.parse(body));
            return;
          } catch {
            resolve(null);
            return;
          }
        }
        resolve(null);
      });
    });
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
    req.on("error", () => resolve(null));
  });
}

async function probeOllama() {
  const data = await httpGetJson(OLLAMA_TAGS_URL);
  if (!data) {
    return { online: false, models: [], exe: findOllamaExe() };
  }
  const models = Array.isArray(data.models)
    ? data.models.map((m) => String(m.name || m.model || "")).filter(Boolean)
    : [];
  return { online: true, models, exe: findOllamaExe() };
}

function downloadFile(url, dest, onProgress) {
  return new Promise((resolve, reject) => {
    const file = fs.createWriteStream(dest);
    const request = https.get(url, { headers: { "User-Agent": "KidsDesktopAgent" } }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        file.close();
        fs.unlink(dest, () => {});
        downloadFile(res.headers.location, dest, onProgress).then(resolve, reject);
        return;
      }
      if (!res.statusCode || res.statusCode < 200 || res.statusCode >= 300) {
        file.close();
        fs.unlink(dest, () => {});
        reject(new Error(`Download failed (HTTP ${res.statusCode || "?"})`));
        return;
      }
      const total = Number(res.headers["content-length"] || 0);
      let received = 0;
      res.on("data", (chunk) => {
        received += chunk.length;
        if (total > 0 && onProgress) {
          onProgress({
            stage: "download",
            message: "Downloading Ollama…",
            percent: Math.min(99, Math.round((received / total) * 100)),
          });
        }
      });
      pipeline(res, file).then(resolve).catch(reject);
    });
    request.on("error", (err) => {
      file.close();
      fs.unlink(dest, () => {});
      reject(err);
    });
  });
}

function runProcess(command, args, { onStdout, timeoutMs } = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: process.env,
    });
    let settled = false;
    const timer =
      timeoutMs != null
        ? setTimeout(() => {
            if (settled) return;
            settled = true;
            child.kill();
            reject(new Error(`Timed out running ${path.basename(command)}`));
          }, timeoutMs)
        : null;

    const finish = (err, code) => {
      if (settled) return;
      settled = true;
      if (timer) clearTimeout(timer);
      if (err) reject(err);
      else resolve(code ?? 0);
    };

    child.stdout.on("data", (buf) => onStdout?.(String(buf)));
    child.stderr.on("data", (buf) => onStdout?.(String(buf)));
    child.on("error", (err) => finish(err));
    child.on("close", (code) => finish(null, code));
  });
}

async function waitForOnline(onProgress, { attempts = 40, delayMs = 1500 } = {}) {
  for (let i = 0; i < attempts; i += 1) {
    onProgress?.({
      stage: "starting",
      message: "Waiting for Ollama to start…",
      percent: Math.min(95, 40 + i * 1.5),
    });
    const status = await probeOllama();
    if (status.online) return status;
    await new Promise((r) => setTimeout(r, delayMs));
  }
  return probeOllama();
}

async function tryStartOllama(exe, onProgress) {
  if (!exe || exe === "ollama") return;
  onProgress?.({ stage: "starting", message: "Starting Ollama…", percent: 35 });
  try {
    // `ollama serve` is long-lived; launch detached so setup can continue.
    const child = spawn(exe, ["serve"], {
      detached: true,
      stdio: "ignore",
      windowsHide: true,
      env: process.env,
    });
    child.unref();
  } catch {
    // Tray app may already auto-start after install.
  }
}

async function pullModel(model, onProgress) {
  const exe = findOllamaExe() || "ollama";
  const name = String(model || "").trim();
  if (!name) return { ok: false, error: "No model selected." };

  onProgress?.({
    stage: "pull",
    message: `Downloading model ${name} (this can take a while)…`,
    percent: 50,
  });

  try {
    const code = await runProcess(exe, ["pull", name], {
      timeoutMs: 60 * 60 * 1000,
      onStdout: (chunk) => {
        const line = chunk.trim().split(/\r?\n/).pop() || "";
        if (line) {
          onProgress?.({ stage: "pull", message: line.slice(0, 160), percent: 70 });
        }
      },
    });
    if (code !== 0) {
      return { ok: false, error: `ollama pull exited with code ${code}` };
    }
    return { ok: true, model: name };
  } catch (err) {
    return { ok: false, error: err.message || String(err) };
  }
}

async function installWindows({ pullModelName, onProgress } = {}) {
  if (process.platform !== "win32") {
    return {
      ok: false,
      error: "Automatic Ollama install is only available on Windows right now. Use Download Ollama instead.",
      openDownload: true,
    };
  }

  onProgress?.({ stage: "download", message: "Downloading Ollama installer…", percent: 5 });
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "kda-ollama-"));
  const setupPath = path.join(tempDir, "OllamaSetup.exe");

  try {
    await downloadFile(OLLAMA_SETUP_URL, setupPath, onProgress);
    onProgress?.({ stage: "install", message: "Installing Ollama…", percent: 30 });

    // Official Windows installer (Inno Setup). No admin required for per-user install.
    const code = await runProcess(
      setupPath,
      ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-"],
      { timeoutMs: 15 * 60 * 1000 }
    );
    if (code !== 0) {
      return {
        ok: false,
        error: `Ollama installer exited with code ${code}. Try Download Ollama instead.`,
        openDownload: true,
      };
    }

    let exe = findOllamaExe();
    await tryStartOllama(exe, onProgress);
    let status = await waitForOnline(onProgress);
    if (!status.online) {
      // One more start attempt after PATH / install settle.
      exe = findOllamaExe();
      await tryStartOllama(exe, onProgress);
      status = await waitForOnline(onProgress, { attempts: 20, delayMs: 1500 });
    }

    if (!status.online) {
      return {
        ok: false,
        error:
          "Ollama installed, but the service is not responding yet. Open the Ollama app from the Start menu, then tap Check again.",
        installed: Boolean(findOllamaExe()),
      };
    }

    if (pullModelName) {
      const pulled = await pullModel(pullModelName, onProgress);
      if (!pulled.ok) {
        return {
          ok: true,
          installed: true,
          online: true,
          modelPulled: false,
          warning: pulled.error || "Model download failed — you can pull it later.",
          models: (await probeOllama()).models,
        };
      }
    }

    onProgress?.({ stage: "done", message: "Ollama is ready.", percent: 100 });
    const finalStatus = await probeOllama();
    return {
      ok: true,
      installed: true,
      online: finalStatus.online,
      models: finalStatus.models,
      modelPulled: Boolean(pullModelName),
    };
  } catch (err) {
    return {
      ok: false,
      error: err.message || String(err),
      openDownload: true,
    };
  } finally {
    try {
      fs.rmSync(tempDir, { recursive: true, force: true });
    } catch {
      // ignore cleanup errors
    }
  }
}

module.exports = {
  OLLAMA_SETUP_URL,
  findOllamaExe,
  probeOllama,
  pullModel,
  installWindows,
};
