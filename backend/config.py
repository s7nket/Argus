import os

from dotenv import load_dotenv

load_dotenv()

# ── Debater models ───────────────────────────────────────────────────────────
# Groq meters tokens per minute PER MODEL, so which models are chosen decides
# throughput as much as how many tokens are spent. Measured limits:
#
#   llama-3.3-70b-versatile   12,000 tok/min
#   openai/gpt-oss-20b         8,000
#   qwen/qwen3.6-27b           8,000
#   openai/gpt-oss-120b        8,000
#   llama-3.1-8b-instant       6,000   <- both debaters used to share this
#
# Both agents on the single most restricted model is what produced
# "CON agent failed (R2S1): 429" partway through a debate. Putting each side on
# its own model draws from separate buckets, so a round no longer contends with
# itself.
#
# The split also fixes a quality problem noted much earlier: two agents running
# the same weights argue in the same voice and converge on the same framing.
#
# The reasoning models are deliberately NOT used here. gpt-oss and qwen emit a
# thinking pass before their answer — measured, gpt-oss-20b spent 198 of 200
# completion tokens reasoning and returned two tokens of prose, and 179 even at
# reasoning_effort="low". For an agent that must produce 120-200 words of
# argument that is the opposite of token efficiency. They suit the judge, whose
# job is deliberation and whose output is short JSON; they do not suit debaters.
DEFAULT_PRO_MODEL = "qwen/qwen3.6-27b"
DEFAULT_CON_MODEL = "openai/gpt-oss-20b"


def debater_model(side: str) -> str:
    """
    Model for a debater. PRO_MODEL / CON_MODEL override DEBATER_MODEL, which in
    turn overrides the per-side defaults.

    Setting DEBATER_MODEL puts both sides back on one model and one rate bucket —
    useful as an ablation control, costly in throughput.
    """
    override = os.getenv("PRO_MODEL" if side == "pro" else "CON_MODEL")
    if override:
        return override
    shared = os.getenv("DEBATER_MODEL")
    if shared:
        return shared
    return DEFAULT_PRO_MODEL if side == "pro" else DEFAULT_CON_MODEL


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

# ── Conformal prediction ─────────────────────────────────────────────────────
# Verdict sets with a distribution-free coverage guarantee, so the judge can
# abstain instead of calling a round it cannot separate. See debate/conformal.py.
#
# alpha is the miscoverage rate: 0.1 targets 90% coverage. It also sets the
# minimum useful calibration size, ceil(1/alpha) - 1, below which no set can be
# narrower than "every outcome".
CONFORMAL_ALPHA = float(os.getenv("CONFORMAL_ALPHA", "0.1"))
CONFORMAL_STATE_PATH = os.getenv(
    "CONFORMAL_STATE_PATH", os.path.join(os.path.dirname(__file__), "data", "conformal.json")
)
# Attach a verdict set to the final verdict when a calibrated predictor exists.
CONFORMAL_ENABLED = os.getenv("CONFORMAL_ENABLED", "1") not in ("0", "false", "False")


# ── LLM rate-limit retry ─────────────────────────────────────────────────────
# Groq's free tier is 6000 tokens/minute and one debate round costs about that,
# so 429s are routine rather than exceptional. Without retry the orchestrator
# aborted the whole debate mid-round. See llm_retry.py.
#
# Total wait is bounded by attempts x backoff, so a genuinely dead key still
# fails in reasonable time instead of hanging an unattended eval sweep.
LLM_MAX_ATTEMPTS = int(os.getenv("LLM_MAX_ATTEMPTS", "4"))
LLM_BACKOFF_BASE = float(os.getenv("LLM_BACKOFF_BASE", "2.0"))
# Caps OUR exponential guess only. It must never clamp a wait the server asked
# for — retrying before the stated window just earns another 429.
LLM_BACKOFF_MAX = float(os.getenv("LLM_BACKOFF_MAX", "45.0"))
# Ceiling on an explicitly requested wait. Groq's TPM window is a minute, so
# anything beyond this means something is wrong and failing beats hanging.
LLM_RATE_LIMIT_MAX_WAIT = float(os.getenv("LLM_RATE_LIMIT_MAX_WAIT", "120.0"))


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

# An idle ngrok tunnel serves its own 404 until traffic wakes it, and rounds are
# minutes apart, so the first call of a round frequently misses. One full debate
# scored on FT for only 1 of 3 rounds because of this. Retries are cheap relative
# to losing the FT scorer — which is the whole hybrid-judge contribution.
FT_MAX_ATTEMPTS = int(os.getenv("FT_MAX_ATTEMPTS", "3"))
FT_RETRY_DELAY = float(os.getenv("FT_RETRY_DELAY", "2.0"))


# ── Retrieval-grounded verification ──────────────────────────────────────────
# The evidence score used to be whatever the scoring model asserted it was. These
# settings govern the independent channel that bounds it — see debate/verifier.py.

# Verification is opt-outable because it adds a round-trip per round. Turning it
# off restores the pre-verification scoring path exactly.
VERIFICATION_ENABLED = os.getenv("VERIFICATION_ENABLED", "1") not in ("0", "false", "False")

# Entailment backend: "groq" (no local model), "local" (cross-encoder NLI, needs
# torch — use this for reproducible eval runs), "lexical" (overlap, no deps).
NLI_BACKEND = os.getenv("NLI_BACKEND", "groq")
NLI_MODEL = os.getenv("NLI_MODEL", "openai/gpt-oss-20b")
NLI_LOCAL_MODEL = os.getenv("NLI_LOCAL_MODEL", "cross-encoder/nli-deberta-v3-small")
NLI_ENTAIL_THRESHOLD = float(os.getenv("NLI_ENTAIL_THRESHOLD", "0.60"))
NLI_CONTRADICT_THRESHOLD = float(os.getenv("NLI_CONTRADICT_THRESHOLD", "0.60"))
LEXICAL_SUPPORT_RATIO = float(os.getenv("LEXICAL_SUPPORT_RATIO", "0.55"))

VERIFIER_TOP_K = int(os.getenv("VERIFIER_TOP_K", "3"))

# Retrieved passages are truncated and the claim batch is split so one round's
# verification fits the provider's per-request ceiling. With the 11-document seed
# corpus a single call was always small enough; Wikipedia passages are ~180 words
# and the same 12 claims produced a 7389-token request against a 6000 limit,
# failing with 413 and degrading verification to all-NEI. ~3 chars/token, so
# 12000 chars is roughly 3000 tokens — half the budget, leaving room for the
# system prompt and the response.
NLI_PASSAGE_CHARS = int(os.getenv("NLI_PASSAGE_CHARS", "700"))
NLI_CHARS_PER_REQUEST = int(os.getenv("NLI_CHARS_PER_REQUEST", "12000"))
# Chroma's default embedding is all-MiniLM-L6-v2 with L2 distance. Unfiltered
# neighbours always look like evidence, so anything past this is treated as the
# corpus having nothing to say rather than as weak support.
RETRIEVAL_MAX_DISTANCE = float(os.getenv("RETRIEVAL_MAX_DISTANCE", "1.20"))

# Evidence ceiling when every adjudicable claim was refuted. Mirrors
# NO_EVIDENCE_CAP: citing only things the corpus contradicts is not better than
# citing nothing at all.
GROUNDING_FLOOR = float(os.getenv("GROUNDING_FLOOR", "3.0"))

# Re-check every refutation on its own before it costs a debater anything. The
# batch screen labelled true claims as refuted ~17% of the time even against a
# 2298-document corpus, and its labels shift with whichever claims share the
# call. Only refutations pay for the extra request, so cost scales with how often
# the system accuses rather than with corpus size. Set 0 to measure the raw
# single-pass behaviour as an ablation.
CONFIRM_REFUTATIONS = os.getenv("CONFIRM_REFUTATIONS", "1") not in ("0", "false", "False")

# Per-refuted-claim penalty applied to the evidence score. Fabricating a citation
# is worse than omitting one, so this bites on top of the ceiling.
FABRICATION_WEIGHT = float(os.getenv("FABRICATION_WEIGHT", "1.0"))
FABRICATION_MAX_PENALTY = float(os.getenv("FABRICATION_MAX_PENALTY", "3.0"))

