"""
Debate persistence.

Nothing was stored. A debate existed only in the WebSocket stream that produced
it, so closing the tab destroyed several minutes of generation, every round
audit, and the grounding evidence behind each score — the material the UI's
DEBATE HISTORY and JUDGE LOGS views exist to show, and the material a paper
draws its examples from.

One JSON file per debate under data/debates, plus a lazily rebuilt index. A
directory of files is deliberate: debates are written once and read whole, they
need to survive a corrupt neighbour, and a single index file that a crash can
truncate would take every record with it.

Turns are also pushed into the ChromaDB history collection, which
add_debate_turn() has always supported and nothing has ever called. That is what
makes cross-debate retrieval possible later.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import config

logger = logging.getLogger("argus.history")

STORE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "debates")
INDEX = os.path.join(STORE, "_index.json")


def _ensure() -> None:
    os.makedirs(STORE, exist_ok=True)


def new_debate_id() -> str:
    """Sortable by construction, so the index falls into chronological order."""
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"


def save_debate(record: dict) -> str | None:
    """
    Persist one completed debate. Never raises.

    A failure here must not take down a debate that already succeeded — the user
    has their result on screen either way, and losing the archive is strictly
    better than losing the run.
    """
    try:
        _ensure()
        debate_id = record.get("id") or new_debate_id()
        record["id"] = debate_id
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())

        with open(os.path.join(STORE, f"{debate_id}.json"), "w", encoding="utf-8") as f:
            json.dump(record, f, indent=1, ensure_ascii=False)

        _append_index(_summarise(record))
        _index_turns(record)
        return debate_id
    except Exception as e:
        logger.warning(f"failed to save debate: {type(e).__name__}: {e}")
        return None


def _summarise(record: dict) -> dict:
    """The row the history list renders — enough to display without opening the file."""
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


def _append_index(summary: dict) -> None:
    index = _read_index()
    index = [row for row in index if row.get("id") != summary["id"]]
    index.insert(0, summary)              # newest first
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)


def _read_index() -> list[dict]:
    if not os.path.exists(INDEX):
        return []
    try:
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _index_turns(record: dict) -> None:
    """
    Push each turn into the ChromaDB history collection.

    Best-effort: the debate is already on disk, and a vector-store hiccup should
    not be able to lose it.
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


# ── Reads ────────────────────────────────────────────────────────────────────

def list_debates(limit: int = 50, offset: int = 0) -> dict:
    index = _read_index()
    if not index and os.path.isdir(STORE):
        index = _rebuild_index()
    return {"total": len(index), "debates": index[offset:offset + limit]}


def get_debate(debate_id: str) -> dict | None:
    # Guard against traversal: ids are generated, but this is a path built from
    # a URL parameter and must not be able to reach outside the store.
    if not debate_id or "/" in debate_id or "\\" in debate_id or ".." in debate_id:
        return None
    path = os.path.join(STORE, f"{debate_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def judge_logs(limit: int = 100) -> list[dict]:
    """
    Flatten every round's audit trail into one reverse-chronological feed.

    This is the JUDGE LOGS view: which scorer ran, what grounding it found, how
    far the two blind passes disagreed, and what penalties applied. Per round
    rather than per debate, because that is the level scoring decisions are
    actually made at.
    """
    out: list[dict] = []
    for row in _read_index():
        record = get_debate(row["id"])
        if not record:
            continue
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
                return out
    return out


def _rebuild_index() -> list[dict]:
    """Reconstruct the index from the stored files when it is missing or corrupt."""
    rows = []
    for name in sorted(os.listdir(STORE), reverse=True):
        if not name.endswith(".json") or name.startswith("_"):
            continue
        record = get_debate(name[:-5])
        if record:
            try:
                rows.append(_summarise(record))
            except Exception:
                continue
    if rows:
        with open(INDEX, "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=1, ensure_ascii=False)
    return rows


def delete_debate(debate_id: str) -> bool:
    record = get_debate(debate_id)
    if record is None:
        return False
    try:
        os.remove(os.path.join(STORE, f"{debate_id}.json"))
    except Exception:
        return False
    index = [r for r in _read_index() if r.get("id") != debate_id]
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=1, ensure_ascii=False)
    return True
