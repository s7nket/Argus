"""
Debate persistence.

Nothing was stored originally. A debate existed only in the WebSocket stream
that produced it, so closing the tab destroyed several minutes of generation,
every round audit, and the grounding evidence behind each score — the material
the DEBATE HISTORY and JUDGE LOGS views exist to show.

Two backends behind one interface:

  MongoDB   when MONGODB_URI is set. Required in deployment: free hosts give the
            container an ephemeral filesystem, so a file-backed archive is wiped
            by every restart, sleep and redeploy. The corpus survives because it
            is baked into the image; runtime output does not.

  Files     otherwise. One JSON file per debate plus a rebuildable index, which
            keeps local development free of any database.

Selection happens once at import. If Mongo is configured but unreachable the
file store takes over rather than failing — losing the archive is bad, losing
the debate that produced it is worse.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone

logger = logging.getLogger("argus.history")

STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "debates")
INDEX = os.path.join(STORE, "_index.json")

MONGODB_URI = os.getenv("MONGODB_URI", "").strip()
MONGODB_DB = os.getenv("MONGODB_DB", "argus")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "debates")


def new_debate_id() -> str:
    """Sortable by construction, so a listing falls into chronological order."""
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def _summarise(record: dict) -> dict:
    """The row a history list renders — enough to display without the full record."""
    final = record.get("final_verdict") or {}
    rounds = record.get("rounds") or []
    confidence = final.get("confidence") or {}
    return {
        "id": record["id"],
        "created_at": record["created_at"],
        "topic": record.get("topic", ""),
        "rounds": len(rounds),
        "winner": final.get("overall_winner"),
        "pro_total": final.get("pro_total"),
        "con_total": final.get("con_total"),
        "margin": final.get("margin"),
        "is_tie": final.get("is_tie"),
        "abstained": confidence.get("abstain"),
        "scorer": (rounds[0].get("audit", {}) or {}).get("scorer") if rounds else None,
        "error": record.get("error"),
    }


def _log_rows(record: dict, out: list, limit: int) -> bool:
    """Flatten one debate's rounds into judge-log rows. True when `limit` is hit."""
    for r in record.get("rounds", []):
        audit = r.get("audit") or {}
        pro_g = audit.get("pro_grounding") or {}
        con_g = audit.get("con_grounding") or {}
        out.append({
            "debate_id": record["id"],
            "created_at": record.get("created_at"),
            "topic": record.get("topic", ""),
            "round": r.get("round"),
            "winner": r.get("round_winner"),
            "pro_total": (r.get("pro_scores") or {}).get("total"),
            "con_total": (r.get("con_scores") or {}).get("total"),
            "scorer": audit.get("scorer"),
            "verification_backend": audit.get("verification_backend"),
            "blind_passes": audit.get("blind_passes"),
            "label_disagreement": audit.get("label_disagreement"),
            "pro_coverage": pro_g.get("coverage"),
            "con_coverage": con_g.get("coverage"),
            "pro_evidence_cited": audit.get("pro_evidence_cited", []),
            "con_evidence_cited": audit.get("con_evidence_cited", []),
            "pro_repetition_penalty": audit.get("pro_repetition_penalty"),
            "con_repetition_penalty": audit.get("con_repetition_penalty"),
            "fallacy": r.get("fallacy_detected"),
            "reasoning": r.get("reasoning", ""),
        })
        if len(out) >= limit:
            return True
    return False


# ── File store ───────────────────────────────────────────────────────────────
# A directory of files rather than one document: debates are written once and
# read whole, and a single index a crash can truncate would take every record
# with it. The index is a convenience and is rebuilt when it goes missing.

class FileStore:
    name = "files"

    def _read_index(self) -> list[dict]:
        if not os.path.exists(INDEX):
            return []
        try:
            with open(INDEX, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_index(self, rows: list[dict]) -> None:
        os.makedirs(STORE, exist_ok=True)
        with open(INDEX, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)

    async def save(self, record: dict) -> str:
        os.makedirs(STORE, exist_ok=True)
        with open(os.path.join(STORE, f"{record['id']}.json"), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=1, ensure_ascii=False)
        rows = [r for r in self._read_index() if r.get("id") != record["id"]]
        rows.insert(0, _summarise(record))
        self._write_index(rows)
        return record["id"]

    async def list_page(self, limit: int, offset: int) -> dict:
        rows = self._read_index() or self._rebuild()
        return {"total": len(rows), "debates": rows[offset:offset + limit]}

    async def get(self, debate_id: str) -> dict | None:
        path = os.path.join(STORE, f"{debate_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    async def logs(self, limit: int) -> list[dict]:
        out: list[dict] = []
        for row in self._read_index():
            record = await self.get(row["id"])
            if record and _log_rows(record, out, limit):
                break
        return out

    async def delete(self, debate_id: str) -> bool:
        path = os.path.join(STORE, f"{debate_id}.json")
        if not os.path.exists(path):
            return False
        try:
            os.remove(path)
        except Exception:
            return False
        self._write_index([r for r in self._read_index() if r.get("id") != debate_id])
        return True

    def _rebuild(self) -> list[dict]:
        if not os.path.isdir(STORE):
            return []
        rows = []
        for name in sorted(os.listdir(STORE), reverse=True):
            if not name.endswith(".json") or name.startswith("_"):
                continue
            try:
                with open(os.path.join(STORE, name), encoding="utf-8") as f:
                    rows.append(_summarise(json.load(f)))
            except Exception:
                continue
        if rows:
            self._write_index(rows)
        return rows


# ── Mongo store ──────────────────────────────────────────────────────────────

class MongoStore:
    name = "mongodb"

    def __init__(self, client):
        self.col = client[MONGODB_DB][MONGODB_COLLECTION]

    async def ensure_indexes(self) -> None:
        # created_at descending backs every listing; id is the lookup key.
        await self.col.create_index("id", unique=True)
        await self.col.create_index([("created_at", -1)])

    async def save(self, record: dict) -> str:
        # Upsert, because a debate is written once mid-run on failure and again
        # at the final verdict — the second write must replace, not duplicate.
        await self.col.replace_one({"id": record["id"]}, record, upsert=True)
        return record["id"]

    async def list_page(self, limit: int, offset: int) -> dict:
        total = await self.col.count_documents({})
        cursor = self.col.find({}, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit)
        return {"total": total, "debates": [_summarise(d) async for d in cursor]}

    async def get(self, debate_id: str) -> dict | None:
        return await self.col.find_one({"id": debate_id}, {"_id": 0})

    async def logs(self, limit: int) -> list[dict]:
        out: list[dict] = []
        cursor = self.col.find({}, {"_id": 0}).sort("created_at", -1)
        async for record in cursor:
            if _log_rows(record, out, limit):
                break
        return out

    async def delete(self, debate_id: str) -> bool:
        result = await self.col.delete_one({"id": debate_id})
        return result.deleted_count > 0


# ── Selection ────────────────────────────────────────────────────────────────

def _make_store():
    if not MONGODB_URI:
        logger.info("MONGODB_URI unset — using the file store")
        return FileStore()
    try:
        from motor.motor_asyncio import AsyncIOMotorClient
        client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
        print(f"[history] MongoDB store: {MONGODB_DB}.{MONGODB_COLLECTION}")
        return MongoStore(client)
    except Exception as e:
        # Configured but unusable. Falling back keeps debates running; failing
        # here would take down the thing the archive exists to record.
        logger.warning(f"MongoDB unavailable ({type(e).__name__}: {e}) — using the file store")
        return FileStore()


_store = _make_store()


def store_name() -> str:
    return _store.name


# ── Public API ───────────────────────────────────────────────────────────────

async def save_debate(record: dict, index_turns: bool = False) -> str | None:
    """
    Persist one debate. Never raises.

    A failure here must not take down a debate that already succeeded — the user
    has their result on screen either way, and losing the archive is strictly
    better than losing the run.

    index_turns is off by default because _index_turns walks EVERY round and
    embeds every turn again. Once the archive started saving after each round
    that became quadratic — a three-round debate embedded 54 turns instead of 18
    — and the embedding work is CPU-bound, so it showed up as health-check
    latency climbing with each round (0.71s, 1.67s, 2.26s locally). Turn
    indexing feeds cross-debate retrieval, which nothing queries yet, so it runs
    once at the end rather than on every snapshot.
    """
    try:
        record.setdefault("id", new_debate_id())
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        await _store.save(record)
        if index_turns:
            await _index_turns(record)
        return record["id"]
    except Exception as e:
        logger.warning(f"failed to save debate: {type(e).__name__}: {e}")
        return None


async def list_debates(limit: int = 50, offset: int = 0) -> dict:
    try:
        return await _store.list_page(limit, offset)
    except Exception as e:
        logger.warning(f"list failed: {type(e).__name__}: {e}")
        return {"total": 0, "debates": []}


async def get_debate(debate_id: str) -> dict | None:
    # Ids are generated, but this one arrives from a URL and the file store
    # builds a path from it.
    if not debate_id or "/" in debate_id or "\\" in debate_id or ".." in debate_id:
        return None
    try:
        return await _store.get(debate_id)
    except Exception as e:
        logger.warning(f"get failed: {type(e).__name__}: {e}")
        return None


async def judge_logs(limit: int = 100) -> list[dict]:
    """Per-round audit trail across debates, newest first."""
    try:
        return await _store.logs(limit)
    except Exception as e:
        logger.warning(f"logs failed: {type(e).__name__}: {e}")
        return []


async def delete_debate(debate_id: str) -> bool:
    if not debate_id or "/" in debate_id or "\\" in debate_id or ".." in debate_id:
        return False
    try:
        return await _store.delete(debate_id)
    except Exception as e:
        logger.warning(f"delete failed: {type(e).__name__}: {e}")
        return False


async def _index_turns(record: dict) -> None:
    """
    Push each turn into the ChromaDB history collection.

    Best-effort and deliberately separate from the archive: the debate is already
    stored, and a vector-store hiccup should not be able to lose it. This is what
    makes cross-debate retrieval possible later.
    """
    try:
        from debate.vector_store import get_vector_store
        vs = get_vector_store()
        if not vs.is_available:
            return
        for r in record.get("rounds", []):
            for turn in r.get("exchange", []):
                vs.add_debate_turn(
                    debate_id=record["id"], topic=record.get("topic", ""),
                    round_num=r.get("round", 0), sub_round=turn.get("sub_round", 0),
                    side=turn.get("speaker", ""), text=turn.get("text", ""),
                )
    except Exception as e:
        logger.info(f"turn indexing skipped: {type(e).__name__}: {e}")
