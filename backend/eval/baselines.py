"""
Baselines the judge has to beat, measured on the same gold pairs it was scored on.

    python -m eval.baselines                 # table + bootstrap CIs
    python -m eval.baselines --resamples 0   # point estimates only, instant

Reads data/scored_pairs.json and makes no network calls, so this is safe to run
during a demo and reproduces the comparison table in the paper exactly.

Why these baselines. A judge that agrees with humans 54% of the time sounds
reasonable until you notice that always naming the affirmative side agrees 53%
of the time on this label distribution, and that is what Cohen's kappa exists to
strip out. The length heuristic is here for a sharper reason: verbosity bias is
the best-documented failure of LLM evaluators, so "pick whichever argument is
longer" is the baseline that tells you whether a pipeline has escaped it. On the
current sample it has not, and the bootstrap says the sample is too small to
tell any of these apart. Both facts belong in the paper.

Kappa and Spearman are imported from eval.calibrate rather than reimplemented so
that a number printed here and a number printed by `--report` cannot drift.
"""

from __future__ import annotations

import argparse
import json
import os
import random
from typing import Callable

from eval.calibrate import SCORED, cohen_kappa, spearman

Pair = dict
Predictor = Callable[[Pair], str]


# -- the baselines ----------------------------------------------------------
# Each maps a pair to a predicted winner using no information the system has.

def always(side: str) -> Predictor:
    return lambda _p: side


def longer_argument(p: Pair) -> str:
    """Verbosity heuristic: the wordier side wins. No ties, by construction."""
    return "pro" if len(p["pro_argument"]) > len(p["con_argument"]) else "con"


def coin_toss(rng: random.Random) -> Predictor:
    return lambda _p: rng.choice(["pro", "con", "tie"])


def argus(p: Pair) -> str:
    return p["argus_winner"]


def _score(pairs: list[Pair], predict: Predictor) -> tuple[float, float | None]:
    gold = [p["true_winner"] for p in pairs]
    pred = [predict(p) for p in pairs]
    agree = sum(1 for a, b in zip(pred, gold) if a == b) / len(pairs)
    return agree, cohen_kappa(pred, gold)


def _bootstrap(pairs: list[Pair], predict: Predictor, resamples: int,
               rng: random.Random) -> tuple[float, float] | None:
    """Percentile CI for kappa. Resampling pairs, not labels, is what makes the
    interval a statement about the sample size we actually have."""
    if resamples <= 0:
        return None
    ks = []
    for _ in range(resamples):
        sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
        k = cohen_kappa([predict(p) for p in sample],
                        [p["true_winner"] for p in sample])
        if k is not None:
            ks.append(k)
    if len(ks) < resamples // 2:
        return None
    ks.sort()
    return ks[int(0.025 * len(ks))], ks[int(0.975 * len(ks))]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--resamples", type=int, default=5000,
                    help="bootstrap resamples for the kappa CI; 0 to skip")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()

    if not os.path.exists(SCORED):
        print(f"no scored pairs at {SCORED} — run `python -m eval.calibrate` first")
        return
    with open(SCORED, encoding="utf-8") as fh:
        pairs = [p for p in json.load(fh)
                 if p.get("argus_winner") and p.get("true_winner")]
    if not pairs:
        print("no usable pairs")
        return

    rng = random.Random(args.seed)
    rows: list[tuple[str, Predictor]] = [
        ("random", coin_toss(random.Random(args.seed))),
        ("always CON", always("con")),
        ("always PRO (majority)", always("pro")),
        ("longer argument wins", longer_argument),
        ("ARGUS (full pipeline)", argus),
    ]

    ci_head = "  kappa 95% CI" if args.resamples > 0 else ""
    print(f"\nbaselines on {len(pairs)} gold pairs\n")
    print(f"{'predictor':<24}{'agree':>8}{'kappa':>8}{ci_head}")
    print("-" * (40 + len(ci_head)))
    intervals = {}
    for name, fn in rows:
        agree, k = _score(pairs, fn)
        ci = _bootstrap(pairs, fn, args.resamples, rng)
        intervals[name] = ci
        ks = f"{k:>8.3f}" if k is not None else f"{'-':>8}"
        cis = f"  [{ci[0]:+.3f}, {ci[1]:+.3f}]" if ci else ""
        print(f"{name:<24}{agree:>8.3f}{ks}{cis}")

    # Does the pipeline merely reproduce the heuristic it is supposed to resist?
    margin = [p["pro_total"] - p["con_total"] for p in pairs]
    length = [len(p["pro_argument"]) - len(p["con_argument"]) for p in pairs]
    human = [p["human_margin"] for p in pairs]
    same = sum(1 for p in pairs if argus(p) == longer_argument(p)) / len(pairs)

    print("\nverbosity check")
    print(f"  ARGUS agrees with the length heuristic   {same:.3f}")
    r_len, r_hum = spearman(margin, length), spearman(margin, human)
    print(f"  Spearman(ARGUS margin, length gap)       {r_len:+.3f}")
    print(f"  Spearman(ARGUS margin, human margin)     {r_hum:+.3f}")
    if r_len is not None and r_hum is not None and r_len > r_hum:
        print("  -> margin tracks length more closely than it tracks the humans;"
              "\n     verbosity bias is not removed, only measured.")

    # The comparison the paper leads with, stated as an interval rather than a
    # winner, because at this n the point estimates do not separate.
    if args.resamples > 0:
        diffs = []
        for _ in range(args.resamples):
            sample = [pairs[rng.randrange(len(pairs))] for _ in pairs]
            gold = [p["true_winner"] for p in sample]
            a = cohen_kappa([argus(p) for p in sample], gold)
            b = cohen_kappa([longer_argument(p) for p in sample], gold)
            if a is not None and b is not None:
                diffs.append(a - b)
        if diffs:
            diffs.sort()
            lo, hi = diffs[int(0.025 * len(diffs))], diffs[int(0.975 * len(diffs))]
            print(f"\nkappa(ARGUS) - kappa(length), 95% CI  [{lo:+.3f}, {hi:+.3f}]")
            print("  interval contains zero: this sample cannot separate them."
                  if lo < 0 < hi else
                  "  interval excludes zero: the difference is real at this n.")


if __name__ == "__main__":
    main()
