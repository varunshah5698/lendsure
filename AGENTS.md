# LendSure — Base44 Dev Environment

## What this is
Full-stack AI lending-intelligence app: FastAPI + SQLite backend, React 19 + Vite 8 frontend.
The backend serves the API on port 8000; the Vite dev server serves the frontend on port 3000
and proxies `/api/*` to the backend (single-origin wiring — no CORS issues for the browser).

## Running
```bash
docker compose -f docker-compose.base44.yml up -d --build
```
- Frontend (preview): http://localhost:3000
- Backend API: http://localhost:8000/api/health
- API docs: http://localhost:8000/docs

## Services
- **backend** — `python:3.12-slim`, bind-mounted at `/app/backend`, uvicorn with `--reload`.
  Dependencies install into a named volume (`backend-venv`) on first boot (~2 min).
  Seed DB (`backend/seed/lending.db`) auto-copies to `backend/lending.db` on first boot.
  Pre-trained ML models ship in `backend/models/`.
- **web** — `node:20-slim`, bind-mounted at `/app/frontend`, Vite dev server with HMR.
  `node_modules` in a named volume. Depends on backend healthcheck.

## Vite config
`frontend/vite.config.js` uses `mode` to set `base`: `/` in dev (BrowserRouter root),
`/static/` in production builds. Proxy target is `process.env.API_PROXY_TARGET`
(defaults to `http://127.0.0.1:8000`, set to `http://backend:8000` in compose).

## Auth / OTP
Demo OTP mode is ON (`LENDSURE_DEMO_OTP=1`): phone and email OTP codes are returned
in the API response and printed to server logs. Guest login also available.
To use real SMS/email OTP, provide Twilio/SMTP credentials via the Base44 secrets dashboard.

## External services (all optional in demo mode)
| Secret | Purpose | Without it |
|---|---|---|
| `LLM_API_KEY` | AI Recovery Assistant (Groq) | Assistant returns 503 |
| `TWILIO_*` (3 keys) | Real SMS OTP | Demo mode shows codes on screen |
| `LENDSURE_SMTP_*` / `SENDGRID_API_KEY` | Email OTP | Demo mode shows codes on screen |
| `NEWS_API_KEY` | Live market headlines | Seeded data used |

## Verifying it works
1. `docker compose -f docker-compose.base44.yml ps` — both services healthy
2. `curl -s localhost:8000/api/health` — returns `{"ok": true, ...}`
3. `curl -s localhost:3000` — returns the Vite-served React app HTML
4. Open the preview, use Guest login or phone OTP (code shown on screen in demo mode)

## Tests
```bash
docker compose -f docker-compose.base44.yml exec backend /app/venv/bin/python -m pytest tests/ -x
```
