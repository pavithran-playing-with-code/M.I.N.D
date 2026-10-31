// Talking to the Python backend
import { useEffect, useState } from 'react'

export function post(path, body = {}) {
  return fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
}

// Asks the backend what's happening 5 times a second: [state, online?]
export function useMind() {
  const [mind, setMind] = useState({ status: 'starting', level: 0, messages: [], wake_word: 'hey mind' })
  const [online, setOnline] = useState(false)
  useEffect(() => {
    let stopped = false
    async function poll() {
      try {
        const res = await fetch('/api/state')
        if (!res.ok) throw new Error('bad response')
        setMind(await res.json())
        setOnline(true)
      } catch {
        setOnline(false)
      }
      if (!stopped) setTimeout(poll, 200)
    }
    poll()
    return () => { stopped = true }
  }, [])
  return [mind, online]
}

// What to show under the core for each status
export function statusLabel(status) {
  switch (status) {
    case 'waiting': return ''  // (nothing to say: the core just waits)
    case 'muted': return 'Offline'
    case 'listening': return 'Listening'
    case 'thinking': return 'Thinking'
    case 'speaking': return 'Speaking'
    case 'starting': return 'Starting up'
    default: return 'Not running'
  }
}

// Battery, CPU, RAM, Wi-Fi and the last speed test, from the backend every 5 seconds
export function useInfo(online) {
  const [info, setInfo] = useState(null)
  useEffect(() => {
    if (!online) return
    const load = () => fetch('/api/info').then((r) => r.json()).then(setInfo).catch(() => {})
    load()
    const timer = setInterval(load, 5000)
    return () => clearInterval(timer)
  }, [online])
  return info
}

const squash = (text) => (text || '').toLowerCase().replace(/[^a-z0-9]/g, '')
const LIST_SECONDS = 4

// The best match for a spoken name ("vs code", "my YouTube tab"): a window title or a tab name with the most of its words
export function bestMatch(windows, name) {
  const want = squash(name)
  const words = (name || '').toLowerCase().split(/\W+/).filter((w) => w.length > 2)
  let best = null, most = 0
  const score = (title) => words.filter((w) => title.toLowerCase().includes(w)).length + (squash(title).includes(want) ? 2 : 0)
  for (const w of windows) {
    if (score(w.title + ' ' + w.app) > most) { most = score(w.title + ' ' + w.app); best = { handle: w.handle, title: w.title, tab: '' } }
    for (const tab of w.tabs) {
      if (score(tab) > most) { most = score(tab); best = { handle: w.handle, title: tab, tab } }
    }
  }
  return best
}

// What's open, refreshed every few seconds
export function useOpenWindows(wanted) {
  const [windows, setWindows] = useState([])
  useEffect(() => {
    if (!wanted) return undefined
    let stopped = false
    async function refresh() {
      try {
        const found = await fetch('/api/windows').then((r) => r.json())
        if (!stopped) setWindows(found.windows)
      } catch { /* the next refresh tries again */ }
      if (!stopped) setTimeout(refresh, LIST_SECONDS * 1000)
    }
    refresh()
    return () => { stopped = true }
  }, [wanted])
  return windows
}
