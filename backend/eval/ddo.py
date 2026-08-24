"""
Debate-level ground truth: real debates with real outcomes.

    python -m eval.ddo --build --limit 40     # filter and sample, no network
    python -m eval.ddo --topics               # topic list for corpus building
    python -m eval.ddo --score --limit 10     # run the judge, resumable
    python -m eval.ddo --report               # metrics, no network

Why this exists. Every number in Section VIII rests on argument-quality pairs:
two independently written arguments, no rebuttal, no engagement. That measures
the scorer on argument quality and cannot measure the adjudicator on a debate,
and on those pairs the extraction stage found a verifiable specific on one side
in 114 — so the verification channel never ran. This module supplies the missing
instrument: transcripts of genuine multi-round debates whose winner was decided
by an audience rather than by us.

Source. The DDO corpus of Durmus and Cardie, 78,376 debates scraped from
debate.org with round-by-round text and per-voter ballots. CC BY-NC-SA 3.0;
debate.org and both papers must be cited. `debates.json` is distributed through
a Google Drive folder that requires an interactive sign-in, so it cannot be
fetched here — download it and place it at the path DEBATES_JSON below.

Filtering follows Liu et al. (ACL 2024), who ran the closest prior experiment on
this data, so that our numbers sit beside theirs on comparable material: three to
five rounds, no forfeit, and a margin above VOTE_MARGIN on the "made more
convincing arguments" ballot. Their reported accuracies are the external
baseline this evaluation should be read against.

What the label is. An audience vote, not an expert adjudication. Durmus and
Cardie's own finding is that a voter's prior beliefs predict how they vote, so
this is a noisy target and the paper must say so.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random

from eval.calibrate import DATA, cohen_kappa, spearman

DEBATES_JSON = os.path.join(DATA, "debates.json")      # you must download this
POOL = os.path.join(DATA, "ddo_pool.json")          # cached filter output
SAMPLED = os.path.join(DATA, "ddo_debates.json")
SCORED = os.path.join(DATA, "ddo_scored.json")

VOTE_MARGIN = 2          # Liu et al.: keep debates decided by more than 2 votes
ROUNDS_ALLOWED = (3, 4, 5)
CONVINCING = "Made more convincing arguments"


# -- building the sample ----------------------------------------------------

def _tally(debate: dict) -> tuple[int, int]:
    """Votes for the convincing-arguments ballot, Pro then Con.

    The field is sometimes a bool and sometimes an int across the dump, so it is
    coerced; a missing entry means that voter did not answer this question and
    contributes nothing rather than zero-for-both.
    """
    pro_name = debate.get("participant_1_name")
    con_name = debate.get("participant_2_name")
    pro = con = 0
    for vote in debate.get("votes") or []:
        vmap = vote.get("votes_map") or {}
        p = (vmap.get(pro_name) or {}).get(CONVINCING)
        c = (vmap.get(con_name) or {}).get(CONVINCING)
        if p is None and c is None:
            continue
        pro += int(p or 0)
        con += int(c or 0)
    return pro, con


def _has_forfeit(debate: dict) -> bool:
    if debate.get("forfeit_label"):
        return True
    for rnd in debate.get("rounds") or []:
        for side in rnd:
            if (side.get("text") or "").strip().lower() == "forfeit":
                return True
    return False


def _exchange(debate: dict) -> list[dict]:
    """Flatten the debate into the judge's exchange format.

    A DDO round holds one utterance per side, which maps onto a sub-round; the
    whole debate is presented as a single scored round. Scoring each DDO round
    separately would be closer to the live protocol but multiplies the cost by
    the round count, and the audience voted on the debate as a whole, which is
    the label we are trying to predict.
    """
    out = []
    for i, rnd in enumerate(debate.get("rounds") or [], 1):
        for side in rnd:
            speaker = "pro" if str(side.get("side", "")).lower().startswith("pro") else "con"
            text = (side.get("text") or "").strip()
            if text:
                out.append({"speaker": speaker, "sub_round": i, "text": text})
    return out


# Categories whose resolutions turn on checkable fact rather than on values or
# doctrine. The verification channel can only be exercised where a claim has a
# truth-maker outside the debate; on Religion and Philosophy it would measure the
# stance of our corpus, which Section VIII-F already identifies as its failure
# mode. Sampling here is a restriction on what the evaluation can support, not a
# filter for debates we expect to do well on, and the paper must report it.
GROUNDABLE = ("Politics", "Science", "Society", "Health",
              "Economics", "Technology", "Education")
MIN_CHARS = 4000

# Upper bound too, and it is a property of the deployment tier rather than of the
# method. The judge model is metered per minute as well as per day; a transcript
# past roughly 40k characters produces a request near 16k tokens once the rubric
# is added, which exceeds the per-minute allowance and fails on every retry
# rather than being slow. Four debates in the first sample were in that range.
# Truncating them would alter the exchange the audience actually voted on, so
# they are excluded and the exclusion is reported.
MAX_CHARS = 40000


def build(limit: int, seed: int, categories: tuple | None = GROUNDABLE,
          min_chars: int = MIN_CHARS, max_chars: int = MAX_CHARS) -> None:
    # The filtered pool is cached because the source dump is 1.2 GB and
    # resampling it repeatedly costs minutes per run for no new information.
    if os.path.exists(POOL):
        with open(POOL, encoding="utf-8") as fh:
            kept = json.load(fh)
        print(f"pool: {len(kept):,} debates (cached from {POOL})")
        _sample(kept, limit, seed, categories, min_chars, max_chars)
        return
    if not os.path.exists(DEBATES_JSON):
        print(f"missing {DEBATES_JSON}\n"
              f"download debates.json from the Drive folder linked at\n"
              f"  https://esdurmus.github.io/ddo.html\n"
              f"and place it there. The folder needs a signed-in browser.")
        return
    print(f"loading {DEBATES_JSON} (this is a large file)...")
    with open(DEBATES_JSON, encoding="utf-8") as fh:
        debates = json.load(fh)
    print(f"  {len(debates):,} debates")

    kept = []
    for name, d in debates.items():
        if d.get("number_of_rounds") not in ROUNDS_ALLOWED or _has_forfeit(d):
            continue
        pro, con = _tally(d)
        if pro > con + VOTE_MARGIN:
            winner = "pro"
        elif pro + VOTE_MARGIN < con:
            winner = "con"
        else:
            continue
        exchange = _exchange(d)
        if len(exchange) < 4:
            continue
        kept.append({
            "id": name,
            "topic": d.get("title") or name,
            "category": d.get("category"),
            "rounds": d.get("number_of_rounds"),
            "pro_votes": pro,
            "con_votes": con,
            "true_winner": winner,
            "human_margin": float(pro - con),
            "exchange": exchange,
            "chars": sum(len(t["text"]) for t in exchange),
        })

    print(f"  {len(kept):,} pass the filter "
          f"({ROUNDS_ALLOWED} rounds, no forfeit, margin > {VOTE_MARGIN})")
    with open(POOL, "w", encoding="utf-8") as fh:
        json.dump(kept, fh, ensure_ascii=False)
    _sample(kept, limit, seed, categories, min_chars, max_chars)


def _sample(kept: list, limit: int, seed: int, categories: tuple | None,
            min_chars: int, max_chars: int) -> None:
    if categories:
        kept = [k for k in kept if k.get("category") in categories]
        print(f"  {len(kept):,} in groundable categories {categories}")
    if min_chars:
        kept = [k for k in kept if k["chars"] >= min_chars]
        print(f"  {len(kept):,} with >= {min_chars:,} characters of transcript")
    if max_chars:
        over = sum(1 for k in kept if k["chars"] > max_chars)
        kept = [k for k in kept if k["chars"] <= max_chars]
        print(f"  {len(kept):,} with <= {max_chars:,} characters "
              f"({over:,} excluded as too large for the per-minute token allowance)")
    rng = random.Random(seed)
    rng.shuffle(kept)
    sample = kept[:limit]

    # Balance matters more than size here: a sample that is 90% pro-wins lets a
    # constant predictor look competent, which is the trap Section VIII-D found
    # in the gold pairs.
    pro_n = sum(1 for s in sample if s["true_winner"] == "pro")
    print(f"  sampled {len(sample)}: {pro_n} pro / {len(sample) - pro_n} con")
    print(f"  transcript size: median {sorted(s['chars'] for s in sample)[len(sample)//2]:,} chars")

    with open(SAMPLED, "w", encoding="utf-8") as fh:
        json.dump(sample, fh, indent=2, ensure_ascii=False)
    print(f"\nwrote {SAMPLED}")
    print("next: `--topics` to build a matching evidence corpus, then `--score`")


def topics() -> None:
    """Topics of the sample, for building an evidence corpus that covers them.

    Without this the verification channel retrieves nothing and goes inert, which
    is exactly how the gold-pair evaluation ended up testing neither Section V nor
    Section VI. Feed these to the corpus builder before scoring.
    """
    if not os.path.exists(SAMPLED):
        print(f"no sample at {SAMPLED} — run `--build` first")
        return
    with open(SAMPLED, encoding="utf-8") as fh:
        for d in json.load(fh):
            print(d["topic"])


# -- scoring ----------------------------------------------------------------

async def score_one(debate: dict) -> dict | None:
    from agents.judge_agent import judge_round
    try:
        v = await judge_round(debate["topic"], 1, debate["exchange"])
    except Exception as e:
        print(f"    failed: {type(e).__name__}: {str(e)[:110]}")
        return None
    audit = v.get("audit") or {}
    pro_g = audit.get("pro_grounding") or {}
    con_g = audit.get("con_grounding") or {}
    return {
        "id": debate["id"],
        "topic": debate["topic"],
        "true_winner": debate["true_winner"],
        "human_margin": debate["human_margin"],
        "pro_total": v["pro_scores"]["total"],
        "con_total": v["con_scores"]["total"],
        "argus_winner": v["round_winner"],
        "scorer": audit.get("scorer"),
        # Recorded per debate, not averaged, so that "the channel ran on n of N"
        # can be stated exactly rather than inferred from a mean over survivors.
        "pro_claims": len(audit.get("pro_evidence_cited") or []),
        "con_claims": len(audit.get("con_evidence_cited") or []),
        "pro_coverage": pro_g.get("coverage"),
        "con_coverage": con_g.get("coverage"),
        "label_disagreement": audit.get("label_disagreement"),
    }


async def score(limit: int) -> None:
    if not os.path.exists(SAMPLED):
        print(f"no sample at {SAMPLED} — run `--build` first")
        return
    with open(SAMPLED, encoding="utf-8") as fh:
        sample = json.load(fh)
    done = _load(SCORED)
    seen = {d["id"] for d in done}
    todo = [d for d in sample if d["id"] not in seen][:limit]
    print(f"{len(done)} scored, {len(todo)} this run, "
          f"{len(sample) - len(done) - len(todo)} left after\n")

    for i, debate in enumerate(todo, 1):
        print(f"[{i}/{len(todo)}] {debate['topic'][:60]}")
        result = await score_one(debate)
        if result is None:
            continue
        print(f"    argus {result['argus_winner']}  (human {result['true_winner']})"
              f"  claims {result['pro_claims']}/{result['con_claims']}")
        done.append(result)
        with open(SCORED, "w", encoding="utf-8") as fh:
            json.dump(done, fh, indent=2, ensure_ascii=False)
    print(f"\n{len(done)} scored -> {SCORED}")


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# -- reporting --------------------------------------------------------------

def report() -> None:
    scored = _load(SCORED)
    if len(scored) < 5:
        print(f"only {len(scored)} scored — not enough to report")
        return
    # A metric computed across two judges describes neither. calibrate.py learned
    # this when an ngrok tunnel dropped mid-run and pooled 16 fine-tuned rounds
    # with 4 Groq ones; the same guard belongs here.
    from collections import Counter
    scorers = Counter(s.get("scorer") for s in scored)
    if len(scorers) > 1:
        print(f"REFUSING to report: {len(scorers)} scorers in this set — {dict(scorers)}")
        print("Re-score the minority set or drop it. A metric pooled across judges "
              "measures neither of them.")
        return
    print(f"scorer: {next(iter(scorers))}")

    gold = [s["true_winner"] for s in scored]
    pred = [s["argus_winner"] for s in scored]
    n = len(scored)
    agree = sum(1 for a, b in zip(pred, gold) if a == b) / n
    nt = [(a, b) for a, b in zip(pred, gold) if a != "tie"]

    print(f"\nARGUS on {n} real debates with audience-voted winners\n")
    print(f"  agreement              {agree:.3f}")
    if nt:
        print(f"  agreement (non-tie)    {sum(1 for a,b in nt if a==b)/len(nt):.3f}")
    k = cohen_kappa(pred, gold)
    r = spearman([s["pro_total"] - s["con_total"] for s in scored],
                 [s["human_margin"] for s in scored])
    print(f"  Cohen's kappa          {k:.3f}" if k is not None else "  kappa n/a")
    print(f"  Spearman rho           {r:+.3f}" if r is not None else "  rho n/a")
    print(f"  abstained (tie)        {sum(1 for p in pred if p=='tie')/n:.3f}")

    # The sample keeps DDO's natural class balance so that accuracy stays
    # comparable with [18], who did not balance either. That makes the majority
    # baseline strong, so it is printed beside the system rather than left for a
    # reader to work out.
    from collections import Counter
    maj, maj_n = Counter(gold).most_common(1)[0]
    print(f"\n  always '{maj}' baseline    {maj_n/n:.3f}   (kappa 0 by construction)")
    if agree <= maj_n / n:
        print("  -> the system does not beat the majority class on this sample")

    # Did the contribution under test actually run this time?
    ran = sum(1 for s in scored
              if (s.get("pro_coverage") is not None or s.get("con_coverage") is not None))
    claims = sum(s.get("pro_claims", 0) + s.get("con_claims", 0) for s in scored)
    print(f"\n  verification engaged   {ran}/{n} debates")
    print(f"  claims extracted       {claims} across {2*n} sides")
    if ran == 0:
        print("  -> channel inert again: the corpus does not cover these topics.\n"
              "     Build one from `--topics` before quoting any grounding number.")

    # Conformal over debate outcomes. Calibrating here rather than reusing the
    # gold-pair fit is deliberate: the guarantee holds only if calibration and
    # test data are exchangeable, and argument-quality pairs are demonstrably a
    # different distribution from multi-round debates — that mismatch is the
    # finding of Section VIII-E. Nothing is persisted, so the fit saved from the
    # pairs is left intact.
    import config
    from debate.conformal import ConformalPredictor
    alpha = config.CONFORMAL_ALPHA
    rounds = [{"pro_total": s["pro_total"], "con_total": s["con_total"],
               "true_winner": s["true_winner"]} for s in scored]
    split = len(rounds) // 2
    need = ConformalPredictor(alpha=alpha).min_calibration_size
    print(f"\n-- conformal (alpha={alpha}) --")
    if split < need:
        print(f"  need >= {need * 2} scored debates to calibrate at this alpha; "
              f"have {len(rounds)}")
    else:
        for k, v in ConformalPredictor(alpha=alpha).fit(
                rounds[:split]).evaluate(rounds[split:]).items():
            print(f"  {k:<22} {v}")

    print("\nexternal baselines on this corpus (Liu et al., ACL 2024, 1,500 debates):")
    print("  GPT-4 0.862 · GPT-3.5 0.820 · human annotators 0.77-0.79 · LLaMA2-70B 0.657")
    print("  Their task is winner prediction only; ours also abstains and audits,")
    print("  and the samples differ, so this is context and not a controlled comparison.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--topics", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int, default=40)
    ap.add_argument("--seed", type=int, default=13)
    ap.add_argument("--all-categories", action="store_true",
                    help="do not restrict to fact-oriented categories")
    ap.add_argument("--min-chars", type=int, default=MIN_CHARS)
    ap.add_argument("--max-chars", type=int, default=MAX_CHARS)
    args = ap.parse_args()
    if args.build:
        build(args.limit, args.seed,
              None if args.all_categories else GROUNDABLE,
              args.min_chars, args.max_chars)
    elif args.topics:
        topics()
    elif args.score:
        asyncio.run(score(args.limit))
    elif args.report:
        report()
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
