// The Mail panel ("Mind, open my mail", or Ctrl + M): all your Gmail accounts in one place (backend gmail.py).
// Views across the top, search, the list on the left, the open mail on the right, and a writer for
// new mails and replies. Every button is your own click, so it acts at once (delete = Trash, undo in Gmail).
import { useEffect, useState } from 'react'
import { post } from '../mind.js'

const VIEWS = [['important', 'Important'], ['unread', 'Unread'], ['inbox', 'Inbox'], ['spam', 'Spam'], ['sent', 'Sent']]
const ask = (what, body) => post('/api/mail/' + what, body).then((r) => r.json())
const short = (address) => (address || '').split('@')[0]

export default function Mail() {
  const [view, setView] = useState('important')
  const [words, setWords] = useState('')
  const [account, setAccount] = useState('')
  const [list, setList] = useState(null)       // {mails, accounts, problems}
  const [busy, setBusy] = useState(false)
  const [open, setOpen] = useState(null)       // the mail being read
  const [writing, setWriting] = useState(null) // {to, subject, body, reply_id, account}
  const [note, setNote] = useState('')
  const [sure, setSure] = useState(false)      // "Delete? Yes" step

  function load(v = view, w = words, a = account) {
    setBusy(true)
    setList((l) => l && { ...l, mails: [] })  // (the old list goes at once: no clicking a mail from the old view)
    ask('list', { view: v, words: w, account: a })
      .then((r) => setList(r))
      .catch(() => setNote("Couldn't reach Gmail"))
      .finally(() => setBusy(false))
  }
  useEffect(() => {  // the first list (Important) when the panel opens
    ask('list', { view: 'important' }).then(setList, () => setNote("Couldn't reach Gmail"))
  }, [])

  function pickView(v) { setView(v); setWords(''); setOpen(null); load(v, '', account) }
  function search(e) { e.preventDefault(); setOpen(null); load(view, words, account) }
  function pickAccount(a) { setAccount(a); setOpen(null); load(view, words, a) }

  function read(m) {
    setWriting(null); setSure(false)
    setOpen({ ...m, text: null })
    ask('open', { id: m.id }).then((r) => {
      if (r.problem) { setNote(r.problem); return }
      setOpen(r)
      setList((l) => l && { ...l, mails: l.mails.map((x) => (x.id === m.id ? { ...x, unread: false } : x)) })
    })
  }
  function act(action) {
    ask('act', { id: open.id, action }).then((r) => {
      setNote(r.said || r.problem || '')
      if (r.ok && action === 'delete') {
        setList((l) => l && { ...l, mails: l.mails.filter((x) => x.id !== open.id) })
        setOpen(null)
      }
      if (r.ok && action === 'unread') {
        setList((l) => l && { ...l, mails: l.mails.map((x) => (x.id === open.id ? { ...x, unread: true } : x)) })
      }
      setSure(false)
    })
  }
  function reply() {
    setWriting({ to: open.from, subject: open.subject.toLowerCase().startsWith('re:') ? open.subject : 'Re: ' + open.subject,
      body: '', reply_id: open.id, account: open.account })
  }
  function compose() {
    setOpen(null)
    setWriting({ to: '', subject: '', body: '', reply_id: '', account: account || list?.accounts?.[0] || '' })
  }
  function send(draft) {
    setNote(draft ? 'Saving…' : 'Sending…')
    ask('send', { ...writing, draft }).then((r) => {
      setNote(r.said || r.problem || '')
      if (r.ok) setWriting(null)
    }, () => setNote("Couldn't reach Gmail"))
  }

  if (list && !list.ready) {
    return <div className="mail"><p className="mail-empty">{list.problem}. Add GMAIL_ADDRESS and GMAIL_APP_PASSWORD to backend/.env.</p></div>
  }
  const mails = list?.mails || []
  return (
    <div className="mail">
      <div className="mail-top">
        <div className="mail-views">
          {VIEWS.map(([v, label]) => (
            <button key={v} className={view === v && !words ? 'on' : ''} onClick={() => pickView(v)}>{label}</button>
          ))}
        </div>
        <form className="mail-search" onSubmit={search}>
          <input placeholder="Search all mail (from:penny, invoice…)" value={words} onChange={(e) => setWords(e.target.value)} />
        </form>
        {(list?.accounts?.length || 0) > 1 && (
          <select className="mail-account" value={account} onChange={(e) => pickAccount(e.target.value)}>
            <option value="">All accounts</option>
            {list.accounts.map((a) => <option key={a} value={a}>{short(a)}</option>)}
          </select>
        )}
        <button className="mail-btn" onClick={() => load()}>{busy ? '…' : '⟳'}</button>
        <button className="mail-btn main" onClick={compose}>✏ Write</button>
      </div>
      {note && <div className="mail-note" onClick={() => setNote('')}>{note}</div>}
      {(list?.problems || []).map((p) => <div key={p} className="mail-note bad">{p}</div>)}
      <div className="mail-body">
        <div className="mail-list">
          {!list && <p className="mail-empty">Checking your mail…</p>}
          {list && !mails.length && <p className="mail-empty">{busy ? 'Checking…' : 'Nothing here.'}</p>}
          {mails.map((m) => (
            <button key={m.id} className={`mail-row ${m.unread ? 'unread' : ''} ${open?.id === m.id ? 'on' : ''}`} onClick={() => read(m)}>
              <span className="mail-who">{m.name}</span>
              <span className="mail-when">{m.ago}</span>
              <span className="mail-subject">{m.subject}</span>
              <span className="mail-snippet">{m.snippet}</span>
              {(list.accounts?.length || 0) > 1 && <span className="mail-tag">{short(m.account)}</span>}
            </button>
          ))}
        </div>
        <div className="mail-read">
          {writing ? (
            <div className="mail-write">
              {(list?.accounts?.length || 0) > 1 && !writing.reply_id && (
                <label>From <select value={writing.account} onChange={(e) => setWriting({ ...writing, account: e.target.value })}>
                  {list.accounts.map((a) => <option key={a} value={a}>{a}</option>)}
                </select></label>
              )}
              <input placeholder="To (address, or a name you've mailed before)" value={writing.to}
                onChange={(e) => setWriting({ ...writing, to: e.target.value })} disabled={!!writing.reply_id} />
              <input placeholder="Subject" value={writing.subject} onChange={(e) => setWriting({ ...writing, subject: e.target.value })} />
              <textarea placeholder="Write your mail…" value={writing.body} autoFocus
                onChange={(e) => setWriting({ ...writing, body: e.target.value })} />
              <div className="mail-actions">
                <button className="mail-btn main" onClick={() => send(false)}>Send</button>
                <button className="mail-btn" onClick={() => send(true)}>Save draft</button>
                <button className="mail-btn" onClick={() => setWriting(null)}>Cancel</button>
              </div>
            </div>
          ) : open ? (
            <>
              <h3 className="mail-title">{open.subject}</h3>
              <div className="mail-meta">
                <b>{open.name}</b> &lt;{open.from}&gt; · {open.ago}{(list?.accounts?.length || 0) > 1 && <> · to {short(open.account)}</>}
              </div>
              <div className="mail-actions">
                <button className="mail-btn main" onClick={reply}>↩ Reply</button>
                <button className="mail-btn" onClick={() => act('unread')}>Mark unread</button>
                {sure
                  ? <button className="mail-btn danger" onClick={() => act('delete')}>Yes, delete</button>
                  : <button className="mail-btn" onClick={() => setSure(true)}>🗑 Delete</button>}
                <a className="mail-btn" href={open.link} target="_blank" rel="noreferrer">Open in Gmail ↗</a>
              </div>
              <div className="mail-text">{open.text === null ? 'Opening…' : open.text}</div>
            </>
          ) : (
            <p className="mail-empty">Pick a mail to read it, or ✏ Write a new one.</p>
          )}
        </div>
      </div>
    </div>
  )
}
