import asyncio
import json
import re
from fastapi import WebSocket
from backend.agents.pro_agent import generate_pro_argument
from backend.agents.con_agent import generate_con_argument
from backend.agents.syn_agent import generate_syn_argument
from backend.agents.rebuttal_agent import generate_pro_rebuttal, generate_con_rebuttal, generate_syn_rebuttal
from backend.agents.judge_agent import judge_round, judge_final_verdict
from backend.agents.fact_checker_agent import fact_check_speeches
from debate.history import new_debate_id, save_debate
from llm_retry import set_retry_listener
from debate.topic import parse_topic


# ── WebSocket message types sent to frontend ───────────────────────────────────
#
# { "type": "debate_start",   "topic": str, "rounds": int, "pro_side": str, "con_side": str, "syn_side": str }
# { "type": "sub_round_start","round": int, "sub_round": int, "label": str }
# { "type": "agent_typing",   "agent": "pro"|"con"|"syn"|"judge"|"fact_checker", "round": int, "sub_round": int }
# { "type": "pro_argument",   "round": int, "sub_round": int, "text": str, "model": str }
# { "type": "con_argument",   "round": int, "sub_round": int, "text": str, "model": str }
# { "type": "syn_argument",   "round": int, "sub_round": int, "text": str, "model": str }
# { "type": "fact_check",     "round": int, "sub_round": int, "data": { ...fact_check report } }
# { "type": "round_verdict",  "round": int, "data": { ...judge_round output } }
# { "type": "final_verdict",  "data": { ...judge_final_verdict output } }
# { "type": "agent_status",   "agents": [ { "id": str, "name": str, "status": str } ] }
# { "type": "debate_end" }
# { "type": "error",          "message": str }
#
# Each main round has 3 sub-rounds across 3 debating agents:
#   Sub-round 1 — Opening  : PRO opens → CON opens → SYN opens → Fact-checker
#   Sub-round 2 — Rebuttal : PRO counters → CON counters → SYN counters → Fact-checker
#   Sub-round 3 — Justify  : PRO justifies → CON justifies → SYN justifies → Fact-checker
#
# After all 3 sub-rounds, the Judge evaluates and scores PRO, CON, and SYN, picking a round winner.
# At the end of all rounds, the Judge computes totals and declares the overall champion among the 3 debaters.
# ──────────────────────────────────────────────────────────────────────────────

SUB_ROUND_LABELS = {
    1: "Opening",
    2: "Rebuttal",
    3: "Justify",
}

_LABEL_RE = re.compile(
    r'(?:\bN/?A\b[\s,.;:—–-]*|REBUTTAL:\s*|ARGUMENT:\s*|POSITION:\s*)+',
    flags=re.IGNORECASE,
)
_LEADING_PUNCT_RE = re.compile(r'^[\s,.;:—–-]+')


def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<think>.*?(?:</think>|$)', '', text, flags=re.DOTALL)
    return _LEADING_PUNCT_RE.sub('', _LABEL_RE.sub('', text)).strip()


# ── Agent pipeline status helper ───────────────────────────────────────────────
# The full multi-agent suite surfaced in the UI.
AGENT_REGISTRY = [
    {"id": "topic_parser",   "name": "Topic Parser",         "role": "Resolves topic into 3 stances"},
    {"id": "pro",            "name": "AGENT-01 (PRO)",       "role": "Argues affirmative stance"},
    {"id": "con",            "name": "AGENT-02 (CON)",       "role": "Argues negative stance"},
    {"id": "syn",            "name": "AGENT-03 (SYN)",       "role": "Argues synthesis & alternative"},
    {"id": "fact_checker",   "name": "AGENT-04 (Verifier)",  "role": "Checks claims against evidence corpus"},
    {"id": "judge",          "name": "AGENT-05 (Judge)",     "role": "Scores all 3 debaters & delivers verdict"},
    {"id": "conformal",      "name": "Conformal Layer",      "role": "Statistical coverage guarantee"},
]


async def _send_agent_status(websocket: WebSocket, active_id: str | None = None, done_ids: list[str] | None = None):
    """Broadcast the current status of all agents in the pipeline."""
    done_ids = done_ids or []
    agents = []
    for a in AGENT_REGISTRY:
        if a["id"] == active_id:
            status = "active"
        elif a["id"] in done_ids:
            status = "done"
        else:
            status = "idle"
        agents.append({"id": a["id"], "name": a["name"], "role": a["role"], "status": status})
    try:
        await websocket.send_json({"type": "agent_status", "agents": agents})
    except Exception:
        pass


async def run_debate(websocket: WebSocket, topic: str, rounds: int = 2, human_side: str | None = None):
    """
    3-Way Multi-Agent Debate.
    human_side: 'pro' | 'con' | 'syn' | None
      None  → 3 AI debaters
      'pro' → user controls PRO, AI controls CON & SYN
      'con' → user controls CON, AI controls PRO & SYN
      'syn' → user controls SYN, AI controls PRO & CON
    """

    async def get_human_argument(role: str, round_num: int, sub_round: int) -> str:
        """Pause and wait for the human's typed argument over the WebSocket."""
        await websocket.send_json({
            "type": "human_turn",
            "role": role,
            "round": round_num,
            "sub_round": sub_round,
        })
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            if msg.get("type") == "human_argument":
                return msg.get("text", "").strip() or "I support my position."

    async def on_retry(attempt: int, total: int, delay: float, rate_limited: bool) -> None:
        try:
            await websocket.send_json({
                "type": "notice",
                "reason": "rate_limit" if rate_limited else "transient_error",
                "attempt": attempt,
                "of": total,
                "retry_in": round(delay),
                "message": (
                    f"Rate limit reached — waiting {round(delay)}s before retrying "
                    f"(attempt {attempt} of {total})."
                    if rate_limited else
                    f"Upstream hiccup — retrying in {round(delay)}s (attempt {attempt} of {total})."
                ),
            })
        except Exception:
            pass

    set_retry_listener(on_retry)

    await websocket.send_json({"type": "accepted", "topic": topic})

    done_agents: list[str] = []

    # 1. Topic Parser
    await _send_agent_status(websocket, active_id="topic_parser", done_ids=done_agents)

    try:
        sides = await parse_topic(topic)
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Could not start the debate: {e}"})
        return

    pro_side = sides["pro_side"]
    con_side = sides["con_side"]
    syn_side = sides.get("syn_side") or f"A nuanced synthesis and pragmatic alternative provides the best resolution for: {topic}"

    done_agents.append("topic_parser")
    await _send_agent_status(websocket, done_ids=done_agents)

    debate_id = new_debate_id()
    record: dict = {
        "id": debate_id,
        "topic": topic,
        "resolution": sides.get("resolution", topic),
        "topic_type": sides.get("type", "tri-way"),
        "pro_side": pro_side,
        "con_side": con_side,
        "syn_side": syn_side,
        "requested_rounds": rounds,
        "rounds": [],
    }

    async def fail(message: str) -> None:
        record["error"] = message
        await save_debate(record)
        await websocket.send_json({"type": "error", "message": message})

    await websocket.send_json({
        "type": "debate_start",
        "topic": topic,
        "rounds": rounds,
        "debate_id": debate_id,
        "resolution": sides.get("resolution", topic),
        "topic_type": sides.get("type", "tri-way"),
        "pro_side": pro_side,
        "con_side": con_side,
        "syn_side": syn_side,
        "human_side": human_side,
    })

    pro_history: list[str] = []
    con_history: list[str] = []
    syn_history: list[str] = []

    pro_all_texts: list[str] = []
    con_all_texts: list[str] = []
    syn_all_texts: list[str] = []
    all_round_verdicts: list[dict] = []

    for round_num in range(1, rounds + 1):
        exchange: list[dict] = []

        # ── Sub-round 1: Opening ────────────────────────────────────────────
        await websocket.send_json({
            "type": "sub_round_start",
            "round": round_num,
            "sub_round": 1,
            "label": SUB_ROUND_LABELS[1]
        })

        # PRO opens
        await _send_agent_status(websocket, active_id="pro", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "pro",
            "round": round_num,
            "sub_round": 1
        })
        pro_model = "human"
        if human_side == "pro":
            pro_open = await get_human_argument("pro", round_num, 1)
        else:
            try:
                pro_open, pro_model = await generate_pro_argument(
                    topic=topic,
                    round_num=round_num,
                    pro_history=pro_history,
                    con_history=con_history,
                    pro_side=pro_side,
                    con_side=con_side,
                )
            except Exception as e:
                await fail(f"PRO agent failed (R{round_num}S1): {e}")
                return

        pro_open = clean_text(pro_open)
        exchange.append({"speaker": "pro", "sub_round": 1, "text": pro_open})
        await websocket.send_json({
            "type": "pro_argument",
            "round": round_num,
            "sub_round": 1,
            "text": pro_open,
            "model": pro_model
        })

        # CON responds
        await _send_agent_status(websocket, active_id="con", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 1
        })
        con_model = "human"
        if human_side == "con":
            con_open = await get_human_argument("con", round_num, 1)
        else:
            try:
                con_open, con_model = await generate_con_argument(
                    topic=topic,
                    round_num=round_num,
                    current_pro_argument=pro_open,
                    pro_history=pro_history,
                    con_history=con_history,
                    pro_side=pro_side,
                    con_side=con_side,
                )
            except Exception as e:
                await fail(f"CON agent failed (R{round_num}S1): {e}")
                return

        con_open = clean_text(con_open)
        exchange.append({"speaker": "con", "sub_round": 1, "text": con_open})
        await websocket.send_json({
            "type": "con_argument",
            "round": round_num,
            "sub_round": 1,
            "text": con_open,
            "model": con_model
        })

        # SYN speaks (AGENT-03 Opening / Synthesis)
        await _send_agent_status(websocket, active_id="syn", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "syn",
            "round": round_num,
            "sub_round": 1
        })
        syn_model = "human"
        if human_side == "syn":
            syn_open = await get_human_argument("syn", round_num, 1)
        else:
            try:
                syn_open, syn_model = await generate_syn_argument(
                    topic=topic,
                    round_num=round_num,
                    current_pro_argument=pro_open,
                    current_con_argument=con_open,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"SYN agent failed (R{round_num}S1): {e}")
                return

        syn_open = clean_text(syn_open)
        exchange.append({"speaker": "syn", "sub_round": 1, "text": syn_open})
        await websocket.send_json({
            "type": "syn_argument",
            "round": round_num,
            "sub_round": 1,
            "text": syn_open,
            "model": syn_model
        })

        # ── Fact-check sub-round 1 ───────────────────────────────────────────
        await _send_agent_status(websocket, active_id="fact_checker", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "fact_checker",
            "round": round_num,
            "sub_round": 1
        })
        try:
            fc1 = await fact_check_speeches(pro_open, con_open, round_num, 1, syn_text=syn_open)
            await websocket.send_json({"type": "fact_check", "round": round_num, "sub_round": 1, "data": fc1})
        except Exception as e:
            print(f"[fact-checker] Sub-round 1 fact-check failed: {e}", flush=True)

        # ── Sub-round 2: Counter / Rebuttal ─────────────────────────────────
        await websocket.send_json({
            "type": "sub_round_start",
            "round": round_num,
            "sub_round": 2,
            "label": SUB_ROUND_LABELS[2]
        })

        # PRO counters
        await _send_agent_status(websocket, active_id="pro", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "pro",
            "round": round_num,
            "sub_round": 2
        })
        pro_model = "human"
        if human_side == "pro":
            pro_counter = await get_human_argument("pro", round_num, 2)
        else:
            try:
                pro_counter, pro_model = await generate_pro_rebuttal(
                    topic=topic,
                    round_num=round_num,
                    sub_round=2,
                    exchange_so_far=exchange,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"PRO rebuttal failed (R{round_num}S2): {e}")
                return

        pro_counter = clean_text(pro_counter)
        exchange.append({"speaker": "pro", "sub_round": 2, "text": pro_counter})
        await websocket.send_json({
            "type": "pro_argument",
            "round": round_num,
            "sub_round": 2,
            "text": pro_counter,
            "model": pro_model
        })

        # CON counters
        await _send_agent_status(websocket, active_id="con", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 2
        })
        con_model = "human"
        if human_side == "con":
            con_counter = await get_human_argument("con", round_num, 2)
        else:
            try:
                con_counter, con_model = await generate_con_rebuttal(
                    topic=topic,
                    round_num=round_num,
                    sub_round=2,
                    exchange_so_far=exchange,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"CON rebuttal failed (R{round_num}S2): {e}")
                return

        con_counter = clean_text(con_counter)
        exchange.append({"speaker": "con", "sub_round": 2, "text": con_counter})
        await websocket.send_json({
            "type": "con_argument",
            "round": round_num,
            "sub_round": 2,
            "text": con_counter,
            "model": con_model
        })

        # SYN counters
        await _send_agent_status(websocket, active_id="syn", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "syn",
            "round": round_num,
            "sub_round": 2
        })
        syn_model = "human"
        if human_side == "syn":
            syn_counter = await get_human_argument("syn", round_num, 2)
        else:
            try:
                syn_counter, syn_model = await generate_syn_rebuttal(
                    topic=topic,
                    round_num=round_num,
                    sub_round=2,
                    exchange_so_far=exchange,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"SYN rebuttal failed (R{round_num}S2): {e}")
                return

        syn_counter = clean_text(syn_counter)
        exchange.append({"speaker": "syn", "sub_round": 2, "text": syn_counter})
        await websocket.send_json({
            "type": "syn_argument",
            "round": round_num,
            "sub_round": 2,
            "text": syn_counter,
            "model": syn_model
        })

        # ── Fact-check sub-round 2 ───────────────────────────────────────────
        await _send_agent_status(websocket, active_id="fact_checker", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "fact_checker",
            "round": round_num,
            "sub_round": 2
        })
        try:
            fc2 = await fact_check_speeches(pro_counter, con_counter, round_num, 2, syn_text=syn_counter)
            await websocket.send_json({"type": "fact_check", "round": round_num, "sub_round": 2, "data": fc2})
        except Exception as e:
            print(f"[fact-checker] Sub-round 2 fact-check failed: {e}", flush=True)

        # ── Sub-round 3: Justify ────────────────────────────────────────────
        await websocket.send_json({
            "type": "sub_round_start",
            "round": round_num,
            "sub_round": 3,
            "label": SUB_ROUND_LABELS[3]
        })

        # PRO justifies
        await _send_agent_status(websocket, active_id="pro", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "pro",
            "round": round_num,
            "sub_round": 3
        })
        pro_model = "human"
        if human_side == "pro":
            pro_justify = await get_human_argument("pro", round_num, 3)
        else:
            try:
                pro_justify, pro_model = await generate_pro_rebuttal(
                    topic=topic,
                    round_num=round_num,
                    sub_round=3,
                    exchange_so_far=exchange,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"PRO justify failed (R{round_num}S3): {e}")
                return

        pro_justify = clean_text(pro_justify)
        exchange.append({"speaker": "pro", "sub_round": 3, "text": pro_justify})
        await websocket.send_json({
            "type": "pro_argument",
            "round": round_num,
            "sub_round": 3,
            "text": pro_justify,
            "model": pro_model
        })

        # CON justifies
        await _send_agent_status(websocket, active_id="con", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 3
        })
        con_model = "human"
        if human_side == "con":
            con_justify = await get_human_argument("con", round_num, 3)
        else:
            try:
                con_justify, con_model = await generate_con_rebuttal(
                    topic=topic,
                    round_num=round_num,
                    sub_round=3,
                    exchange_so_far=exchange,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"CON justify failed (R{round_num}S3): {e}")
                return

        con_justify = clean_text(con_justify)
        exchange.append({"speaker": "con", "sub_round": 3, "text": con_justify})
        await websocket.send_json({
            "type": "con_argument",
            "round": round_num,
            "sub_round": 3,
            "text": con_justify,
            "model": con_model
        })

        # SYN justifies
        await _send_agent_status(websocket, active_id="syn", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "syn",
            "round": round_num,
            "sub_round": 3
        })
        syn_model = "human"
        if human_side == "syn":
            syn_justify = await get_human_argument("syn", round_num, 3)
        else:
            try:
                syn_justify, syn_model = await generate_syn_rebuttal(
                    topic=topic,
                    round_num=round_num,
                    sub_round=3,
                    exchange_so_far=exchange,
                    pro_history=pro_history,
                    con_history=con_history,
                    syn_history=syn_history,
                    pro_side=pro_side,
                    con_side=con_side,
                    syn_side=syn_side,
                )
            except Exception as e:
                await fail(f"SYN justify failed (R{round_num}S3): {e}")
                return

        syn_justify = clean_text(syn_justify)
        exchange.append({"speaker": "syn", "sub_round": 3, "text": syn_justify})
        await websocket.send_json({
            "type": "syn_argument",
            "round": round_num,
            "sub_round": 3,
            "text": syn_justify,
            "model": syn_model
        })

        # ── Fact-check sub-round 3 ───────────────────────────────────────────
        await _send_agent_status(websocket, active_id="fact_checker", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "fact_checker",
            "round": round_num,
            "sub_round": 3
        })
        try:
            fc3 = await fact_check_speeches(pro_justify, con_justify, round_num, 3, syn_text=syn_justify)
            await websocket.send_json({"type": "fact_check", "round": round_num, "sub_round": 3, "data": fc3})
        except Exception as e:
            print(f"[fact-checker] Sub-round 3 fact-check failed: {e}", flush=True)

        # ── Judge scores the full round (all three debaters) ───────────────
        await _send_agent_status(websocket, active_id="judge", done_ids=done_agents)
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "judge",
            "round": round_num,
            "sub_round": 0
        })

        try:
            verdict = await judge_round(
                topic=sides.get("resolution", topic),
                round_num=round_num,
                exchange=exchange,
                prior_pro_texts=list(pro_all_texts),
                prior_con_texts=list(con_all_texts),
                prior_syn_texts=list(syn_all_texts),
            )
        except Exception as e:
            await fail(f"Judge failed (R{round_num}): {e}")
            return

        all_round_verdicts.append(verdict)

        record["rounds"].append({"round": round_num, "exchange": list(exchange), **verdict})
        await save_debate(record)

        await websocket.send_json({
            "type": "round_verdict",
            "round": round_num,
            "data": verdict
        })

        pro_history.append(pro_open)
        con_history.append(con_open)
        syn_history.append(syn_open)

        pro_all_texts.extend(t["text"] for t in exchange if t["speaker"] == "pro")
        con_all_texts.extend(t["text"] for t in exchange if t["speaker"] == "con")
        syn_all_texts.extend(t["text"] for t in exchange if t["speaker"] == "syn")

    # ── Final verdict after all main rounds ─────────────────────────────────
    done_agents.extend(["pro", "con", "syn", "fact_checker"])
    await _send_agent_status(websocket, active_id="judge", done_ids=done_agents)
    await websocket.send_json({
        "type": "agent_typing",
        "agent": "judge",
        "round": rounds + 1,
        "sub_round": 0
    })

    try:
        final = await judge_final_verdict(
            topic=sides.get("resolution", topic),
            all_rounds=all_round_verdicts,
            pro_arguments=pro_history,
            con_arguments=con_history,
            syn_arguments=syn_history,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        await fail(f"Final verdict failed: {e}")
        return

    record["final_verdict"] = final
    await save_debate(record, index_turns=True)

    await websocket.send_json({
        "type": "final_verdict",
        "data": final
    })

    # All agents are done
    done_agents.extend(["judge", "conformal"])
    await _send_agent_status(websocket, done_ids=done_agents)

    await websocket.send_json({"type": "debate_end"})