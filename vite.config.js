import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // While developing with "npm run dev", send /api calls to the Python backend
    proxy: { '/api': 'http://127.0.0.1:8000' },
  },
})
