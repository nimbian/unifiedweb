# Satchemon Frontend (React + Mantine)

SPA for the Satchemon card-collection tracker.

## Stack
React 19 · Vite 6 · TypeScript (strict) · Mantine UI 7 · mantine-datatable ·
TanStack Query 5 · React Router 7 · Axios

## Layout
```
src/
├── api/          # axios client (+ interceptors) and typed API modules
├── components/   # CardsTable, SetTable, ProtectedRoute
├── contexts/     # AuthContext (current user + Discord login)
├── hooks/        # useAuth, useUsers, useCollections, useSets, useDrive
├── layouts/      # MainLayout (Mantine AppShell)
├── pages/        # Users, UserCards, Search, Slideshow, Login, AuthCallback
├── routes/       # AppRoutes
├── types/        # mirrors backend schemas
├── utils/        # CR sort + formatting (ports sets.js)
└── main.tsx
```

## Local dev
```bash
npm install
cp .env.example .env        # VITE_API_BASE_URL=/api
npm run dev                 # http://localhost:5173 (proxies /api -> :8080)
```
Run the backend on :8080 first (Vite proxies `/api` to it).

## Build / checks
```bash
npm run typecheck           # tsc --noEmit, strict mode
npm run build               # -> dist/
```

## Notes
- Access token is held **in memory** (not localStorage); the refresh token is an
  httpOnly cookie. The axios response interceptor performs a single-flight
  refresh on 401 and replays the request.
- Mantine `<Tabs>` replaces the jQuery button wall in `userCards.j2`; expandable
  `mantine-datatable` rows replace the DataTables child-row drill-down.
