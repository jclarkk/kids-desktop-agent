const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("kda", {
  minimize: () => ipcRenderer.invoke("window:minimize"),
  close: () => ipcRenderer.invoke("window:close"),
  resize: (width, height) => ipcRenderer.invoke("window:resize", width, height),
  backendStatus: () => ipcRenderer.invoke("backend:status"),
  restartBackend: () => ipcRenderer.invoke("backend:restart"),
  onBackendStatus: (handler) => {
    const listener = (_event, status) => handler(status);
    ipcRenderer.on("backend:status", listener);
    return () => ipcRenderer.removeListener("backend:status", listener);
  },
});
