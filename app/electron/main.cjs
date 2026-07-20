const { app, BrowserWindow, ipcMain, screen } = require("electron");
const { spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
let autoUpdater = null;
try {
  autoUpdater = require("electron-updater").autoUpdater;
} catch {
  autoUpdater = null;
}

const isDev = !app.isPackaged;
let backendProcess = null;
let backendRestartTimer = null;
let manualQuit = false;
let backendStatus = { running: false, lastError: null };

function broadcastBackendStatus() {
  for (const win of BrowserWindow.getAllWindows()) {
    win.webContents.send("backend:status", backendStatus);
  }
}

function packagedBackendPath() {
  const exe = process.platform === "win32" ? "kids_agent.exe" : "kids_agent";
  return path.join(process.resourcesPath, "backend", "kids_agent", exe);
}

function packagedAssetsPath() {
  return path.join(process.resourcesPath, "assets");
}

function userConfigPath() {
  return path.join(app.getPath("userData"), "config.local.json");
}

function userDataPath() {
  return path.join(app.getPath("userData"), "data");
}

function backendEnv() {
  fs.mkdirSync(userDataPath(), { recursive: true });
  return {
    ...process.env,
    KDA_CONFIG: userConfigPath(),
    KDA_DATA_DIR: userDataPath(),
    KDA_ASSETS_DIR: isDev ? path.join(__dirname, "..", "..", "assets") : packagedAssetsPath(),
    KDA_PACKAGED: isDev ? "0" : "1",
    KDA_WS_HOST: "127.0.0.1",
    KDA_WS_PORT: process.env.KDA_WS_PORT || "8765",
  };
}

function startBackend() {
  if (isDev || backendProcess) return;
  const exePath = packagedBackendPath();
  if (!fs.existsSync(exePath)) {
    backendStatus = { running: false, lastError: `Backend not found: ${exePath}` };
    broadcastBackendStatus();
    return;
  }
  backendProcess = spawn(exePath, [], {
    cwd: path.dirname(exePath),
    env: backendEnv(),
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  backendStatus = { running: true, lastError: null };
  broadcastBackendStatus();
  backendProcess.stdout.on("data", (chunk) => console.log(`[backend] ${chunk}`));
  backendProcess.stderr.on("data", (chunk) => console.error(`[backend] ${chunk}`));
  backendProcess.on("exit", (code, signal) => {
    backendProcess = null;
    backendStatus = {
      running: false,
      lastError: manualQuit ? null : `Backend exited (${code ?? signal ?? "unknown"})`,
    };
    broadcastBackendStatus();
    if (!manualQuit) {
      backendRestartTimer = setTimeout(startBackend, 1500);
    }
  });
}

function stopBackend() {
  manualQuit = true;
  if (backendRestartTimer) clearTimeout(backendRestartTimer);
  backendRestartTimer = null;
  if (backendProcess) {
    backendProcess.kill();
  }
}

function setupAutoUpdater() {
  if (isDev || !autoUpdater) return;
  autoUpdater.autoDownload = true;
  autoUpdater.on("error", (err) => console.warn("Auto-update check failed:", err?.message || err));
  autoUpdater.checkForUpdatesAndNotify().catch((err) => {
    console.warn("Auto-update unavailable:", err?.message || err);
  });
}

function createAvatarWindow() {
  const { width, height } = screen.getPrimaryDisplay().workAreaSize;
  const win = new BrowserWindow({
    width: 320,
    height: 640,
    x: width - 340,
    y: Math.max(20, height - 680),
    frame: false,
    transparent: true,
    alwaysOnTop: true,
    resizable: true,
    skipTaskbar: false,
    hasShadow: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  if (process.platform === "darwin") {
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  }

  if (isDev) {
    win.loadURL("http://127.0.0.1:5173");
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  return win;
}

app.whenReady().then(() => {
  startBackend();
  createAvatarWindow();
  setupAutoUpdater();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createAvatarWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopBackend();
});

ipcMain.handle("window:minimize", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.minimize();
});

ipcMain.handle("window:close", (event) => {
  BrowserWindow.fromWebContents(event.sender)?.close();
});

// Resize keeping the right edge anchored (used when parent settings open/close)
ipcMain.handle("window:resize", (event, width, height) => {
  const win = BrowserWindow.fromWebContents(event.sender);
  if (!win) return;
  const w = Math.max(280, Math.round(Number(width) || 320));
  const h = Math.max(400, Math.round(Number(height) || 640));
  const bounds = win.getBounds();
  if (bounds.width === w && bounds.height === h) return;
  const workArea = screen.getDisplayMatching(bounds).workArea;
  const x = Math.max(workArea.x, bounds.x + bounds.width - w);
  const y = Math.max(workArea.y, Math.min(bounds.y, workArea.y + workArea.height - h));
  win.setBounds({ x, y, width: w, height: h }, true);
});

ipcMain.handle("backend:status", () => backendStatus);

ipcMain.handle("backend:restart", () => {
  if (isDev) return backendStatus;
  stopBackend();
  setTimeout(() => {
    manualQuit = false;
    startBackend();
  }, 750);
  return backendStatus;
});
