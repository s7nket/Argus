"""
Gold-label data for calibration and scorer validation.

The conformal layer needs rounds whose true winner was decided by people, not by
ARGUS. Calibrating on the system's own verdicts would measure self-consistency
and guarantee nothing.

Source: IBM-Rank-30k (ibm-research/argument_quality_ranking_30k), ~30k arguments
carrying a human quality score and a stance label, from IBM's Project Debater.
Each row gives:

    argument   the text
    topic      the resolution it addresses
    WA         weighted-average human quality, 0-1  <- the gold label
    MACE-P     MACE-P human quality, 0-1
    stance_WA  +1 pro, -1 con

Pairing a PRO argument against a CON argument on the same topic yields a round
whose winner follows from the two human scores. That gives two things at once:

  1. Calibration data for the conformal predictor.
  2. A correlation target — does ARGUS rank arguments the way people did?

IMPORTANT LIMITATION, and it belongs in the paper rather than in a footnote:
two independently written arguments are not a debate. There is no rebuttal, no
adaptation, no engagement between the sides. This calibrates and validates the
SCORER on argument quality. Debate-level dynamics need either debate.org winner
labels or the human annotation study, and neither is covered here.

Fetched through the HuggingFace datasets-server HTTP API so no `datasets`
dependency is required, and cached to disk so a run is reproducible offline.
"""

import itertools
import json
import os
import random
import sys
import time
from dataclasses import dataclass

import httpx

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROWS_API = "https://datasets-server.huggingface.co/rows"
DATASET = "ibm-research/argument_quality_ranking_30k"
CONFIG = "argument_quality_ranking"

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")

# The API caps a single request at 100 rows.
PAGE = 100

# Below this gap the two human scores are too close to call a winner, and the
# pair becomes label noise rather than signal. Pairs inside the band are kept and
# labelled "tie" so the predictor sees genuinely undecidable rounds too, which is
# the case abstention exists for.
TIE_BAND_WA = 0.05


@dataclass
class Argument:
    text: str
    topic: str
    quality: float          # WA, human weighted average
    mace_p: float
    stance: int             # +1 pro, -1 con


def _cache_path(split: str) -> str:
    return os.path.join(CACHE_DIR, f"ibm_rank_{split}.json")


def fetch_split(split: str = "test", limit: int | None = None,
                force: bool = False) -> list[Argument]:
    """Download one split, caching to disk. Cached reads are offline and exact."""
    path = _cache_path(split)
    if os.path.exists(path) and not force:
        with open(path, encoding="utf-8") as f:
            rows = json.load(f)
        args = [Argument(**r) for r in rows]
        return args[:limit] if limit else args

    os.makedirs(CACHE_DIR, exist_ok=True)
    collected: list[Argument] = []
    offset = 0
    total = None

    with httpx.Client(timeout=60.0) as client:
        while True:
            resp = client.get(ROWS_API, params={
                "dataset": DATASET, "config": CONFIG, "split": split,
                "offset": offset, "length": PAGE,
            })
            resp.raise_for_status()
            payload = resp.json()
            total = payload.get("num_rows_total", total)

            batch = payload.get("rows", [])
            if not batch:
                break
            for item in batch:
                r = item["row"]
                # Rows missing a human score cannot serve as gold labels.
                if r.get("WA") is None or r.get("stance_WA") is None:
                    continue
                collected.append(Argument(
                    text=r["argument"], topic=r["topic"],
                    quality=float(r["WA"]), mace_p=float(r.get("MACE-P") or 0.0),
                    stance=int(r["stance_WA"]),
                ))

            offset += PAGE
            print(f"  fetched {len(collected)}" + (f"/{total}" if total else ""))
            if limit and len(collected) >= limit:
                break
            if total and offset >= total:
                break
            time.sleep(0.1)

    with open(path, "w", encoding="utf-8") as f:
        json.dump([a.__dict__ for a in collected], f)
    print(f"cached {len(collected)} arguments -> {path}")
    return collected[:limit] if limit else collected


def build_pairs(arguments: list[Argument], max_pairs: int = 400,
                seed: int = 0) -> list[dict]:
    """
    Pair PRO against CON on the same topic, with the winner set by human scores.

    Pairs are drawn per topic rather than globally so no single well-populated
    topic dominates the calibration set — conformal coverage assumes
    exchangeability, and a set skewed to one resolution breaks it in a way that
    quietly inflates coverage on that topic and destroys it elsewhere.
    """
    rng = random.Random(seed)
    by_topic: dict[str, dict[int, list[Argument]]] = {}
    for a in arguments:
        by_topic.setdefault(a.topic, {1: [], -1: []})
        if a.stance in (1, -1):
            by_topic[a.topic][a.stance].append(a)

    usable = [(t, s) for t, s in by_topic.items() if s[1] and s[-1]]
    if not usable:
        return []

    per_topic = max(1, max_pairs // len(usable))
    pairs: list[dict] = []

    for topic, sides in usable:
        pros, cons = sides[1][:], sides[-1][:]
        rng.shuffle(pros)
        rng.shuffle(cons)
        for pro, con in itertools.islice(zip(pros, cons), per_topic):
            gap = pro.quality - con.quality
            winner = "tie" if abs(gap) < TIE_BAND_WA else ("pro" if gap > 0 else "con")
            pairs.append({
                "topic": topic,
                "pro_argument": pro.text,
                "con_argument": con.text,
                "human_pro": round(pro.quality, 4),
                "human_con": round(con.quality, 4),
                "human_margin": round(gap, 4),
                "true_winner": winner,
            })

    rng.shuffle(pairs)
    return pairs[:max_pairs]


def summarise(pairs: list[dict]) -> dict:
    from collections import Counter
    counts = Counter(p["true_winner"] for p in pairs)
    margins = [abs(p["human_margin"]) for p in pairs]
    return {
        "pairs": len(pairs),
        "topics": len({p["topic"] for p in pairs}),
        "winners": dict(counts),
        "mean_abs_margin": round(sum(margins) / len(margins), 4) if margins else 0,
        "ties": counts.get("tie", 0),
    }


def save_pairs(pairs: list[dict], name: str = "pairs.json") -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(pairs, f, indent=1)
    return path


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Build gold-label argument pairs from IBM-Rank-30k.")
    ap.add_argument("--split", default="test", choices=["train", "validation", "test"])
    ap.add_argument("--limit", type=int, default=2000, help="arguments to fetch")
    ap.add_argument("--pairs", type=int, default=400, help="pairs to build")
    ap.add_argument("--force", action="store_true", help="refetch, ignoring the cache")
    args = ap.parse_args()

    print(f"fetching {DATASET} [{args.split}]...")
    arguments = fetch_split(args.split, limit=args.limit, force=args.force)
    print(f"\n{len(arguments)} arguments over {len({a.topic for a in arguments})} topics")

    pairs = build_pairs(arguments, max_pairs=args.pairs)
    print(f"\n{json.dumps(summarise(pairs), indent=1)}")
    print(f"\nsaved -> {save_pairs(pairs)}")
    if pairs:
        p = pairs[0]
        print(f"\nexample:\n  topic: {p['topic']}\n  PRO ({p['human_pro']}): {p['pro_argument'][:90]}"
              f"\n  CON ({p['human_con']}): {p['con_argument'][:90]}\n  winner: {p['true_winner']}")
