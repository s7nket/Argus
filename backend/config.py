import os

from dotenv import load_dotenv

load_dotenv()

# ── Debater models ───────────────────────────────────────────────────────────
# Previously hardcoded as "llama-3.1-8b-instant" in three separate files, which
# made the landing page's model picker fiction and forced both agents to share
# one small model (the main reason both sides sounded identical and looped).
DEFAULT_DEBATER_MODEL = "llama-3.1-8b-instant"


def debater_model(side: str) -> str:
    """Model for a debater. PRO_MODEL / CON_MODEL override DEBATER_MODEL."""
    override = os.getenv("PRO_MODEL" if side == "pro" else "CON_MODEL")
    return override or os.getenv("DEBATER_MODEL") or DEFAULT_DEBATER_MODEL


# ── Scoring policy ───────────────────────────────────────────────────────────
# A margin at or below this is a tie, not a win. The old code called a 0.5-point
# margin on a 30-point scale a victory.
TIE_BAND = float(os.getenv("TIE_BAND", "0.5"))

# Repetition penalty: agents recycled their position sentence verbatim across
# rounds while scores went UP. Overlap below FREE is unpenalised; above it the
# penalty ramps to MAX.
REPETITION_FREE_RATIO = 0.30
REPETITION_MAX_PENALTY = 1.5

# Evidence anchor enforcement — a side that cited nothing verifiable cannot be
# scored as "evidence-based" no matter what the scorer says.
NO_EVIDENCE_CAP = 3.0

# Blind scoring passes per round, with the debater labels swapped between them.
# Two passes cancel label bias and expose scorer disagreement, but double the
# judge's token spend — enough to exhaust a free Groq tier (100k tokens/day) in
# roughly five 3-round debates. Set to 1 to trade the bias check for headroom.
BLIND_PASSES = max(1, min(2, int(os.getenv("BLIND_PASSES", "2"))))
