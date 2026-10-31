// What the Jarvis-mode page may ask the desktop app for (nothing else: the page can't touch your files)
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('mindDesktop', {
  hole: (rect, above) => ipcRenderer.invoke('hole', rect, above),  // cut a hole for a real window (null = no hole)
  onShown: (call) => ipcRenderer.on('shown', (event, shown) => call(shown)),  // minimized / back
  minimize: () => ipcRenderer.invoke('minimize'),
  close: () => ipcRenderer.invoke('close'),
})
