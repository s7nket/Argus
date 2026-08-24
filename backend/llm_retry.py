"""
Rate-limit retry for Groq calls.

Groq's free tier allows 6000 tokens per minute. A single debate round costs
roughly that much — six agent turns, two blind scoring passes at up to 1400
tokens each, and a verification call — so a three-round debate reliably hit 429
partway through and the orchestrator aborted the whole debate:

    CON agent failed (R2S1): Error code: 429 - Limit 6000, Used 5597,
    Requested 1384. Please try again in 9.81s.

Losing a debate two rounds in is bad interactively and fatal for an unattended
eval sweep, where hundreds of debates run without anyone watching. Retrying is
what makes those runs *complete*; it does not make them faster, since the
token-per-minute ceiling is a hard physical limit.

Groq states the exact wait in the error message, so the first choice is always
to obey what the server said rather than guess.
"""

import asyncio
import contextvars
import logging
import random
import re

import config

logger = logging.getLogger("argus.llm_retry")

# A caller can register an async callback here to be told when a call is waiting
# out a rate limit. Without it a retry is completely silent, and since a single
# wait can run to LLM_RATE_LIMIT_MAX_WAIT seconds — several minutes across
# attempts — the UI showed nothing at all between clicking Start Debate and the
# eventual failure. That is indistinguishable from a broken button.
#
# A ContextVar rather than a global: it propagates into the tasks a debate
# spawns without being visible to unrelated requests handled concurrently.
_retry_listener: contextvars.ContextVar = contextvars.ContextVar("argus_retry_listener", default=None)


def set_retry_listener(fn) -> None:
    """Register an async fn(attempt, total, delay, rate_limited) for this context."""
    _retry_listener.set(fn)


async def _notify(attempt: int, total: int, delay: float, rate_limited: bool) -> None:
    fn = _retry_listener.get()
    if fn is None:
        return
    try:
        await fn(attempt, total, delay, rate_limited)
    except Exception:
        # Telling the user about a delay must never itself break the call.
        pass

# "Please try again in 9.81s" / "try again in 1m30s"
_WAIT_RE = re.compile(r"try again in\s+(?:(\d+)m)?([\d.]+)s", re.IGNORECASE)


def _server_requested_delay(exc: Exception) -> float | None:
    """The wait Groq asked for, from the Retry-After header or the message."""
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


def _is_rate_limit(exc: Exception) -> bool:
    """
    True only for "you sent too much too fast", never "this request is too big".

    Groq reports an oversized single request as HTTP 413 but tags it
    code: rate_limit_exceeded, so a naive string match retries it — and the
    identical request fails identically every time. That cost 45s of pointless
    backoff before failing anyway. Size errors must reach the caller, which can
    respond by splitting the batch.
    """
    status = getattr(exc, "status_code", None)
    if status == 413:
        return False
    if status == 429:
        return True
    text = str(exc).lower()
    if "413" in text or "request too large" in text or "reduce your message size" in text:
        return False
    return "429" in text or "rate_limit" in text


def _is_transient(exc: Exception) -> bool:
    """Server-side wobble worth retrying. Never retry 4xx other than 429."""
    status = getattr(exc, "status_code", None)
    if status is not None:
        return status in (408, 500, 502, 503, 504)
    return any(s in str(exc).lower() for s in
               ("timeout", "connection", "temporarily unavailable", "service unavailable"))


import os

_API_KEYS = []
_CURRENT_KEY_IDX = 0

def _init_api_keys():
    global _API_KEYS
    if not _API_KEYS:
        keys = []
        for var in ("GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_API_KEY_3"):
            raw = os.getenv(var, "")
            keys.extend([k.strip() for k in raw.split(",") if k.strip()])
        _API_KEYS = keys if keys else [""]

def _is_quota_exceeded(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    err_text = str(exc).lower()
    if status == 401:
        return True
    if status == 429:
        if "insufficient_quota" in err_text or "billing" in err_text or "please upgrade" in err_text:
            return True
        requested = _server_requested_delay(exc)
        if requested is None or requested > 300:
            return True
    return False

async def groq_call(fn, *args, **kwargs):
    """
    Call a Groq endpoint, waiting out rate limits instead of failing the debate.

    Usage mirrors the original call, one wrapper deep:

        response = await groq_call(client.chat.completions.create, model=..., ...)

    A 429 waits for whatever the server asked for; anything else transient uses
    exponential backoff. Jitter matters here because the two blind scoring passes
    fire concurrently via asyncio.gather — without it they would rate-limit
    together, sleep for the same interval, and collide again on every retry.

    Non-retryable errors (bad key, bad model, malformed request) propagate
    immediately: retrying those just delays a failure the caller must see.
    """
    _init_api_keys()
    global _CURRENT_KEY_IDX
    
    base_attempts = max(1, config.LLM_MAX_ATTEMPTS)
    attempts = base_attempts * max(1, len(_API_KEYS))
    last: Exception | None = None

    for attempt in range(attempts):
        try:
            return await fn(*args, **kwargs)
        except Exception as e:                     # noqa: BLE001 - re-raised below
            last = e
            
            quota_exceeded = _is_quota_exceeded(e)
            if quota_exceeded and len(_API_KEYS) > 1:
                _CURRENT_KEY_IDX = (_CURRENT_KEY_IDX + 1) % len(_API_KEYS)
                new_key = _API_KEYS[_CURRENT_KEY_IDX]
                
                client = getattr(getattr(fn, "__self__", None), "_client", None)
                if client and hasattr(client, "api_key"):
                    client.api_key = new_key
                    
                logger.warning(f"Quota/Auth error. Switched to key index {_CURRENT_KEY_IDX}")
                print(f"[llm] Quota/Auth error — switching API key (now using index {_CURRENT_KEY_IDX})")
                continue
                
            rate_limited = _is_rate_limit(e)
            if not (rate_limited or _is_transient(e)) or attempt == attempts - 1:
                raise

            requested = _server_requested_delay(e) if rate_limited else None
            if requested is not None:
                # Obey the server. LLM_BACKOFF_MAX must NOT clamp this: if Groq
                # says wait 60s and our cap is 45, we retry early and get limited
                # again immediately. A separate, larger ceiling only guards
                # against a pathological instruction to sleep for hours.
                delay = min(requested + 0.5, config.LLM_RATE_LIMIT_MAX_WAIT)
            else:
                # Our own guess, so our own cap applies.
                delay = min(config.LLM_BACKOFF_BASE * (2 ** (attempt % base_attempts)), config.LLM_BACKOFF_MAX)

            delay += random.uniform(0, 0.75)
            logger.warning(
                f"{'rate limited' if rate_limited else type(e).__name__}, "
                f"retry {attempt + 1}/{attempts - 1} in {delay:.1f}s"
            )
            print(f"[llm] {'429' if rate_limited else type(e).__name__} — "
                  f"retry {attempt + 1}/{attempts - 1} in {delay:.1f}s")
            await _notify(attempt + 1, attempts - 1, delay, rate_limited)
            await asyncio.sleep(delay)

    raise last if last else RuntimeError("groq_call exhausted with no exception")
