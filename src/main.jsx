import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Overlay from './Overlay.jsx'

// ?overlay=1 = Jarvis mode (the see-through desktop HUD in the desktop app); otherwise the normal HUD
const overlay = new URLSearchParams(window.location.search).has('overlay')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {overlay ? <Overlay /> : <App />}
  </StrictMode>,
)
