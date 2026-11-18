// What the Jarvis-mode page may ask the desktop app for (nothing else: the page can't touch your files)
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('mindDesktop', {
  hole: (rects) => ipcRenderer.invoke('hole', rects),  // cut holes for real windows (null = none)
  onShown: (call) => ipcRenderer.on('shown', (event, shown) => call(shown)),  // minimized / back
  minimize: () => ipcRenderer.invoke('minimize'),
  close: () => ipcRenderer.invoke('close'),
})
