// First-run setup: shown over the HUD until a new user has M.I.N.D ready (backend/setup.py).
// Steps: hello -> about you -> brain key (Gemini) -> hearing key (Groq) -> your voice -> Chrome extension -> done.
import { useEffect, useState } from 'react'
import { post } from '../mind.js'
import PhoneSetup from './PhoneSetup.jsx'

const CALL_ME = ['Sir', 'Boss', 'Bro', 'My name']
const STEPS = ['hello', 'about', 'gemini', 'groq', 'voice', 'extension', 'phone', 'done']

async function act(what, args = {}) {
  try {
    const answer = await post(`/api/setup/${what}`, args)
    return await answer.json()
  } catch {
    return { ok: false, message: "Can't reach M.I.N.D. Is it running?" }
  }
}

function KeyStep({ kind, title, why, site, steps, optional, status, onStatus, onDone, onBack }) {
  const [key, setKey] = useState('')
  const [note, setNote] = useState(null)
  const [busy, setBusy] = useState(false)
  const has = status?.[kind]
  async function check() {
    setBusy(true)
    setNote(null)
    const answer = await act('key', { kind, key })
    setBusy(false)
    setNote(answer)
    if (answer.status) onStatus(answer.status)
    if (answer.ok) setKey('')
  }
  return (
    <>
      <h2>{title}</h2>
      <p className="setup-why">{why}</p>
      <ol className="setup-steps">
        <li>
          <button className="setup-link" onClick={() => act('open', { what: kind })}>Open {site} ↗</button>
        </li>
        {steps.map((line) => <li key={line}>{line}</li>)}
        <li>Paste it here:</li>
      </ol>
      <div className="setup-row">
        <input type="password" placeholder={has ? 'Saved ✓ (paste a new one to change it)' : 'Paste your key'}
          value={key} onChange={(e) => setKey(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && key && check()} />
        <button className="setup-main" disabled={!key || busy} onClick={check}>{busy ? 'Checking…' : 'Check key'}</button>
      </div>
      {note && <p className={`setup-note ${note.ok ? 'ok' : 'bad'}`}>{note.ok ? '✅ ' : '❌ '}{note.message}</p>}
      <div className="setup-nav">
        <button className="setup-skip" onClick={onBack}>← Back</button>
        {(has || note?.ok) && <button className="setup-main" onClick={onDone}>Next →</button>}
        {optional && !has && !note?.ok && <button className="setup-skip" onClick={onDone}>Skip for now</button>}
      </div>
    </>
  )
}

export default function Setup() {
  const [status, setStatus] = useState(null)
  const [step, setStep] = useState(0)
  const [about, setAbout] = useState({ real_name: '', call_me: 'Sir', city: '' })
  const [custom, setCustom] = useState('')
  const [note, setNote] = useState(null)
  const [finished, setFinished] = useState(false)
  const [phone, setPhone] = useState(false)

  // Ask at start (until M.I.N.D answers), and every 1.5 s on the voice step (to see when it's learned)
  useEffect(() => {
    let stop = false
    async function load() {
      try {
        const answer = await (await fetch('/api/setup')).json()
        if (stop) return true
        setStatus(answer)
        if (answer.real_name) setAbout((a) => ({ ...a, real_name: a.real_name || answer.real_name, city: a.city || answer.city }))
        return true
      } catch { return false }
    }
    let timer = setInterval(async () => { if (await load()) clearInterval(timer) }, 3000)
    load().then((worked) => { if (worked) clearInterval(timer) })
    return () => { stop = true; clearInterval(timer) }
  }, [])
  useEffect(() => {
    if (STEPS[step] !== 'voice') return
    const timer = setInterval(async () => {
      try { setStatus(await (await fetch('/api/setup')).json()) } catch { /* try again */ }
    }, 1500)
    return () => clearInterval(timer)
  }, [step])

  if (!status || (!status.needed && !finished && step === 0)) return null
  const next = () => { setNote(null); setStep((s) => Math.min(s + 1, STEPS.length - 1)) }
  const back = () => { setNote(null); setStep((s) => Math.max(s - 1, 0)) }
  const name = STEPS[step]

  async function saveAbout() {
    const call = about.call_me === 'My name' ? '' : about.call_me === 'custom' ? custom : about.call_me
    const answer = await act('about', { ...about, call_me: call })
    setNote(answer)
    if (answer.ok) next()
  }

  async function finish() {
    setFinished(true)
    setNote(await act('finish'))
  }

  return (
    <div className="setup">
      <div className="setup-card">
        <div className="setup-dots">
          {STEPS.map((s, i) => <span key={s} className={i < step ? 'done' : i === step ? 'now' : ''} />)}
        </div>

        {name === 'hello' && (
          <>
            <h1>Hi, I'm M.I.N.D 👋</h1>
            <p className="setup-why">Your own voice assistant. Let's get me ready: about 5 minutes, and everything is free.</p>
            <p className="setup-why">You'll need: a Google account, and your laptop's mic.</p>
            <div className="setup-nav"><button className="setup-main" onClick={next}>Let's start →</button></div>
          </>
        )}

        {name === 'about' && (
          <>
            <h2>About you</h2>
            <label>Your name<input autoFocus value={about.real_name} placeholder="e.g. Arjun"
              onChange={(e) => setAbout({ ...about, real_name: e.target.value })} /></label>
            <label>What should I call you?</label>
            <div className="setup-chips">
              {[...CALL_ME, 'custom'].map((c) => (
                <button key={c} className={about.call_me === c ? 'on' : ''} onClick={() => setAbout({ ...about, call_me: c })}>
                  {c === 'custom' ? 'Something else' : c}
                </button>
              ))}
            </div>
            {about.call_me === 'custom' && <input value={custom} placeholder="e.g. Captain" onChange={(e) => setCustom(e.target.value)} />}
            <label>Your city (for weather and time)<input value={about.city} placeholder="e.g. Chennai"
              onChange={(e) => setAbout({ ...about, city: e.target.value })} /></label>
            {note && !note.ok && <p className="setup-note bad">❌ {note.message}</p>}
            <div className="setup-nav">
              <button className="setup-skip" onClick={back}>← Back</button>
              <button className="setup-main" disabled={!about.real_name.trim()} onClick={saveAbout}>Next →</button>
            </div>
          </>
        )}

        {name === 'gemini' && (
          <KeyStep kind="gemini" status={status} onStatus={setStatus} onDone={next} onBack={back} site="Google AI Studio"
            title="My brain: a free Google key"
            why="I think, hear and speak with Google's Gemini. Your own key is free (no card) and only lives on this laptop."
            steps={['Sign in with your Google account.', 'Click "Create API key" (accept the terms if it asks).', 'Copy the key.']} />
        )}

        {name === 'groq' && (
          <KeyStep kind="groq" status={status} onStatus={setStatus} onDone={next} onBack={back} site="Groq Console" optional
            title="My ears: a free Groq key"
            why='Groq turns your voice into words fast, so I know you said "Mind". Also free, no card. Recommended.'
            steps={['Sign in (Google works).', 'Click "Create API Key", give it any name.', 'Copy the key.']} />
        )}

        {name === 'voice' && (
          <>
            <h2>Learn your voice</h2>
            <p className="setup-why">So I only listen to you, not the TV or people around. I'll say 5 short lines: read each one after me, in your normal voice.</p>
            <ol className="setup-lines">{(status.lines || []).map((l) => <li key={l}>{l}</li>)}</ol>
            {status.learning
              ? <p className="setup-note">🎙 Listening… read each line after me.</p>
              : status.voice
                ? <p className="setup-note ok">✅ Got your voice.</p>
                : <button className="setup-main" onClick={async () => { const a = await act('voice'); if (a.status) setStatus({ ...a.status, learning: true }) }}>🎙 Start</button>}
            <div className="setup-nav">
              <button className="setup-skip" onClick={back}>← Back</button>
              {status.voice && !status.learning
                ? <button className="setup-main" onClick={next}>Next →</button>
                : <button className="setup-skip" onClick={next}>Skip for now</button>}
            </div>
          </>
        )}

        {name === 'extension' && (
          <>
            <h2>Chrome extension (optional)</h2>
            <p className="setup-why">Lets me tell you when a Claude or ChatGPT chat finishes, even in a hidden tab.</p>
            <ol className="setup-steps">
              <li><button className="setup-link" onClick={() => act('open', { what: 'extensions' })}>Open Chrome's extensions page ↗</button></li>
              <li>Turn on <b>Developer mode</b> (top right).</li>
              <li>Click <b>Load unpacked</b> and pick this folder:</li>
            </ol>
            <div className="setup-row">
              <input readOnly value={status.extension_folder} onFocus={(e) => e.target.select()} />
              <button className="setup-skip" onClick={() => navigator.clipboard?.writeText(status.extension_folder)}>Copy</button>
            </div>
            <div className="setup-nav">
              <button className="setup-skip" onClick={back}>← Back</button>
              <button className="setup-main" onClick={next}>Next →</button>
            </div>
          </>
        )}

        {name === 'phone' && (
          <>
            <h2>Phone app (optional)</h2>
            <p className="setup-why">Control this laptop, talk to me and get my alerts on your phone, from anywhere. Nothing to install on the phone: you just scan a QR code.</p>
            {phone ? <PhoneSetup /> : <button className="setup-main" onClick={() => setPhone(true)}>📱 Set up my phone</button>}
            <div className="setup-nav">
              <button className="setup-skip" onClick={back}>← Back</button>
              <button className={phone ? 'setup-main' : 'setup-skip'} onClick={next}>{phone ? 'Next →' : 'Skip for now'}</button>
            </div>
          </>
        )}

        {name === 'done' && (
          <>
            <h1>You're all set! 🎉</h1>
            {!status.gemini && <p className="setup-note bad">⚠ No brain key yet: I can't think without it. Go back and add it.</p>}
            <p className="setup-why">Just talk to me: say <b>"Hey Mind"</b>, or start with "Mind, …".</p>
            <ul className="setup-tips">
              <li>"Mind, what can you do?" shows everything I can do.</li>
              <li>Click the glowing reactor to type to me.</li>
              <li>Tap the core here once for all settings.</li>
            </ul>
            {note
              ? <p className={`setup-note ${note.ok ? 'ok' : 'bad'}`}>{note.message}</p>
              : (
                <div className="setup-nav">
                  <button className="setup-skip" onClick={back}>← Back</button>
                  <button className="setup-main" disabled={!status.gemini} onClick={finish}>Finish</button>
                </div>
              )}
          </>
        )}
      </div>
    </div>
  )
}
