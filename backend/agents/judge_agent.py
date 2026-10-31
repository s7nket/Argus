import asyncio
import os
import re
import json
import time
import httpx
from typing import Any
from dotenv import load_dotenv
from groq import AsyncGroq
from openai import AsyncOpenAI

import config
from config import (
    BLIND_PASSES,
    NO_EVIDENCE_CAP,
    REPETITION_FREE_RATIO,
    REPETITION_MAX_PENALTY,
    TIE_BAND,
)
from llm_retry import groq_call

# Load .env from the backend directory regardless of CWD
_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(_here), ".env"), override=True)
# Trigger uvicorn reload 3

# ── Judge client — Gemini (preferred) or Groq (fallback) ─────────
_GEMINI_KEY = os.getenv("GEMINI_API_KEY", "").strip()

if _GEMINI_KEY:
    JUDGE_MODEL = os.getenv("JUDGE_MODEL", "gemini-3.6-flash")
    judge_client = AsyncOpenAI(
        api_key=_GEMINI_KEY,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=60.0,
    )
    print(f"[judge] Gemini -> {JUDGE_MODEL}")
else:
    JUDGE_MODEL = os.getenv("JUDGE_GROQ_MODEL", "openai/gpt-oss-120b")
    key = os.getenv("JUDGE_GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
    if not key:
        raise ValueError("Set GEMINI_API_KEY or GROQ_API_KEY in backend/.env")
    judge_client = AsyncGroq(api_key=key, timeout=45.0)
    print(f"[judge] Groq fallback -> {JUDGE_MODEL}")

groq_client = judge_client

# ── Fine-tuned 4B (Kaggle FT_JUDGE_URL) — round scoring only ─────────────────
FT_JUDGE_URL = os.getenv("FT_JUDGE_URL", "http://127.0.0.1:8002")
NGROK_HEADERS = {"ngrok-skip-browser-warning": "true"}

EXPLANATION_SYSTEM_PROMPT = """You are a debate analyst. Scores have already been computed by an NLP model.
Your only job: explain WHY these scores make sense in 1-2 sentences using plain English.
Do NOT re-score. Do NOT output JSON. Just explain the reasoning.
Describe what the debaters actually said. Never repeat a debater's own adjectives about their own case
(such as "evidence-based" or "nuanced") as if it were your finding."""

FINAL_VERDICT_SYSTEM_PROMPT = """You are a debate judge. Write in plain, simple English anyone can understand. Return ONLY valid JSON, no markdown.

Schema:
{
  "score_explanation": {
    "pro": "1 sentence: what did PRO do to earn their score?",
    "con": "1 sentence: what did CON do to earn their score?",
    "syn": "1 sentence: what did SYN do to earn their score?"
  },
  "winner": {
    "decisive_argument": "The single best point that won the debate. Max 20 words. Must reference an actual argument they made.",
    "points": ["Specific point or argument they made that scored well — max 15 plain words.", "Another specific point they made — max 15 plain words."]
  },
  "loser": {
    "fatal_weakness": "The main reason the runners-up fell short. Max 20 plain words. Must reference something they actually failed to do.",
    "missed_points": ["A specific argument they should have made — max 15 plain words.", "Another thing they missed — max 15 plain words."]
  },
  "rounds": [
    {"r": int, "swing": "What specific argument decided this round? Max 12 words."}
  ],
  "verdict": "Exactly 3 plain sentences: (1) who won and why in simple words, (2) what the runner-up got wrong, (3) the one moment that settled the debate."
}

Rules:
- Use simple everyday words. verdict = exactly 3 sentences. Output JSON only.
- The winner, the totals, the per-round winners and the strongest round are ALREADY DECIDED and given to
  you in the user message. Describe them. Do not compute, re-score, or contradict them.
- Never justify a score using a debater's own description of their own case. Cite what they actually cited.
- If the outcome given to you is a TIE, say so plainly instead of naming a winner."""


# ── Blind scoring rubric ─────────────────────────────────────────────────────
# The judge never sees named sides — only DEBATER-X, DEBATER-Y, and DEBATER-Z — and every
# round is scored with labels rotated, so a preference for any label cancels out.
ROUND_SCORING_SYSTEM_PROMPT = """You are a strict, impartial debate judge scoring one round of a multi-agent debate.

The debaters are labelled DEBATER-X, DEBATER-Y, and DEBATER-Z (if present). You are NOT told which stance each one holds. Judge only what is on the page.

STEP 1 — EXTRACT BEFORE YOU SCORE.
For each debater, list the evidence they ACTUALLY cited. Evidence means verifiable specifics:
named people, dates, places, events, numbers, laws, institutions, named works or named sources.

Write each item as a COMPLETE, SELF-CONTAINED STATEMENT that someone could check against a
reference source without having read this debate. A bare fragment is not checkable and must not
be emitted on its own.
  BAD:  "508 BCE"        "Cleisthenes"        "the Agoge"
  GOOD: "Cleisthenes established the Athenian democratic assembly in 508 BCE."
        "The Spartan Agoge was a state-run military education system."

ATTRIBUTE BY RELIANCE, NOT BY MENTION. An item belongs to the debater who used it to support
their OWN case. If a debater names a specific only to deny it, reframe it, or turn it against
its author, it is NOT their evidence and must not appear in their list.

MERGE DUPLICATES. One entry per distinct factual claim.

- A debater describing their own case as "evidence-based", "empirical", "data-driven" or "nuanced"
  is NOT evidence. Ignore all self-description entirely.
- Gesturing at evidence without naming it is NOT evidence. It is an unsupported claim.
- If a debater cited nothing verifiable, return an empty list. Empty lists are common and correct.

STEP 2 — LIST UNSUPPORTED CLAIMS: statements presented as established fact with nothing behind them,
and any claim you can identify as factually false.

STEP 3 — VALIDATE EVERY FALLACY ACCUSATION.
If a debater names a fallacy against an opponent, quote the accused text and decide whether the
label genuinely fits. Naming fallacies is not a virtue and earns no credit by itself. A misapplied
fallacy label is a reasoning error that LOWERS the accuser's logic score.

STEP 4 — SCORE. Use the full range (0-10) for Evidence, Logic, and Relevance.
  Evidence   0-2 pure assertion; 3-4 vague appeals; 5-6 one concrete example; 7-8 multiple specifics; 9-10 precise data/dates/sources.
  Logic      0-2 incoherent; 3-4 asserts without connection; 5-6 valid with unaddressed gaps; 7-8 sound reasoning; 9-10 airtight synthesis.
  Relevance  0-2 ignores topic; 3-4 drifting; 5-6 on topic; 7-8 directly addresses core question; 9-10 laser-focused.

CALIBRATION: most real debate turns land between 3 and 6. Scores above 8 are rare and must be earned
by specifics listed in STEP 1. If a debater's evidence list is empty, their evidence score must not exceed 3.

Return ONLY valid JSON. No markdown.
{
  "x_evidence_cited": [str],
  "y_evidence_cited": [str],
  "z_evidence_cited": [str],
  "x_unsupported_claims": [str],
  "y_unsupported_claims": [str],
  "z_unsupported_claims": [str],
  "fallacy_claims": [{"by": "x" | "y" | "z", "named": str, "quote": str, "valid": true | false, "note": str}],
  "x_scores": {"evidence": float, "logic": float, "relevance": float},
  "y_scores": {"evidence": float, "logic": float, "relevance": float},
  "z_scores": {"evidence": float, "logic": float, "relevance": float},
  "reasoning": "2-3 sentences comparing the debaters citing what was actually said."
}"""


def _clean_response(raw: str) -> str:
    if not raw:
        return ""
    # Strip completed <think> blocks
    cleaned = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()
    
    # Locate JSON object
    start = cleaned.find("{")
    if start == -1:
        # Fallback: maybe JSON was inside <think> or raw string
        start = raw.find("{")
        if start != -1:
            cleaned = raw[start:]
        else:
            return raw.strip()
    else:
        cleaned = cleaned[start:]

    depth = 0
    for i, ch in enumerate(cleaned):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return cleaned[:i + 1]
    return cleaned


def _format_exchange_for_judge(exchange: list[dict]) -> str:
    """Labelled transcript for judge evaluation."""
    lines = []
    current_sub = 0
    sub_labels = {1: "Opening", 2: "Counter", 3: "Justify"}
    speaker_map = {"pro": "PRO", "con": "CON", "syn": "SYN"}
    for turn in exchange:
        sr = turn["sub_round"]
        if sr != current_sub:
            current_sub = sr
            lines.append(f"-- Sub-round {sr}: {sub_labels.get(sr, str(sr))} --")
        label = speaker_map.get(turn["speaker"], str(turn["speaker"]).upper())
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)


def _format_exchange_blind(exchange: list[dict], swap: bool = False) -> str:
    """
    Anonymised transcript.
    When 3 debaters are present:
      swap=False -> PRO: DEBATER-X, CON: DEBATER-Y, SYN: DEBATER-Z
      swap=True  -> PRO: DEBATER-Y, CON: DEBATER-Z, SYN: DEBATER-X (cyclic shift)
    When 2 debaters are present:
      swap=False -> PRO: DEBATER-X, CON: DEBATER-Y
      swap=True  -> PRO: DEBATER-Y, CON: DEBATER-X
    """
    has_syn = any(t.get("speaker") == "syn" for t in exchange)
    if has_syn:
        mapping = (
            {"pro": "DEBATER-Y", "con": "DEBATER-Z", "syn": "DEBATER-X"}
            if swap else
            {"pro": "DEBATER-X", "con": "DEBATER-Y", "syn": "DEBATER-Z"}
        )
    else:
        mapping = (
            {"pro": "DEBATER-Y", "con": "DEBATER-X"}
            if swap else
            {"pro": "DEBATER-X", "con": "DEBATER-Y"}
        )

    lines = []
    current_sub = 0
    sub_labels = {1: "Opening", 2: "Counter", 3: "Justify"}
    for turn in exchange:
        sr = turn["sub_round"]
        if sr != current_sub:
            current_sub = sr
            lines.append(f"-- Sub-round {sr}: {sub_labels.get(sr, str(sr))} --")
        label = mapping.get(turn["speaker"], f"DEBATER-{turn['speaker'].upper()}")
        lines.append(f"{label}: {turn['text']}")
    return "\n\n".join(lines)


# ── Repetition penalty (deterministic, no LLM) ───────────────────────────────

def _ngrams(text: str, n: int = 5) -> set:
    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def repetition_ratio(current_texts: list[str], prior_texts: list[str]) -> float:
    """Fraction of this round's 5-grams that already appeared in the same side's earlier rounds."""
    current = set()
    for t in current_texts:
        current |= _ngrams(t)
    if not current:
        return 0.0
    prior = set()
    for t in prior_texts:
        prior |= _ngrams(t)
    if not prior:
        return 0.0
    return len(current & prior) / len(current)


# Scorers return placeholder rows like {"named": "none", "valid": false} to mean
# "no fallacy here". Rendering those as "PRO misapplied 'none'" is nonsense.
_NON_FALLACY_LABELS = {"", "none", "n/a", "na", "null", "no fallacy", "no fallacy detected"}


def _as_text(value) -> str:
    """
    Flatten whatever the model returned into a plain sentence.

    The verdict schema asks for strings, but a language model asked for "exactly
    3 sentences: (1) who won, (2) what the loser got wrong, (3) the turning
    point" will sometimes helpfully return {"result": ..., "loser_error": ...,
    "turning_point": ...} instead. The frontend renders these fields directly, so
    an object reaches React as a child and crashes the whole dashboard with
    "Objects are not valid as a React child".

    Values are joined rather than dropped — the content is correct, only the
    shape is wrong.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(t for t in (_as_text(v) for v in value.values()) if t)
    if isinstance(value, (list, tuple)):
        return " ".join(t for t in (_as_text(v) for v in value) if t)
    return str(value)


def _coerce_verdict_strings(result: dict) -> None:
    """
    Force every field the UI renders as text to actually be text.

    Applied in place, after parsing and before the deterministic fields are
    written, so a malformed shape from the model can never reach the client.
    """
    for key in ("verdict", "final_reasoning"):
        if key in result:
            result[key] = _as_text(result[key])

    for section, fields in (
        ("score_explanation", ("pro", "con")),
        ("winner", ("decisive_argument",)),
        ("loser", ("fatal_weakness",)),
    ):
        block = result.get(section)
        if isinstance(block, dict):
            for f in fields:
                if f in block:
                    block[f] = _as_text(block[f])

    for section, field in (("winner", "points"), ("loser", "missed_points")):
        block = result.get(section)
        if isinstance(block, dict) and isinstance(block.get(field), list):
            block[field] = [_as_text(p) for p in block[field] if _as_text(p)]


def _normalise_claim(text: str) -> str:
    """Lowercase, strip punctuation and collapse whitespace, for comparison only."""
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", str(text).lower()).split())


def _dedup_claims(items: list) -> list:
    """
    Collapse restatements of the same claim into the longest phrasing.

    Exact-match dedup was enough while extraction emitted bare spans, but it is
    not once the extractor emits full sentences: the two blind passes word the
    same claim slightly differently, and a short fragment is frequently a
    substring of a fuller statement of the same fact ("Thermopylae" inside
    "Sparta resisted Persia at Thermopylae in 480 BCE"). Both used to survive and
    count twice, inflating the denominator that coverage and precision divide by.

    Keeping the longest form is deliberate — it is the most checkable, which is
    what the verification channel needs.

    Longest-first is what makes this order-independent: a single greedy pass in
    input order can absorb one fragment and then stop, leaving a second fragment
    of the same claim alive.

    Containment is tested on space-padded text so matches land on word
    boundaries — a raw substring test merges "art" into "Sparta".
    """
    indexed = []
    for i, item in enumerate(items):
        norm = _normalise_claim(item)
        if norm:
            indexed.append((i, norm, item))

    kept: list[tuple[int, str, Any]] = []
    for entry in sorted(indexed, key=lambda t: len(t[1]), reverse=True):
        _, norm, _item = entry
        if not any(f" {norm} " in f" {k} " for _, k, _ in kept):
            kept.append(entry)

    # Restore the transcript order the extractor emitted; sorting was only a
    # device for deciding which phrasing survives.
    return [item for _, _, item in sorted(kept, key=lambda t: t[0])]


def _is_real_fallacy_claim(f) -> bool:
    return isinstance(f, dict) and str(f.get("named", "")).strip().lower() not in _NON_FALLACY_LABELS


def _agreed_fallacy_claims(passes: list[dict]) -> list[dict]:
    """
    Keep only accusations that BOTH blind passes found AND attributed to the same
    debater. The passes see swapped labels, so a claim surviving both is one the
    scorer identified independently of which label the speaker wore — and a claim
    that flips sides between passes was a mis-attribution, not a finding.
    """
    real = [[f for f in p.get("fallacy_claims", []) if _is_real_fallacy_claim(f)] for p in passes]
    if len(real) < 2:
        return real[0] if real else []

    def key(f: dict) -> tuple:
        return (
            str(f.get("named", "")).strip().lower(),
            " ".join(str(f.get("quote", "")).lower().split())[:60],
        )

    other = {key(f): f for f in real[1]}
    return [f for f in real[0] if other.get(key(f), {}).get("by") == f.get("by")]


def _repetition_penalty(ratio: float) -> float:
    over = ratio - REPETITION_FREE_RATIO
    if over <= 0:
        return 0.0
    return round(min(REPETITION_MAX_PENALTY, over * 5.0), 1)


async def _score_blind_once(topic: str, exchange: list[dict], swap: bool) -> dict:
    """One blind scoring pass. Returns scores keyed by 'pro'/'con'/'syn' after unmapping X/Y/Z."""
    exchange_text = _format_exchange_blind(exchange, swap=swap)
    has_syn = any(t.get("speaker") == "syn" for t in exchange)
    print(f"[blind-score] INPUT EXCHANGE LENGTH: {len(exchange_text)}\n{exchange_text[:200]}...", flush=True)
    response = await groq_call(groq_client.chat.completions.create,
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": ROUND_SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Resolution being debated: {topic}\n\n"
                f"Exchange:\n{exchange_text}\n\n"
                f"Extract first, then score the debaters. Return ONLY the JSON object."
            )},
        ],
        max_tokens=4096,
        temperature=0,
    )
    raw = _clean_response(response.choices[0].message.content)
    if not raw:
        raise ValueError("Judge returned empty round scores.")
    result = json.loads(raw)

    if has_syn:
        # swap=False: pro=x, con=y, syn=z. swap=True: pro=y, con=z, syn=x
        pro_key, con_key, syn_key = ("y", "z", "x") if swap else ("x", "y", "z")
    else:
        pro_key, con_key = ("y", "x") if swap else ("x", "y")
        syn_key = None

    def side(prefix: str | None) -> dict:
        if not prefix:
            return {"evidence": 0.0, "logic": 0.0, "relevance": 0.0}
        s = result.get(f"{prefix}_scores", {}) or {}
        return {
            "evidence": float(s.get("evidence", 0) or 0),
            "logic": float(s.get("logic", 0) or 0),
            "relevance": float(s.get("relevance", 0) or 0),
        }

    # Unmask the reasoning text so the UI shows PRO/CON/SYN instead of DEBATER-X/Y/Z.
    reasoning = result.get("reasoning", "")
    if reasoning:
        if has_syn:
            x_target = "SYN" if swap else "PRO"
            y_target = "PRO" if swap else "CON"
            z_target = "CON" if swap else "SYN"
            reasoning = re.sub(r"\bdebater[\s\-_]*x\b", x_target, reasoning, flags=re.IGNORECASE)
            reasoning = re.sub(r"\bdebater[\s\-_]*y\b", y_target, reasoning, flags=re.IGNORECASE)
            reasoning = re.sub(r"\bdebater[\s\-_]*z\b", z_target, reasoning, flags=re.IGNORECASE)
        else:
            x_target = "CON" if swap else "PRO"
            y_target = "PRO" if swap else "CON"
            reasoning = re.sub(r"\bdebater[\s\-_]*x\b", x_target, reasoning, flags=re.IGNORECASE)
            reasoning = re.sub(r"\bdebater[\s\-_]*y\b", y_target, reasoning, flags=re.IGNORECASE)

    def _unmask_by(by_val: Any) -> str:
        b = str(by_val).strip().lower()
        if b == pro_key:
            return "pro"
        elif b == con_key:
            return "con"
        elif syn_key and b == syn_key:
            return "syn"
        return b

    return {
        "pro_scores": side(pro_key),
        "con_scores": side(con_key),
        "syn_scores": side(syn_key) if syn_key else {"evidence": 0.0, "logic": 0.0, "relevance": 0.0},
        "pro_evidence_cited": result.get(f"{pro_key}_evidence_cited", []) or [],
        "con_evidence_cited": result.get(f"{con_key}_evidence_cited", []) or [],
        "syn_evidence_cited": result.get(f"{syn_key}_evidence_cited", []) or [] if syn_key else [],
        "pro_unsupported_claims": result.get(f"{pro_key}_unsupported_claims", []) or [],
        "con_unsupported_claims": result.get(f"{con_key}_unsupported_claims", []) or [],
        "syn_unsupported_claims": result.get(f"{syn_key}_unsupported_claims", []) or [] if syn_key else [],
        "fallacy_claims": [
            {**f, "by": _unmask_by(f.get("by"))}
            for f in (result.get("fallacy_claims", []) or [])
            if isinstance(f, dict)
        ],
        "reasoning": reasoning,
    }


# An ngrok free tunnel drops idle connections and serves its OWN 404 page until
# traffic re-establishes it. Rounds are minutes apart once rate limiting slows
# the agents, which is long enough for the tunnel to go cold — a full debate was
# observed scoring on FT for only 1 of 3 rounds, silently falling back to Groq
# for the rest. So a 404 here is transient, unlike a 404 from a real API.
#
# 500 is deliberately NOT retried: it means the notebook raised, and greedy
# decoding is deterministic, so the identical request would fail identically.
_FT_RETRYABLE_STATUS = {425, 429, 502, 503, 504}


async def _get_ft_round_scores(topic: str, exchange_text: str) -> dict | None:
    """
    Queries the fine-tuned 4B scorer on Kaggle via FT_JUDGE_URL.

    Retries transient tunnel failures, then gives up and returns None so the
    caller falls back to the blind-swap scores. Failures are logged with the
    exception TYPE, not just its message: httpx timeouts stringify to "", so the
    original handler printed a bare "failed:" and hid the fact that every call
    was timing out rather than erroring.
    """
    attempts = max(1, config.FT_MAX_ATTEMPTS)
    started = time.monotonic()

    for attempt in range(attempts):
        reason = None
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{FT_JUDGE_URL.rstrip('/')}/ft-judge",
                    json={"topic": topic, "exchange": exchange_text},
                    headers=NGROK_HEADERS,
                    timeout=config.FT_JUDGE_TIMEOUT,
                )
                if resp.status_code == 200:
                    result = resp.json()
                    # v3 emits {"winner", "pro_total", "con_total"}; v2 emitted
                    # per-criterion pro_scores/con_scores. Both are accepted so a
                    # rollback to v2 does not need a code change, and so a
                    # half-updated deployment fails loudly rather than silently
                    # scoring with whichever half it got.
                    if "pro_total" in result and "con_total" in result:
                        print(f"[FT] v3 scored in {time.monotonic() - started:.1f}s"
                              f"{f' (attempt {attempt + 1})' if attempt else ''}")
                        return result
                    if "pro_scores" in result and "con_scores" in result:
                        print(f"[FT] v2 scored in {time.monotonic() - started:.1f}s"
                              f"{f' (attempt {attempt + 1})' if attempt else ''}")
                        return result
                    # The notebook returns {"error": ...} on a parse failure.
                    err = str(result.get("error", ""))[:160] if isinstance(result, dict) else ""
                    print(f"[FT] 200 but unusable payload, keys={list(result)[:6]} {err}")
                    return None
                if resp.status_code == 404:
                    print(f"[FT] HTTP 404 — Kaggle FT endpoint not mounted, falling back to Groq")
                    return None
                if resp.status_code not in _FT_RETRYABLE_STATUS:
                    print(f"[FT] HTTP {resp.status_code} — not retryable, falling back to Groq")
                    return None
                reason = f"HTTP {resp.status_code}"
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            print(f"[FT] Kaggle offline ({type(e).__name__}) — falling back to Groq")
            return None
        except Exception as e:
            reason = f"{type(e).__name__}: {e or '<no message>'}"

        if attempt == attempts - 1:
            print(f"[FT] {reason} after {time.monotonic() - started:.1f}s, "
                  f"{attempts} attempt(s) — falling back to Groq")
            return None

        print(f"[FT] {reason} — retry {attempt + 1}/{attempts - 1} in {config.FT_RETRY_DELAY:.1f}s")
        await asyncio.sleep(config.FT_RETRY_DELAY)

    return None


async def _get_explanation(topic: str, exchange_text: str, scores: dict) -> str:
    """Groq explains the scores in plain English — does NOT score."""
    pro = scores.get("pro_scores", {}).get("total", 0)
    con = scores.get("con_scores", {}).get("total", 0)
    winner = scores.get("round_winner", "tie")

    response = await groq_call(groq_client.chat.completions.create,
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


def _apply_evidence_cap(scores: dict, cited: list) -> None:
    """A side that cited nothing verifiable cannot be scored as evidence-based."""
    if not cited and scores["evidence"] > NO_EVIDENCE_CAP:
        scores["evidence"] = NO_EVIDENCE_CAP


async def _ground_side(cited: list) -> dict | None:
    """
    Check one side's cited specifics against the retrieval corpus.

    Returns None when verification is disabled or there was nothing to check, in
    which case the caller leaves the score untouched.
    """
    if not config.VERIFICATION_ENABLED or not cited:
        return None
    from debate.verifier import grounding_report, verify_claims
    return grounding_report(await verify_claims([str(c) for c in cited]))


def _apply_grounding(scores: dict, report: dict | None) -> None:
    """
    Bound the evidence score by what retrieval could actually confirm.

    Only ever lowers a score. The ceiling is computed over claims the corpus could
    rule on, so an empty or off-topic corpus yields a ceiling of 10.0 and this is
    a no-op — the verification channel can never invent grounding, only withhold
    credit for grounding that is absent.
    """
    if not report:
        return
    cap = report.get("evidence_cap", 10.0)
    penalty = report.get("fabrication_penalty", 0.0)
    scores["evidence"] = round(max(0.0, min(scores["evidence"], cap) - penalty), 1)


def _total(scores: dict, penalty: float) -> float:
    base = (scores["evidence"] + scores["logic"] + scores["relevance"]) / 3
    return round(max(0.0, min(10.0, base - penalty)), 1)


async def judge_round(
    topic: str,
    round_num: int,
    exchange: list[dict],
    prior_pro_texts: list[str] | None = None,
    prior_con_texts: list[str] | None = None,
    prior_syn_texts: list[str] | None = None,
) -> dict:
    """
    Scores a round blind, twice, with debater labels rotated, and averages —
    so a scorer preference for any label cancels out. Evidence caps and the
    repetition penalty are then applied deterministically in Python.
    Supports 2 or 3 debating agents.
    """
    exchange_text = _format_exchange_for_judge(exchange)
    has_syn = any(t.get("speaker") == "syn" for t in exchange)

    # Blind passes and FT probe (FT is trained for 2-agent; 3-agent uses 3-way blind rotation)
    scoring = [_score_blind_once(topic, exchange, swap=(i == 1)) for i in range(BLIND_PASSES)]
    if has_syn:
        raw_passes = await asyncio.gather(*scoring, return_exceptions=True)
        ft = None
    else:
        *raw_passes, ft = await asyncio.gather(*scoring, _get_ft_round_scores(topic, exchange_text),
                                               return_exceptions=True)

    passes = [p for p in raw_passes if isinstance(p, dict)]
    if not passes:
        raise ValueError(f"All {BLIND_PASSES} blind scoring pass(es) failed: {raw_passes}")

    def averaged(side: str, criterion: str) -> float:
        return round(sum(p[f"{side}_scores"][criterion] for p in passes) / len(passes), 1)

    pro_scores = {c: averaged("pro", c) for c in ("evidence", "logic", "relevance")}
    con_scores = {c: averaged("con", c) for c in ("evidence", "logic", "relevance")}
    syn_scores = {c: averaged("syn", c) for c in ("evidence", "logic", "relevance")} if has_syn else {"evidence": 0.0, "logic": 0.0, "relevance": 0.0}

    # Union the audit output across passes.
    def merged(key: str) -> list:
        seen, out = set(), []
        for p in passes:
            for item in p.get(key, []):
                k = str(item).strip().lower()
                if k and k not in seen:
                    seen.add(k)
                    out.append(item)
        return out

    pro_evidence = _dedup_claims(merged("pro_evidence_cited"))
    con_evidence = _dedup_claims(merged("con_evidence_cited"))
    syn_evidence = _dedup_claims(merged("syn_evidence_cited")) if has_syn else []

    ft_used = isinstance(ft, dict) and ft is not None
    ft_totals = None
    if not has_syn and ft_used and "pro_total" in ft and "con_total" in ft:
        try:
            ft_totals = (float(ft["pro_total"]), float(ft["con_total"]))
        except (TypeError, ValueError):
            ft_totals = None

    _apply_evidence_cap(pro_scores, pro_evidence)
    _apply_evidence_cap(con_scores, con_evidence)
    if has_syn:
        _apply_evidence_cap(syn_scores, syn_evidence)

    # Retrieval-grounded verification. Runs concurrently for all debaters.
    grounding_coros = [_ground_side(pro_evidence), _ground_side(con_evidence)]
    if has_syn:
        grounding_coros.append(_ground_side(syn_evidence))
    grounding_results = await asyncio.gather(*grounding_coros, return_exceptions=True)
    pro_grounding = grounding_results[0] if isinstance(grounding_results[0], dict) else None
    con_grounding = grounding_results[1] if isinstance(grounding_results[1], dict) else None
    syn_grounding = grounding_results[2] if (has_syn and len(grounding_results) > 2 and isinstance(grounding_results[2], dict)) else None

    _apply_grounding(pro_scores, pro_grounding)
    _apply_grounding(con_scores, con_grounding)
    if has_syn:
        _apply_grounding(syn_scores, syn_grounding)

    pro_rep = repetition_ratio([t["text"] for t in exchange if t["speaker"] == "pro"], prior_pro_texts or [])
    con_rep = repetition_ratio([t["text"] for t in exchange if t["speaker"] == "con"], prior_con_texts or [])
    syn_rep = repetition_ratio([t["text"] for t in exchange if t["speaker"] == "syn"], prior_syn_texts or []) if has_syn else 0.0
    pro_penalty, con_penalty, syn_penalty = _repetition_penalty(pro_rep), _repetition_penalty(con_rep), _repetition_penalty(syn_rep)

    pro_scores["total"] = _total(pro_scores, pro_penalty)
    con_scores["total"] = _total(con_scores, con_penalty)
    if has_syn:
        syn_scores["total"] = _total(syn_scores, syn_penalty)

    if ft_totals is not None and not has_syn:
        pro_fab = (pro_grounding or {}).get("fabrication_penalty", 0.0)
        con_fab = (con_grounding or {}).get("fabrication_penalty", 0.0)
        for total, scores, penalty in ((ft_totals[0], pro_scores, pro_penalty + pro_fab),
                                       (ft_totals[1], con_scores, con_penalty + con_fab)):
            scores["total"] = round(max(0.0, min(10.0, total) - penalty), 1)

    # Determine round winner among 2 or 3 debaters
    candidates = [("pro", pro_scores["total"]), ("con", con_scores["total"])]
    if has_syn:
        candidates.append(("syn", syn_scores["total"]))
    sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
    best_side, best_score = sorted_candidates[0]
    second_side, second_score = sorted_candidates[1]

    if (best_score - second_score) <= TIE_BAND:
        round_winner = "tie"
    else:
        round_winner = best_side

    fallacies = _agreed_fallacy_claims(passes)
    invalid_labels = [
        f"{f.get('by', '?').upper()} misapplied \"{f.get('named')}\""
        for f in fallacies if f.get("valid") is False
    ]

    reasoning = _as_text(next((p.get("reasoning") for p in passes if p.get("reasoning")), ""))

    final_scores = {"pro": pro_scores["total"], "con": con_scores["total"]}
    if has_syn:
        final_scores["syn"] = syn_scores["total"]

    return {
        "pro_scores":            pro_scores,
        "con_scores":            con_scores,
        "syn_scores":            syn_scores if has_syn else None,
        "round_winner":          round_winner,
        "reasoning":             reasoning,
        "winner_evidence":       "",
        "loser_weakness":        "",
        "fallacy_detected":      invalid_labels[0] if invalid_labels else None,
        "final_score_out_of_10": final_scores,
        # Audit trail — why the scores are what they are.
        "audit": {
            "pro_evidence_cited":      pro_evidence,
            "con_evidence_cited":      con_evidence,
            "syn_evidence_cited":      syn_evidence if has_syn else [],
            "pro_unsupported_claims":  merged("pro_unsupported_claims"),
            "con_unsupported_claims":  merged("con_unsupported_claims"),
            "syn_unsupported_claims":  merged("syn_unsupported_claims") if has_syn else [],
            "fallacy_claims":          fallacies,
            "pro_repetition":          round(pro_rep, 2),
            "con_repetition":          round(con_rep, 2),
            "syn_repetition":          round(syn_rep, 2) if has_syn else 0.0,
            "pro_repetition_penalty":  pro_penalty,
            "con_repetition_penalty":  con_penalty,
            "syn_repetition_penalty":  syn_penalty if has_syn else 0.0,
            "pro_grounding":           pro_grounding,
            "con_grounding":           con_grounding,
            "syn_grounding":           syn_grounding if has_syn else None,
            "verification_backend":    config.NLI_BACKEND if config.VERIFICATION_ENABLED else "disabled",
            "scorer":                  "kaggle-ft (audited)" if ft_used and not has_syn else "groq-blind-swap",
            "blind_passes":            len(passes),
            "label_disagreement":      round(abs(
                passes[0]["pro_scores"]["evidence"] - passes[-1]["pro_scores"]["evidence"]
            ), 1) if len(passes) > 1 else None,
        },
    }


def _verdict_receipts(all_rounds: list[dict]) -> dict:
    """
    Aggregate the per-round audits into the evidence behind the verdict.

    Everything here was already computed and then thrown away: the judge returned
    prose about who won while the extracted claims, the corpus verification, and
    the penalties that actually moved the totals stayed buried in each round's
    audit. A reader was left taking the outcome on trust.

    This exposes the arithmetic instead — which criterion produced the gap, which
    rounds contributed it, what each side cited and whether the corpus confirmed
    it, and every penalty applied with its reason.
    """
    if not all_rounds:
        return {}

    n = len(all_rounds)

    def mean(side: str, criterion: str) -> float:
        return round(sum(r[f"{side}_scores"].get(criterion, 0) for r in all_rounds) / n, 2)

    criteria = {
        side: {c: mean(side, c) for c in ("evidence", "logic", "relevance")}
        for side in ("pro", "con")
    }
    # The criterion that opened the largest gap is the honest answer to "why".
    gaps = {c: round(criteria["pro"][c] - criteria["con"][c], 2)
            for c in ("evidence", "logic", "relevance")}
    decisive_criterion = max(gaps, key=lambda c: abs(gaps[c]))

    per_round = [{
        "r": i + 1,
        "pro": r["pro_scores"]["total"],
        "con": r["con_scores"]["total"],
        "delta": round(r["pro_scores"]["total"] - r["con_scores"]["total"], 1),
        "winner": r["round_winner"],
    } for i, r in enumerate(all_rounds)]

    def verification(side: str) -> dict:
        supported = refuted = nei = 0
        checked = 0
        for r in all_rounds:
            g = (r.get("audit") or {}).get(f"{side}_grounding") or {}
            supported += g.get("supported", 0)
            refuted += g.get("refuted", 0)
            nei += g.get("nei", 0)
            checked += g.get("claims_checked", 0)
        adjudicable = supported + refuted
        return {
            "claims_checked": checked,
            "supported": supported,
            "refuted": refuted,
            "nei": nei,
            "coverage": round(adjudicable / checked, 2) if checked else None,
            "precision": round(supported / adjudicable, 2) if adjudicable else None,
        }

    def cited(side: str) -> list[str]:
        out: list[str] = []
        for r in all_rounds:
            out.extend((r.get("audit") or {}).get(f"{side}_evidence_cited", []) or [])
        return _dedup_claims(out)

    def penalties(side: str) -> dict:
        rep = round(sum((r.get("audit") or {}).get(f"{side}_repetition_penalty", 0) or 0
                        for r in all_rounds), 1)
        fab = round(sum(((r.get("audit") or {}).get(f"{side}_grounding") or {}).get("fabrication_penalty", 0) or 0
                        for r in all_rounds), 1)
        # A capped round is one where the corpus refused to certify the evidence
        # score the scorer wanted to give.
        capped = sum(1 for r in all_rounds
                     if (((r.get("audit") or {}).get(f"{side}_grounding") or {}).get("evidence_cap", 10.0) < 10.0))
        return {"repetition": rep, "fabrication": fab, "rounds_evidence_capped": capped}

    disagreements = [(r.get("audit") or {}).get("label_disagreement") for r in all_rounds]
    disagreements = [d for d in disagreements if d is not None]

    return {
        "criteria": criteria,
        "criterion_gaps": gaps,
        "decisive_criterion": decisive_criterion,
        "per_round": per_round,
        "verification": {"pro": verification("pro"), "con": verification("con")},
        "cited": {"pro": cited("pro"), "con": cited("con")},
        "penalties": {"pro": penalties("pro"), "con": penalties("con")},
        "scorer": (all_rounds[0].get("audit") or {}).get("scorer"),
        "verification_backend": (all_rounds[0].get("audit") or {}).get("verification_backend"),
        # Mean disagreement between the two label-swapped passes. Near zero means
        # the result did not depend on which side wore which label.
        "position_bias": round(sum(disagreements) / len(disagreements), 2) if disagreements else None,
    }


def _verdict_confidence(pro_total: float, con_total: float) -> dict:
    """
    Attach a conformal verdict set to the final result.

    The point verdict is still computed and still returned — this does not
    override it. What it adds is an honest statement of how much separation the
    scores actually carry, backed by a distribution-free guarantee rather than by
    the judge's own confidence, which is exactly the thing that cannot be trusted.

    Absent calibration this reports "uncalibrated" and claims nothing. That is
    the common case on a fresh checkout, and it must never look like a guarantee:
    a coverage claim with no calibration behind it is worse than none.
    """
    if not config.CONFORMAL_ENABLED:
        return {"available": False, "reason": "disabled"}

    try:
        from debate.conformal import get_predictor
        predictor = get_predictor()
    except Exception as e:
        logger_msg = f"conformal unavailable: {type(e).__name__}: {e}"
        print(f"[conformal] {logger_msg}")
        return {"available": False, "reason": "error"}

    if predictor is None or predictor.quantile is None:
        return {
            "available": False,
            "reason": "uncalibrated",
            "hint": "run `python -m eval.calibrate` to fit a predictor",
        }

    prediction = predictor.predict(pro_total, con_total)
    return {
        "available": True,
        "verdict_set": prediction["verdict_set"],
        "abstain": prediction["abstain"],
        "reason": prediction["reason"],
        "alpha": prediction["alpha"],
        "target_coverage": round(1 - prediction["alpha"], 3),
        "n_calibration": prediction["n_calibration"],
        # Stated so the number is never read as a claim about this one round.
        "guarantee": (
            f"Over exchangeable rounds this set contains the true winner at least "
            f"{round((1 - prediction['alpha']) * 100)}% of the time."
        ),
    }


async def judge_final_verdict(
    topic: str,
    all_rounds: list[dict],
    pro_arguments: list[str] | None = None,
    con_arguments: list[str] | None = None,
    syn_arguments: list[str] | None = None,
) -> dict:
    def _safe_total(r: dict, side: str) -> float:
        s = r.get(f"{side}_scores") or {}
        return float(s.get("total", 0) or 0)

    has_syn = any("syn_scores" in r and r["syn_scores"] is not None and r["syn_scores"].get("total") is not None for r in all_rounds)

    pro_total = round(sum(_safe_total(r, "pro") for r in all_rounds), 1)
    con_total = round(sum(_safe_total(r, "con") for r in all_rounds), 1)
    syn_total = round(sum(_safe_total(r, "syn") for r in all_rounds), 1) if has_syn else 0.0
    max_possible = len(all_rounds) * 10

    # Determine overall winner among 2 or 3 debaters
    candidates = [("pro", pro_total), ("con", con_total)]
    if has_syn:
        candidates.append(("syn", syn_total))
    sorted_candidates = sorted(candidates, key=lambda x: x[1], reverse=True)
    best_side, best_total = sorted_candidates[0]
    second_side, second_total = sorted_candidates[1]

    margin = round(best_total - second_total, 1)
    overall_winner = "tie" if margin <= TIE_BAND else best_side
    win_key = f"{overall_winner}_scores" if overall_winner in ("pro", "con", "syn") else "pro_scores"
    strongest_round = max(
        range(len(all_rounds)), key=lambda i: ((all_rounds[i].get(win_key) or {}).get("total") or 0)
    ) + 1 if all_rounds else 1

    rounds_summary_lines = []
    for i, r in enumerate(all_rounds):
        line = f"R{i+1}: PRO={_safe_total(r, 'pro')} CON={_safe_total(r, 'con')}"
        if has_syn:
            line += f" SYN={_safe_total(r, 'syn')}"
        line += f" Winner={(r.get('round_winner') or 'tie').upper()} — {r.get('reasoning', '')}"
        rounds_summary_lines.append(line)
    rounds_summary = "\n".join(rounds_summary_lines)

    audit_lines = []
    for i, r in enumerate(all_rounds):
        a = r.get("audit", {})
        line = f"R{i+1} evidence cited — PRO: {a.get('pro_evidence_cited') or 'NONE'} | CON: {a.get('con_evidence_cited') or 'NONE'}"
        if has_syn:
            line += f" | SYN: {a.get('syn_evidence_cited') or 'NONE'}"
        audit_lines.append(line)
    audit_block = "\n".join(audit_lines)

    args_block = ""
    if pro_arguments or con_arguments or syn_arguments:
        lines = []
        for i, r in enumerate(all_rounds):
            pro_arg = (pro_arguments or [])[i] if i < len(pro_arguments or []) else ""
            con_arg = (con_arguments or [])[i] if i < len(con_arguments or []) else ""
            syn_arg = (syn_arguments or [])[i] if (has_syn and i < len(syn_arguments or [])) else ""
            if pro_arg: lines.append(f"R{i+1} PRO: {pro_arg[:150]}")
            if con_arg: lines.append(f"R{i+1} CON: {con_arg[:150]}")
            if syn_arg: lines.append(f"R{i+1} SYN: {syn_arg[:150]}")
        args_block = "\nKey arguments made:\n" + "\n".join(lines)

    outcome = (
        f"OUTCOME (already decided — describe, do not recompute): "
        f"{'TIE' if overall_winner == 'tie' else overall_winner.upper() + ' WINS'}. "
        f"Strongest round for the winner: Round {strongest_round}."
    )

    score_line = f"PRO total: {pro_total}/{max_possible} | CON total: {con_total}/{max_possible}"
    if has_syn:
        score_line += f" | SYN total: {syn_total}/{max_possible}"

    response = await groq_call(groq_client.chat.completions.create,
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": FINAL_VERDICT_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Scores:\n{rounds_summary}\n\n"
                f"{audit_block}"
                f"{args_block}\n\n"
                f"{score_line}\n"
                f"{outcome}\n\n"
                f"Return ONLY the JSON object."
            )},
        ],
        max_tokens=4096,
        temperature=0,
    )

    raw = _clean_response(response.choices[0].message.content)

    try:
        result = json.loads(raw)
    except Exception as e:
        print(f"Failed to parse final verdict JSON: {e}. Output was: {raw}")
        exp = {
            "pro": f"PRO earned {pro_total} total points across {len(all_rounds)} rounds.",
            "con": f"CON earned {con_total} total points across {len(all_rounds)} rounds.",
        }
        if has_syn:
            exp["syn"] = f"SYN earned {syn_total} total points across {len(all_rounds)} rounds."
        result = {
            "score_explanation": exp,
            "winner": {
                "decisive_argument": "Stronger evidence and argument consistency throughout the debate.",
                "points": ["Maintained key arguments and factual grounding across rounds."],
            },
            "loser": {
                "fatal_weakness": "Scored lower across the overall debate rounds.",
                "missed_points": ["Could have addressed opponent counterarguments more directly."]
            },
            "verdict": (
                f"The debate ended in a tie. "
                if overall_winner == "tie" else
                f"{overall_winner.upper()} won the debate with {best_total} points. "
            ) + "The winning side cited more checkable evidence across rounds."
        }

    _coerce_verdict_strings(result)

    def _sanitize_list(items: list, fallback: list) -> list:
        cleaned = [s for s in items if s and str(s).strip() not in ("...", ".", "…", "-", "")]
        return cleaned if cleaned else fallback

    w_block = result.get("winner") if isinstance(result.get("winner"), dict) else {}
    result["winner"] = w_block
    w_block["points"] = _sanitize_list(
        w_block.get("points", []),
        [f"Consistent performance across {len(all_rounds)} rounds of debate."]
    )
    if str(w_block.get("decisive_argument", "")).strip() in ("...", ".", "…", ""):
        w_block["decisive_argument"] = "Superior factual evidence and coherent logical structure."

    l_block = result.get("loser") if isinstance(result.get("loser"), dict) else {}
    result["loser"] = l_block
    l_block["missed_points"] = _sanitize_list(
        l_block.get("missed_points", []),
        ["Failed to counter key factual claims made by the opponent."]
    )
    if str(l_block.get("fatal_weakness", "")).strip() in ("...", ".", "…", ""):
        l_block["fatal_weakness"] = "Lack of verifiable source citations in core arguments."

    result["overall_winner"] = overall_winner
    result["pro_total"] = pro_total
    result["con_total"] = con_total
    if has_syn:
        result["syn_total"] = syn_total
    result["margin"] = abs(margin)
    result["is_tie"] = overall_winner == "tie"
    accuracy_dict = {
        "pro": round((pro_total / max_possible) * 100, 1) if max_possible else 0.0,
        "con": round((con_total / max_possible) * 100, 1) if max_possible else 0.0,
    }
    if has_syn:
        accuracy_dict["syn"] = round((syn_total / max_possible) * 100, 1) if max_possible else 0.0
    result["accuracy"] = accuracy_dict
    result["winner"]["strongest_round"] = strongest_round
    result["confidence"] = _verdict_confidence(pro_total, con_total)
    result["receipts"] = _verdict_receipts(all_rounds)

    # Per-round winners and margins come from the scores, never from the model.
    model_rounds = {r.get("r"): r for r in (result.get("rounds") or []) if isinstance(r, dict)}
    result["rounds"] = []
    for i, r in enumerate(all_rounds):
        swing_val = _as_text(model_rounds.get(i + 1, {}).get("swing"))
        if not swing_val or swing_val.strip() in ("...", ".", "…", "-"):
            swing_val = _as_text(r.get("reasoning"))
        result["rounds"].append({
            "r": i + 1,
            "winner": r.get("round_winner") or "tie",
            "margin": round(abs(_safe_total(r, "pro") - _safe_total(r, "con")), 1),
            "swing": (swing_val or "Round decided on argumentation and evidence.")[:120],
        })

    # Surface only fallacy accusations the judge confirmed were misapplied.
    result["fallacies"] = [
        f"{(f.get('by') or '?').upper()} misapplied \"{f.get('named')}\""
        for r in all_rounds if isinstance(r, dict)
        for f in ((r.get("audit") or {}).get("fallacy_claims") or [])
        if isinstance(f, dict) and _is_real_fallacy_claim(f) and f.get("valid") is False
    ][:6]

    return result