import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8010',
      // built sphinx output (pages + _static theme assets) — without this,
      // /built/* falls through to the SPA fallback and the "new tab" shows
      // the editor itself instead of the built page
      '/built': 'http://localhost:8010',
    },
  },
})
