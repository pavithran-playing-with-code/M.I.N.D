// What the overlay page may ask the desktop app for (nothing else: the page can't touch your files)
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('mindOverlay', {
  interactive: (on) => ipcRenderer.send('interactive', on),  // mouse over a panel: take clicks
  hide: () => ipcRenderer.send('hide'),
  windows: () => ipcRenderer.invoke('windows'),              // the open windows with small live pictures
})
