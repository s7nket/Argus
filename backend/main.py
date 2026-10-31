import asyncio
import os
import sys
import urllib.request
import urllib.error
import httpx
from dotenv import load_dotenv

# ── Path bootstrap ────────────────────────────────────────────────────────────
# The codebase mixes two import styles:
#   • main.py / orchestrator.py use  `from backend.debate.X`  (absolute from root)
#   • internal modules use           `from config import …`    (relative to backend/)
# Adding both directories satisfies both styles regardless of CWD.
_backend_dir = os.path.dirname(os.path.abspath(__file__))   # …/Argus/backend
_project_root = os.path.dirname(_backend_dir)               # …/Argus
for _p in (_project_root, _backend_dir):
    if _p not in sys.path:
        sys.path.insert(0, _p)

load_dotenv(os.path.join(_backend_dir, ".env"), override=True)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from backend.debate.orchestrator import run_debate

from backend.debate.vector_store import get_vector_store
from backend.debate.history import store_name as history_store_name

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    vs = get_vector_store()
    if vs.is_available:
        seeded = vs.seed_default_knowledge()
        print(f"[VectorDB] ChromaDB ready. Seeded {seeded} evidence documents.")


@app.get("/healthz", include_in_schema=False)
async def healthz():
    """
    Liveness only. Touches nothing.

    This exists because /status was being used as the host's health check, and
    /status calls into ChromaDB for its document count. During a debate the
    retrieval work saturated the instance, /status exceeded the 5-second health
    check budget, and the host killed the container — ending the debate it was
    in the middle of running. A health check must never contend with the work it
    is checking on.
    """
    return {"ok": True}


# Deployed, "/" serves the built single-page app, so the backend status moved to
# its own path. "/" still answers with this payload when no frontend build is
# present, which is the local backend-only workflow.
@app.get("/status")
async def status():
    vs = get_vector_store()
    return {
        "name": "Argus AI Debate Backend",
        "status": "online",
        "health_check": "/judge/health",
        "websocket": "/ws/debate",
        "vector_db": vs.get_stats(),
        # Which archive is live. On a free host the file store is wiped by every
        # restart, so this is the difference between history that survives and
        # history that quietly does not.
        "history_store": history_store_name(),
    }


@app.get("/vector-db/stats")
async def vector_db_stats():
    vs = get_vector_store()
    return vs.get_stats()


@app.get("/vector-db/seed")
async def vector_db_seed():
    vs = get_vector_store()
    count = vs.seed_default_knowledge()
    return {"seeded": count, "stats": vs.get_stats()}


@app.get("/vector-db/query")
async def vector_db_query(q: str, top_k: int = 3):
    vs = get_vector_store()
    evidence = vs.query_evidence(query=q, top_k=top_k)
    rebuttals = vs.query_similar_rebuttals(claim=q, top_k=top_k)
    return {
        "query": q,
        "evidence": evidence,
        "history_matches": rebuttals
    }


# ── Debate history and judge logs ────────────────────────────────────────────
# Backing for the DEBATE HISTORY and JUDGE LOGS views. Debates used to exist only
# in the WebSocket stream that produced them, so closing the tab destroyed the
# result, every round audit, and the grounding evidence behind each score.

@app.get("/debates")
async def debates_list(limit: int = 50, offset: int = 0):
    from debate.history import list_debates
    return await list_debates(limit=limit, offset=offset)


@app.get("/debates/{debate_id}")
async def debate_detail(debate_id: str):
    from debate.history import get_debate
    record = await get_debate(debate_id)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "no such debate"})
    return record


@app.delete("/debates/{debate_id}")
async def debate_delete(debate_id: str):
    from debate.history import delete_debate
    return {"deleted": await delete_debate(debate_id)}


@app.get("/judge/logs")
async def judge_log_feed(limit: int = 100):
    """Per-round audit trail across all debates, newest first."""
    from debate.history import judge_logs
    return {"logs": await judge_logs(limit=limit)}


NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}


def _ft_judge_probe_urls(ft_url: str) -> list[str]:
    base = ft_url.rstrip("/")
    # /health requires the FastAPI app inside the Kaggle notebook to be alive.
    # /openapi.json is served by ngrok itself and would return 200 even when the
    # Kaggle session has expired, causing a false-positive online report.
    return [f"{base}/health"]


def _probe_url_sync(url: str, headers: dict) -> bool:
    try:
        req = urllib.request.Request(url, headers=headers)
        # Fast 2.5s timeout for Kaggle health probe
        with urllib.request.urlopen(req, timeout=2.5) as response:
            if response.status != 200:
                return False
            # Validate the response is JSON, not the ngrok HTML warning page.
            # The warning page also returns HTTP 200 but has Content-Type: text/html.
            content_type = response.headers.get("Content-Type", "")
            if "text/html" in content_type:
                return False
            return True
    except Exception:
        return False


async def _probe_ft_judge_once(ft_url: str) -> bool:
    loop = asyncio.get_event_loop()
    for url in _ft_judge_probe_urls(ft_url):
        online = await loop.run_in_executor(None, _probe_url_sync, url, NGROK_HEADERS)
        if online:
            return True
    return False


async def _is_ft_judge_online(ft_url: str, attempts: int = 1) -> bool:
    """Fast probe check for Kaggle FT scorer."""
    for attempt in range(attempts):
        if await _probe_ft_judge_once(ft_url):
            return True
        if attempt < attempts - 1:
            await asyncio.sleep(0.1)
    return False


# Nemotron health probe (disabled — JUDGE_BASE_URL was for Nemotron 30B verdict)
# def _nemotron_probe_urls(judge_url: str) -> list[str]:
#     base = judge_url.rstrip("/").removesuffix("/v1")
#     return [f"{base}/v1/models", f"{base}/health", f"{judge_url.rstrip('/')}/models"]


@app.get("/judge/health")
async def judge_health():
    """
    Checks Kaggle FT scorer (FT_JUDGE_URL) and Groq fallback judge.
    If Kaggle FT is offline, gracefully reports online under Groq fallback mode.
    """
    load_dotenv(override=True)
    ft_url = os.getenv("FT_JUDGE_URL", "http://127.0.0.1:8002")

    ft_online = await _is_ft_judge_online(ft_url, attempts=1)
    has_groq = bool(os.getenv("JUDGE_GROQ_API_KEY") or os.getenv("GROQ_API_KEY"))
    judge_online = ft_online or has_groq

    result = {
        "status": "online" if judge_online else "offline",
        "mode": "kaggle_ft" if ft_online else ("groq_fallback" if has_groq else "offline"),
        "ft_online": ft_online,
        "groq_fallback": has_groq,
        "model": "ArguScore-4B (FT)" if ft_online else "openai/gpt-oss-120b (Groq)",
        "scorer": "Kaggle Fine-Tuned" if ft_online else "Groq Fallback",
        "url": ft_url,
    }
    if not ft_online:
        if has_groq:
            result["note"] = "Kaggle FT offline — routing judge to Groq fallback"
        else:
            result["note"] = "Neither Kaggle FT nor Groq API keys are available"
    return result



@app.websocket("/ws/debate")
async def debate_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        topic = data.get("topic", "").strip()
        rounds = int(data.get("rounds", 3))
        human_side = data.get("human_side") or None  # 'pro' | 'con' | None

        if not topic:
            await websocket.send_json({"type": "error", "message": "Topic is required."})
            await websocket.close()
            return

        await run_debate(websocket, topic, rounds, human_side=human_side)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass


# ── Frontend ─────────────────────────────────────────────────────────────────
# Deployed, one process serves both halves: same origin, so no CORS to configure
# and no second URL to keep in sync. Mounted last so every API route above wins.
#
# When no build exists — the local `uvicorn` + `npm run dev` workflow — these
# routes simply do not register and "/" falls back to the status payload.

FRONTEND_DIST = os.getenv(
    "FRONTEND_DIST",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist"),
)

if os.path.isdir(FRONTEND_DIST):
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _INDEX = os.path.join(FRONTEND_DIST, "index.html")
    _ASSETS = os.path.join(FRONTEND_DIST, "assets")
    if os.path.isdir(_ASSETS):
        app.mount("/assets", StaticFiles(directory=_ASSETS), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        """
        Serve the SPA, letting react-router own client-side paths.

        A deep link such as /debate-dashboard has no file behind it, so a plain
        static mount would 404 on refresh. Real files are served when they exist;
        everything else returns index.html and the router takes over.
        """
        candidate = os.path.normpath(os.path.join(FRONTEND_DIST, full_path))
        # normpath collapses "..", so confirm the result stayed inside the build.
        if candidate.startswith(FRONTEND_DIST) and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(_INDEX)

    print(f"[frontend] serving build from {FRONTEND_DIST}")
else:
    @app.get("/", include_in_schema=False)
    async def root_no_build():
        return await status()

    print(f"[frontend] no build at {FRONTEND_DIST} — API only")
