"""
Fact-Checker Agent (AGENT-03).

This agent runs after each pair of debater speeches within a sub-round. It
extracts specific, verifiable claims from both sides and checks them against the
ChromaDB evidence corpus, producing a visible fact-check report that appears in
the debate timeline.

The verification logic delegates to the existing `debate.verifier` module, which
already handles retrieval, entailment (Groq / local / lexical), refutation
confirmation, and grounding reports. This agent wraps that pipeline with:

  1. Claim extraction — an LLM call that pulls out cited specifics from prose.
  2. Per-side verification — runs `verify_claims` on each side's extracted claims.
  3. A structured report formatted for the WebSocket / UI.

The agent is intentionally lightweight: it should not slow down the debate
noticeably, so claim extraction is limited to at most 5 claims per side per
sub-round, and the whole pipeline is wrapped in a try/except that degrades
gracefully to an empty report.
"""

import asyncio
import json
import logging
import os
import re
from typing import Any

from dotenv import load_dotenv

import config
from llm_retry import groq_call
from debate.verifier import verify_claims, ClaimVerdict

logger = logging.getLogger("argus.fact_checker")

_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(_here), ".env"), override=True)


# ── Claim extraction prompt ─────────────────────────────────────────────────

EXTRACT_CLAIMS_PROMPT = """You extract verifiable factual claims from debate speeches.

A "verifiable claim" is a statement that cites a specific: person, date, number,
event, place, law, study, or named work. Opinions, assertions of value ("X is
better"), and vague gestures ("studies show", "history demonstrates") are NOT
verifiable claims.

From the text below, extract up to 5 specific, verifiable factual claims.
Return ONLY a JSON array of strings. If there are no verifiable claims, return [].

Example output: ["Athens introduced jury pay under Pericles around 461 BC", "The rent control study by Diamond et al. (2019) found a 15% reduction"]"""


def _strip_json_array(raw: str) -> list[str]:
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    raw = raw.replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        parsed = json.loads(raw[start:end + 1])
        return [str(c).strip() for c in parsed if isinstance(c, str) and c.strip()]
    except Exception:
        return []


async def _extract_claims(text: str) -> list[str]:
    """Pull verifiable claims out of a speech using the NLI model."""
    if not text or len(text.strip()) < 30:
        return []

    from agents.judge_agent import groq_client

    try:
        response = await groq_call(
            groq_client.chat.completions.create,
            model=config.NLI_MODEL,
            messages=[
                {"role": "system", "content": EXTRACT_CLAIMS_PROMPT},
                {"role": "user", "content": f"SPEECH:\n{text}\n\nReturn ONLY the JSON array."},
            ],
            max_tokens=400,
            temperature=0,
        )
        return _strip_json_array(response.choices[0].message.content)[:5]
    except Exception as e:
        logger.warning(f"Claim extraction failed, returning empty: {e}")
        return []


# ── Main fact-check pipeline ─────────────────────────────────────────────────

def _verdict_summary(v: ClaimVerdict) -> dict:
    """Format a single claim verdict for the WebSocket payload."""
    return {
        "claim": v.claim,
        "label": v.label,
        "confidence": round(v.confidence, 2),
    }


async def fact_check_speeches(
    pro_text: str,
    con_text: str,
    round_num: int,
    sub_round: int,
    syn_text: str | None = None,
) -> dict[str, Any]:
    """
    Run the fact-checker on speeches from PRO, CON, and optionally SYN (AGENT-03).

    Returns a structured report suitable for sending over the WebSocket:
    {
        "round": int,
        "sub_round": int,
        "pro": { "claims_checked": int, "supported": int, "refuted": int, "nei": int, "verdicts": [...] },
        "con": { "claims_checked": int, "supported": int, "refuted": int, "nei": int, "verdicts": [...] },
        "syn": { "claims_checked": int, "supported": int, "refuted": int, "nei": int, "verdicts": [...] },
        "summary": str,
    }
    """
    try:
        # Extract claims from all sides concurrently
        extraction_tasks = [_extract_claims(pro_text), _extract_claims(con_text)]
        if syn_text:
            extraction_tasks.append(_extract_claims(syn_text))

        extracted = await asyncio.gather(*extraction_tasks)
        pro_claims = extracted[0]
        con_claims = extracted[1]
        syn_claims = extracted[2] if syn_text else []

        # Verify claims against the corpus concurrently
        v_tasks = [
            verify_claims(pro_claims) if pro_claims else asyncio.sleep(0, result=[]),
            verify_claims(con_claims) if con_claims else asyncio.sleep(0, result=[]),
        ]
        if syn_text:
            v_tasks.append(verify_claims(syn_claims) if syn_claims else asyncio.sleep(0, result=[]))

        v_results = await asyncio.gather(*v_tasks)
        pro_verdicts = v_results[0]
        con_verdicts = v_results[1]
        syn_verdicts = v_results[2] if syn_text else []

        def _side_report(verdicts: list[ClaimVerdict]) -> dict:
            supported = sum(1 for v in verdicts if v.label == "SUPPORTED")
            refuted = sum(1 for v in verdicts if v.label == "REFUTED")
            nei = sum(1 for v in verdicts if v.label == "NEI")
            return {
                "claims_checked": len(verdicts),
                "supported": supported,
                "refuted": refuted,
                "nei": nei,
                "verdicts": [_verdict_summary(v) for v in verdicts],
            }

        pro_report = _side_report(pro_verdicts)
        con_report = _side_report(con_verdicts)
        syn_report = _side_report(syn_verdicts)

        # Build a human-readable one-liner summary
        parts = []
        total_checked = pro_report["claims_checked"] + con_report["claims_checked"] + syn_report["claims_checked"]
        total_supported = pro_report["supported"] + con_report["supported"] + syn_report["supported"]
        total_refuted = pro_report["refuted"] + con_report["refuted"] + syn_report["refuted"]

        if total_checked == 0:
            summary = "No verifiable claims detected in this exchange."
        else:
            parts.append(f"{total_checked} claims checked across 3 debaters" if syn_text else f"{total_checked} claims checked")
            if total_supported:
                parts.append(f"{total_supported} supported")
            if total_refuted:
                parts.append(f"{total_refuted} refuted")
            summary = " · ".join(parts)

        return {
            "round": round_num,
            "sub_round": sub_round,
            "pro": pro_report,
            "con": con_report,
            "syn": syn_report,
            "summary": summary,
        }

    except Exception as e:
        logger.warning(f"Fact-check pipeline failed, returning empty report: {e}")
        empty_side = {"claims_checked": 0, "supported": 0, "refuted": 0, "nei": 0, "verdicts": []}
        return {
            "round": round_num,
            "sub_round": sub_round,
            "pro": empty_side,
            "con": empty_side,
            "syn": empty_side,
            "summary": "Fact-check unavailable for this exchange.",
        }
