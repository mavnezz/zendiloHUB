import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// The server of `npm run dev:server` (ZENDILOHUB_PORT=8095).
const SERVER = 'http://127.0.0.1:8096'

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    // ZENDILOHUB_WEB_HOST=0.0.0.0 makes the dev server reachable from other machines (e.g. a remote dev box).
    host: process.env.ZENDILOHUB_WEB_HOST ?? '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': { target: SERVER, changeOrigin: false },
      '/health': SERVER,
      // MCP and OAuth sit at the paths their protocols fix; /oauth/authorize is a page of the app.
      '/mcp': SERVER,
      '/.well-known': SERVER,
      '/oauth/token': SERVER,
      '/oauth/register': SERVER,
    },
  },
})
