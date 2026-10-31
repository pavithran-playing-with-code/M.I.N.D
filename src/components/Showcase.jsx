// The hologram panel: what M.I.N.D shows on the HUD.
// kind "pictures": pictures + facts ("show me Iron Man suits"), product picks with Amazon/Flipkart buttons
// kind "animation": a hologram M.I.N.D made (its engine page, in a locked-down frame)
// kind "building": a golden globe of light while a hologram is being made
// kind "book": a page of a free classic book; kind "typing": typing practice (apps.py)
// kind "lesson": a lesson card ("help me learn Spanish")
// kind "grammar": your text, the fixed text and why ("fix my grammar")
// The orb sits below it like a projector, with a beam of light going up into the panel.
import { useEffect, useState } from 'react'
import HoloLoader from './HoloLoader.jsx'
import BookReader from './BookReader.jsx'
import TypingTrainer from './TypingTrainer.jsx'

// One picture card. If the big picture won't load, use Bing's small copy; if that fails too, hide the card.
function Card({ card, index }) {
  const [src, setSrc] = useState(card.url || card.thumb)
  const [broken, setBroken] = useState(false)
  if (broken) return null

  function failed() {
    if (card.thumb && src !== card.thumb) setSrc(card.thumb)
    else setBroken(true)
  }

  return (
    <div className="holo-card" style={{ '--i': index }}>
      <a className="holo-pic" href={card.page || card.url} target="_blank" rel="noreferrer" title={card.title}>
        <img src={src} alt={card.name || card.title} onError={failed} referrerPolicy="no-referrer" />
      </a>
      {(card.name || card.note) && (
        <div className="holo-label">
          {card.name && <strong>{card.name}</strong>}
          {card.note && <span>{card.note}</span>}
        </div>
      )}
      {card.shops && (
        <div className="holo-shops">
          <a href={card.shops.amazon} target="_blank" rel="noreferrer">Amazon ↗</a>
          <a href={card.shops.flipkart} target="_blank" rel="noreferrer">Flipkart ↗</a>
        </div>
      )}
    </div>
  )
}

function Pictures({ show }) {
  const { info, cards } = show
  const labelled = cards.some((c) => c.name) // product-style cards (name + note) get a wider grid
  return (
    <>
      {info?.text && (
        <p className="holo-info">
          {info.text}
          {info.link && <a href={info.link} target="_blank" rel="noreferrer"> Wikipedia ↗</a>}
        </p>
      )}
      <div className={`holo-grid ${labelled ? 'labelled' : ''}`}>
        {cards.map((card, i) => <Card key={i} card={card} index={i} />)}
      </div>
    </>
  )
}

function Lesson({ show }) {
  return (
    <div className="holo-lesson">
      <ol>
        {show.points.map((point, i) => <li key={i} style={{ '--i': i }}>{point}</li>)}
      </ol>
      {show.example && <div className="holo-example"><span>Example</span>{show.example}</div>}
      {show.question && <div className="holo-question"><span>Your turn</span>{show.question}</div>}
    </div>
  )
}

// Grammar check: what you wrote, the fixed version (with a Copy button) and why each change was made
function Grammar({ show }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard?.writeText(show.fixed).then(() => setCopied(true), () => {})
  }
  return (
    <div className="holo-grammar">
      <div className="holo-text before"><span>You wrote</span>{show.original}</div>
      <div className="holo-text after">
        <span>Better</span>
        {show.fixed}
        <button className="holo-copy" onClick={copy}>{copied ? 'Copied ✓' : 'Copy'}</button>
      </div>
      {show.changes.length > 0 && (
        <ul className="holo-changes">
          {show.changes.map((c, i) => (
            <li key={i} style={{ '--i': i }}>
              <s>{c.from}</s> → <b>{c.to}</b> <em>{c.why}</em>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// A hologram can't reach M.I.N.D itself (it's locked down), so if it hits an error it tells the HUD,
// and the HUD writes it into M.I.N.D's log
function useHologramProblems() {
  useEffect(() => {
    function heard(event) {
      if (event.data && event.data.hologramProblem) {
        fetch('/api/hologram_problem', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: String(event.data.hologramProblem) }),
        })
      }
    }
    window.addEventListener('message', heard)
    return () => window.removeEventListener('message', heard)
  }, [])
}

export default function Showcase({ show }) {
  const kind = show.kind || 'pictures'
  useHologramProblems()
  return (
    <div className="holo" key={show.id}>
      <div className={`holo-panel ${kind}`}>
        <div className="holo-head">
          <span className="holo-title">{kind === 'lesson' && show.topic ? `${show.topic} · ${show.title}` : show.title}</span>
        </div>
        <div className="holo-body">
          {kind === 'animation' && (
            // sandbox without same-origin: the animation can't touch the HUD or M.I.N.D
            <iframe className="holo-frame" src={show.src} title={show.title} sandbox="allow-scripts" />
          )}
          {kind === 'building' && <HoloLoader title={show.title} />}
          {kind === 'book' && <BookReader show={show} />}
          {kind === 'typing' && <TypingTrainer show={show} />}
          {kind === 'lesson' && <Lesson show={show} />}
          {kind === 'grammar' && <Grammar show={show} />}
          {kind === 'pictures' && <Pictures show={show} />}
        </div>
      </div>
      <div className="holo-beam" aria-hidden="true" />
    </div>
  )
}
