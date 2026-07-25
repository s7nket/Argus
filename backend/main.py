import asyncio
import os
import urllib.request
import urllib.error
import httpx
from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from debate.orchestrator import run_debate

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "name": "Argus AI Debate Backend",
        "status": "online",
        "health_check": "/judge/health",
        "websocket": "/ws/debate",
        "frontend_url": "http://localhost:5174/"
    }

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
