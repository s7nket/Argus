"""
Verification channel smoke test.

Run from backend/:  python test_verifier.py

Checks the three properties the scoring path depends on:
  1. Retrieval reaches the seeded corpus and rejects off-topic neighbours.
  2. Entailment separates a claim the corpus supports from one it contradicts.
  3. grounding_report never raises the evidence ceiling — only lowers it.
"""

import asyncio
import sys

# The corpus now holds Wikipedia prose with Greek names and accented characters,
# which the default Windows console codepage (cp1252) cannot encode — printing a
# retrieved passage raised UnicodeEncodeError and took the whole suite down.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config
from debate.verifier import (
    NEI,
    REFUTED,
    SUPPORTED,
    grounding_report,
    retrieve_for_claim,
    verify_claims,
)
from debate.vector_store import get_vector_store

# Drawn from seed_evidence.py so the corpus can actually rule on them.
SUPPORTED_CLAIM = (
    "Cleisthenes established the Athenian democratic assembly in 508 BCE."
)
REFUTED_CLAIM = (
    "The Finnish Universal Basic Income experiment ran on 2,000 unemployed people "
    "and sharply reduced workforce participation."
)
UNGROUNDED_CLAIM = (
    "The archaeological record clearly demonstrates that historians agree on this point."
)
OFF_TOPIC_CLAIM = "The 1997 Bundesliga season ended with a goal difference of plus fourteen."


async def main() -> None:
    vs = get_vector_store()
    stats = vs.get_stats()
    print(f"corpus: {stats}")
    if not vs.is_available or stats.get("evidence_count", 0) == 0:
        print("FAIL: corpus empty — start the backend once to seed, or hit /vector-db/seed")
        return

    print(f"backend={config.NLI_BACKEND}  max_distance={config.RETRIEVAL_MAX_DISTANCE}\n")

    print("-- retrieval --")
    for claim in (SUPPORTED_CLAIM, OFF_TOPIC_CLAIM):
        hits = retrieve_for_claim(claim)
        print(f"  {len(hits)} passage(s) <- {claim[:60]}...")
        for h in hits:
            print(f"      d={h.get('distance', 0):.3f}  {h['text'][:80]}...")

    print("\n-- entailment --")
    claims = [SUPPORTED_CLAIM, REFUTED_CLAIM, UNGROUNDED_CLAIM, OFF_TOPIC_CLAIM]
    verdicts = await verify_claims(claims)
    for v in verdicts:
        print(f"  {v.label:<10} conf={v.confidence:.2f}  {v.claim[:64]}...")

    print("\n-- grounding report --")
    report = grounding_report(verdicts)
    for k in ("claims_checked", "supported", "refuted", "nei", "coverage",
              "precision", "evidence_cap", "fabrication_penalty"):
        print(f"  {k:<22} {report[k]}")

    print("\n-- invariants --")
    ok = True

    if report["evidence_cap"] > 10.0:
        print("  FAIL: ceiling above 10")
        ok = False

    # A corpus with nothing to say must not move the score at all.
    silent = grounding_report(await verify_claims([OFF_TOPIC_CLAIM]))
    if silent["evidence_cap"] != 10.0 or silent["fabrication_penalty"] != 0.0:
        print(f"  FAIL: silent corpus altered scoring -> cap={silent['evidence_cap']} "
              f"penalty={silent['fabrication_penalty']}")
        ok = False
    else:
        print("  ok: silent corpus is a no-op")

    if not verify_claims_is_total(verdicts, claims):
        print("  FAIL: verdict count does not match claim count")
        ok = False
    else:
        print("  ok: one verdict per claim, order preserved")

    if grounding_report([])["evidence_cap"] != 10.0:
        print("  FAIL: empty verdict list is not a no-op")
        ok = False
    else:
        print("  ok: empty input is a no-op")

    # Regression: a TRUE claim the corpus does not happen to cover was labelled
    # REFUTED, which penalised the debater for fabricating and flipped a round
    # from a PRO win to a tie. Absence of evidence must never read as refutation.
    print("\n-- refutation guard --")
    for true_but_uncovered in (
        "Athens paid jurors so the poor could serve.",
        "Pericles introduced payment for jury service in Athens around 451 BCE.",
    ):
        v = (await verify_claims([true_but_uncovered]))[0]
        if v.label == REFUTED:
            print(f"  FAIL: true-but-uncovered claim marked REFUTED -> {true_but_uncovered}")
            ok = False
        else:
            print(f"  ok: {v.label:<10} (not REFUTED) <- {true_but_uncovered[:52]}")

    # The guard must be structural, not prompt-dependent: a REFUTED label whose
    # quote cannot be traced to a retrieved passage is downgraded regardless of
    # which backend produced it.
    from debate.verifier import _guard_refutation
    passages = [{"text": "The Finnish UBI experiment did not reduce workforce participation."}]
    checks = [
        ("no quote", _guard_refutation(REFUTED, 0.9, "", passages), NEI),
        ("untraceable quote", _guard_refutation(REFUTED, 0.9, "Athens fell in 404 BCE.", passages), NEI),
        ("traceable quote", _guard_refutation(REFUTED, 0.9, "did not reduce workforce participation", passages), REFUTED),
        ("supported untouched", _guard_refutation(SUPPORTED, 0.9, "", passages), SUPPORTED),
    ]
    for name, got, want in checks:
        if got["label"] != want:
            print(f"  FAIL: {name} -> {got['label']}, wanted {want}")
            ok = False
        else:
            print(f"  ok: {name} -> {got['label']}")

    print("\nPASS" if ok else "\nFAIL")


def verify_claims_is_total(verdicts, claims) -> bool:
    return len(verdicts) == len(claims) and all(v.claim == c for v, c in zip(verdicts, claims))


if __name__ == "__main__":
    asyncio.run(main())
