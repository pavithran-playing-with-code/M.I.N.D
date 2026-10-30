// What the Jarvis-mode page may ask the desktop app for (nothing else: the page can't touch your files)
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('mindDesktop', {
  sources: () => ipcRenderer.invoke('sources'),  // your windows and screens, with small pictures
})
