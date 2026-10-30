// A book page on the HUD (apps.read_book): the text, page x of y, and ‹ › to turn pages.
// The arrow keys turn pages too, and so does your voice ("Mind, next page").
import { useEffect } from 'react'

function turn(step) {
  fetch('/api/book', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ step }),
  })
}

export default function BookReader({ show }) {
  useEffect(() => {
    function key(event) {
      if (event.target.closest('input, textarea')) return  // (typing a command, not reading)
      if (event.key === 'ArrowRight') turn(1)
      if (event.key === 'ArrowLeft') turn(-1)
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])

  return (
    <div className="book">
      {show.author && <p className="book-author">by {show.author}</p>}
      <div className="book-page" key={show.page}>
        {show.text.split('\n\n').map((para, i) => <p key={i}>{para}</p>)}
      </div>
      <div className="book-nav">
        <button onClick={() => turn(-1)} disabled={show.page <= 1} aria-label="Previous page">‹</button>
        <span>Page {show.page} of {show.pages}</span>
        <button onClick={() => turn(1)} disabled={show.page >= show.pages} aria-label="Next page">›</button>
      </div>
    </div>
  )
}
