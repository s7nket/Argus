import os
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

@app.get("/judge/health")
async def judge_health():
    """
    Pings the Kaggle llama-server to check if the judge is alive.
    Returns: { "status": "online" | "offline", "url": str }
    """
    judge_url = os.getenv("JUDGE_BASE_URL", "http://127.0.0.1:8001/v1")
    health_url = judge_url.replace("/v1", "") + "/health"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(health_url)
            if resp.status_code == 200:
                return {"status": "online", "url": judge_url}
    except Exception:
        pass
    return {"status": "offline", "url": judge_url}


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
