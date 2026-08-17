import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // The components call the API with relative paths (`/api/...`), and Vite
    // forwards those to Flask. That keeps the backend host out of the frontend
    // source entirely: the browser only ever talks to whatever origin served the
    // page, so the app works unchanged from the VM, from another machine on the
    // network, or through a single forwarded port.
    //
    // BACKEND_PORT is honoured so this stays in step with the run scripts.
    proxy: {
      '/api': {
        target: `http://localhost:${process.env.BACKEND_PORT ?? 5000}`,
        changeOrigin: true,
      },
    },
  },
})
