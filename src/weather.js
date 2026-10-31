// The weather where you are, shared by the Weather card and its edge dial. M.I.N.D fetches it (it has a backup when
// one weather service refuses), so the card always looks the same.
import { useEffect, useState } from 'react'

const REFRESH_SECONDS = 60  // (the backend only really asks every 10 minutes)

export function useWeatherNow(online) {
  const [weather, setWeather] = useState(null)

  // If Chrome was already allowed to know the location, use it, silently. Never ask: no popups.
  useEffect(() => {
    if (!navigator.permissions || !navigator.geolocation) return
    navigator.permissions.query({ name: 'geolocation' }).then((permission) => {
      if (permission.state !== 'granted') return
      navigator.geolocation.getCurrentPosition(({ coords }) => {
        fetch('/api/location', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ lat: coords.latitude, lon: coords.longitude, name: '', accuracy: coords.accuracy }),
        })
      }, () => {}, { timeout: 15000, maximumAge: 10 * 60 * 1000 })
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (!online) return undefined
    const load = () => fetch('/api/weather').then((r) => r.json()).then((w) => { if (w && w.temp != null) setWeather(w) }).catch(() => {})
    load()
    const timer = setInterval(load, REFRESH_SECONDS * 1000)
    return () => clearInterval(timer)
  }, [online])

  return weather
}

// Which icon fits the sky right now
export function weatherIcon(weather) {
  const words = (weather?.desc || '').toLowerCase()
  if (/rain|drizzle|shower|storm|thunder/.test(words)) return 'rain'
  if (/cloud|overcast|fog|mist|haze/.test(words)) return 'cloud'
  return 'sun'
}
