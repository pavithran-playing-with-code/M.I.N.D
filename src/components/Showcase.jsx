// The hologram panel: what M.I.N.D shows on the HUD.
// kind "pictures": pictures + facts ("show me Iron Man suits"), product picks with Amazon/Flipkart buttons
// kind "animation": an animation M.I.N.D wrote itself, in a locked-down frame
// kind "lesson": a lesson card ("help me learn Spanish")
// The orb sits below it like a projector, with a beam of light going up into the panel.
import { useState } from 'react'

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

export default function Showcase({ show, onClose }) {
  const kind = show.kind || 'pictures'
  return (
    <div className="holo" key={show.id}>
      <div className={`holo-panel ${kind}`}>
        <div className="holo-head">
          <span className="holo-title">{kind === 'lesson' && show.topic ? `${show.topic} · ${show.title}` : show.title}</span>
          <button className="holo-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="holo-body">
          {kind === 'animation' && (
            // sandbox without same-origin: the animation can't touch the HUD or M.I.N.D
            <iframe className="holo-frame" src={show.src} title={show.title} sandbox="allow-scripts" />
          )}
          {kind === 'lesson' && <Lesson show={show} />}
          {kind === 'pictures' && <Pictures show={show} />}
        </div>
      </div>
      <div className="holo-beam" aria-hidden="true" />
    </div>
  )
}
