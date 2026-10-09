import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// В разработке API и MCP — на uvicorn :8000. Прокси даёт один адрес, поэтому cookie сессии работает без CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': 'http://localhost:8000' },
    fs: { allow: ['..'] }, // дизайн-система лежит рядом, в ../design-system
  },
})
