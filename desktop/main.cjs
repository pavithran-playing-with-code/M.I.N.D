// M.I.N.D's Jarvis mode: the HUD as its own desktop app, with no frame. It can cut a real hole in itself, and any of
// your windows sits exactly in that hole (backend/overlay.py moves it there): the real window, not a video of it,
// so there's no lag and your mouse and keyboard work in it directly.
// Started and stopped by the Python side. Ctrl+Alt+M brings it forward / tucks it away.
// It shows the normal HUD page: http://127.0.0.1:8000/?jarvis=1
const { app, BrowserWindow, Menu, globalShortcut, ipcMain } = require('electron')
const path = require('path')

const PAGE = 'http://127.0.0.1:8000/?jarvis=1'
const SHORTCUT = 'Control+Alt+M'
let win = null

if (!app.requestSingleInstanceLock()) app.quit()  // (one Jarvis window only)
Menu.setApplicationMenu(null)  // (no File/Edit/View menu bar: it's a HUD, not a document app)

function createWindow() {
  win = new BrowserWindow({
    width: 1400,
    height: 860,
    show: false,
    frame: false,
    title: 'M.I.N.D Jarvis',
    backgroundColor: '#03070d',
    icon: path.join(__dirname, '..', 'backend', 'icons', 'mind_on.ico'),
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, backgroundThrottling: false },
  })
  // Keep its own name ("M.I.N.D" is the normal HUD's name; M.I.N.D tells them apart by it)
  win.on('page-title-updated', (event) => event.preventDefault())
  win.once('ready-to-show', () => { win.maximize(); win.show() })
  load()
  win.on('minimize', () => win.webContents.send('shown', false))
  win.on('restore', () => win.webContents.send('shown', true))
  win.on('closed', () => { win = null })
}

// The backend may still be starting: keep trying for a while
function load(tries = 0) {
  win.loadURL(PAGE).catch(() => {
    if (tries < 30 && win) setTimeout(() => load(tries + 1), 1000)
  })
}

function toggle() {
  if (!win) return createWindow()
  if (win.isFocused() && !win.isMinimized()) return win.minimize()
  if (win.isMinimized()) win.restore()
  win.show()
  win.focus()
}

const whole = (r) => ({ x: Math.round(r.x), y: Math.round(r.y), width: Math.round(r.width), height: Math.round(r.height) })

// The page asks for a hole: everything stays, except the hole's rectangle, and things above it (other widgets) stay
// too. Answers with where the hole is on the screen, for the real window. null = no hole: the whole HUD again.
ipcMain.handle('hole', (event, hole, above) => {
  if (!win) return null
  if (!hole) {
    win.setShape([])  // (an empty list = the normal rectangle)
    return null
  }
  const [width, height] = win.getContentSize()
  const r = whole(hole)
  const pieces = [
    { x: 0, y: 0, width, height: r.y },
    { x: 0, y: r.y + r.height, width, height: height - r.y - r.height },
    { x: 0, y: r.y, width: r.x, height: r.height },
    { x: r.x + r.width, y: r.y, width: width - r.x - r.width, height: r.height },
    ...above.map(whole),
  ].filter((p) => p.width > 0 && p.height > 0)
  win.setShape(pieces)
  const at = win.getContentBounds()
  return { x: at.x + r.x, y: at.y + r.y, width: r.width, height: r.height }
})
ipcMain.handle('minimize', () => win && win.minimize())
ipcMain.handle('close', () => win && win.close())

app.whenReady().then(() => {
  createWindow()
  globalShortcut.register(SHORTCUT, toggle)
})

app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus() } })
app.on('will-quit', () => globalShortcut.unregisterAll())
app.on('window-all-closed', () => app.quit())
