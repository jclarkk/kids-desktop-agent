const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kda", {
  minimize: () => ipcRenderer.invoke("window:minimize"),
  close: () => ipcRenderer.invoke("window:close"),
  resize: (width, height) => ipcRenderer.invoke("window:resize", width, height),
  moveAside: () => ipcRenderer.invoke("window:moveAside"),
  openExternal: (url) => ipcRenderer.invoke("shell:openExternal", url),
  ollamaStatus: () => ipcRenderer.invoke("ollama:status"),
  ollamaInstall: (options) => ipcRenderer.invoke("ollama:install", options || {}),
  ollamaPull: (model) => ipcRenderer.invoke("ollama:pull", model),
  onOllamaProgress: (handler) => {
    const listener = (_event, payload) => handler(payload);
    ipcRenderer.on("ollama:progress", listener);
    return () => ipcRenderer.removeListener("ollama:progress", listener);
  },
  backendStatus: () => ipcRenderer.invoke("backend:status"),
  restartBackend: () => ipcRenderer.invoke("backend:restart"),
  onBackendStatus: (handler) => {
    const listener = (_event, status) => handler(status);
    ipcRenderer.on("backend:status", listener);
    return () => ipcRenderer.removeListener("backend:status", listener);
  },
});
