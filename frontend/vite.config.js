// Optional Vite setup for SongForge's frontend.
// The default app is the zero-build ../frontend/index.html served by FastAPI.
// To develop with Vite + hot reload instead:
//   cd frontend && npm install && npm run dev   (proxies /api -> :8000)
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
  build: {
    outDir: 'dist',
  },
})
