"""
Rate-limit retry tests.

Run from backend/:  python test_llm_retry.py

No network. Fake exceptions stand in for Groq's, since the behaviour under test
is the decision to retry and how long to wait — not the SDK.
"""

import asyncio
import time

import config
from llm_retry import _is_rate_limit, _is_transient, _server_requested_delay, groq_call


class FakeError(Exception):
    def __init__(self, message, status_code=None, headers=None):
        super().__init__(message)
        self.status_code = status_code
        if headers is not None:
            self.response = type("R", (), {"headers": headers})()


# The message Groq actually returned when this bug was found.
REAL_429 = (
    "Error code: 429 - {'error': {'message': 'Rate limit reached for model "
    "`llama-3.1-8b-instant` in organization `org_01k` service tier `on_demand` on "
    "tokens per minute (TPM): Limit 6000, Used 5597, Requested 1384. Please try "
    "again in 9.81s.', 'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
)

ok = True


def check(name, got, want):
    global ok
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {name:<44} {got!r}")
    if not good:
        print(f"       wanted {want!r}")
        ok = False


async def main() -> None:
    print("-- classification --")
    check("real Groq 429 is a rate limit", _is_rate_limit(FakeError(REAL_429, 429)), True)
    check("429 by status code alone", _is_rate_limit(FakeError("slow down", 429)), True)
    check("500 is not a rate limit", _is_rate_limit(FakeError("boom", 500)), False)
    check("401 is not retryable", _is_transient(FakeError("bad key", 401)), False)
    check("400 is not retryable", _is_transient(FakeError("bad request", 400)), False)
    check("503 is transient", _is_transient(FakeError("unavailable", 503)), True)
    check("timeout is transient", _is_transient(FakeError("Connection timeout")), True)

    print("\n-- delay parsing --")
    check("parses '9.81s' from real message", _server_requested_delay(FakeError(REAL_429, 429)), 9.81)
    check("parses minutes+seconds", _server_requested_delay(FakeError("try again in 1m30s")), 90.0)
    check("Retry-After header wins", _server_requested_delay(
        FakeError("try again in 9.81s", 429, {"retry-after": "3"})), 3.0)
    check("no hint -> None", _server_requested_delay(FakeError("nope", 429)), None)

    print("\n-- retry behaviour --")
    config.LLM_BACKOFF_BASE = 0.05      # keep the suite fast
    config.LLM_BACKOFF_MAX = 0.2

    calls = {"n": 0}

    async def fails_twice_then_works(**_):
        calls["n"] += 1
        if calls["n"] <= 2:
            raise FakeError("Error code: 429 - rate_limit_exceeded", 429)
        return "recovered"

    check("recovers after 2 rate limits", await groq_call(fails_twice_then_works), "recovered")
    check("called exactly 3 times", calls["n"], 3)

    # A dead API key must fail immediately — retrying it just delays a failure
    # the operator has to see, and would stall an unattended sweep.
    auth_calls = {"n": 0}

    async def always_401(**_):
        auth_calls["n"] += 1
        raise FakeError("invalid api key", 401)

    try:
        await groq_call(always_401)
        check("401 propagates", "no raise", "raise")
    except FakeError:
        check("401 propagates immediately", auth_calls["n"], 1)

    # Exhaustion must still raise, not return None — a silent None would be
    # scored as a missing argument rather than a failed call.
    exhaust = {"n": 0}

    async def always_429(**_):
        exhaust["n"] += 1
        raise FakeError("429 rate_limit_exceeded", 429)

    try:
        await groq_call(always_429)
        check("exhaustion raises", "returned", "raised")
    except FakeError:
        check("exhaustion raises after N attempts", exhaust["n"], config.LLM_MAX_ATTEMPTS)

    print("\n-- server delay is actually honoured --")
    slow = {"n": 0}

    async def wants_one_second(**_):
        slow["n"] += 1
        if slow["n"] == 1:
            raise FakeError("Error code: 429 - try again in 1.0s", 429)
        return "ok"

    t0 = time.monotonic()
    await groq_call(wants_one_second)
    waited = time.monotonic() - t0
    # 1.0s requested + 0.5 skew margin + up to 0.75 jitter. LLM_BACKOFF_MAX is
    # 0.2 here on purpose: a server-stated wait must ignore that cap entirely.
    check("honours 1s request despite 0.2s backoff cap", 1.4 <= waited <= 2.5, True)
    print(f"       actual wait {waited:.2f}s")

    # And the ceiling that DOES apply to server requests still holds.
    config.LLM_RATE_LIMIT_MAX_WAIT = 0.3
    capped = {"n": 0}

    async def wants_an_hour(**_):
        capped["n"] += 1
        if capped["n"] == 1:
            raise FakeError("Error code: 429 - try again in 3600.0s", 429)
        return "ok"

    t0 = time.monotonic()
    await groq_call(wants_an_hour)
    check("absurd request is capped", time.monotonic() - t0 < 1.5, True)
    config.LLM_RATE_LIMIT_MAX_WAIT = 120.0

    print("\nPASS" if ok else "\nFAIL")


if __name__ == "__main__":
    asyncio.run(main())
