"""
Score gold-label pairs with ARGUS, then calibrate the conformal predictor.

Two questions, one run:

  1. Does ARGUS rank arguments the way people did? Spearman rho against the
     human quality scores, plus verdict agreement and Cohen's kappa.
  2. Given those scores, what verdict sets does conformal prediction produce, and
     does the coverage guarantee hold on real data rather than synthetic?

Scoring is cached per pair so a rate-limited run can be resumed rather than
restarted — at 6000 TPM a few hundred pairs takes a while, and losing that to a
dropped connection twice is enough to learn the lesson.

Usage:
    python -m eval.calibrate --limit 60        # score 60 pairs
    python -m eval.calibrate --report          # analyse what is already scored
"""

import argparse
import asyncio
import json
import math
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
from debate.conformal import ConformalPredictor

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
PAIRS = os.path.join(DATA, "pairs.json")
SCORED = os.path.join(DATA, "scored_pairs.json")


# ── Statistics, written out rather than pulled from scipy ────────────────────
# The project already runs on a RAM-constrained machine; these are short enough
# that adding scipy for them is not worth it.

def _ranks(xs: list[float]) -> list[float]:
    """Average ranks, so ties do not distort the correlation."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        shared = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def spearman(a: list[float], b: list[float]) -> float | None:
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    n = len(a)
    ma, mb = sum(ra) / n, sum(rb) / n
    num = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    den = math.sqrt(sum((x - ma) ** 2 for x in ra) * sum((y - mb) ** 2 for y in rb))
    return round(num / den, 4) if den else None


def cohen_kappa(a: list[str], b: list[str]) -> float | None:
    """Agreement above chance. Raw agreement flatters a skewed label set."""
    if not a:
        return None
    labels = sorted(set(a) | set(b))
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((a.count(l) / n) * (b.count(l) / n) for l in labels)
    return round((observed - expected) / (1 - expected), 4) if expected < 1 else None


# ── Scoring ──────────────────────────────────────────────────────────────────

async def score_pair(pair: dict, require_scorer: str | None = None) -> dict | None:
    """
    Run one pair through the real judge as a single-exchange round.

    judge_round is used unmodified so the measurement covers the actual scoring
    path — blind swap, extraction, grounding, caps — rather than a simplified
    stand-in that would not reflect what the system does.

    require_scorer drops any pair the requested scorer did not handle. The first
    run mixed 16 kaggle-ft rounds with 4 groq-blind-swap rounds, because the
    ngrok tunnel dropped partway, and a metric computed across two different
    judges measures neither of them. Discarding the round costs one pair;
    keeping it silently corrupts every number derived from the set.
    """
    from agents.judge_agent import judge_round

    exchange = [
        {"speaker": "pro", "sub_round": 1, "text": pair["pro_argument"]},
        {"speaker": "con", "sub_round": 1, "text": pair["con_argument"]},
    ]
    try:
        v = await judge_round(pair["topic"], 1, exchange)
    except Exception as e:
        print(f"    scoring failed: {type(e).__name__}: {str(e)[:120]}")
        return None

    scorer = v["audit"]["scorer"]
    if require_scorer and require_scorer not in scorer:
        print(f"    skipped — scored by {scorer!r}, run requires {require_scorer!r}")
        return None

    return {
        **pair,
        "pro_total": v["pro_scores"]["total"],
        "con_total": v["con_scores"]["total"],
        "argus_winner": v["round_winner"],
        "scorer": v["audit"]["scorer"],
        "pro_coverage": (v["audit"].get("pro_grounding") or {}).get("coverage"),
        "con_coverage": (v["audit"].get("con_grounding") or {}).get("coverage"),
    }


def _load(path: str, default):
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


async def run(limit: int, require_scorer: str | None = None, drop_mismatched: bool = False) -> None:
    pairs = _load(PAIRS, [])
    if not pairs:
        print(f"no pairs at {PAIRS} — run `python -m eval.datasets` first")
        return

    scored = _load(SCORED, [])

    if drop_mismatched and require_scorer:
        before = len(scored)
        scored = [s for s in scored if require_scorer in s.get("scorer", "")]
        if before != len(scored):
            print(f"dropped {before - len(scored)} round(s) not scored by {require_scorer!r}\n")

    done = {(s["topic"], s["pro_argument"][:60]) for s in scored}
    todo = [p for p in pairs if (p["topic"], p["pro_argument"][:60]) not in done][:limit]

    print(f"{len(scored)} already scored, {len(todo)} to do"
          f"{f' (requiring {require_scorer})' if require_scorer else ''}\n")
    for i, pair in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {pair['topic'][:56]}")
        result = await score_pair(pair, require_scorer=require_scorer)
        if result:
            scored.append(result)
            print(f"    argus pro={result['pro_total']} con={result['con_total']} "
                  f"-> {result['argus_winner']}   human -> {pair['true_winner']}")
            # Written every iteration: a rate-limited run that dies partway keeps
            # everything it paid for.
            with open(SCORED, "w", encoding="utf-8") as f:
                json.dump(scored, f, indent=1)

    print(f"\n{len(scored)} scored -> {SCORED}")


def report() -> None:
    scored = _load(SCORED, [])
    if len(scored) < 10:
        print(f"only {len(scored)} scored pairs — need more before this means anything")
        return

    human_margin = [s["human_margin"] for s in scored]
    argus_margin = [s["pro_total"] - s["con_total"] for s in scored]
    human_win = [s["true_winner"] for s in scored]
    argus_win = [s["argus_winner"] for s in scored]

    agree = sum(1 for a, b in zip(human_win, argus_win) if a == b) / len(scored)
    decisive = [s for s in scored if s["true_winner"] != "tie"]
    agree_decisive = (sum(1 for s in decisive if s["true_winner"] == s["argus_winner"]) / len(decisive)
                      if decisive else None)

    from collections import Counter
    by_scorer = Counter(s["scorer"] for s in scored)

    print(f"n = {len(scored)}")
    print(f"  scorers used            {dict(by_scorer)}")
    if len(by_scorer) > 1:
        # Metrics pooled across judges describe neither. Surfaced loudly because
        # the first run silently mixed 16 kaggle-ft rounds with 4 groq ones.
        print("  WARNING: mixed scorers — pooled metrics below are not attributable "
              "to any single judge. Re-run with --require-scorer --drop-mismatched.")
    print(f"  verdict agreement       {agree:.3f}")
    print(f"  agreement (non-tie)     {agree_decisive:.3f}" if agree_decisive is not None else "")
    print(f"  Cohen's kappa           {cohen_kappa(human_win, argus_win)}")
    print(f"  Spearman rho (margins)  {spearman(human_margin, argus_margin)}")

    covs = [s[k] for s in scored for k in ("pro_coverage", "con_coverage") if s.get(k) is not None]
    if covs:
        print(f"  mean grounding coverage {sum(covs) / len(covs):.3f}")

    # ── Conformal on real data ───────────────────────────────────────────────
    print(f"\n-- conformal (alpha={config.CONFORMAL_ALPHA}) --")
    rounds = [{"pro_total": s["pro_total"], "con_total": s["con_total"],
               "true_winner": s["true_winner"]} for s in scored]
    split = len(rounds) // 2
    if split < ConformalPredictor(alpha=config.CONFORMAL_ALPHA).min_calibration_size:
        print(f"  need >= {ConformalPredictor(alpha=config.CONFORMAL_ALPHA).min_calibration_size * 2} "
              f"scored pairs to calibrate at this alpha; have {len(rounds)}")
        return

    pred = ConformalPredictor(alpha=config.CONFORMAL_ALPHA).fit(rounds[:split])
    result = pred.evaluate(rounds[split:])
    for k, v in result.items():
        print(f"  {k:<22} {v}")

    path = pred.fit(rounds).save()
    print(f"\ncalibrated on all {len(rounds)} rounds -> {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=40, help="pairs to score this run")
    ap.add_argument("--report", action="store_true", help="analyse existing scores only")
    ap.add_argument("--require-scorer", default="kaggle-ft",
                    help="only keep rounds this scorer handled; '' to allow any")
    ap.add_argument("--drop-mismatched", action="store_true",
                    help="also discard already-scored rounds from other scorers")
    args = ap.parse_args()

    if args.report:
        report()
    else:
        asyncio.run(run(args.limit, require_scorer=args.require_scorer or None,
                       drop_mismatched=args.drop_mismatched))
        report()
