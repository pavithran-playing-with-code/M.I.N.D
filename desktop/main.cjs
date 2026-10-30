// M.I.N.D's Jarvis mode: the HUD as its own desktop app window, which can show any of your windows or
// screens LIVE inside the HUD, in full quality (a normal browser can't do that without asking every time).
// Started and stopped by the Python side (backend/overlay.py). Ctrl+Alt+M brings it forward / tucks it away.
// It shows the normal HUD page: http://127.0.0.1:8000/?jarvis=1
const { app, BrowserWindow, Menu, desktopCapturer, globalShortcut, ipcMain, session } = require('electron')
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
    title: 'M.I.N.D Jarvis',
    backgroundColor: '#03070d',
    autoHideMenuBar: true,
    icon: path.join(__dirname, '..', 'backend', 'icons', 'mind_on.ico'),
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, backgroundThrottling: false },
  })
  // Keep its own name ("M.I.N.D" is the normal HUD's name; M.I.N.D tells them apart by it)
  win.on('page-title-updated', (event) => event.preventDefault())
  win.once('ready-to-show', () => { win.maximize(); win.show() })
  load()
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

// Your windows and screens, with small pictures (the page picks one to show live).
// A window's id is "window:<handle>:0"; the handle lets the Python side bring it forward / minimize / close it.
ipcMain.handle('sources', async () => {
  const sources = await desktopCapturer.getSources({ types: ['screen', 'window'], thumbnailSize: { width: 320, height: 200 } })
  const mine = win ? win.getMediaSourceId() : ''
  return sources
    .filter((s) => s.id !== mine && s.name && !/^M\.I\.N\.D( mini| Live| Jarvis)?$/.test(s.name))
    .map((s) => ({
      id: s.id,
      screen: s.id.startsWith('screen:'),
      handle: s.id.startsWith('window:') ? Number(s.id.split(':')[1]) || 0 : 0,
      name: s.id.startsWith('screen:') ? (s.name === 'Entire Screen' ? 'Whole screen' : s.name) : s.name,
      picture: s.thumbnail.toDataURL(),
    }))
})

app.whenReady().then(() => {
  // The page asks for a window's live picture by its id: allow it (it's our own page, nothing else)
  session.defaultSession.setPermissionRequestHandler((wc, permission, done) => done(permission === 'media'))
  createWindow()
  globalShortcut.register(SHORTCUT, toggle)
})

app.on('second-instance', () => { if (win) { if (win.isMinimized()) win.restore(); win.show(); win.focus() } })
app.on('will-quit', () => globalShortcut.unregisterAll())
app.on('window-all-closed', () => app.quit())
