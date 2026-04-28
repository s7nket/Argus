import os
import re
import json
from openai import AsyncOpenAI

client = AsyncOpenAI(
    base_url=os.getenv("JUDGE_BASE_URL", "http://127.0.0.1:8001/v1"),
    api_key="sk-no-key-required"
)

# ── Fix 3 (tighter prompts kept from previous suggestion, included for completeness) ──

JUDGE_SYSTEM_PROMPT = """You are a strict debate judge. Score PRO and CON across 3 sub-rounds.

Criteria (0–10 each): Evidence, Logic, Relevance. Total = average, 1 decimal.

Return ONLY this JSON, no markdown, no explanation:
{"pro_scores":{"evidence":int,"logic":int,"relevance":int,"total":float},"con_scores":{"evidence":int,"logic":int,"relevance":int,"total":float},"round_winner":"pro"|"con"|"tie","reasoning":"1 sentence.","fallacy_detected":null|"fallacy name"}"""

FINAL_VERDICT_SYSTEM_PROMPT = """You are a strict debate judge delivering a final verdict.

Return ONLY this JSON, no markdown, no explanation:
{"overall_winner":"pro"|"con"|"tie","pro_total":float,"con_total":float,"final_reasoning":"2 sentences."}"""


def _clean_response(raw: str) -> str:
    """Strip <think>...</think> blocks, markdown fences, then extract
    the first complete JSON object via brace counting."""
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
    raw = raw.replace("```json", "").replace("```", "").strip()

    # Extract the first complete {...} object, handling nested braces
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
    # If we never balanced, return whatever we have (will fail json.loads with a clear error)
    return raw[start:]


async def judge_round(
    topic: str,
    round_num: int,
    exchange: list[dict],
) -> dict:
    exchange_block = _format_exchange_for_judge(exchange)

    response = await client.chat.completions.create(
        model="unsloth/Nemotron-3-Nano-30B-A3B",
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Round {round_num} exchange:\n{exchange_block}\n\n"
                f"Return ONLY the JSON object."
            )}
        ],
        max_tokens=500,
        temperature=0,
    )

    raw = _clean_response(response.choices[0].message.content)

    if not raw:
        raise ValueError(f"Judge returned empty response for round {round_num}.")

    return json.loads(raw)


def _format_exchange_for_judge(exchange: list[dict]) -> str:
    """
    Truncates each turn to 300 chars to minimise input tokens while
    preserving enough content for accurate scoring.
    """
    lines = []
    current_sub = 0
    sub_labels = {1: "Opening", 2: "Counter", 3: "Justify"}

    for turn in exchange:
        sr = turn["sub_round"]
        if sr != current_sub:
            current_sub = sr
            lines.append(f"-- Sub-round {sr}: {sub_labels.get(sr, str(sr))} --")

        label = "PRO" if turn["speaker"] == "pro" else "CON"
        text = turn["text"]

        # Fix 6: truncate long turns — judge needs the gist, not every word
        if len(text) > 300:
            text = text[:300].rsplit(" ", 1)[0] + "…"

        lines.append(f"{label}: {text}")

    # single \n instead of \n\n saves tokens
    return "\n".join(lines)


async def judge_final_verdict(
    topic: str,
    all_rounds: list[dict]
) -> dict:
    pro_total = round(sum(r["pro_scores"]["total"] for r in all_rounds), 1)
    con_total = round(sum(r["con_scores"]["total"] for r in all_rounds), 1)

    rounds_summary = "\n".join([
        f"R{i+1}: PRO={r['pro_scores']['total']} CON={r['con_scores']['total']} "
        f"Winner={r['round_winner'].upper()} — {r['reasoning']}"
        for i, r in enumerate(all_rounds)
    ])

    response = await client.chat.completions.create(
        model="unsloth/Nemotron-3-Nano-30B-A3B",
        messages=[
            {"role": "system", "content": FINAL_VERDICT_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Results:\n{rounds_summary}\n\n"
                f"PRO total: {pro_total} | CON total: {con_total}\n\n"
                f"Return ONLY the JSON object."
            )}
        ],
        max_tokens=300,
        temperature=0,
    )

    raw = _clean_response(response.choices[0].message.content)

    if not raw:
        raise ValueError("Judge returned empty final verdict.")

    result = json.loads(raw)
    # Always enforce computed totals (don't trust model arithmetic)
    result["pro_total"] = pro_total
    result["con_total"] = con_total
    return result