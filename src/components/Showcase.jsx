// The hologram panel: pictures and facts M.I.N.D shows on the HUD ("show me Iron Man suits").
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
    <a
      className="holo-card"
      style={{ '--i': index }}
      href={card.page || card.url}
      target="_blank"
      rel="noreferrer"
      title={card.title}
    >
      <div className="holo-pic">
        <img src={src} alt={card.name || card.title} onError={failed} referrerPolicy="no-referrer" />
      </div>
      {(card.name || card.note) && (
        <div className="holo-label">
          {card.name && <strong>{card.name}</strong>}
          {card.note && <span>{card.note}</span>}
        </div>
      )}
    </a>
  )
}

export default function Showcase({ show, onClose }) {
  const { title, info, cards } = show
  const labelled = cards.some((c) => c.name)  // product-style cards (name + note) get a different grid

  return (
    <div className="holo" key={show.id}>
      <div className="holo-panel">
        <div className="holo-head">
          <span className="holo-title">{title}</span>
          <button className="holo-close" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <div className="holo-body">
          {info?.text && (
            <p className="holo-info">
              {info.text}
              {info.link && <a href={info.link} target="_blank" rel="noreferrer"> Wikipedia ↗</a>}
            </p>
          )}
          <div className={`holo-grid ${labelled ? 'labelled' : ''}`}>
            {cards.map((card, i) => <Card key={i} card={card} index={i} />)}
          </div>
        </div>
      </div>
      <div className="holo-beam" aria-hidden="true" />
    </div>
  )
}
