/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  // Phase 0 homepage tiles link OUT to the existing standalone sites. Set these
  // to the current production URLs; the SPA never hardcodes them. When the pages
  // are ported in-app (Phase 2), the tiles will point at internal routes instead.
  readonly VITE_SATCHEMON_URL: string;
  readonly VITE_DNDBATTLE_URL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
