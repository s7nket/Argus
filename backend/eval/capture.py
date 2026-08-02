"""
Runs debates against a live backend and saves each round to the eval dataset.

    python -m eval.capture --rounds 2 --topics eval/topics.txt

Debates normally stream over the WebSocket and are lost. This records them so the
same rounds can be replayed through different scorers later — every scorer sees
identical text, which is what makes the comparison meaningful.
"""

import argparse
import asyncio
import json
import os
import uuid

import websockets

from eval.dataset import DEFAULT_PATH, RoundRecord, append

DEFAULT_TOPICS = [
    # Comparative — the shape that used to collapse into a one-sided debate.
    "Ancient Athens or Sparta: Which was the better place to live?",
    "Remote work or office work: which produces better engineering teams?",
    "Nuclear power or solar power: which should a country build next?",
    # Propositions — one claim, affirmed or denied.
    "Social media has done more harm than good to democratic societies.",
    "University degrees are no longer worth their cost.",
    "Artificial intelligence should be regulated like pharmaceuticals.",
]


async def capture_debate(uri: str, topic: str, rounds: int) -> list[RoundRecord]:
    debate_id = uuid.uuid4().hex[:8]
    by_round: dict[int, list[dict]] = {}
    resolution, pro_side, con_side = topic, "", ""

    async with websockets.connect(uri, max_size=None) as ws:
        await ws.send(json.dumps({"topic": topic, "rounds": rounds}))
        while True:
            msg = json.loads(await ws.recv())
            t = msg.get("type")

            if t == "debate_start":
                resolution = msg.get("resolution", topic)
                pro_side = msg.get("pro_side", "")
                con_side = msg.get("con_side", "")
                print(f"  PRO: {pro_side}\n  CON: {con_side}")

            elif t in ("pro_argument", "con_argument"):
                speaker = "pro" if t == "pro_argument" else "con"
                by_round.setdefault(msg["round"], []).append({
                    "speaker": speaker,
                    "sub_round": msg["sub_round"],
                    "text": msg["text"],
                })
                print(f"  [{speaker.upper()} R{msg['round']}S{msg['sub_round']}] captured")

            elif t == "error":
                raise RuntimeError(msg["message"])

            elif t == "debate_end":
                break

    return [
        RoundRecord(
            debate_id=debate_id,
            topic=topic,
            resolution=resolution,
            round=rnd,
            exchange=turns,
            pro_side=pro_side,
            con_side=con_side,
        )
        for rnd, turns in sorted(by_round.items())
    ]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", default="ws://127.0.0.1:8000/ws/debate")
    ap.add_argument("--rounds", type=int, default=2, help="rounds per debate")
    ap.add_argument("--topics", help="file with one topic per line (default: built-in list)")
    ap.add_argument("--limit", type=int, help="only run the first N topics")
    ap.add_argument("--out", default=DEFAULT_PATH)
    args = ap.parse_args()

    if args.topics:
        with open(args.topics, encoding="utf-8") as f:
            topics = [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    else:
        topics = DEFAULT_TOPICS
    if args.limit:
        topics = topics[:args.limit]

    all_records: list[RoundRecord] = []
    for i, topic in enumerate(topics, 1):
        print(f"\n[{i}/{len(topics)}] {topic}")
        try:
            all_records += await capture_debate(args.uri, topic, args.rounds)
        except Exception as e:
            print(f"  FAILED: {e}")

    if all_records:
        append(all_records, args.out)
        print("\nNext: label them ->\n  python -m eval.label")
    else:
        print("\nNothing captured. Is the backend running on port 8000?")


if __name__ == "__main__":
    asyncio.run(main())
