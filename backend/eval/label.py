"""
Interactive labelling. Run it in a real terminal — it reads stdin.

    python -m eval.label

Deliberately shows you no model opinion before you decide. A suggested label
would anchor you to the scorer you are trying to measure, and the whole point of
the gold set is that it was produced independently.

Judge the same question the scorer is asked: which side argued better in THIS
round — not which side you personally agree with.
"""

import argparse
import textwrap

from eval.dataset import DEFAULT_PATH, RoundRecord, load, save

WRAP = textwrap.TextWrapper(width=96, initial_indent="    ", subsequent_indent="    ")
SUB_LABELS = {1: "OPENING", 2: "COUNTER", 3: "JUSTIFY"}

PROMPT = """
  [p] PRO argued better   [c] CON argued better   [t] genuine tie
  [s] skip                [b] back                [q] save and quit
> """


def show(rec: RoundRecord, index: int, total: int) -> None:
    print("\n" + "=" * 100)
    print(f"[{index}/{total}]  {rec.topic}   (round {rec.round})")
    if rec.pro_side:
        print(f"  PRO argues: {rec.pro_side}")
        print(f"  CON argues: {rec.con_side}")
    print("=" * 100)
    for turn in rec.exchange:
        head = f"{turn['speaker'].upper()} — {SUB_LABELS.get(turn['sub_round'], turn['sub_round'])}"
        print(f"\n  {head}")
        print(WRAP.fill(turn["text"]))
    if rec.gold_winner:
        print(f"\n  (currently labelled: {rec.gold_winner.upper()})")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=DEFAULT_PATH)
    ap.add_argument("--relabel", action="store_true", help="also revisit already-labelled rounds")
    args = ap.parse_args()

    records = load(args.path)
    if not records:
        print(f"No rounds at {args.path}. Capture some first:\n  python -m eval.capture")
        return

    queue = [i for i, r in enumerate(records)
             if args.relabel or r.gold_winner is None]
    if not queue:
        print(f"All {len(records)} rounds already labelled. Use --relabel to revisit.")
        return

    choices = {"p": "pro", "c": "con", "t": "tie"}
    pos = 0
    while 0 <= pos < len(queue):
        rec = records[queue[pos]]
        show(rec, pos + 1, len(queue))

        answer = input(PROMPT).strip().lower()
        if answer == "q":
            break
        if answer == "s":
            pos += 1
            continue
        if answer == "b":
            pos = max(0, pos - 1)
            continue
        if answer in choices:
            rec.gold_winner = choices[answer]
            note = input("  one-line reason (optional): ").strip()
            if note:
                rec.notes = note
            save(records, args.path)
            pos += 1
            continue
        print("  ? use p / c / t / s / b / q")

    done = sum(1 for r in records if r.gold_winner)
    save(records, args.path)
    print(f"\nSaved. {done}/{len(records)} rounds labelled.")
    if done >= 20:
        print("Enough to evaluate:\n  python -m eval.evaluate")
    else:
        print(f"Aim for ~30 labelled rounds before trusting the numbers (have {done}).")


if __name__ == "__main__":
    main()
