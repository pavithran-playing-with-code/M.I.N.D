import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Mini from './components/Mini.jsx'
import './App.css'

// http://localhost:8000/?mini is the small floating window; anything else is the full HUD
const isMini = new URLSearchParams(window.location.search).has('mini')

createRoot(document.getElementById('root')).render(
  <StrictMode>
    {isMini ? <Mini /> : <App />}
  </StrictMode>,
)
