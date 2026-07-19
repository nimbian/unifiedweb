import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

// During local dev, proxy the API to the backends so the SPA shares their origin
// (no CORS, cookies flow). In production the reverse proxy does this. Two rules,
// matched in order: /api/arena -> the arena server (strip the /arena segment to
// its native /api/*), everything else /api -> the portal backend.
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: {
    port: 5173,
    // Hosts allowed to reach the dev server. Vite blocks unknown hosts by
    // default; this is required when the dev server runs behind a reverse proxy
    // on a real domain (e.g. Apache -> localhost:5173).
    allowedHosts: ['new.moorednd.com'],
    proxy: {
      // The arena server hosts /api on its WebSocket app (WS_HOST:WS_PORT, 8765).
      '/api/arena': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api\/arena/, '/api'),
      },
      '/api': {
        target: 'http://127.0.0.1:8080',
        changeOrigin: true,
      },
    },
  },
});
