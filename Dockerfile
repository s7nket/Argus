# ARGUS — one image serving the API and the built frontend.
#
# Same origin for both halves: no CORS to configure, one URL to share, and the
# WebSocket inherits the page's TLS scheme instead of needing its own host.
#
# Targets Hugging Face Spaces (Docker SDK), which runs as UID 1000 on port 7860,
# but nothing here is Spaces-specific — any Docker host works.

# ── Stage 1: build the frontend ──────────────────────────────────────────────
FROM node:20-slim AS frontend

WORKDIR /build
# Copy manifests first so the dependency layer survives source-only changes.
COPY package.json package-lock.json* ./
RUN npm ci --no-audit --no-fund || npm install --no-audit --no-fund

COPY index.html vite.config.ts tsconfig*.json ./
COPY src ./src
RUN npm run build


# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/app/.cache \
    # ChromaDB's default embedder downloads a model on first use; without a
    # writable cache it fails on hosts that mount the app read-only.
    SENTENCE_TRANSFORMERS_HOME=/app/.cache

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY --from=frontend /build/dist ./dist

# Spaces runs containers as a non-root user; ChromaDB and the debate archive
# both need to write, so hand ownership over rather than relying on world-write.
RUN mkdir -p /app/backend/chroma_db /app/backend/data/debates /app/.cache \
    && chmod -R 777 /app/backend/chroma_db /app/backend/data /app/.cache

# Build the verification corpus into the image rather than on first request.
# Retrieval grounding is the point of the system, and an empty corpus silently
# degrades every score — the ceiling becomes a no-op and coverage reads 0.
# Non-fatal on purpose: a Wikipedia hiccup should not fail a deploy, and the
# 11-document seed corpus still boots a working app.
RUN cd backend && python -m debate.build_corpus \
    || echo "[build] corpus fetch failed — falling back to the seed corpus"

RUN chmod -R 777 /app/backend/chroma_db

EXPOSE 7860

# PORT is respected so the same image runs on Spaces (7860), Render, and Koyeb
# without a rebuild.
CMD ["sh", "-c", "cd backend && uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}"]
