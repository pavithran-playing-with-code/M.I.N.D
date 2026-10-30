// M.I.N.D's see-through desktop HUD ("Jarvis mode"): a transparent window over the whole desktop.
// Only the floating panels are solid; everywhere else your clicks go through to your own windows.
// Started and stopped by the Python side (backend/overlay.py), or shown/hidden with Ctrl+Alt+M.
// It shows the normal HUD page in overlay mode: http://127.0.0.1:8000/?overlay=1
const { app, BrowserWindow, desktopCapturer, globalShortcut, ipcMain, screen } = require('electron')
const path = require('path')

const PAGE = 'http://127.0.0.1:8000/?overlay=1'
const SHORTCUT = 'Control+Alt+M'
let win = null

if (!app.requestSingleInstanceLock()) app.quit()  // (one overlay only)

function createWindow() {
  const area = screen.getPrimaryDisplay().workArea  // (the taskbar stays usable)
  win = new BrowserWindow({
    ...area,
    title: 'M.I.N.D overlay',
    transparent: true,
    frame: false,
    hasShadow: false,
    resizable: false,
    movable: false,
    skipTaskbar: true,
    alwaysOnTop: true,
    backgroundColor: '#00000000',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, backgroundThrottling: false },
  })
  win.setAlwaysOnTop(true, 'floating')
  // Keep its own name: the page's title ("M.I.N.D") made it look like the normal HUD window to M.I.N.D
  win.on('page-title-updated', (event) => event.preventDefault())
  win.setIgnoreMouseEvents(true, { forward: true })  // clicks go through until the mouse is over a panel
  load()
  win.on('closed', () => { win = null })
}

// The backend may still be starting: keep trying for a while
function load(tries = 0) {
  win.loadURL(PAGE).catch(() => {
    if (tries < 30 && win) setTimeout(() => load(tries + 1), 1000)
  })
}

// M.I.N.D shows its small floating reactor while the overlay is hidden, and hides it while it shows
function tell(shown) {
  fetch('http://127.0.0.1:8000/api/overlay_shown', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ shown }),
  }).catch(() => {})
}

function hide() {
  if (win && win.isVisible()) { win.hide(); tell(false) }
}

function toggle() {
  if (!win) return createWindow()
  if (win.isVisible()) return hide()
  win.showInactive()  // (your window keeps the keyboard)
  tell(true)
}

// The page says when the mouse is over a panel (then the overlay takes clicks) or not (clicks go through)
ipcMain.on('interactive', (_, on) => {
  if (win) win.setIgnoreMouseEvents(!on, { forward: true })
})
ipcMain.on('hide', hide)

// Live previews of the open windows (small pictures, refreshed by the page every couple of seconds).
// The source id is "window:<handle>:0"; the handle lets the Python side move/minimize/close that window.
ipcMain.handle('windows', async () => {
  const sources = await desktopCapturer.getSources({ types: ['window'], thumbnailSize: { width: 360, height: 220 } })
  const mine = win ? win.getMediaSourceId() : ''
  return sources
    .filter((s) => s.id !== mine && s.name && !/^M\.I\.N\.D( mini| Live| overlay)?$/.test(s.name))
    .map((s) => ({ id: s.id, handle: Number(s.id.split(':')[1]) || 0, name: s.name, picture: s.thumbnail.toDataURL() }))
})

app.whenReady().then(() => {
  createWindow()
  globalShortcut.register(SHORTCUT, toggle)
})

app.on('second-instance', () => { if (win) { win.showInactive(); tell(true) } })
app.on('will-quit', () => globalShortcut.unregisterAll())
app.on('window-all-closed', () => app.quit())
