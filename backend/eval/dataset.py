"""
Eval dataset: one record per debate ROUND, stored as JSONL.

A round is the unit of judgement — it is what judge_round() scores — so it is
also the unit the scorers are measured on.
"""

import json
import os
from dataclasses import dataclass, field, asdict

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "data", "rounds.jsonl")

VALID_WINNERS = ("pro", "con", "tie")


@dataclass
class RoundRecord:
    debate_id: str
    topic: str
    resolution: str
    round: int
    exchange: list[dict]                 # [{"speaker","sub_round","text"}, ...]
    pro_side: str = ""
    con_side: str = ""
    gold_winner: str | None = None       # "pro" | "con" | "tie" | None (unlabelled)
    notes: str = ""
    meta: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.debate_id}#r{self.round}"

    def pro_text(self) -> str:
        return "\n\n".join(t["text"] for t in self.exchange if t["speaker"] == "pro")

    def con_text(self) -> str:
        return "\n\n".join(t["text"] for t in self.exchange if t["speaker"] == "con")


def load(path: str = DEFAULT_PATH) -> list[RoundRecord]:
    if not os.path.exists(path):
        return []
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(RoundRecord(**json.loads(line)))
    return records


def save(records: list[RoundRecord], path: str = DEFAULT_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")


def append(records: list[RoundRecord], path: str = DEFAULT_PATH) -> None:
    """Adds records, skipping any key already present. Existing labels are kept."""
    existing = load(path)
    seen = {r.key for r in existing}
    added = [r for r in records if r.key not in seen]
    save(existing + added, path)
    print(f"{len(added)} new round(s) written, {len(records) - len(added)} duplicate(s) skipped "
          f"-> {path} ({len(existing) + len(added)} total)")


def labelled(records: list[RoundRecord]) -> list[RoundRecord]:
    return [r for r in records if r.gold_winner in VALID_WINNERS]
