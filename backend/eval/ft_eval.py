"""
Accuracy of the fine-tuned judge, on its own, against real debate outcomes.

    python -m eval.ft_eval --build --limit 100    # pick debates, no network
    python -m eval.ft_eval --score                # call the FT endpoint, resumable
    python -m eval.ft_eval --report               # accuracy, no network

This answers one question: given a real debate whose winner a human audience
decided, how often does ArguScore-4B name the same winner?

It calls the fine-tuned endpoint directly and nothing else. No Groq, no
extraction, no retrieval, no blind swap. That is the point — the full pipeline
in judge_round always runs the Groq passes to produce the audit, and lets the
fine-tuned scores override the numbers afterwards, so a number measured through
that path is a property of the pipeline rather than of the trained model. Here
the model is alone, so the accuracy reported is its own.

Length ceiling. The endpoint returns 500 with "Parse failed after N tok" once
the transcript grows: measured working at 4,936 characters and failing at 10,454
and above, because the 4B model stops emitting JSON and starts commenting. The
sample is therefore drawn below MAX_CHARS. This is a real limit on the trained
model and belongs in the paper next to whatever accuracy it earns.

Balance. Outcomes in this corpus lean CON roughly 60/40, and an unbalanced
sample lets a constant answer look competent. The sample is balanced by default
so that the majority baseline is 50% and the headline number means what a reader
assumes it means. --natural keeps the corpus distribution instead.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time

import httpx

from config import TIE_BAND
from eval.calibrate import DATA, cohen_kappa
from eval.ddo import POOL

SAMPLED = os.path.join(DATA, "ft_debates.json")
SCORED = os.path.join(DATA, "ft_scored.json")

# Was 5000, the measured ceiling when the server loaded the adapter with
# max_seq_length=2048 and a 400-token generation budget. With those raised the
# endpoint scores 30k-character transcripts, so the cap now exists only to keep
# a single call under a minute rather than to avoid a failure.
MAX_CHARS = 30000
MIN_CHARS = 800       # below this there is barely an argument to judge


def _endpoint() -> tuple[str, dict]:
    from agents.judge_agent import FT_JUDGE_URL, NGROK_HEADERS
    return FT_JUDGE_URL.rstrip("/") + "/ft-judge", NGROK_HEADERS


def build(limit: int, seed: int, natural: bool) -> None:
    if not os.path.exists(POOL):
        print(f"no pool at {POOL} — run `python -m eval.ddo --build` first")
        return
    with open(POOL, encoding="utf-8") as fh:
        pool = json.load(fh)
    fits = [d for d in pool if MIN_CHARS <= d["chars"] <= MAX_CHARS]
    print(f"{len(pool):,} labelled debates, {len(fits):,} within "
          f"{MIN_CHARS:,}-{MAX_CHARS:,} chars")

    rng = random.Random(seed)
    if natural:
        rng.shuffle(fits)
        sample = fits[:limit]
    else:
        pro = [d for d in fits if d["true_winner"] == "pro"]
        con = [d for d in fits if d["true_winner"] == "con"]
        rng.shuffle(pro), rng.shuffle(con)
        half = min(limit // 2, len(pro), len(con))
        sample = pro[:half] + con[:half]
        rng.shuffle(sample)

    pro_n = sum(1 for d in sample if d["true_winner"] == "pro")
    print(f"sampled {len(sample)}: {pro_n} pro / {len(sample) - pro_n} con")
    with open(SAMPLED, "w", encoding="utf-8") as fh:
        json.dump(sample, fh, ensure_ascii=False)
    print(f"wrote {SAMPLED}")


def _winner(pro: float, con: float) -> str:
    return "tie" if abs(pro - con) <= TIE_BAND else ("pro" if pro > con else "con")


def _total(side: dict) -> float:
    """Recompute from the three criteria rather than trusting the model's own
    `total`, for the reason Section IV-E gives: the scorer is not the authority
    on its own arithmetic."""
    vals = [float(side.get(c, 0) or 0) for c in ("evidence", "logic", "relevance")]
    return round(sum(vals) / len(vals), 2)


SCORED_SWAP = os.path.join(DATA, "ft_scored_swapped.json")


def _exchange_text(debate: dict, swap: bool) -> str:
    """Render the transcript, optionally with the two labels exchanged.

    Nothing about the argument changes — same speeches, same order, same rebuttal
    chain. Only the name attached to each side is different. A scorer that reads
    the arguments must reach the same verdict either way; one that reacts to the
    label will not, and the gap between the two runs is that reaction measured.
    """
    out = []
    for t in debate["exchange"]:
        side = t["speaker"]
        if swap:
            side = "con" if side == "pro" else "pro"
        out.append(f"{side.upper()}: {t['text']}")
    return "\n\n".join(out)


def compare() -> None:
    """How much of the verdict came from the label rather than the argument."""
    if not (os.path.exists(SCORED) and os.path.exists(SCORED_SWAP)):
        print("need both arms: `--score` then `--score --swap`")
        return
    a = {r["id"]: r for r in json.load(open(SCORED, encoding="utf-8"))
         if not r.get("failed")}
    b = {r["id"]: r for r in json.load(open(SCORED_SWAP, encoding="utf-8"))
         if not r.get("failed")}
    both = [(a[i], b[i]) for i in a if i in b]
    if not both:
        print("no debates scored successfully in both arms")
        return
    n = len(both)

    stable = sum(1 for x, y in both if x["ft_winner"] == y["ft_winner"])
    gold = [x["true_winner"] for x, _ in both]
    acc_a = sum(1 for x, _ in both if x["ft_winner"] == x["true_winner"]) / n
    acc_b = sum(1 for _, y in both if y["ft_winner"] == y["true_winner"]) / n

    from collections import Counter
    print(f"\nlabel-swap consistency on {n} debates scored in both arms\n")
    print(f"  same verdict both ways   {stable}/{n} = {stable/n:.3f}")
    print(f"  verdict changed          {n-stable}/{n} = {(n-stable)/n:.3f}")
    print(f"\n  accuracy, original       {acc_a:.3f}")
    print(f"  accuracy, labels swapped {acc_b:.3f}")
    print(f"\n  predicted PRO, original       {Counter(x['ft_winner'] for x,_ in both)}")
    print(f"  predicted PRO, swapped        {Counter(y['ft_winner'] for _,y in both)}")

    # If the scorer favours a label rather than a case, the side it favours stays
    # put while the arguments move underneath it.
    pro_a = sum(1 for x, _ in both if x["ft_winner"] == "pro") / n
    pro_b = sum(1 for _, y in both if y["ft_winner"] == "pro") / n
    print(f"\n  share of verdicts going to the PRO label: "
          f"{pro_a:.3f} original, {pro_b:.3f} swapped")
    if pro_a > 0.5 and pro_b > 0.5:
        print("  -> the PRO label wins most debates whichever side holds it:"
              "\n     a preference for the label, not for the argument.")

    # Averaging the two arms is what Section IV-C does, and the tie band of
    # Section IV-D then withholds a verdict on the remainder. Scoring an
    # abstention as an error would understate the mechanism badly — the whole
    # claim is that declining to answer beats answering wrongly — so coverage
    # and selective accuracy are reported as a pair. Neither means anything
    # alone: 100% accuracy on one debate out of fifty-seven is not a judge.
    print(f"\n  averaging both passes, then abstaining inside the tie band:")
    print(f"    {'tie band':<10}{'decides':>9}{'coverage':>11}{'accuracy when it decides':>27}")
    for band in (0.0, 0.25, 0.5, 1.0):
        correct = decided = 0
        for x, y in both:
            pro = (x["pro_total"] + y["pro_total"]) / 2
            con = (x["con_total"] + y["con_total"]) / 2
            if abs(pro - con) <= band:
                continue
            decided += 1
            if ("pro" if pro > con else "con") == x["true_winner"]:
                correct += 1
        acc = correct / decided if decided else 0.0
        star = "  <- production" if band == TIE_BAND else ""
        print(f"    {band:<10}{decided:>6}/{n}{decided/n:>10.3f}"
              f"{correct:>18}/{decided} = {acc:.3f}{star}")


def score(limit: int, swap: bool = False) -> None:
    if not os.path.exists(SAMPLED):
        print(f"no sample at {SAMPLED} — run `--build` first")
        return
    with open(SAMPLED, encoding="utf-8") as fh:
        sample = json.load(fh)
    out_path = SCORED_SWAP if swap else SCORED
    done = json.load(open(out_path, encoding="utf-8")) if os.path.exists(out_path) else []
    seen = {d["id"] for d in done}
    todo = [d for d in sample if d["id"] not in seen][:limit]
    url, headers = _endpoint()
    print(f"{len(done)} scored, {len(todo)} this run\n")

    failures = 0
    for i, d in enumerate(todo, 1):
        text = _exchange_text(d, swap)
        t0 = time.monotonic()
        try:
            r = httpx.post(url, json={"topic": d["topic"], "exchange": text},
                           headers=headers, timeout=240)
            if r.status_code != 200:
                # Recorded, not retried: a parse failure at this length is the
                # model's behaviour, and retrying would hide how often it happens.
                failures += 1
                print(f"[{i}/{len(todo)}] {r.status_code} {r.text[:70]}")
                done.append({"id": d["id"], "topic": d["topic"],
                             "true_winner": d["true_winner"],
                             "chars": d["chars"], "failed": True})
            else:
                body = r.json()
                pro, con = _total(body.get("pro_scores", {})), _total(body.get("con_scores", {}))
                # In the swapped arm the endpoint's "pro" is the real CON side,
                # so map back here — everything downstream then speaks about the
                # actual debaters and the two arms are directly comparable.
                if swap:
                    pro, con = con, pro
                w = _winner(pro, con)
                mark = "OK " if w == d["true_winner"] else "  x"
                print(f"[{i}/{len(todo)}] {mark} ft={w:<4} human={d['true_winner']:<4}"
                      f" {pro:.1f}/{con:.1f}  {time.monotonic()-t0:>3.0f}s  {d['topic'][:38]}")
                done.append({"id": d["id"], "topic": d["topic"],
                             "true_winner": d["true_winner"], "chars": d["chars"],
                             "pro_total": pro, "con_total": con, "ft_winner": w,
                             "failed": False})
        except Exception as e:
            failures += 1
            print(f"[{i}/{len(todo)}] {type(e).__name__}: {str(e)[:60]}")
            done.append({"id": d["id"], "topic": d["topic"],
                         "true_winner": d["true_winner"],
                         "chars": d["chars"], "failed": True})
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(done, fh, indent=2, ensure_ascii=False)

    print(f"\n{len(done)} scored -> {out_path}   ({failures} failed this run)")


def report() -> None:
    if not os.path.exists(SCORED):
        print(f"nothing at {SCORED} — run `--score` first")
        return
    with open(SCORED, encoding="utf-8") as fh:
        rows = json.load(fh)
    ok = [r for r in rows if not r.get("failed")]
    failed = len(rows) - len(ok)
    if not ok:
        print("no successful scores")
        return

    gold = [r["true_winner"] for r in ok]
    pred = [r["ft_winner"] for r in ok]
    n = len(ok)
    correct = sum(1 for a, b in zip(pred, gold) if a == b)
    ties = sum(1 for p in pred if p == "tie")

    print(f"\nArguScore-4B on {n} real debates with audience-decided winners\n")
    print(f"  accuracy               {correct}/{n} = {correct/n:.3f}")
    from collections import Counter
    maj, maj_n = Counter(gold).most_common(1)[0]
    print(f"  always '{maj}' baseline    {maj_n/n:.3f}")
    k = cohen_kappa(pred, gold)
    if k is not None:
        print(f"  Cohen's kappa          {k:.3f}")
    print(f"  called a tie           {ties}/{n} = {ties/n:.3f}")
    if failed:
        print(f"\n  endpoint failures      {failed}/{len(rows)} "
              f"({failed/len(rows):.1%}) — model did not return usable JSON")

    # The compression failure of Section VIII-E, measured on this scorer.
    totals = [t for r in ok for t in (r["pro_total"], r["con_total"])]
    band = sum(1 for t in totals if 7.0 <= t <= 8.5) / len(totals)
    print(f"  scores in 7.0-8.5 band {band:.1%}  (margin uninformative in this band)")
    print(f"  mean score             {sum(totals)/len(totals):.2f}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--swap", action="store_true",
                    help="present the same debate with PRO/CON labels exchanged")
    ap.add_argument("--compare", action="store_true", help="compare the two arms")
    ap.add_argument("--natural", action="store_true",
                    help="keep the corpus class balance instead of balancing")
    args = ap.parse_args()
    if args.build:
        build(args.limit, args.seed, args.natural)
    elif args.score:
        score(args.limit, args.swap)
    elif args.compare:
        compare()
    elif args.report:
        report()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
