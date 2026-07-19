import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev: the vite server proxies /api to the game server so the site is
// single-origin in dev too (WEB_BASE_URL=http://localhost:5173, and the
// Twitch OAuth redirect flows through this proxy).
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8765",
    },
  },
});
