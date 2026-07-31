"""
Retrieval-grounded claim verification.

The judge's evidence score used to be whatever the scoring model said it was.
A debater who wrote "as the archaeological record clearly shows" could be scored
as evidence-based by a model that never checked whether anything was actually
shown. The extraction pass in judge_agent caught some of this, but extraction is
still the same model grading its own reading.

This module closes the loop: every specific a debater cited is matched against a
retrieval corpus and labelled SUPPORTED / REFUTED / NEI by an entailment check
that is independent of the scorer. The result bounds the evidence score from
above — the judge cannot award grounding it cannot find — and a claim the corpus
actively contradicts is penalised as fabrication.

NEI is deliberately not punished. A corpus that has nothing to say about a claim
is a gap in the corpus, not a fault of the debater, so the ceiling only tightens
in proportion to how much the corpus could actually adjudicate. As the corpus
grows, verification coverage rises and the ceiling binds more often — which is
the quantity worth reporting.
"""

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import config
from debate.vector_store import get_vector_store

logger = logging.getLogger("argus.verifier")

SUPPORTED = "SUPPORTED"
REFUTED = "REFUTED"
NEI = "NEI"


@dataclass
class ClaimVerdict:
    claim: str
    label: str = NEI
    confidence: float = 0.0
    evidence: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "claim": self.claim,
            "label": self.label,
            "confidence": round(self.confidence, 2),
            "evidence": [
                {"text": e.get("text", "")[:240], "source": (e.get("metadata") or {}).get("source", "")}
                for e in self.evidence
            ],
        }


# ── Retrieval ────────────────────────────────────────────────────────────────

def retrieve_for_claim(claim: str, top_k: int | None = None) -> list[dict]:
    """
    Passages the corpus offers for a claim, filtered by distance.

    Chroma returns its nearest neighbours whether or not they are relevant, so an
    unfiltered top-k always looks like evidence. Anything beyond the distance
    threshold is treated as the corpus having no opinion.
    """
    vs = get_vector_store()
    if not vs.is_available:
        return []
    hits = vs.query_evidence(query=claim, top_k=top_k or config.VERIFIER_TOP_K)
    return [h for h in hits if h.get("distance", 99.0) <= config.RETRIEVAL_MAX_DISTANCE]


# ── Entailment backends ──────────────────────────────────────────────────────
#
# Three backends, selected by NLI_BACKEND. They differ in cost and in what they
# require to be installed, not in their contract: each maps (claim, passages) to
# a label and a confidence.
#
#   groq    — default. No local model, no torch, reuses the existing API key.
#   local   — cross-encoder NLI (deberta-v3-small). Deterministic and free per
#             call, so this is the one to use for paper eval runs; needs torch.
#   lexical — no dependencies at all. Content-word overlap. A floor, not a method.

_NLI_PROMPT = """You are a fact-checking entailment classifier. You are given claims made in a debate and, for each, passages retrieved from a reference corpus.

For each claim decide, using ONLY the passages provided:
- SUPPORTED: the passages state or directly imply the claim.
- REFUTED: a passage positively CONTRADICTS the claim — it asserts something that cannot be true
  at the same time as the claim (wrong date, wrong number, wrong attribution, opposite outcome).
- NEI: the passages do not settle it either way.

ABSENCE IS NOT CONTRADICTION. This is the most common mistake — do not make it. If the passages
simply do not mention the claim, or mention the general subject without addressing this specific
point, the answer is NEI. A true claim the corpus happens not to cover is NEI, never REFUTED.
REFUTED accuses the debater of stating a falsehood and is penalised as fabrication, so use it only
when you can point to the exact contradicting words.

To return REFUTED you MUST fill "contradicted_by" with the VERBATIM sentence from the passages
that does the contradicting. If you cannot quote one, the label is NEI.

Judge only against the passages. Do not use outside knowledge — a claim you personally believe is
true but that the passages do not cover is NEI, not SUPPORTED. Vague gestures ("studies show",
"history demonstrates") with no specific named content are NEI.

Return ONLY a JSON array, one object per claim, in the same order:
[{"i": int, "label": "SUPPORTED" | "REFUTED" | "NEI", "confidence": float between 0 and 1,
  "contradicted_by": "verbatim quote, required for REFUTED, else empty string"}]"""


def _strip_json(raw: str) -> str:
    raw = re.sub(r"<think>.*?</think>", "", raw or "", flags=re.DOTALL)
    raw = raw.replace("```json", "").replace("```", "").strip()
    start, end = raw.find("["), raw.rfind("]")
    return raw[start:end + 1] if start != -1 and end > start else raw


async def _entail_groq(items: list[tuple[str, list[dict]]]) -> list[tuple[str, float]]:
    """One call for every claim in the round — batching keeps judge latency flat."""
    from agents.judge_agent import groq_client  # shared client, shared key

    blocks = []
    for i, (claim, passages) in enumerate(items):
        ev = "\n".join(f"  - {p.get('text', '')}" for p in passages) or "  (no passages retrieved)"
        blocks.append(f"[{i}] CLAIM: {claim}\nPASSAGES:\n{ev}")

    response = await groq_client.chat.completions.create(
        model=config.NLI_MODEL,
        messages=[
            {"role": "system", "content": _NLI_PROMPT},
            {"role": "user", "content": "\n\n".join(blocks) + "\n\nReturn ONLY the JSON array."},
        ],
        max_tokens=700,
        temperature=0,
    )
    parsed = json.loads(_strip_json(response.choices[0].message.content))

    out: list[tuple[str, float, str]] = [(NEI, 0.0, "")] * len(items)
    for row in parsed:
        if not isinstance(row, dict):
            continue
        i = int(row.get("i", -1))
        label = str(row.get("label", NEI)).strip().upper()
        if 0 <= i < len(items) and label in (SUPPORTED, REFUTED, NEI):
            out[i] = (label, float(row.get("confidence", 0.0) or 0.0),
                      str(row.get("contradicted_by", "") or ""))
    return out


_local_pipe = None


def _load_local_nli():
    global _local_pipe
    if _local_pipe is None:
        from transformers import pipeline  # imported lazily — torch is optional
        _local_pipe = pipeline("text-classification", model=config.NLI_LOCAL_MODEL, top_k=None)
    return _local_pipe


async def _entail_local(items: list[tuple[str, list[dict]]]) -> list[tuple[str, float]]:
    """
    Cross-encoder NLI, premise=passage, hypothesis=claim. A claim is SUPPORTED if
    any single passage entails it, REFUTED if any contradicts it and none entail.
    """
    pipe = _load_local_nli()

    def run() -> list[tuple[str, float]]:
        out = []
        for claim, passages in items:
            if not passages:
                out.append((NEI, 0.0, ""))
                continue
            best_e, best_c, best_c_text = 0.0, 0.0, ""
            for p in passages:
                text = p.get("text", "")
                scores = {s["label"].lower(): s["score"] for s in pipe({"text": text, "text_pair": claim})[0]}
                best_e = max(best_e, scores.get("entailment", 0.0))
                if scores.get("contradiction", 0.0) > best_c:
                    best_c, best_c_text = scores["contradiction"], text
            if best_e >= config.NLI_ENTAIL_THRESHOLD:
                out.append((SUPPORTED, best_e, ""))
            elif best_c >= config.NLI_CONTRADICT_THRESHOLD:
                # The cross-encoder scores contradiction directly against a
                # specific premise, so the premise itself is the citation.
                out.append((REFUTED, best_c, best_c_text))
            else:
                out.append((NEI, max(best_e, best_c), ""))
        return out

    return await asyncio.get_running_loop().run_in_executor(None, run)


_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "for", "with",
    "is", "was", "are", "were", "be", "been", "that", "this", "it", "as", "by", "from",
}


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", (text or "").lower()) if w not in _STOPWORDS and len(w) > 2}


async def _entail_lexical(items: list[tuple[str, list[dict]]]) -> list[tuple[str, float]]:
    """Overlap fallback. Cannot detect contradiction, so it never returns REFUTED."""
    out = []
    for claim, passages in items:
        cw = _content_words(claim)
        if not cw or not passages:
            out.append((NEI, 0.0, ""))
            continue
        best = max(len(cw & _content_words(p.get("text", ""))) / len(cw) for p in passages)
        out.append((SUPPORTED, best, "") if best >= config.LEXICAL_SUPPORT_RATIO else (NEI, best, ""))
    return out


_BACKENDS = {"groq": _entail_groq, "local": _entail_local, "lexical": _entail_lexical}


# ── Public API ───────────────────────────────────────────────────────────────

async def verify_claims(claims: list[str]) -> list[ClaimVerdict]:
    """
    Label each claim against the corpus. Never raises: a verification channel that
    can take the whole judge down with it would be worse than no channel, so any
    backend failure degrades to all-NEI, which leaves scoring exactly as it was
    before this module existed.
    """
    cleaned = [c.strip() for c in claims if isinstance(c, str) and c.strip()]
    if not cleaned:
        return []

    items = [(c, retrieve_for_claim(c)) for c in cleaned]
    backend = _BACKENDS.get(config.NLI_BACKEND, _entail_groq)

    try:
        labels = await backend(items)
    except Exception as e:
        logger.warning(f"NLI backend '{config.NLI_BACKEND}' failed, defaulting to NEI: {e}")
        labels = [(NEI, 0.0, "")] * len(items)

    return [
        ClaimVerdict(claim=c, **_guard_refutation(lab, conf, quote, ps), evidence=ps)
        for (c, ps), (lab, conf, quote) in zip(items, labels)
    ]


def _guard_refutation(label: str, confidence: float, quote: str, passages: list[dict]) -> dict:
    """
    Refutation carries a burden of proof; support does not.

    A REFUTED label accuses a debater of fabricating, costs them a penalty on top
    of the ceiling, and has been observed flipping a round's winner — all from a
    backend conflating "the corpus does not mention this" with "the corpus says
    this is false". A true claim the corpus simply does not cover must be NEI.

    So REFUTED survives only when the backend can point at the contradicting text
    AND that text actually came from a retrieved passage. Anything else is
    downgraded to NEI, which is inert. The asymmetry is deliberate: a missed
    fabrication costs a little precision, an invented one corrupts the verdict.
    """
    if label != REFUTED:
        return {"label": label, "confidence": confidence}

    quoted = _normalise(quote)
    if not quoted:
        logger.info("REFUTED downgraded to NEI: no contradicting text supplied")
        return {"label": NEI, "confidence": 0.0}

    # The quote has to be traceable to something actually retrieved — otherwise
    # the backend is refuting from its own parametric memory, not the corpus.
    if not any(quoted in _normalise(p.get("text", "")) for p in passages):
        logger.info(f"REFUTED downgraded to NEI: quote not found in retrieved passages: {quote[:80]!r}")
        return {"label": NEI, "confidence": 0.0}

    return {"label": REFUTED, "confidence": confidence}


def _normalise(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9\s]", " ", (text or "").lower()).split())


def grounding_report(verdicts: list[ClaimVerdict]) -> dict[str, Any]:
    """
    Turn labels into the two numbers that touch the score: a ceiling on evidence,
    and a fabrication penalty.

    The ceiling is a function of precision over ADJUDICABLE claims only — those
    the corpus supported or refuted. Claims it could not reach (NEI) are excluded
    from the denominator, so a thin corpus produces a loose ceiling rather than a
    uniformly crushed score. With zero adjudicable claims the ceiling is 10.0 and
    this module is a no-op by construction.
    """
    n = len(verdicts)
    supported = sum(1 for v in verdicts if v.label == SUPPORTED)
    refuted = sum(1 for v in verdicts if v.label == REFUTED)
    adjudicable = supported + refuted

    if adjudicable == 0:
        cap, precision = 10.0, None
    else:
        precision = supported / adjudicable
        cap = round(config.GROUNDING_FLOOR + (10.0 - config.GROUNDING_FLOOR) * precision, 1)

    return {
        "claims_checked": n,
        "supported": supported,
        "refuted": refuted,
        "nei": n - adjudicable,
        # Share of claims the corpus could rule on. Rises with corpus size and is
        # the headline number for how much of the score is actually grounded.
        "coverage": round(adjudicable / n, 2) if n else 0.0,
        "precision": round(precision, 2) if precision is not None else None,
        "evidence_cap": cap,
        "fabrication_penalty": round(min(config.FABRICATION_MAX_PENALTY,
                                         refuted * config.FABRICATION_WEIGHT), 1),
        "verdicts": [v.as_dict() for v in verdicts],
    }
