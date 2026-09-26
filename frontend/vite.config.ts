import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const proxyConfig = {
  '/api': {
    target: process.env.VITE_BACKEND_URL || 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/ws': {
    target: process.env.VITE_WS_URL || 'ws://127.0.0.1:8000',
    ws: true,
  }
};

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: proxyConfig,
  },
  preview: {
    host: '0.0.0.0',
    port: 3000,
    proxy: proxyConfig,
  }
})
