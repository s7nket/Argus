import asyncio
import os
import re
import json
import time
import httpx
from dotenv import load_dotenv
from groq import AsyncGroq

import config
from config import (
    BLIND_PASSES,
    NO_EVIDENCE_CAP,
    REPETITION_FREE_RATIO,
    REPETITION_MAX_PENALTY,
    TIE_BAND,
)
from llm_retry import groq_call

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
    "con": "1 sentence: what did CON do to earn their score?"
  },
  "winner": {
    "decisive_argument": "The single best point that won the debate. Max 20 words. Must reference an actual argument they made.",
    "points": ["Specific point or argument they made that scored well — max 15 plain words.", "Another specific point they made — max 15 plain words."]
  },
  "loser": {
    "fatal_weakness": "The main reason they lost. Max 20 plain words. Must reference something they actually failed to do.",
    "missed_points": ["A specific argument they should have made — max 15 plain words.", "Another thing they missed — max 15 plain words."]
  },
  "rounds": [
    {"r": int, "swing": "What specific argument decided this round? Max 12 words."}
  ],
  "verdict": "Exactly 3 plain sentences: (1) who won and why in simple words, (2) what the loser got wrong, (3) the one moment that changed the debate."
}

Rules:
- Use simple everyday words. verdict = exactly 3 sentences. Output JSON only.
- The winner, the totals, the per-round winners and the strongest round are ALREADY DECIDED and given to
  you in the user message. Describe them. Do not compute, re-score, or contradict them.
- Never justify a score using a debater's own description of their own case. Cite what they actually cited.
- If the outcome given to you is a TIE, say so plainly instead of naming a winner."""


# ── Blind scoring rubric ─────────────────────────────────────────────────────
# The judge never sees "PRO" / "CON" — only DEBATER-X and DEBATER-Y — and every
# round is scored twice with those labels swapped, so a preference for either
# label cancels out. Extraction happens BEFORE scoring: the old prompt asked for
# an "evidence" score with no definition and no scale, so the model rewarded
# whichever side used the WORD "evidence" more often.
ROUND_SCORING_SYSTEM_PROMPT = """You are a strict, impartial debate judge scoring one round of a two-sided debate.

The debaters are labelled DEBATER-X and DEBATER-Y. You are NOT told which side of the resolution
each one holds. Judge only what is on the page.

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
  Example: CON cites "Thermopylae, 480 BCE" as proof of Spartan strength; PRO replies
  "Thermopylae was a defeat". Thermopylae belongs to CON's list ONLY.

MERGE DUPLICATES. One entry per distinct factual claim. "Thermopylae", "480 BCE" and
"Thermopylae in 480 BCE" are one claim, not three — emit the single complete statement.

- A debater describing their own case as "evidence-based", "empirical", "data-driven" or "nuanced"
  is NOT evidence. Ignore all self-description entirely.
- Gesturing at evidence without naming it ("the archaeological record shows", "studies confirm",
  "history demonstrates") is NOT evidence. It is an unsupported claim.
- If a debater cited nothing verifiable, return an empty list. Empty lists are common and
  correct. Do not pad them, and never invent a statement the debater did not make.

STEP 2 — LIST UNSUPPORTED CLAIMS: statements presented as established fact with nothing behind them,
and any claim you can identify as factually false.

STEP 3 — VALIDATE EVERY FALLACY ACCUSATION.
If a debater names a fallacy against their opponent, quote the accused text and decide whether the
label genuinely fits. Naming fallacies is not a virtue and earns no credit by itself. A misapplied
fallacy label is a reasoning error that LOWERS the accuser's logic score.

STEP 4 — SCORE. Use the full range.
  Evidence   0-2  pure assertion, nothing cited
             3-4  vague appeals to evidence or data with no specifics
             5-6  one concrete, checkable example
             7-8  several concrete specifics that carry the argument
             9-10 precise data, dates or named sources that settle the point
  Logic      0-2  incoherent or self-contradictory
             3-4  asserts a conclusion without connecting it; misapplied fallacy labels
             5-6  valid structure with unaddressed gaps
             7-8  sound chain of reasoning, engages the opponent's strongest point
             9-10 airtight, defeats the opponent on their own terms
  Relevance  0-2  ignores the resolution
             3-4  argues a neighbouring question rather than the one asked
             5-6  on topic but drifting
             7-8  directly on the resolution throughout
             9-10 sharply focused on what actually decides the resolution

CALIBRATION: most real debate turns land between 3 and 6. Scores above 8 are rare and must be earned
by the specifics you listed in STEP 1. If a debater's evidence list is empty, their evidence score
must not exceed 3. Repeating a position more forcefully is not an argument and earns nothing.

Return ONLY valid JSON. No markdown.
{
  "x_evidence_cited": [str],   // complete checkable statements, deduplicated
  "y_evidence_cited": [str],   // complete checkable statements, deduplicated
  "x_unsupported_claims": [str],
  "y_unsupported_claims": [str],
  "fallacy_claims": [{"by": "x" | "y", "named": str, "quote": str, "valid": true | false, "note": str}],
  "x_scores": {"evidence": float, "logic": float, "relevance": float},
  "y_scores": {"evidence": float, "logic": float, "relevance": float},
  "reasoning": "1-2 sentences citing what was actually said. Never echo a debater's own adjectives about themselves."
}"""


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
    """Labelled transcript — used for the FT scorer, which expects PRO/CON."""
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


def _format_exchange_blind(exchange: list[dict], swap: bool = False) -> str:
    """
    Anonymised transcript. swap=False maps pro->X, con->Y; swap=True reverses it.
    Turn order is preserved either way — reordering would break the rebuttal chain.
    """
    pro_label, con_label = ("DEBATER-Y", "DEBATER-X") if swap else ("DEBATER-X", "DEBATER-Y")
    lines = []
    current_sub = 0
    sub_labels = {1: "Opening", 2: "Counter", 3: "Justify"}
    for turn in exchange:
        sr = turn["sub_round"]
        if sr != current_sub:
            current_sub = sr
            lines.append(f"-- Sub-round {sr}: {sub_labels.get(sr, str(sr))} --")
        lines.append(f"{pro_label if turn['speaker'] == 'pro' else con_label}: {turn['text']}")
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
    """One blind scoring pass. Returns scores keyed by 'pro'/'con' after unmapping X/Y."""
    response = await groq_call(groq_client.chat.completions.create,
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": ROUND_SCORING_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Resolution being debated: {topic}\n\n"
                f"Exchange:\n{_format_exchange_blind(exchange, swap=swap)}\n\n"
                f"Extract first, then score both debaters. Return ONLY the JSON object."
            )},
        ],
        max_tokens=1400,
        temperature=0,
    )
    raw = _clean_response(response.choices[0].message.content)
    if not raw:
        raise ValueError("Judge returned empty round scores.")
    result = json.loads(raw)

    # swap=False: pro was X. swap=True: pro was Y.
    pro_key, con_key = ("y", "x") if swap else ("x", "y")

    def side(prefix: str) -> dict:
        s = result.get(f"{prefix}_scores", {}) or {}
        return {
            "evidence": float(s.get("evidence", 0) or 0),
            "logic": float(s.get("logic", 0) or 0),
            "relevance": float(s.get("relevance", 0) or 0),
        }

    return {
        "pro_scores": side(pro_key),
        "con_scores": side(con_key),
        "pro_evidence_cited": result.get(f"{pro_key}_evidence_cited", []) or [],
        "con_evidence_cited": result.get(f"{con_key}_evidence_cited", []) or [],
        "pro_unsupported_claims": result.get(f"{pro_key}_unsupported_claims", []) or [],
        "con_unsupported_claims": result.get(f"{con_key}_unsupported_claims", []) or [],
        "fallacy_claims": [
            {**f, "by": "pro" if f.get("by") == pro_key else "con"}
            for f in (result.get("fallacy_claims", []) or [])
            if isinstance(f, dict)
        ],
        "reasoning": result.get("reasoning", ""),
    }


# An ngrok free tunnel drops idle connections and serves its OWN 404 page until
# traffic re-establishes it. Rounds are minutes apart once rate limiting slows
# the agents, which is long enough for the tunnel to go cold — a full debate was
# observed scoring on FT for only 1 of 3 rounds, silently falling back to Groq
# for the rest. So a 404 here is transient, unlike a 404 from a real API.
#
# 500 is deliberately NOT retried: it means the notebook raised, and greedy
# decoding is deterministic, so the identical request would fail identically.
_FT_RETRYABLE_STATUS = {404, 408, 425, 429, 502, 503, 504}


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
                    if "pro_scores" in result and "con_scores" in result:
                        print(f"[FT] scored in {time.monotonic() - started:.1f}s"
                              f"{f' (attempt {attempt + 1})' if attempt else ''}")
                        return result
                    # The notebook returns {"error": ...} on a parse failure.
                    err = str(result.get("error", ""))[:160] if isinstance(result, dict) else ""
                    print(f"[FT] 200 but unusable payload, keys={list(result)[:6]} {err}")
                    return None
                if resp.status_code not in _FT_RETRYABLE_STATUS:
                    print(f"[FT] HTTP {resp.status_code} — not retryable")
                    return None
                reason = f"HTTP {resp.status_code}"
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
) -> dict:
    """
    Scores a round blind, twice, with the debater labels swapped, and averages —
    so a scorer preference for either label cancels out. Evidence caps and the
    repetition penalty are then applied deterministically in Python.
    """
    exchange_text = _format_exchange_for_judge(exchange)

    # Blind passes and the FT probe run concurrently — the extra accuracy costs
    # roughly one call of wall time, though it does double the token spend.
    scoring = [_score_blind_once(topic, exchange, swap=(i == 1)) for i in range(BLIND_PASSES)]
    *raw_passes, ft = await asyncio.gather(*scoring, _get_ft_round_scores(topic, exchange_text),
                                           return_exceptions=True)

    passes = [p for p in raw_passes if isinstance(p, dict)]
    if not passes:
        raise ValueError(f"All {BLIND_PASSES} blind scoring pass(es) failed: {raw_passes}")

    def averaged(side: str, criterion: str) -> float:
        return round(sum(p[f"{side}_scores"][criterion] for p in passes) / len(passes), 1)

    pro_scores = {c: averaged("pro", c) for c in ("evidence", "logic", "relevance")}
    con_scores = {c: averaged("con", c) for c in ("evidence", "logic", "relevance")}

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

    # Evidence lists get the stronger collapse — they are what the verification
    # channel divides by, so a claim counted twice distorts coverage directly.
    pro_evidence = _dedup_claims(merged("pro_evidence_cited"))
    con_evidence = _dedup_claims(merged("con_evidence_cited"))

    # The FT scorer, when online, supplies the raw numbers — but the blind audit
    # still governs the evidence ceiling, so FT cannot certify evidence that the
    # extraction pass could not find.
    ft_used = isinstance(ft, dict) and ft is not None
    if ft_used:
        for src, dst in ((ft.get("pro_scores", {}), pro_scores), (ft.get("con_scores", {}), con_scores)):
            for c in ("evidence", "logic", "relevance"):
                if c in src:
                    dst[c] = float(src[c])

    _apply_evidence_cap(pro_scores, pro_evidence)
    _apply_evidence_cap(con_scores, con_evidence)

    # Retrieval-grounded verification. Runs after extraction because it consumes
    # the extracted specifics rather than the raw transcript — the scorer says what
    # was cited, the corpus says whether it holds. Both sides check concurrently.
    pro_grounding, con_grounding = await asyncio.gather(
        _ground_side(pro_evidence), _ground_side(con_evidence), return_exceptions=True,
    )
    pro_grounding = pro_grounding if isinstance(pro_grounding, dict) else None
    con_grounding = con_grounding if isinstance(con_grounding, dict) else None

    _apply_grounding(pro_scores, pro_grounding)
    _apply_grounding(con_scores, con_grounding)

    pro_rep = repetition_ratio([t["text"] for t in exchange if t["speaker"] == "pro"], prior_pro_texts or [])
    con_rep = repetition_ratio([t["text"] for t in exchange if t["speaker"] == "con"], prior_con_texts or [])
    pro_penalty, con_penalty = _repetition_penalty(pro_rep), _repetition_penalty(con_rep)

    pro_scores["total"] = _total(pro_scores, pro_penalty)
    con_scores["total"] = _total(con_scores, con_penalty)

    margin = round(pro_scores["total"] - con_scores["total"], 1)
    round_winner = "tie" if abs(margin) <= TIE_BAND else ("pro" if margin > 0 else "con")

    fallacies = _agreed_fallacy_claims(passes)
    invalid_labels = [
        f"{f.get('by', '?').upper()} misapplied \"{f.get('named')}\""
        for f in fallacies if f.get("valid") is False
    ]

    reasoning = _as_text(next((p.get("reasoning") for p in passes if p.get("reasoning")), ""))

    return {
        "pro_scores":            pro_scores,
        "con_scores":            con_scores,
        "round_winner":          round_winner,
        "reasoning":             reasoning,
        "winner_evidence":       "",
        "loser_weakness":        "",
        "fallacy_detected":      invalid_labels[0] if invalid_labels else None,
        "final_score_out_of_10": {"pro": pro_scores["total"], "con": con_scores["total"]},
        # Audit trail — why the scores are what they are.
        "audit": {
            "pro_evidence_cited":      pro_evidence,
            "con_evidence_cited":      con_evidence,
            "pro_unsupported_claims":  merged("pro_unsupported_claims"),
            "con_unsupported_claims":  merged("con_unsupported_claims"),
            "fallacy_claims":          fallacies,
            "pro_repetition":          round(pro_rep, 2),
            "con_repetition":          round(con_rep, 2),
            "pro_repetition_penalty":  pro_penalty,
            "con_repetition_penalty":  con_penalty,
            "pro_grounding":           pro_grounding,
            "con_grounding":           con_grounding,
            "verification_backend":    config.NLI_BACKEND if config.VERIFICATION_ENABLED else "disabled",
            "scorer":                  "kaggle-ft (audited)" if ft_used else "groq-blind-swap",
            "blind_passes":            len(passes),
            "label_disagreement":      round(abs(
                passes[0]["pro_scores"]["evidence"] - passes[-1]["pro_scores"]["evidence"]
            ), 1) if len(passes) > 1 else None,
        },
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

    # Decided here, in Python, from the scores. The old code let the language
    # model free-text the winner and the strongest round, so it could contradict
    # the totals it was handed — and did.
    margin = round(pro_total - con_total, 1)
    overall_winner = "tie" if abs(margin) <= TIE_BAND else ("pro" if margin > 0 else "con")
    win_key = "con_scores" if overall_winner == "con" else "pro_scores"
    strongest_round = max(
        range(len(all_rounds)), key=lambda i: all_rounds[i][win_key]["total"]
    ) + 1 if all_rounds else 1

    rounds_summary = "\n".join([
        f"R{i+1}: PRO={r['pro_scores']['total']} CON={r['con_scores']['total']} "
        f"Winner={r['round_winner'].upper()} — {r['reasoning']}"
        for i, r in enumerate(all_rounds)
    ])

    # Hand the verdict writer the extracted evidence, so it describes what was
    # actually cited instead of echoing whoever said "evidence-based" most.
    audit_lines = []
    for i, r in enumerate(all_rounds):
        a = r.get("audit", {})
        audit_lines.append(
            f"R{i+1} evidence actually cited — PRO: {a.get('pro_evidence_cited') or 'NONE'} | "
            f"CON: {a.get('con_evidence_cited') or 'NONE'}"
        )
    audit_block = "\n".join(audit_lines)

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

    outcome = (
        f"OUTCOME (already decided — describe, do not recompute): "
        f"{'TIE' if overall_winner == 'tie' else overall_winner.upper() + ' WINS'}. "
        f"Strongest round for the winner: Round {strongest_round}."
    )

    response = await groq_call(groq_client.chat.completions.create,
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": FINAL_VERDICT_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Topic: {topic}\n\n"
                f"Scores:\n{rounds_summary}\n\n"
                f"{audit_block}"
                f"{args_block}\n\n"
                f"PRO total: {pro_total}/{max_possible} | CON total: {con_total}/{max_possible}\n"
                f"{outcome}\n\n"
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
        result = {
            "score_explanation": {
                "pro": f"PRO earned {pro_total} total points across {len(all_rounds)} rounds.",
                "con": f"CON earned {con_total} total points across {len(all_rounds)} rounds."
            },
            "winner": {
                "decisive_argument": "Stronger evidence and argument consistency throughout the debate.",
                "points": ["Maintained key arguments across all rounds."],
            },
            "loser": {
                "fatal_weakness": "Scored lower across the overall debate rounds.",
                "missed_points": ["Could have addressed opponent counterarguments more directly."]
            },
            "verdict": (
                f"The debate ended in a tie at {pro_total} points each. "
                if overall_winner == "tie" else
                f"{overall_winner.upper()} won the debate with {max(pro_total, con_total)} points "
                f"versus {min(pro_total, con_total)} points. "
            ) + "The winning side cited more checkable evidence across rounds. "
                "Key turning point occurred in the mid-round exchanges."
        }

    # Shape first: the model is free to return the right content in the wrong
    # container, and the client renders these fields directly.
    _coerce_verdict_strings(result)

    # Deterministic fields always win over anything the model returned.
    result["overall_winner"] = overall_winner
    result["pro_total"] = pro_total
    result["con_total"] = con_total
    result["margin"] = abs(margin)
    result["is_tie"] = overall_winner == "tie"
    result["accuracy"] = {
        "pro": round((pro_total / max_possible) * 100, 1) if max_possible else 0.0,
        "con": round((con_total / max_possible) * 100, 1) if max_possible else 0.0,
    }
    result.setdefault("winner", {})
    result["winner"]["strongest_round"] = strongest_round

    # Per-round winners and margins come from the scores, never from the model.
    model_rounds = {r.get("r"): r for r in (result.get("rounds") or []) if isinstance(r, dict)}
    result["rounds"] = [
        {
            "r": i + 1,
            "winner": r["round_winner"],
            "margin": round(abs(r["pro_scores"]["total"] - r["con_scores"]["total"]), 1),
            # _as_text, not a bare slice: a dict here raises TypeError on [:80].
            "swing": (_as_text(model_rounds.get(i + 1, {}).get("swing"))
                      or _as_text(r.get("reasoning")))[:80],
        }
        for i, r in enumerate(all_rounds)
    ]

    # Surface only fallacy accusations the judge confirmed were misapplied.
    result["fallacies"] = [
        f"{f.get('by', '?').upper()} misapplied \"{f.get('named')}\""
        for r in all_rounds
        for f in r.get("audit", {}).get("fallacy_claims", [])
        if _is_real_fallacy_claim(f) and f.get("valid") is False
    ][:6]

    return result
