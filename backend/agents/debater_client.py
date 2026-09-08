"""
Shared debater client factory.

Supports two backends, selected by DEBATER_PROVIDER in backend/.env:
  - "cerebras"  (default) : Cerebras Cloud — llama-3.3-70b at ~2000 tok/s, free
  - "groq"                : Groq — fast but tight rate limits on free tier
  - "nvidia"              : NVIDIA NIM — OpenAI-compatible, good fallback

Set CEREBRAS_API_KEY (from cloud.cerebras.ai) to use Cerebras.
"""
import os
from dotenv import load_dotenv

_here = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(_here), ".env"), override=True)

DEBATER_PROVIDER = os.getenv("DEBATER_PROVIDER", "cerebras").lower()

_CEREBRAS_KEY = os.getenv("CEREBRAS_API_KEY", "")
_NVIDIA_KEY    = os.getenv("NVIDIA_API_KEY", "")
_GROQ_KEY      = os.getenv("GROQ_API_KEY", "")

_PROVIDER_VALID = {
    "cerebras": bool(_CEREBRAS_KEY and not _CEREBRAS_KEY.startswith("your-")),
    "nvidia":   bool(_NVIDIA_KEY   and not _NVIDIA_KEY.startswith("your-")),
    "groq":     bool(_GROQ_KEY),
}

# Auto-fallback: pick first available in preferred order
_ORDER = ["cerebras", "nvidia", "groq"]
if not _PROVIDER_VALID.get(DEBATER_PROVIDER):
    for _p in _ORDER:
        if _PROVIDER_VALID[_p]:
            print(f"[debater] {DEBATER_PROVIDER!r} key missing — falling back to {_p!r}")
            DEBATER_PROVIDER = _p
            break

# If we fell back to Groq, validate the DEBATER_MODEL is still available.
# Discontinued models get replaced with a capable default.
_DISCONTINUED = {"llama-3.3-70b", "llama-3.3-70b-versatile", "llama-3.1-8b-instant"}
if DEBATER_PROVIDER == "groq" and os.getenv("DEBATER_MODEL", "") in _DISCONTINUED:
    os.environ["DEBATER_MODEL"] = "allam-2-7b"


def _make_client():
    from openai import AsyncOpenAI
    from groq import AsyncGroq

    if DEBATER_PROVIDER == "cerebras":
        print(f"[debater] Cerebras -> {os.getenv('DEBATER_MODEL', 'llama-3.3-70b')}")
        return AsyncOpenAI(
            api_key=_CEREBRAS_KEY,
            base_url="https://api.cerebras.ai/v1",
            timeout=30.0,
        )
    if DEBATER_PROVIDER == "nvidia":
        base = os.getenv("JUDGE_BASE_URL", "https://integrate.api.nvidia.com/v1")
        model = os.getenv("DEBATER_MODEL", "meta/llama-3.3-70b-instruct")
        print(f"[debater] NVIDIA NIM -> {model}")
        return AsyncOpenAI(
            api_key=_NVIDIA_KEY,
            base_url=base,
            timeout=60.0,
        )
    # groq
    print(f"[debater] Groq -> {os.getenv('DEBATER_MODEL', 'per-side config')}")
    return AsyncGroq(api_key=_GROQ_KEY, timeout=20.0)


debater_client = _make_client()
