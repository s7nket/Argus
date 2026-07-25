"""
Replays labelled rounds through every scorer and prints the comparison table.

    python -m eval.evaluate                      # all available arms
    python -m eval.evaluate --arms blind legacy  # just those two
    python -m eval.evaluate --json out.json      # also dump raw results

Arms
  legacy  the original rubric: three undefined criteria, no scale anchors, PRO/CON
          labels visible, one pass. This is what produced the 7.3-8.5 scores.
  blind   the current pipeline: extraction before scoring, anchored scale, two
          passes with the debater labels swapped, evidence caps applied.
  ft      the fine-tuned 4B scorer on Kaggle via FT_JUDGE_URL, raw and unaudited.

What the numbers answer
  agreement / kappa  does the scorer pick the same winner a human did?
  compression        what fraction of its scores land in the narrow 7.0-8.5 band?
                     A scorer can agree with humans often and still be useless if
                     every score is 8-ish, because the margin carries no signal.
  label bias         mean gap between the two swapped passes. Large means the
                     scorer is reading the labels rather than the arguments.
                     (blind arm only — it is the arm that runs both passes.)
  pro rate           how often each scorer picks PRO. Compare against the gold
                     pro rate: a scorer that always favours one chair is biased
                     by position, which label-swapping cannot fix.
"""

import argparse
import asyncio
import json

from config import TIE_BAND
from agents.judge_agent import (
    _apply_evidence_cap,
    _clean_response,
    _format_exchange_for_judge,
    _score_blind_once,
    _get_ft_round_scores,
    _total,
    groq_client,
    JUDGE_MODEL,
)
from eval import metrics
from eval.dataset import DEFAULT_PATH, RoundRecord, labelled, load

# The exact pre-fix rubric, kept here so the improvement can be measured rather
# than asserted. Never imported by production code.
LEGACY_ROUND_SCORING_PROMPT = """You are a strict and impartial AI debate judge.

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


def _winner(pro_total: float, con_total: float) -> str:
    margin = round(pro_total - con_total, 1)
    return "tie" if abs(margin) <= TIE_BAND else ("pro" if margin > 0 else "con")


def _avg_total(scores: dict) -> float:
    return round((scores["evidence"] + scores["logic"] + scores["relevance"]) / 3, 1)


# ── Arms ─────────────────────────────────────────────────────────────────────

async def arm_legacy(rec: RoundRecord) -> dict:
    response = await groq_client.chat.completions.create(
        model=JUDGE_MODEL,
        messages=[
            {"role": "system", "content": LEGACY_ROUND_SCORING_PROMPT},
            {"role": "user", "content": (
                f"Topic: {rec.resolution}\n\n"
                f"Exchange:\n{_format_exchange_for_judge(rec.exchange)}\n\n"
                f"Score both agents. Return ONLY the JSON object."
            )},
        ],
        max_tokens=600,
        temperature=0,
    )
    raw = json.loads(_clean_response(response.choices[0].message.content))

    def side(key: str) -> dict:
        s = raw.get(key, {}) or {}
        return {c: float(s.get(c, 0) or 0) for c in ("evidence", "logic", "relevance")}

    pro, con = side("pro_scores"), side("con_scores")
    pro_t, con_t = _avg_total(pro), _avg_total(con)
    return {
        "pro_total": pro_t,
        "con_total": con_t,
        "winner": _winner(pro_t, con_t),
        "pro_scores": pro,
        "con_scores": con,
    }


async def arm_blind(rec: RoundRecord) -> dict:
    a, b = await asyncio.gather(
        _score_blind_once(rec.resolution, rec.exchange, swap=False),
        _score_blind_once(rec.resolution, rec.exchange, swap=True),
    )

    pro = {c: round((a["pro_scores"][c] + b["pro_scores"][c]) / 2, 1)
           for c in ("evidence", "logic", "relevance")}
    con = {c: round((a["con_scores"][c] + b["con_scores"][c]) / 2, 1)
           for c in ("evidence", "logic", "relevance")}

    pro_ev = a["pro_evidence_cited"] + b["pro_evidence_cited"]
    con_ev = a["con_evidence_cited"] + b["con_evidence_cited"]
    _apply_evidence_cap(pro, pro_ev)
    _apply_evidence_cap(con, con_ev)

    pro_t, con_t = _total(pro, 0.0), _total(con, 0.0)

    # How far the two swapped passes drifted — the label-bias signal.
    drift = metrics.mean([
        abs(a[f"{side}_scores"][c] - b[f"{side}_scores"][c])
        for side in ("pro", "con")
        for c in ("evidence", "logic", "relevance")
    ])

    return {
        "pro_total": pro_t,
        "con_total": con_t,
        "winner": _winner(pro_t, con_t),
        "pro_scores": pro,
        "con_scores": con,
        "label_drift": round(drift, 2),
        "pro_evidence_count": len(pro_ev),
        "con_evidence_count": len(con_ev),
    }


async def arm_ft(rec: RoundRecord) -> dict:
    result = await _get_ft_round_scores(rec.resolution, _format_exchange_for_judge(rec.exchange))
    if not result:
        raise RuntimeError("FT scorer unreachable")

    def side(key: str) -> dict:
        s = result.get(key, {}) or {}
        return {c: float(s.get(c, 0) or 0) for c in ("evidence", "logic", "relevance")}

    pro, con = side("pro_scores"), side("con_scores")
    pro_t, con_t = _avg_total(pro), _avg_total(con)
    return {
        "pro_total": pro_t,
        "con_total": con_t,
        "winner": _winner(pro_t, con_t),
        "pro_scores": pro,
        "con_scores": con,
    }


ARMS = {"legacy": arm_legacy, "blind": arm_blind, "ft": arm_ft}


# ── Runner ───────────────────────────────────────────────────────────────────

async def run_arm(name: str, records: list[RoundRecord], concurrency: int) -> list[dict | None]:
    fn = ARMS[name]
    sem = asyncio.Semaphore(concurrency)
    failures = {"n": 0}

    async def one(rec: RoundRecord, i: int) -> dict | None:
        async with sem:
            for attempt in range(3):
                try:
                    out = await fn(rec)
                    print(f"  {name}: {i + 1}/{len(records)}", end="\r")
                    return out
                except Exception as e:
                    if attempt == 2:
                        failures["n"] += 1
                        print(f"\n  {name} failed on {rec.key}: {e}")
                        return None
                    await asyncio.sleep(2 * (attempt + 1))   # rate-limit backoff

    results = await asyncio.gather(*(one(r, i) for i, r in enumerate(records)))
    print(f"  {name}: {len(records) - failures['n']}/{len(records)} scored" + " " * 20)
    return list(results)


def report(records: list[RoundRecord], by_arm: dict[str, list[dict | None]]) -> None:
    gold = [r.gold_winner for r in records]
    gold_pro_rate = gold.count("pro") / len(gold) if gold else 0.0

    print("\n" + "=" * 92)
    print(f"EVAL - {len(records)} labelled rounds   "
          f"(gold: {gold.count('pro')} pro / {gold.count('con')} con / {gold.count('tie')} tie)")
    print("=" * 92)
    print(f"{'arm':<9}{'n':>5}{'agree':>8}{'kappa':>8}{'corr':>8}{'compress':>10}"
          f"{'spread':>10}{'pro rate':>10}{'drift':>8}")
    print("-" * 92)

    for arm, results in by_arm.items():
        pairs = [(r, g) for r, g in zip(results, gold) if r is not None]
        if not pairs:
            print(f"{arm:<9}{'-':>5}  no successful runs")
            continue

        preds = [r["winner"] for r, _ in pairs]
        golds = [g for _, g in pairs]
        totals = [t for r, _ in pairs for t in (r["pro_total"], r["con_total"])]
        margins = [r["pro_total"] - r["con_total"] for r, _ in pairs]
        gold_dir = [{"pro": 1.0, "con": -1.0, "tie": 0.0}[g] for g in golds]
        drifts = [r["label_drift"] for r, _ in pairs if "label_drift" in r]

        print(
            f"{arm:<9}{len(pairs):>5}"
            f"{metrics.agreement(preds, golds):>7.0%}"
            f"{metrics.cohens_kappa(preds, golds):>8.2f}"
            f"{metrics.pearson(margins, gold_dir):>8.2f}"
            f"{metrics.compression(totals):>9.0%}"
            f"{metrics.stdev(totals):>10.2f}"
            f"{preds.count('pro') / len(preds):>9.0%}"
            f"{(metrics.mean(drifts) if drifts else float('nan')):>8.2f}"
        )

    print("-" * 92)
    print(f"{'gold':<9}{len(gold):>5}{'-':>8}{'-':>8}{'-':>8}{'-':>10}{'-':>10}{gold_pro_rate:>9.0%}")

    print("\nscore spread (0-10, flat and wide is healthy):")
    for arm, results in by_arm.items():
        totals = [t for r in results if r for t in (r["pro_total"], r["con_total"])]
        if totals:
            print(f"  {arm:<8} {metrics.histogram(totals)}  "
                  f"min {min(totals):.1f}  mean {metrics.mean(totals):.1f}  max {max(totals):.1f}")

    names = [a for a, r in by_arm.items() if any(x is not None for x in r)]
    if len(names) > 1:
        print("\nscorer-vs-scorer agreement:")
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                both = [(x, y) for x, y in zip(by_arm[a], by_arm[b]) if x and y]
                if both:
                    pa = [x["winner"] for x, _ in both]
                    pb = [y["winner"] for _, y in both]
                    print(f"  {a} vs {b}: {metrics.agreement(pa, pb):.0%} ({len(both)} rounds)")

    print("\nhow to read this:")
    print("  compression high + agreement high  -> scorer is right but its margins mean nothing")
    print("  drift above ~0.5                   -> scorer reacts to labels, not arguments")
    print("  pro rate far from gold pro rate    -> position bias; swapping labels will not fix it")
    print("  kappa near 0                       -> no better than guessing the majority outcome")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--arms", nargs="+", choices=list(ARMS), default=["legacy", "blind", "ft"])
    ap.add_argument("--limit", type=int, help="only evaluate the first N labelled rounds")
    ap.add_argument("--concurrency", type=int, default=3, help="parallel scorer calls")
    ap.add_argument("--json", help="write raw per-round results here")
    args = ap.parse_args()

    records = labelled(load(args.path))
    if not records:
        print(f"No labelled rounds at {args.path}.\n"
              f"  python -m eval.capture   then   python -m eval.label")
        return
    if args.limit:
        records = records[:args.limit]

    if len(records) < 20:
        print(f"WARNING: only {len(records)} labelled rounds. Treat these numbers as directional; "
              f"aim for 30+.\n")

    by_arm: dict[str, list[dict | None]] = {}
    for arm in args.arms:
        print(f"running arm: {arm}")
        by_arm[arm] = await run_arm(arm, records, args.concurrency)

    report(records, by_arm)

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({
                "rounds": [{"key": r.key, "topic": r.topic, "gold": r.gold_winner} for r in records],
                "results": by_arm,
            }, f, indent=2)
        print(f"\nraw results -> {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
