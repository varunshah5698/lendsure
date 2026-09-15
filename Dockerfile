# LendSure — single-container production image.
# Stage 1 builds the React frontend; stage 2 serves API + static via uvicorn.
# The tracked seed DB (backend/seed/lending.db) + ML model ship inside the
# image; the live DB is created from the seed at boot and never committed.

# ---------- Stage 1: frontend ----------
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
# Build to an absolute dir (config points at ../backend/static for local dev).
RUN npx vite build --outDir /app-static

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LENDSURE_ENV=production \
    LENDSURE_DEMO_OTP=0
WORKDIR /srv/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# Fresh production frontend (overwrites the dev build in backend/static).
COPY --from=web /app-static ./static
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/health', timeout=3)"
# Render (and most PaaS) inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "python -m uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
