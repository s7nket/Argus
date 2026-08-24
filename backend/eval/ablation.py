"""
Ablation: the same gold pairs, scored by the rubric ARGUS started with.

    python -m eval.ablation --limit 20      # score 20 more pairs (resumable)
    python -m eval.ablation --report        # compare arms, no network calls

The baselines in eval.baselines answer "is the judge better than a heuristic".
This answers the different and more important question: "did the machinery we
added do anything". It re-scores the pairs already in data/scored_pairs.json
using LEGACY_ROUND_SCORING_PROMPT — three undefined criteria, PRO and CON
visible, one pass, no extraction step, no grounding, no caps, no tie band —
and reports both arms against the same human labels.

Cost. One call per pair, single pass, temperature 0. That is roughly half the
token cost of the full pipeline, but it is still ~1.4k tokens per pair, so a
full sweep of the current set runs close to a free-tier daily allowance and
should be given a clean quota day. --limit exists so the run can be split
across days; scored pairs are written after every pair and skipped on re-entry.

Reporting an arm that is not fully scored would compare a 57-pair judge against
a 20-pair one, so --report refuses to print unless both arms cover the same
pairs, and compares only the intersection.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re

from agents.judge_agent import (
    _clean_response,
    _format_exchange_for_judge,
    groq_client,
    JUDGE_MODEL,
)
from config import TIE_BAND
from eval.calibrate import SCORED, cohen_kappa, spearman
from eval.evaluate import LEGACY_ROUND_SCORING_PROMPT
from llm_retry import groq_call

LEGACY_SCORED = os.path.join(os.path.dirname(SCORED), "scored_pairs_legacy.json")


_ARITHMETIC = re.compile(r"(:\s*)(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)(\s*[,}])")

# How often the legacy arm returned an expression where a number was required.
# Counted rather than silently repaired, because it is evidence for the claim in
# Section IV-E that totals must be computed in code: the rubric asks the model to
# divide, and a third of the time it answers with the division itself.
arithmetic_repairs = 0


def _repair_arithmetic(text: str) -> str:
    """Evaluate `"total": 10.0/3` in place so the object parses.

    The match is anchored between a colon and the following comma or brace, so a
    date or ratio inside a reasoning string is not touched. The repaired value is
    discarded anyway — totals are recomputed from the three criteria below — but
    without this the whole response is unparseable and the pair is lost, and pairs
    lost this way are not lost at random.
    """
    global arithmetic_repairs

    def sub(m: "re.Match[str]") -> str:
        global arithmetic_repairs
        arithmetic_repairs += 1
        num, den = float(m.group(2)), float(m.group(3))
        return f"{m.group(1)}{(num / den if den else 0.0):.4f}{m.group(4)}"

    return _ARITHMETIC.sub(sub, text)


def _winner(pro: float, con: float) -> str:
    """The legacy arm had no tie band. It is applied here anyway, because
    otherwise the arms differ in two ways at once and the comparison stops
    being an ablation of the rubric."""
    return "tie" if abs(pro - con) <= TIE_BAND else ("pro" if pro > con else "con")


async def score_legacy(pair: dict) -> dict | None:
    exchange = [
        {"speaker": "pro", "sub_round": 1, "text": pair["pro_argument"]},
        {"speaker": "con", "sub_round": 1, "text": pair["con_argument"]},
    ]
    try:
        response = await groq_call(
            groq_client.chat.completions.create,
            model=JUDGE_MODEL,
            messages=[
                {"role": "system", "content": LEGACY_ROUND_SCORING_PROMPT},
                {"role": "user", "content": (
                    f"Topic: {pair['topic']}\n\n"
                    f"Exchange:\n{_format_exchange_for_judge(exchange)}\n\n"
                    f"Score both agents. Return ONLY the JSON object."
                )},
            ],
            max_tokens=600,
            temperature=0,
        )
        raw = json.loads(_repair_arithmetic(_clean_response(
            response.choices[0].message.content)))
    except Exception as e:
        print(f"    failed: {type(e).__name__}: {str(e)[:110]}")
        return None

    def total(key: str) -> float:
        s = raw.get(key, {}) or {}
        vals = [float(s.get(c, 0) or 0) for c in ("evidence", "logic", "relevance")]
        return round(sum(vals) / len(vals), 2)

    pro_t, con_t = total("pro_scores"), total("con_scores")
    return {
        "topic": pair["topic"],
        "true_winner": pair["true_winner"],
        "human_margin": pair["human_margin"],
        "pro_total": pro_t,
        "con_total": con_t,
        "legacy_winner": _winner(pro_t, con_t),
    }


def _key(rec: dict) -> tuple:
    """Identity of a gold pair, for resuming and for pairing the two arms.

    Not the topic. The 57 pairs cover only 14 topics, so keying on topic alone
    silently treats four distinct pairs as one already done — which is how the
    first sweep stopped at 24 records believing it had finished. Topic plus the
    human label and margin is unique across the set, and both a source pair and a
    legacy record carry all three, so no stored identifier or migration is needed.
    """
    return (rec["topic"], rec["true_winner"], round(float(rec["human_margin"]), 6))


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


async def run(limit: int) -> None:
    pairs = _load(SCORED)
    if not pairs:
        print(f"no pairs at {SCORED} — run `python -m eval.calibrate` first")
        return
    done = _load(LEGACY_SCORED)
    seen = {_key(d) for d in done}
    todo = [p for p in pairs if _key(p) not in seen][:limit]
    print(f"{len(done)} already scored, {len(todo)} to do this run "
          f"({len(pairs) - len(done) - len(todo)} left after)\n")

    for i, pair in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {pair['topic'][:56]}")
        result = await score_legacy(pair)
        if result is None:
            continue
        print(f"    legacy pro={result['pro_total']} con={result['con_total']} "
              f"-> {result['legacy_winner']}  (human {result['true_winner']})")
        done.append(result)
        with open(LEGACY_SCORED, "w", encoding="utf-8") as fh:
            json.dump(done, fh, indent=2, ensure_ascii=False)

    print(f"\n{len(done)} scored -> {LEGACY_SCORED}")
    if arithmetic_repairs:
        print(f"repaired {arithmetic_repairs} unevaluated arithmetic expression(s) "
              f"the legacy rubric returned where a number was required")


def _compression(totals: list[float], lo: float = 7.0, hi: float = 8.5) -> float:
    """Fraction of scores inside a narrow band. The original rubric's defining
    failure was that every score landed here, which makes the margin noise."""
    return sum(1 for t in totals if lo <= t <= hi) / len(totals) if totals else 0.0


def report() -> None:
    full, legacy = _load(SCORED), _load(LEGACY_SCORED)
    if not legacy:
        print(f"nothing at {LEGACY_SCORED} — run `python -m eval.ablation` first")
        return

    by_key = {_key(p): p for p in full}
    shared = [(by_key[_key(l)], l) for l in legacy if _key(l) in by_key]
    if not shared:
        print("no overlapping pairs between the arms")
        return
    if len(shared) < len(full):
        print(f"NOTE: comparing {len(shared)} of {len(full)} pairs — the legacy "
              f"arm is incomplete. Finish the sweep before quoting these.\n")

    gold = [f["true_winner"] for f, _ in shared]
    arms = {
        "legacy rubric": ([l["legacy_winner"] for _, l in shared],
                          [l["pro_total"] - l["con_total"] for _, l in shared],
                          [t for _, l in shared for t in (l["pro_total"], l["con_total"])]),
        "ARGUS full": ([f["argus_winner"] for f, _ in shared],
                       [f["pro_total"] - f["con_total"] for f, _ in shared],
                       [t for f, _ in shared for t in (f["pro_total"], f["con_total"])]),
    }
    human = [f["human_margin"] for f, _ in shared]

    print(f"\nablation on {len(shared)} gold pairs\n")
    print(f"{'arm':<16}{'agree':>8}{'kappa':>8}{'rho':>8}{'compressed':>12}")
    print("-" * 52)
    for name, (pred, margin, totals) in arms.items():
        agree = sum(1 for a, b in zip(pred, gold) if a == b) / len(gold)
        k, r = cohen_kappa(pred, gold), spearman(margin, human)
        print(f"{name:<16}{agree:>8.3f}"
              f"{(k if k is not None else float('nan')):>8.3f}"
              f"{(r if r is not None else float('nan')):>8.3f}"
              f"{_compression(totals):>11.1%}")
    print("\ncompressed = share of scores inside the 7.0-8.5 band, where a margin "
          "\ncarries no information. Lower is better.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=20, help="pairs to score this run")
    ap.add_argument("--report", action="store_true", help="compare arms, no calls")
    args = ap.parse_args()
    if args.report:
        report()
    else:
        asyncio.run(run(args.limit))


if __name__ == "__main__":
    main()
