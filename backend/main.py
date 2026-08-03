import asyncio
import os
import urllib.request
import urllib.error
import httpx
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from debate.orchestrator import run_debate

from debate.vector_store import get_vector_store

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
    return list_debates(limit=limit, offset=offset)


@app.get("/debates/{debate_id}")
async def debate_detail(debate_id: str):
    from debate.history import get_debate
    record = get_debate(debate_id)
    if record is None:
        return JSONResponse(status_code=404, content={"error": "no such debate"})
    return record


@app.delete("/debates/{debate_id}")
async def debate_delete(debate_id: str):
    from debate.history import delete_debate
    return {"deleted": delete_debate(debate_id)}


@app.get("/judge/logs")
async def judge_log_feed(limit: int = 100):
    """Per-round audit trail across all debates, newest first."""
    from debate.history import judge_logs
    return {"logs": judge_logs(limit=limit)}


NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}


def _ft_judge_probe_urls(ft_url: str) -> list[str]:
    base = ft_url.rstrip("/")
    return [f"{base}/openapi.json", f"{base}/ft-judge"]


def _probe_url_sync(url: str, headers: dict) -> bool:
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=2.5) as response:
            return response.status == 200
    except urllib.error.HTTPError as e:
        # 405/422 prove a real handler is behind the URL and only rejected the
        # method or payload. 404 does NOT: an offline ngrok tunnel serves its own
        # 404 page, so accepting it reported the Kaggle scorer as online while
        # every scoring call was silently falling back to Groq.
        if e.code in (200, 405, 422):
            return True
        return False
    except Exception:
        return False


async def _probe_ft_judge_once(ft_url: str) -> bool:
    loop = asyncio.get_event_loop()
    for url in _ft_judge_probe_urls(ft_url):
        online = await loop.run_in_executor(None, _probe_url_sync, url, NGROK_HEADERS)
        if online:
            return True
    return False


async def _is_ft_judge_online(ft_url: str, attempts: int = 2) -> bool:
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
    Checks Kaggle FT scorer (FT_JUDGE_URL) and Groq key for verdict generation.
    Returns: { "status": "online" | "offline", "url": str, "scorer": str, "verdict": str }
    """
    load_dotenv(override=True)
    ft_url = os.getenv("FT_JUDGE_URL", "http://127.0.0.1:8002")
    groq_key = os.getenv("JUDGE_GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    model = os.getenv("JUDGE_MODEL", "llama-3.3-70b-versatile")

    ft_online = await _is_ft_judge_online(ft_url)
    groq_configured = bool(groq_key)
    # The application is operational if Groq or Kaggle FT scorer is online
    online = groq_configured or ft_online

    result = {
        "status": "online" if online else "offline",
        "url": ft_url,
        "scorer": "kaggle-ft" if ft_online else "groq-fallback",
        "verdict": "groq",
        "model": model,
        "ft_online": ft_online,
        "groq_configured": groq_configured,
    }
    if not groq_configured and not ft_online:
        result["reason"] = "Neither Kaggle FT judge (FT_JUDGE_URL) nor JUDGE_GROQ_API_KEY is available in backend/.env"
    elif not ft_online:
        result["note"] = "Kaggle FT scorer offline — using Groq fallback for round scoring"
    return result


@app.websocket("/ws/debate")
async def debate_websocket(websocket: WebSocket):
    await websocket.accept()
    try:
        data = await websocket.receive_json()
        topic = data.get("topic", "").strip()
        rounds = int(data.get("rounds", 3))

        if not topic:
            await websocket.send_json({"type": "error", "message": "Topic is required."})
            await websocket.close()
            return

        await run_debate(websocket, topic, rounds)

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
