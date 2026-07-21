/**
 * Keep the avatar above normal desktop apps, but not above games /
 * fullscreen apps (exclusive or borderless).
 *
 * Electron's "screen-saver" level sits above almost everything, including
 * games. We use "floating" instead, skip macOS fullscreen Spaces, and on
 * Windows hide while another process owns a monitor-sized foreground window.
 */

const { spawn } = require("child_process");
const { screen } = require("electron");

/** Stay above ordinary windows; do not use "screen-saver" (covers games). */
const OVERLAY_LEVEL = "floating";

function applyOverlayOnTop(win) {
  if (!win || win.isDestroyed()) return;
  win.setAlwaysOnTop(true, OVERLAY_LEVEL);
  if (process.platform === "darwin") {
    // Visible on other Spaces, but not over fullscreen apps/games.
    win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: false });
  }
}

function applyOverlayYield(win) {
  if (!win || win.isDestroyed()) return;
  win.setAlwaysOnTop(false);
  if (win.isVisible()) win.hide();
}

function restoreOverlay(win) {
  if (!win || win.isDestroyed()) return;
  // Don't steal focus from whatever the kid just left.
  if (!win.isVisible()) win.showInactive();
  applyOverlayOnTop(win);
}

function displayBoundsList() {
  return screen.getAllDisplays().map((d) => {
    const b = d.bounds;
    return `${b.x},${b.y},${b.width},${b.height}`;
  });
}

/**
 * Long-lived PowerShell watcher: prints "1" / "0" when a foreign foreground
 * window covers a whole display (typical for games & F11 fullscreen).
 */
function startWindowsFullscreenWatcher(win) {
  const displays = displayBoundsList();
  if (!displays.length) return null;

  const script = `
$ErrorActionPreference = 'SilentlyContinue'
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class KdaFg {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
$ourPid = ${process.pid}
$displays = @(${displays.map((d) => `"${d}"`).join(",")})
while ($true) {
  $fullscreen = 0
  $hwnd = [KdaFg]::GetForegroundWindow()
  if ($hwnd -ne [IntPtr]::Zero) {
    $fgPid = [uint32]0
    [void][KdaFg]::GetWindowThreadProcessId($hwnd, [ref]$fgPid)
    if ($fgPid -ne $ourPid) {
      $rect = New-Object KdaFg+RECT
      if ([KdaFg]::GetWindowRect($hwnd, [ref]$rect)) {
        $w = $rect.Right - $rect.Left
        $h = $rect.Bottom - $rect.Top
        foreach ($spec in $displays) {
          $p = $spec.Split(',')
          $dx = [int]$p[0]; $dy = [int]$p[1]; $dw = [int]$p[2]; $dh = [int]$p[3]
          if ($w -ge ($dw - 4) -and $h -ge ($dh - 4) -and
              $rect.Left -le ($dx + 4) -and $rect.Top -le ($dy + 4) -and
              $rect.Right -ge ($dx + $dw - 4) -and $rect.Bottom -ge ($dy + $dh - 4)) {
            $fullscreen = 1
            break
          }
        }
      }
    }
  }
  Write-Output $fullscreen
  Start-Sleep -Milliseconds 1500
}
`;

  const child = spawn(
    "powershell.exe",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
    { windowsHide: true, stdio: ["ignore", "pipe", "ignore"] },
  );

  let yielding = false;
  let buf = "";
  child.stdout.on("data", (chunk) => {
    buf += chunk.toString();
    const lines = buf.split(/\r?\n/);
    buf = lines.pop() || "";
    for (const line of lines) {
      const foreignFullscreen = line.trim() === "1";
      if (foreignFullscreen && !yielding) {
        yielding = true;
        applyOverlayYield(win);
      } else if (!foreignFullscreen && yielding) {
        yielding = false;
        restoreOverlay(win);
      }
    }
  });

  child.on("error", () => {
    // Fall back to floating always-on-top only.
  });

  return child;
}

function attachOverlayPolicy(win) {
  applyOverlayOnTop(win);

  let watcher = null;
  const stopWatcher = () => {
    if (watcher && !watcher.killed) {
      try {
        watcher.kill();
      } catch {
        // ignore
      }
    }
    watcher = null;
  };

  const startWatcher = () => {
    if (process.platform !== "win32" || win.isDestroyed()) return;
    stopWatcher();
    watcher = startWindowsFullscreenWatcher(win);
  };

  startWatcher();

  const onDisplayChange = () => startWatcher();
  screen.on("display-added", onDisplayChange);
  screen.on("display-removed", onDisplayChange);

  const stop = () => {
    stopWatcher();
    screen.removeListener("display-added", onDisplayChange);
    screen.removeListener("display-removed", onDisplayChange);
  };

  win.on("closed", stop);
  return { stop };
}

module.exports = {
  OVERLAY_LEVEL,
  applyOverlayOnTop,
  attachOverlayPolicy,
};
