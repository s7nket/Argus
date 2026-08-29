"""Provider-neutral async LLM retry helper for ARGUS.

The judge uses Gemini (primary) or Groq (fallback). This wrapper does not
assume a provider-specific client; it retries only transient/rate-limit failures.
It keeps ``groq_call`` as a backwards-compatible alias for existing imports.
"""

import asyncio
import contextvars
import logging
import os
import random
import re

import config

logger = logging.getLogger("argus.llm_retry")

_retry_listener: contextvars.ContextVar = contextvars.ContextVar(
    "argus_retry_listener", default=None
)


def set_retry_listener(fn) -> None:
    """Register an async fn(attempt, total, delay, rate_limited)."""
    _retry_listener.set(fn)


async def _notify(attempt: int, total: int, delay: float, rate_limited: bool) -> None:
    fn = _retry_listener.get()
    if fn is None:
        return
    try:
        await fn(attempt, total, delay, rate_limited)
    except Exception:
        pass


_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _server_requested_delay(exc: Exception) -> float | None:
    """Extract a server-provided retry delay when one exists."""
    response = getattr(exc, "response", None)
    if response is not None:
        header = getattr(response, "headers", {}) or {}
        for key in ("retry-after", "Retry-After", "x-ratelimit-reset-tokens"):
            raw = header.get(key)
            if raw:
                try:
                    return float(str(raw).rstrip("s"))
                except ValueError:
                    pass

    match = _WAIT_RE.search(str(exc))
    if match:
        minutes = float(match.group(1) or 0)
        return minutes * 60 + float(match.group(2))
    return None


def _status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is not None:
        try:
            return int(status)
        except (TypeError, ValueError):
            pass
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None) if response is not None else None
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _is_rate_limit(exc: Exception) -> bool:
    """True for throttling/rate-limit failures, not request-size failures."""
    status = _status_code(exc)
    if status == 413:
        return False
    if status == 429:
        return True
    text = str(exc).lower()
    if "413" in text or "request too large" in text or "reduce your message size" in text:
        return False
    return "429" in text or "rate_limit" in text or "rate limit" in text


def _is_transient(exc: Exception) -> bool:
    """Retry server/network failures; never retry ordinary 4xx errors."""
    status = _status_code(exc)
    if status is not None:
        return status in (408, 500, 502, 503, 504)
    text = str(exc).lower()
    return any(s in text for s in (
        "timeout", "connection", "temporarily unavailable", "service unavailable",
        "server disconnected", "connection reset",
    ))


def _provider() -> str:
    """Gemini takes priority; fall back to Groq."""
    if os.getenv("GEMINI_API_KEY", "").strip():
        return "gemini"
    return "groq"


def _init_groq_api_keys() -> list[str]:
    keys = []
    for var in ("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3"):
        raw = os.getenv(var, "")
        keys.extend(k.strip() for k in raw.split(",") if k.strip())
    return keys


async def llm_call(fn, *args, **kwargs):
    """Call the configured LLM client with safe retry/backoff behavior.

    Gemini uses a single key via the OpenAI-compat endpoint.
    Groq retains its multi-key rotation behavior.
    """
    provider = _provider()
    groq_keys = _init_groq_api_keys() if provider == "groq" else []
    current_key_idx = 0

    base_attempts = max(1, config.LLM_MAX_ATTEMPTS)
    attempts = base_attempts * max(1, len(groq_keys)) if provider == "groq" else base_attempts
    last: Exception | None = None

    for attempt in range(attempts):
        try:
            return await fn(*args, **kwargs)
        except Exception as exc:
            last = exc
            status = _status_code(exc)
            text = str(exc).lower()

            # Groq-only key rotation.
            quota_exceeded = (
                provider == "groq"
                and (
                    status == 401
                    or (status == 429 and (
                        "insufficient_quota" in text
                        or "billing" in text
                        or "please upgrade" in text
                    ))
                )
            )
            if quota_exceeded and len(groq_keys) > 1:
                current_key_idx = (current_key_idx + 1) % len(groq_keys)
                client = getattr(getattr(fn, "__self__", None), "_client", None)
                if client is not None and hasattr(client, "api_key"):
                    client.api_key = groq_keys[current_key_idx]
                print(
                    f"[llm] Groq quota/auth error — switching key "
                    f"(index {current_key_idx})"
                )
                continue

            rate_limited = _is_rate_limit(exc)
            transient = _is_transient(exc)
            if not (rate_limited or transient) or attempt == attempts - 1:
                raise

            requested = _server_requested_delay(exc) if rate_limited else None
            if requested is not None:
                delay = min(
                    requested + 0.5,
                    config.LLM_RATE_LIMIT_MAX_WAIT,
                )
            else:
                delay = min(
                    config.LLM_BACKOFF_BASE * (2 ** (attempt % base_attempts)),
                    config.LLM_BACKOFF_MAX,
                )

            delay += random.uniform(0, 0.75)
            logger.warning(
                "%s %s, retry %s/%s in %.1fs",
                provider,
                "rate limited" if rate_limited else type(exc).__name__,
                attempt + 1,
                attempts - 1,
                delay,
            )
            print(
                f"[llm] {provider} — "
                f"{'429' if rate_limited else type(exc).__name__} — "
                f"retry {attempt + 1}/{attempts - 1} in {delay:.1f}s"
            )
            await _notify(attempt + 1, attempts - 1, delay, rate_limited)
            await asyncio.sleep(delay)

    raise last if last else RuntimeError("llm_call exhausted with no exception")


# Backwards compatibility: other ARGUS modules can continue importing groq_call.
groq_call = llm_call