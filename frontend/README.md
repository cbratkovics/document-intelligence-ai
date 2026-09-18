# Demo frontend

Next.js (App Router, TypeScript, Tailwind) single page for the public demo of
[document-intelligence-ai](https://github.com/cbratkovics/document-intelligence-ai).
The browser never calls the API directly: route handlers under `app/api/*`
proxy to it and attach the API key from server-side environment variables.

Only five upstream routes are exposed: health, search, upload, document list,
and document chunks. Replace, delete, summary, judge, and stats are not
reachable through this app.

## Environment

| Variable | Where | Purpose |
|---|---|---|
| `API_BASE_URL` | server only | Base URL of the API, for example the Hugging Face Space URL |
| `API_KEY` | server only | The same value as the API's `API_KEY` secret |

No `NEXT_PUBLIC_*` variables exist. Copy `.env.example` to `.env.local` for
local development.

## Run locally

```bash
npm install
cp .env.example .env.local   # then edit API_BASE_URL and API_KEY
npm run dev                  # http://localhost:3000
```

The API must be running and reachable at `API_BASE_URL` with the same key.
See the repository README for the matching API command.

## Vercel

- Root Directory: `frontend`
- Framework preset: Next.js
- Environment variables: `API_BASE_URL`, `API_KEY` (production and preview)

Nothing else needs configuring. The client IP that Vercel forwards is passed
to the API as `X-Client-IP`, which the API trusts only on requests carrying
the valid key, so per-visitor rate limits apply behind the proxy.

## Behaviour worth knowing

- Uploads are recorded per browser in `sessionStorage`; the document list and
  every search are scoped to the seeded samples plus those ids. Other
  visitors' uploads are never shown.
- Files are checked client-side (type and 4 MB limit) before upload, and
  checked again in the route handler.
- On start the page polls `/api/health` with backoff and shows a "waking"
  state until the API answers, which covers a sleeping Space.

## Checks

```bash
npm run lint
npx tsc --noEmit
npm run build
```
