import os
import json
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url=os.getenv("JUDGE_BASE_URL", "http://127.0.0.1:8001/v1"),
    api_key="sk-no-key-required"
)

JUDGE_SYSTEM_PROMPT = """You are JUDGE-0 OMNI, a strict and impartial AI debate judge powered by Nemotron.

Each main round consists of 3 sub-rounds:
  Sub-round 1 — Opening: PRO makes their main argument, CON responds.
  Sub-round 2 — Counter: PRO rebuts CON, CON counters back.
  Sub-round 3 — Justify: PRO justifies, CON delivers a closing counter.

You evaluate the ENTIRE round (all sub-rounds combined) on three criteria per agent:
- Evidence   (0–10): Are real-world facts, data, or concrete examples cited across the sub-rounds?
- Logic      (0–10): Is the argument structurally sound with no logical fallacies?
- Relevance  (0–10): Does the argument directly and consistently address the debate topic?

Total score per agent = average of the three criteria, rounded to 1 decimal place.

<think> through each agent's full performance before scoring. </think>

You MUST respond with ONLY a valid JSON object. No markdown. No explanation outside the JSON. No preamble.

JSON schema for round scoring:
{
  "pro_scores":       { "evidence": int, "logic": int, "relevance": int, "total": float },
  "con_scores":       { "evidence": int, "logic": int, "relevance": int, "total": float },
  "round_winner":     "pro" | "con" | "tie",
  "reasoning":        "1–2 sentences explaining why the round winner prevailed across all sub-rounds.",
  "fallacy_detected": null | "Name of the fallacy if one was detected in either agent's arguments"
}"""

FINAL_VERDICT_SYSTEM_PROMPT = """You are JUDGE-0 OMNI. All rounds are complete. Deliver the final debate verdict.

You MUST respond with ONLY a valid JSON object. No markdown. No preamble.

JSON schema:
{
  "overall_winner":   "pro" | "con" | "tie",
  "pro_total":        float,
  "con_total":        float,
  "final_reasoning":  "2–3 sentences explaining why the overall winner prevailed, referencing specific rounds."
}"""


async def judge_round(
    topic: str,
    round_num: int,
    exchange: list[dict],   # ordered list of {"speaker": "pro"|"con", "sub_round": int, "text": str}
) -> dict:
    """
    exchange: all utterances from all 3 sub-rounds for this main round.
    """
    exchange_block = _format_exchange_for_judge(exchange)

    response = await client.chat.completions.create(
        model="unsloth/Nemotron-3-Nano-30B-A3B",
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user",   "content": (
                f"Debate Topic: {topic}\n\n"
                f"Round {round_num} — Full Exchange (3 sub-rounds):\n\n"
                f"{exchange_block}\n\n"
                f"Score both agents across the entire round. Return ONLY the JSON object."
            )}
        ],
        max_tokens=400,
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()
    return json.loads(raw)


def _format_exchange_for_judge(exchange: list[dict]) -> str:
    lines = []
    current_sub = 0
    sub_labels = {1: "Opening", 2: "Counter", 3: "Justify"}
    for turn in exchange:
        sr = turn["sub_round"]
        if sr != current_sub:
            current_sub = sr
            lines.append(f"--- Sub-round {sr}: {sub_labels.get(sr, str(sr))} ---")
        label = "AGENT-01 (PRO)" if turn["speaker"] == "pro" else "AGENT-02 (CON)"
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)


async def judge_final_verdict(
    topic: str,
    all_rounds: list[dict]
) -> dict:
    """
    all_rounds: list of round scoring dicts returned by judge_round()
    """
    pro_total = round(sum(r["pro_scores"]["total"] for r in all_rounds), 1)
    con_total = round(sum(r["con_scores"]["total"] for r in all_rounds), 1)

    rounds_summary = "\n".join([
        f"Round {i+1}: PRO={r['pro_scores']['total']} CON={r['con_scores']['total']} "
        f"Winner={r['round_winner'].upper()} — {r['reasoning']}"
        for i, r in enumerate(all_rounds)
    ])

    response = await client.chat.completions.create(
        model="unsloth/Nemotron-3-Nano-30B-A3B",
        messages=[
            {"role": "system", "content": FINAL_VERDICT_SYSTEM_PROMPT},
            {"role": "user",   "content": (
                f"Debate Topic: {topic}\n\n"
                f"Round-by-round results:\n{rounds_summary}\n\n"
                f"PRO cumulative score: {pro_total}\n"
                f"CON cumulative score: {con_total}\n\n"
                f"Deliver the final verdict. Return ONLY the JSON object."
            )}
        ],
        max_tokens=300,
        temperature=0.3,
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.replace("```json", "").replace("```", "").strip()

    result = json.loads(raw)
    result["pro_total"] = pro_total
    result["con_total"] = con_total
    return result
