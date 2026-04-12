import asyncio
from fastapi import WebSocket
from agents.pro_agent import generate_pro_argument
from agents.con_agent import generate_con_argument
from agents.rebuttal_agent import generate_pro_rebuttal, generate_con_rebuttal
from agents.judge_agent import judge_round, judge_final_verdict


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
# ──────────────────────────────────────────────────────────────────────────────

SUB_ROUND_LABELS = {
    1: "Opening",
    2: "Counter",
    3: "Justify",
}


async def run_debate(websocket: WebSocket, topic: str, rounds: int = 3):
    await websocket.send_json({
        "type": "debate_start",
        "topic": topic,
        "rounds": rounds
    })

    # History of full main-round exchanges accumulated across rounds
    pro_history: list[str] = []   # PRO opening arguments from completed rounds
    con_history: list[str] = []   # CON opening arguments from completed rounds
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
        pro_open = await generate_pro_argument(
            topic=topic,
            round_num=round_num,
            pro_history=pro_history,
            con_history=con_history
        )
        exchange.append({"speaker": "pro", "sub_round": 1, "text": pro_open})
        await websocket.send_json({
            "type": "pro_argument",
            "round": round_num,
            "sub_round": 1,
            "text": pro_open
        })

        await asyncio.sleep(0.4)

        # CON responds to PRO's opening
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 1
        })
        con_open = await generate_con_argument(
            topic=topic,
            round_num=round_num,
            current_pro_argument=pro_open,
            pro_history=pro_history,
            con_history=con_history
        )
        exchange.append({"speaker": "con", "sub_round": 1, "text": con_open})
        await websocket.send_json({
            "type": "con_argument",
            "round": round_num,
            "sub_round": 1,
            "text": con_open
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
        pro_counter = await generate_pro_rebuttal(
            topic=topic,
            round_num=round_num,
            sub_round=2,
            exchange_so_far=exchange
        )
        exchange.append({"speaker": "pro", "sub_round": 2, "text": pro_counter})
        await websocket.send_json({
            "type": "pro_argument",
            "round": round_num,
            "sub_round": 2,
            "text": pro_counter
        })

        await asyncio.sleep(0.4)

        # CON doubles down against PRO's counter
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 2
        })
        con_counter = await generate_con_rebuttal(
            topic=topic,
            round_num=round_num,
            sub_round=2,
            exchange_so_far=exchange
        )
        exchange.append({"speaker": "con", "sub_round": 2, "text": con_counter})
        await websocket.send_json({
            "type": "con_argument",
            "round": round_num,
            "sub_round": 2,
            "text": con_counter
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
        pro_justify = await generate_pro_rebuttal(
            topic=topic,
            round_num=round_num,
            sub_round=3,
            exchange_so_far=exchange
        )
        exchange.append({"speaker": "pro", "sub_round": 3, "text": pro_justify})
        await websocket.send_json({
            "type": "pro_argument",
            "round": round_num,
            "sub_round": 3,
            "text": pro_justify
        })

        await asyncio.sleep(0.4)

        # CON delivers closing counter-justification
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "con",
            "round": round_num,
            "sub_round": 3
        })
        con_justify = await generate_con_rebuttal(
            topic=topic,
            round_num=round_num,
            sub_round=3,
            exchange_so_far=exchange
        )
        exchange.append({"speaker": "con", "sub_round": 3, "text": con_justify})
        await websocket.send_json({
            "type": "con_argument",
            "round": round_num,
            "sub_round": 3,
            "text": con_justify
        })

        await asyncio.sleep(0.4)

        # ── Judge scores the full round (all 3 sub-rounds) ──────────────────
        await websocket.send_json({
            "type": "agent_typing",
            "agent": "judge",
            "round": round_num,
            "sub_round": 0   # 0 = scoring phase
        })

        verdict = await judge_round(
            topic=topic,
            round_num=round_num,
            exchange=exchange
        )
        all_round_verdicts.append(verdict)

        await websocket.send_json({
            "type": "round_verdict",
            "round": round_num,
            "data": verdict
        })

        # Store opening arguments as cross-round context
        pro_history.append(pro_open)
        con_history.append(con_open)

        await asyncio.sleep(0.4)

    # ── Final verdict after all main rounds ─────────────────────────────────
    await websocket.send_json({
        "type": "agent_typing",
        "agent": "judge",
        "round": rounds + 1,
        "sub_round": 0
    })

    final = await judge_final_verdict(
        topic=topic,
        all_rounds=all_round_verdicts
    )

    await websocket.send_json({
        "type": "final_verdict",
        "data": final
    })

    await websocket.send_json({"type": "debate_end"})
