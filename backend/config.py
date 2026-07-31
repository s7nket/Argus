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

# ── Vector Database (ChromaDB) ────────────────────────────────────────────────
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", os.path.join(os.path.dirname(__file__), "chroma_db"))
CHROMA_EVIDENCE_COLLECTION = os.getenv("CHROMA_EVIDENCE_COLLECTION", "argus_evidence")
CHROMA_HISTORY_COLLECTION = os.getenv("CHROMA_HISTORY_COLLECTION", "argus_debate_history")
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# ── Kaggle fine-tuned scorer ─────────────────────────────────────────────────
# This was hardcoded at 12s, which is shorter than a single ArguScore-4B call has
# ever taken — so every FT probe timed out and every round silently fell back to
# Groq. Raised and made configurable: interactive demos want it low, paper eval
# runs want it high enough that the FT path is actually exercised.
# ArguScore-4B runs ~16 tok/s on a T4. With reasoning skipped (a pre-closed empty
# think block in the prompt) a full 6-turn round costs ~185 tokens and ~12s, so
# 45s is generous. Raise to ~150 when running the notebook in "think" mode, which
# costs ~1500 tokens and ~90s per round.
FT_JUDGE_TIMEOUT = float(os.getenv("FT_JUDGE_TIMEOUT", "45.0"))


# ── Retrieval-grounded verification ──────────────────────────────────────────
# The evidence score used to be whatever the scoring model asserted it was. These
# settings govern the independent channel that bounds it — see debate/verifier.py.

# Verification is opt-outable because it adds a round-trip per round. Turning it
# off restores the pre-verification scoring path exactly.
VERIFICATION_ENABLED = os.getenv("VERIFICATION_ENABLED", "1") not in ("0", "false", "False")

# Entailment backend: "groq" (no local model), "local" (cross-encoder NLI, needs
# torch — use this for reproducible eval runs), "lexical" (overlap, no deps).
NLI_BACKEND = os.getenv("NLI_BACKEND", "groq")
NLI_MODEL = os.getenv("NLI_MODEL", "llama-3.1-8b-instant")
NLI_LOCAL_MODEL = os.getenv("NLI_LOCAL_MODEL", "cross-encoder/nli-deberta-v3-small")
NLI_ENTAIL_THRESHOLD = float(os.getenv("NLI_ENTAIL_THRESHOLD", "0.60"))
NLI_CONTRADICT_THRESHOLD = float(os.getenv("NLI_CONTRADICT_THRESHOLD", "0.60"))
LEXICAL_SUPPORT_RATIO = float(os.getenv("LEXICAL_SUPPORT_RATIO", "0.55"))

VERIFIER_TOP_K = int(os.getenv("VERIFIER_TOP_K", "3"))
# Chroma's default embedding is all-MiniLM-L6-v2 with L2 distance. Unfiltered
# neighbours always look like evidence, so anything past this is treated as the
# corpus having nothing to say rather than as weak support.
RETRIEVAL_MAX_DISTANCE = float(os.getenv("RETRIEVAL_MAX_DISTANCE", "1.20"))

# Evidence ceiling when every adjudicable claim was refuted. Mirrors
# NO_EVIDENCE_CAP: citing only things the corpus contradicts is not better than
# citing nothing at all.
GROUNDING_FLOOR = float(os.getenv("GROUNDING_FLOOR", "3.0"))

# Per-refuted-claim penalty applied to the evidence score. Fabricating a citation
# is worse than omitting one, so this bites on top of the ceiling.
FABRICATION_WEIGHT = float(os.getenv("FABRICATION_WEIGHT", "1.0"))
FABRICATION_MAX_PENALTY = float(os.getenv("FABRICATION_MAX_PENALTY", "3.0"))

