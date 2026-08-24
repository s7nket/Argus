"""
Build the swap-invariant training set for ArguScore from real debate outcomes.

    python -m eval.build_training_set --out data/train

Replaces the IBM-derived set the current adapter was trained on. That set built
its labels with compute_scores(), which anchored every criterion on the same
human quality score, added keyword bonuses, injected +/-0.4 of random noise into
a target whose decision margin is 0.5, and fed transcript length directly into
the relevance score. Each of those shows up in what the resulting model does:
verdicts that follow the label, scores clustered in a dead band, and a margin
correlating with length more strongly than with human judgement.

What changes here:

  Real outcomes.   The target is which side a human audience voted for, on a
                   genuine multi-round debate, not a number we computed.
  No noise.        Nothing random enters a label.
  No length term.  Length is actively decorrelated from the outcome (below), so
                   the shortcut is not available to be learned.
  Swap pairs.      Every debate appears twice, labels exchanged and the target
                   flipped. This is the contribution: counterbalancing moved
                   from inference, where it costs a second pass every time, to
                   training, where it is paid once.

The evaluated debates are excluded. If the 100 in ft_debates.json leaked into
training, every number in the paper's Section VIII-B would be measuring memory.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from collections import Counter

from eval.calibrate import DATA
from eval.ddo import POOL, SAMPLED as DDO_SAMPLE
from eval.ft_eval import SAMPLED as FT_SAMPLE

SYSTEM = (
    "You are a debate judge. Read the exchange and decide which side argued "
    "better. Return ONLY a single-line JSON object:\n"
    '{"winner":"pro|con|tie","pro_total":float,"con_total":float}'
)

MIN_CHARS, MAX_CHARS = 800, 30000


def _exchange_text(debate: dict, swap: bool) -> str:
    out = []
    for t in debate["exchange"]:
        side = t["speaker"]
        if swap:
            side = "con" if side == "pro" else "pro"
        out.append(f"{side.upper()}: {t['text']}")
    return "\n\n".join(out)


def _totals(winner: str, margin: float) -> tuple[float, float]:
    """Scores for the two sides, derived from the human vote margin.

    The only supervision available is the outcome and how decisive it was, so
    that is all this encodes: a midpoint of 6.0 and a gap that grows with the
    margin, capped so a landslide does not train the model to emit 10 and 2.
    Per-criterion scores are deliberately NOT produced. There is no ground truth
    for evidence, logic and relevance separately, and inventing three numbers
    from one signal is exactly what produced a scorer whose three criteria were
    the same number in three hats.
    """
    gap = min(2.5, 0.5 + 0.25 * abs(margin))
    hi, lo = round(6.0 + gap / 2, 1), round(6.0 - gap / 2, 1)
    if winner == "pro":
        return hi, lo
    if winner == "con":
        return lo, hi
    return 6.0, 6.0


def _flip(winner: str) -> str:
    return {"pro": "con", "con": "pro"}.get(winner, "tie")


def _example(debate: dict, swap: bool) -> dict:
    """One training row. When swapped, the transcript's labels move and the
    target moves with them, so the pair teaches that the verdict is a property
    of the arguments and not of the name attached to them."""
    winner = _flip(debate["true_winner"]) if swap else debate["true_winner"]
    pro, con = _totals(winner, debate["human_margin"])
    target = {"winner": winner, "pro_total": pro, "con_total": con}
    return {
        "id": debate["id"],
        "swapped": swap,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content":
                f"Topic: {debate['topic']}\n\nExchange:\n{_exchange_text(debate, swap)}"},
            {"role": "assistant", "content": json.dumps(target, separators=(",", ":"))},
        ],
    }


def _decorrelate(debates: list, rng: random.Random) -> list:
    """Make the winner independent of transcript length.

    Within each length quartile the two outcomes are sampled to equal counts. A
    model cannot learn "longer side wins" from data where length carries no
    information about the outcome, which is a stronger guarantee than removing
    the length term from the label and hoping.
    """
    ordered = sorted(debates, key=lambda d: d["chars"])
    q = max(1, len(ordered) // 4)
    kept = []
    for i in range(0, len(ordered), q):
        bucket = ordered[i:i + q]
        pro = [d for d in bucket if d["true_winner"] == "pro"]
        con = [d for d in bucket if d["true_winner"] == "con"]
        n = min(len(pro), len(con))
        rng.shuffle(pro), rng.shuffle(con)
        kept.extend(pro[:n] + con[:n])
    rng.shuffle(kept)
    return kept


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=os.path.join(DATA, "train"))
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--val", type=int, default=150, help="debates held for validation")
    ap.add_argument("--test", type=int, default=250, help="debates held for test")
    args = ap.parse_args()

    with open(POOL, encoding="utf-8") as fh:
        pool = json.load(fh)
    # Both evaluated samples, not just one. The Section VIII-B experiment used
    # ft_debates.json and the pipeline run used ddo_debates.json; either leaking
    # into training would turn a reported result into a memorisation check.
    excluded = set()
    for path in (FT_SAMPLE, DDO_SAMPLE):
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                excluded |= {d["id"] for d in json.load(fh)}

    usable = [d for d in pool
              if MIN_CHARS <= d["chars"] <= MAX_CHARS
              and d["id"] not in excluded
              and d["true_winner"] in ("pro", "con")]
    print(f"pool {len(pool):,} -> {len(usable):,} usable "
          f"({len(excluded)} already-evaluated debates excluded)")

    rng = random.Random(args.seed)
    balanced = _decorrelate(usable, rng)
    print(f"length-decorrelated and outcome-balanced: {len(balanced):,}")

    # Split by debate before augmenting, so a debate and its swapped twin can
    # never straddle the train/test boundary.
    test, val, train = (balanced[:args.test],
                        balanced[args.test:args.test + args.val],
                        balanced[args.test + args.val:])

    os.makedirs(args.out, exist_ok=True)
    for name, split, augment in (("train", train, True),
                                 ("val", val, True),
                                 ("test", test, False)):
        rows = []
        for d in split:
            rows.append(_example(d, swap=False))
            if augment:
                rows.append(_example(d, swap=True))
        path = os.path.join(args.out, f"{name}.jsonl")
        with open(path, "w", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        wins = Counter(json.loads(r["messages"][-1]["content"])["winner"] for r in rows)
        chars = [len(r["messages"][1]["content"]) for r in rows]
        print(f"  {name:<6} {len(split):>4} debates -> {len(rows):>5} rows  "
              f"{dict(wins)}  median {sorted(chars)[len(chars)//2]:,} chars")

    # The claim that length carries no signal should be checked, not asserted.
    import statistics as st
    pro_len = [d["chars"] for d in balanced if d["true_winner"] == "pro"]
    con_len = [d["chars"] for d in balanced if d["true_winner"] == "con"]
    print(f"\nmedian transcript length by outcome: "
          f"pro {st.median(pro_len):,.0f}  con {st.median(con_len):,.0f}")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
