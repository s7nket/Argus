import asyncio
import re
from fastapi import WebSocket
from agents.pro_agent import generate_pro_argument
from agents.con_agent import generate_con_argument
from agents.rebuttal_agent import generate_pro_rebuttal, generate_con_rebuttal
from agents.judge_agent import judge_round, judge_final_verdict
from debate.topic import parse_topic


# ── WebSocket message types sent to frontend ───────────────────────────────────
#
# { "type": "debate_start",   "topic": str, "rounds": int }
# { "type": "sub_round_start","round": int, "sub_round": int, "label": str }
# { "type": "agent_typing",   "agent": "pro"|"con"|"judge", "round": int, "sub_round": int }
# { "type": "pro_argument",   "round": int, "sub_round": int, "text": str }
# { "type": "con_argument",   "round": int, "sub_round": int, "text": str }
# { "type": "round_verdict",  "round": int, "data": { ...judge_round output } }
# { "type": "final_verdict",  "data": { ...judge_final_verdict output } }
# { "type": "debate_end" }
# { "type": "error",          "message": str }
#
# Each main round has 3 sub-rounds:
#   Sub-round 1 — Opening : PRO makes main argument → CON responds
#   Sub-round 2 — Counter : PRO rebuts CON          → CON doubles down
#   Sub-round 3 — Justify : PRO justifies position  → CON closing counter
#
# History stored across rounds:
#   pro_history / con_history store FULL round summaries (all 3 sub-rounds),
#   not just the opening argument — so agents in later rounds have complete
#   memory of everything said in prior rounds.
# ──────────────────────────────────────────────────────────────────────────────

SUB_ROUND_LABELS = {
    1: "Opening",
    2: "Counter",
    3: "Justify",
}




# POSITION: was missing from the old alternation, so every Counter and Justify
# turn rendered with a raw "POSITION:" label in the UI. The trailing-punctuation
# class after N/A removes the dangling comma that used to leave round 2 and 3
# openings starting mid-sentence with ", as this is the PRO's opening argument".
_LABEL_RE = re.compile(
    r'(?:\bN/?A\b[\s,.;:—–-]*|REBUTTAL:\s*|ARGUMENT:\s*|POSITION:\s*)+',
    flags=re.IGNORECASE,
)
_LEADING_PUNCT_RE = re.compile(r'^[\s,.;:—–-]+')


def clean_text(text: str) -> str:
    if not text:
        return ""
    return _LEADING_PUNCT_RE.sub('', _LABEL_RE.sub('', text)).strip()


async def run_debate(websocket: WebSocket, topic: str, rounds: int = 3):
    # Resolve the topic into two explicit stances BEFORE any agent runs. On a
    # comparative topic ("Athens or Sparta?") the old code told CON to "argue
    # against the topic", so CON attacked Athens and nobody ever argued for Sparta.
    sides = await parse_topic(topic)
    pro_side, con_side = sides["pro_side"], sides["con_side"]

    await websocket.send_json({
        "type": "debate_start",
        "topic": topic,
        "rounds": rounds,
        "resolution": sides.get("resolution", topic),
        "topic_type": sides.get("type", "proposition"),
        "pro_side": pro_side,
        "con_side": con_side,
    })

    # Opening arguments only — kept short to bound agent context growth.
    pro_history: list[str] = []
    con_history: list[str] = []
    # Every utterance, per side — used for the deterministic repetition penalty.
    pro_all_texts: list[str] = []
    con_all_texts: list[str] = []
    all_round_verdicts: list[dict] = []

    for round_num in range(1, rounds + 1):

        # exchange holds all utterances for this main round (all sub-rounds)
        exchange: list[dict] = []

        # ── Sub-round 1: Opening ────────────────────────────────────────────
        await websocket.send_json({
            "type": "sub_round_start",
            "round": round_num,
            "sub_round": 1,
            "label": SUB_ROUND_LABELS[1]
        })

        # PRO opens
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "pro",
            "round": round_num,
            "sub_round": 1
        })
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
            await websocket.send_json({"type": "error", "message": f"PRO agent failed (R{round_num}S1): {e}"})
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

        await asyncio.sleep(0.4)

        # CON responds to PRO's opening
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 1
        })
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
            await websocket.send_json({"type": "error", "message": f"CON agent failed (R{round_num}S1): {e}"})
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

        await asyncio.sleep(0.4)

        # ── Sub-round 2: Counter ────────────────────────────────────────────
        await websocket.send_json({
            "type": "sub_round_start",
            "round": round_num,
            "sub_round": 2,
            "label": SUB_ROUND_LABELS[2]
        })

        # PRO counters CON's opening response
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "pro",
            "round": round_num,
            "sub_round": 2
        })
        try:
            pro_counter, pro_model = await generate_pro_rebuttal(
                topic=topic,
                round_num=round_num,
                sub_round=2,
                exchange_so_far=exchange,
                pro_history=pro_history,
                con_history=con_history,
                pro_side=pro_side,
                con_side=con_side,
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"PRO rebuttal failed (R{round_num}S2): {e}"})
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

        await asyncio.sleep(0.4)

        # CON doubles down against PRO's counter
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 2
        })
        try:
            con_counter, con_model = await generate_con_rebuttal(
                topic=topic,
                round_num=round_num,
                sub_round=2,
                exchange_so_far=exchange,
                pro_history=pro_history,
                con_history=con_history,
                pro_side=pro_side,
                con_side=con_side,
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"CON rebuttal failed (R{round_num}S2): {e}"})
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

        await asyncio.sleep(0.4)

        # ── Sub-round 3: Justify ────────────────────────────────────────────
        await websocket.send_json({
            "type": "sub_round_start",
            "round": round_num,
            "sub_round": 3,
            "label": SUB_ROUND_LABELS[3]
        })

        # PRO justifies their position
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "pro",
            "round": round_num,
            "sub_round": 3
        })
        try:
            pro_justify, pro_model = await generate_pro_rebuttal(
                topic=topic,
                round_num=round_num,
                sub_round=3,
                exchange_so_far=exchange,
                pro_history=pro_history,
                con_history=con_history,
                pro_side=pro_side,
                con_side=con_side,
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"PRO rebuttal failed (R{round_num}S3): {e}"})
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

        await asyncio.sleep(0.4)

        # CON delivers closing counter-justification
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 3
        })
        try:
            con_justify, con_model = await generate_con_rebuttal(
                topic=topic,
                round_num=round_num,
                sub_round=3,
                exchange_so_far=exchange,
                pro_history=pro_history,
                con_history=con_history,
                pro_side=pro_side,
                con_side=con_side,
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"CON rebuttal failed (R{round_num}S3): {e}"})
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

        await asyncio.sleep(0.4)

        # ── Judge scores the full round (all 3 sub-rounds) ──────────────────
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
                # Prior rounds only — this round's turns are appended below, after
                # scoring, so a side is never penalised for repeating itself here.
                prior_pro_texts=list(pro_all_texts),
                prior_con_texts=list(con_all_texts),
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"Judge failed (R{round_num}): {e}"})
            return

        all_round_verdicts.append(verdict)

        await websocket.send_json({
            "type": "round_verdict",
            "round": round_num,
            "data": verdict
        })

        # Store only the opening arguments in the history to prevent the context
        # window from growing too large and increasing agent latency. Sub-rounds 
        # 2 and 3 (rebuttals) are intentionally dropped from historical memory.
        pro_history.append(pro_open)
        con_history.append(con_open)

        # Full per-side text feeds the repetition penalty in later rounds.
        pro_all_texts.extend(t["text"] for t in exchange if t["speaker"] == "pro")
        con_all_texts.extend(t["text"] for t in exchange if t["speaker"] == "con")

        await asyncio.sleep(0.4)

    # ── Final verdict after all main rounds ─────────────────────────────────
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
        )
    except Exception as e:
        await websocket.send_json({"type": "error", "message": f"Final verdict failed: {e}"})
        return

    await websocket.send_json({
        "type": "final_verdict",
        "data": final
    })

    await websocket.send_json({"type": "debate_end"})