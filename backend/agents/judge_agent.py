import os
import re
import json
import httpx
from dotenv import load_dotenv
from groq import AsyncGroq

load_dotenv()

# ── Groq — explanation + final verdict ───────────────────────────────────────
JUDGE_MODEL = os.getenv("JUDGE_MODEL", "llama-3.3-70b-versatile")


def _judge_api_key() -> str:
    key = os.getenv("JUDGE_GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("Set JUDGE_GROQ_API_KEY (or GROQ_API_KEY) in backend/.env")
    return key


groq_client = AsyncGroq(api_key=_judge_api_key(), timeout=45.0)

# ── Fine-tuned 4B (Kaggle FT_JUDGE_URL) — round scoring only ─────────────────
FT_JUDGE_URL = os.getenv("FT_JUDGE_URL", "http://127.0.0.1:8002")
NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}

# ── Nemotron 30B (Kaggle JUDGE_BASE_URL) — verdict/explanation (disabled) ────
# from openai import AsyncOpenAI
#
# nemotron_client = AsyncOpenAI(
#     base_url=os.getenv("JUDGE_BASE_URL", "http://127.0.0.1:8001/v1"),
#     api_key="sk-no-key-required",
# )
# NEMOTRON_MODEL = "unsloth/Nemotron-3-Nano-30B-A3B"
#
# async def _get_explanation_nemotron(topic: str, exchange_text: str, scores: dict) -> str:
#     """Nemotron 30B explains the scores — slow; replaced by Groq."""
#     pro = scores.get("pro_scores", {}).get("total", 0)
#     con = scores.get("con_scores", {}).get("total", 0)
#     winner = scores.get("round_winner", "tie")
#     response = await nemotron_client.chat.completions.create(
#         model=NEMOTRON_MODEL,
#         messages=[
#             {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
#             {"role": "user", "content": (
#                 f"Topic: {topic}\n\n"
#                 f"Exchange:\n{exchange_text}\n\n"
#                 f"Scores — PRO: {pro}/10, CON: {con}/10, Winner: {winner.upper()}\n\n"
#                 f"Explain in 1-2 sentences why these scores make sense."
#             )},
#         ],
#         max_tokens=150,
#         temperature=0.3,
#     )
#     return response.choices[0].message.content.strip()
#
# async def _judge_final_verdict_nemotron(...) -> dict:
#     """Final verdict via Nemotron 30B — slow; replaced by Groq."""
#     ...

EXPLANATION_SYSTEM_PROMPT = """You are a debate analyst. Scores have already been computed by an NLP model.
Your only job: explain WHY these scores make sense in 1-2 sentences using plain English.
Do NOT re-score. Do NOT output JSON. Just explain the reasoning."""

FINAL_VERDICT_SYSTEM_PROMPT = """You are a debate judge. Write in plain, simple English anyone can understand. Return ONLY valid JSON, no markdown.

Schema:
{
  "overall_winner": "pro"|"con"|"tie",
  "pro_total": float,
  "con_total": float,
  "accuracy": {"pro": float, "con": float},
  "score_explanation": {
    "pro": "1 sentence: what did PRO do to earn their score?",
    "con": "1 sentence: what did CON do to earn their score?"
  },
  "winner": {
    "decisive_argument": "The single best point that won the debate. Max 20 words. Must reference an actual argument they made.",
    "points": ["Specific point or argument they made that scored well — max 15 plain words.", "Another specific point they made — max 15 plain words."],
    "strongest_round": int
  },
  "loser": {
    "fatal_weakness": "The main reason they lost. Max 20 plain words. Must reference something they actually failed to do.",
    "missed_points": ["A specific argument they should have made — max 15 plain words.", "Another thing they missed — max 15 plain words."]
  },
  "rounds": [
    {"r": int, "winner": "pro"|"con"|"tie", "margin": float, "swing": "What specific argument decided this round? Max 12 words."}
  ],
  "fallacies": [],
  "verdict": "Exactly 3 plain sentences: (1) who won and why in simple words, (2) what the loser got wrong, (3) the one moment that changed the debate."
}

Rules: Use simple everyday words. Do not invent scores. verdict = exactly 3 sentences. Output JSON only."""

# Groq round scoring (disabled — FT fine-tuned model on Kaggle generates scores)
# ROUND_SCORING_SYSTEM_PROMPT = """..."""
#
# async def _get_groq_round_scores(topic: str, exchange_text: str) -> dict:
#     response = await groq_client.chat.completions.create(
#         model=JUDGE_MODEL,
#         messages=[...],
#         max_tokens=400,
#         temperature=0,
#     )
#     ...


def _clean_response(raw: str) -> str:
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
    raw = raw.replace("```json", "").replace("```", "").strip()
    start = raw.find("{")
    if start == -1:
        return raw
    depth = 0
    for i, ch in enumerate(raw[start:], start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return raw[start:i + 1]
    return raw[start:]


def _format_exchange_for_judge(exchange: list[dict]) -> str:
    lines = []
    current_sub = 0
    sub_labels = {1: "Opening", 2: "Counter", 3: "Justify"}
    for turn in exchange:
        sr = turn["sub_round"]
        if sr != current_sub:
            current_sub = sr
            lines.append(f"-- Sub-round {sr}: {sub_labels.get(sr, str(sr))} --")
        label = "PRO" if turn["speaker"] == "pro" else "CON"
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)


ROUND_SCORING_SYSTEM_PROMPT = """You are a strict and impartial AI debate judge.

Evaluate the ENTIRE round exchange on three criteria per agent:
- Evidence (0.0 to 10.0): Are real-world facts, data, or concrete examples cited?
- Logic (0.0 to 10.0): Is the argument structurally sound?
- Relevance (0.0 to 10.0): Does it address the topic?

Return ONLY a valid JSON object. No markdown. No explanations outside JSON.
Schema:
{
  "pro_scores": { "evidence": float, "logic": float, "relevance": float, "total": float },
  "con_scores": { "evidence": float, "logic": float, "relevance": float, "total": float },
  "round_winner": "pro" | "con" | "tie",
  "reasoning": "1-2 sentences explaining why the round winner prevailed.",
  "fallacy_detected": null | "Name of the fallacy if detected"
}
"""

async def _get_groq_round_scores(topic: str, exchange_text: str) -> dict:
    response = await groq_client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": ROUND_SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": f"Topic: {topic}\n\nExchange:\n{exchange_text}\n\nScore both agents. Return ONLY the JSON object."}
        ],
        max_tokens=600,
        temperature=0,
    )
    raw = _clean_response(response.choices[0].message.content)
    if not raw:
        raise ValueError("Judge returned empty round scores.")
    
    result = json.loads(raw)
    
    # Ensure totals are calculated
    for side in ["pro_scores", "con_scores"]:
        if side in result:
            scores = result[side]
            ev = scores.get("evidence", 0)
            logic = scores.get("logic", 0)
            rel = scores.get("relevance", 0)
            scores["total"] = round((ev + logic + rel) / 3, 1)
            
    return result


async def _get_explanation(topic: str, exchange_text: str, scores: dict) -> str:
    """Groq explains the FT scores in plain English — does NOT score."""
    pro = scores.get("pro_scores", {}).get("total", 0)
    con = scores.get("con_scores", {}).get("total", 0)
    winner = scores.get("round_winner", "tie")

    response = await groq_client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": EXPLANATION_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Exchange:\n{exchange_text}\n\n"
                f"Scores — PRO: {pro}/10, CON: {con}/10, Winner: {winner.upper()}\n\n"
                f"Explain in 1-2 sentences why these scores make sense."
            )},
        ],
        max_tokens=150,
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


async def _get_ft_round_scores(topic: str, exchange_text: str) -> dict | None:
    """Queries the fine-tuned 4B scorer on Kaggle via FT_JUDGE_URL."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{FT_JUDGE_URL.rstrip('/')}/ft-judge",
                json={"topic": topic, "exchange": exchange_text},
                headers=NGROK_HEADERS,
                timeout=12.0
            )
            if resp.status_code == 200:
                result = resp.json()
                if "pro_scores" in result and "con_scores" in result:
                    # Ensure totals are calculated/validated
                    for side in ["pro_scores", "con_scores"]:
                        scores = result[side]
                        ev = scores.get("evidence", 0)
                        logic = scores.get("logic", 0)
                        rel = scores.get("relevance", 0)
                        scores["total"] = round((ev + logic + rel) / 3, 1)
                    return result
    except Exception as e:
        print(f"Kaggle FT scoring attempt failed, falling back to Groq: {e}")
    return None


async def judge_round(
    topic: str,
    round_num: int,
    exchange: list[dict],
) -> dict:
    exchange_text = _format_exchange_for_judge(exchange)

    # Attempt to use the Kaggle fine-tuned scorer if available
    scores = await _get_ft_round_scores(topic, exchange_text)

    # Fallback to Groq if the fine-tuned model is offline or returns invalid response
    if not scores:
        scores = await _get_groq_round_scores(topic, exchange_text)

    return {
        "pro_scores":            scores.get("pro_scores", {}),
        "con_scores":            scores.get("con_scores", {}),
        "round_winner":          scores.get("round_winner", "tie"),
        "reasoning":             scores.get("reasoning", ""),
        "winner_evidence":       "",
        "loser_weakness":        "",
        "fallacy_detected":      scores.get("fallacy_detected"),
        "final_score_out_of_10": {"pro": scores.get("pro_scores", {}).get("total", 0), "con": scores.get("con_scores", {}).get("total", 0)},
    }


async def judge_final_verdict(
    topic: str,
    all_rounds: list[dict],
    pro_arguments: list[str] | None = None,
    con_arguments: list[str] | None = None,
) -> dict:
    pro_total = round(sum(r["pro_scores"]["total"] for r in all_rounds), 1)
    con_total = round(sum(r["con_scores"]["total"] for r in all_rounds), 1)
    max_possible = len(all_rounds) * 10

    rounds_summary = "\n".join([
        f"R{i+1}: PRO={r['pro_scores']['total']} CON={r['con_scores']['total']} "
        f"Winner={r['round_winner'].upper()} — {r['reasoning']}"
        for i, r in enumerate(all_rounds)
    ])

    args_block = ""
    if pro_arguments or con_arguments:
        lines = []
        for i, r in enumerate(all_rounds):
            pro_arg = (pro_arguments or [])[i] if i < len(pro_arguments or []) else ""
            con_arg = (con_arguments or [])[i] if i < len(con_arguments or []) else ""
            if pro_arg:
                lines.append(f"R{i+1} PRO: {pro_arg[:200]}")
            if con_arg:
                lines.append(f"R{i+1} CON: {con_arg[:200]}")
        args_block = "\nKey arguments made:\n" + "\n".join(lines)

    response = await groq_client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": FINAL_VERDICT_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Scores:\n{rounds_summary}"
                f"{args_block}\n\n"
                f"PRO total: {pro_total}/{max_possible} | CON total: {con_total}/{max_possible}\n\n"
                f"Return ONLY the JSON object."
            )},
        ],
        max_tokens=600,
        temperature=0,
    )

    raw = _clean_response(response.choices[0].message.content)

    try:
        result = json.loads(raw)
    except Exception as e:
        print(f"Failed to parse final verdict JSON: {e}. Output was: {raw}")
        overall_winner = "pro" if pro_total > con_total else ("con" if con_total > pro_total else "tie")
        result = {
            "overall_winner": overall_winner,
            "pro_total": pro_total,
            "con_total": con_total,
            "score_explanation": {
                "pro": f"PRO earned {pro_total} total points across {len(all_rounds)} rounds.",
                "con": f"CON earned {con_total} total points across {len(all_rounds)} rounds."
            },
            "winner": {
                "decisive_argument": "Stronger evidence and argument consistency throughout the debate.",
                "points": ["Maintained key arguments across all rounds."],
                "strongest_round": 1
            },
            "loser": {
                "fatal_weakness": "Scored lower across the overall debate rounds.",
                "missed_points": ["Could have addressed opponent counterarguments more directly."]
            },
            "fallacies": [],
            "verdict": f"{overall_winner.upper()} won the debate with {max(pro_total, con_total)} points versus {min(pro_total, con_total)} points. The winning side provided clearer evidence across rounds. Key turning point occurred in the mid-round exchanges."
        }

    result["pro_total"] = pro_total
    result["con_total"] = con_total
    result["accuracy"] = {
        "pro": round((pro_total / max_possible) * 100, 1),
        "con": round((con_total / max_possible) * 100, 1),
    }

    if not result.get("rounds"):
        result["rounds"] = [
            {
                "r": i + 1,
                "winner": r["round_winner"],
                "margin": round(abs(r["pro_scores"]["total"] - r["con_scores"]["total"]), 1),
                "swing": r.get("reasoning", "")[:60],
            }
            for i, r in enumerate(all_rounds)
        ]

    return result
