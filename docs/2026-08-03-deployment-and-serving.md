# ARGUS engineering log — 2026-08-03

Deployment, persistence, rate-limit allocation, and a serving bug that made the
host kill debates mid-run.

Sections are labelled by where the material belongs in the paper. Continues
`2026-08-01-calibration-and-conformal.md`.

---

## 1. Summary

The system is now reachable from any machine without local setup, debates
survive restarts, and a serving defect that silently ended debates is fixed.

| Work | Outcome |
|---|---|
| Single-origin deploy | Live at `argus-smjp.onrender.com` |
| MongoDB persistence | Debates survive restarts and redeploys |
| Rate-limit allocation | Four independent per-model buckets |
| Event-loop fix | Health-check latency 3.12s → 0.02s |
| Conformal wired into the verdict | C2 is a working feature, not a module |
| Verdict rebuilt around evidence | Implementation detail moved to JUDGE LOGS |

No new evaluation numbers. Nothing here changes kappa = 0.115 (n=56).

---

## 2. Deployment → *Methods / Appendix*

### 2.1 Single origin

The frontend hardcoded `http://localhost:8000` in six places, which works only
where both halves run on one machine. `src/app/lib/api.ts` resolves the base
once: `VITE_API_BASE` if the halves are deployed apart, `localhost:8000` in
split dev, same-origin otherwise.

`wsUrl()` derives the socket scheme from the page. A `wss://` page cannot open a
`ws://` socket and every free host terminates TLS, so a hardcoded `ws://` works
locally and fails on deploy — a class of bug that only appears in production.

The backend serves the built SPA when a build is present, so one process answers
both. The status payload moved from `/` to `/status`, and a catch-all returns
`index.html` for client-side routes: a deep link such as `/debate-dashboard` has
no file behind it and would 404 on refresh. The catch-all registers last so
every API route wins, and rejects paths escaping the build directory.

Verified before deploying: `/` serves the SPA, `/status` returns JSON,
`/debate-dashboard` returns HTML, `/judge/health` and `/assets/*` still resolve.

### 2.2 Host selection

**Hugging Face Spaces was the first recommendation and it was wrong** — the
Docker SDK is behind a paid plan. Recorded because the reasoning that produced
it (specs recalled rather than checked) is the error worth avoiding, not the
conclusion.

| | Render free | HF Spaces free |
|---|---|---|
| CPU / RAM | 0.1 vCPU / 512 MB | 2 vCPU / 16 GB |
| Docker | yes | **paid** |
| Sleep | 15 min idle, ~50s wake | ~48 h idle |
| Persistent disk | paid | included |

Vercel cannot host this half at all: serverless functions have no WebSocket
support and a 10s execution ceiling, against agent turns that take 15s.

Render deployed successfully in about four minutes. The 512 MB concern did not
materialise — the corpus builds into the image at build time, so nothing large
is assembled at runtime.

`render.yaml` declares the configuration so a redeploy reproduces it.
`GROQ_API_KEY` is `sync: false` — set in the dashboard, never committed.

### 2.3 Persistence

Free hosts give the container an ephemeral filesystem, so a file-backed archive
is wiped by every restart, sleep and redeploy. The corpus survives because it is
baked into the image; runtime output does not.

`history.py` selects a backend at import: MongoDB when `MONGODB_URI` is set,
files otherwise, behind one interface. Local development needs no database, and
a deployment that configures Mongo but cannot reach it falls back to files
rather than failing — losing the archive is bad, losing the debate that produced
it is worse. `/status` reports which store is live, because a deployment can
otherwise look healthy while quietly discarding everything it records.

Writes are upserts keyed on debate id. The store functions became async; a
blocking driver call inside the debate loop would stall the WebSocket streaming
that debate.

---

## 3. Rate-limit allocation → *Methods / threats to validity*

Groq meters tokens **per model**, so which model runs where decides throughput
as much as how many tokens are spent. Measured from response headers:

| Model | Tokens/min | Requests/day |
|---|---|---|
| `llama-3.3-70b-versatile` | 12,000 | 1,000 |
| `openai/gpt-oss-20b` | 8,000 | 1,000 |
| `openai/gpt-oss-120b` | 8,000 | 1,000 |
| `qwen/qwen3.6-27b` | 8,000 | 1,000 |
| `llama-3.1-8b-instant` | 6,000 | **14,400** |
| `allam-2-7b` | 6,000 | 7,000 |

Daily **token** limits are not exposed in headers and appear only inside a 429.
The one observed figure is **100,000 TPD on `llama-3.3-70b-versatile`**.

**Both debaters shared the single most restricted model.** That, not the judge,
is what produced `CON agent failed (R2S1): 429` partway through a debate.

### 3.1 Reasoning models are wrong for debaters

Measured, not assumed. `openai/gpt-oss-20b` spent **198 of 200 completion tokens
on its thinking pass** and returned two tokens of prose — 179 even at
`reasoning_effort="low"`. `qwen/qwen3.6-27b` emits a `<think>` block. For an
agent that must produce 120–200 words of argument this is the opposite of token
efficiency. They suit a judge, whose job is deliberation and whose output is
short JSON.

`groq/compound-mini` is also unusable for bucket isolation: its 429 names
`llama-3.3-70b-versatile`, so it proxies to that model and draws from the same
quota.

### 3.2 allam-2-7b as CON — works, with a disqualifying defect

The only remaining model with a separate bucket that produces direct prose.
Tested over a full debate: fluent English, no truncation, no language leakage
(the non-ASCII characters were smart quotes and `agōn`), and it cites real
specifics — `gerousia`, `hoplites`, Battle of Mantinea, the Thirty Tyrants.
Scores were competitive: R1 8.2 vs 6.8, R2 7.2 vs 6.5.

**But it abandons its stance.** Defending Sparta in R1S3 it wrote:

> "This reveals that **Athens was indeed the better place to live**, as its
> citizens were encouraged to explore new ideas... Sparta's approach limited
> intellectual progress."

It also asserted Plato and Socrates were Spartan; both were Athenian.

A debater that concedes hands the opponent points unrelated to argument quality,
and **the blind label-swap cannot correct for it** — swapping labels does not
fix a side that abandoned its position. Acceptable for exercising the pipeline,
disqualifying for any reported number.

**Any measurement must record which models produced it.** Two configurations now
exist.

---

## 4. The serving bug → *Methods / threats to validity*

A debate on the deployed instance ended with "Connection lost. The debate was
interrupted." Disabling auto-deploy did not help, because that was never the
cause. The host's event log was decisive:

    Instance failed: HTTP health check failed (timed out after 5 seconds)
    while running your code.

Render concluded the container was hung and killed it, ending the debate. Three
faults, each concealing the next.

**1. Retrieval ran on the event loop.** `retrieve_for_claim` is synchronous and
CPU-bound — it embeds the query, then scans every vector — and `verify_claims`
called it directly in a list comprehension, once per claim, up to eight per
round. On 0.1 vCPU that stalls the whole process for seconds, starving both the
WebSocket feeding the UI and the health check watching the container. Now
dispatched through `asyncio.to_thread`.

**2. The health check queried the database.** `/status` calls `get_stats()`,
which counts ChromaDB documents, so the check contended with the work it was
meant to observe. `/healthz` returns a constant and touches nothing.

**3. Turn indexing was quadratic — self-inflicted.** `_index_turns` walks every
round and embeds every turn, harmless while it ran once at the end. Saving after
each round, added the same day to survive restarts, made a three-round debate
embed 54 turns instead of 18. It now runs once, on the final save.

Measured over a full three-round debate, polling `/healthz` every two seconds:

| | Polls | Worst | Trend |
|---|---|---|---|
| Before | 121 | **3.12s** | climbing: 0.71 → 1.67 → 2.26 |
| After | 183 | **0.02s** | flat |

### 4.1 The lesson worth keeping

**The first run passed.** 3/3 rounds, zero failed health checks — the assertion
was green and the regression would have shipped. The signal was the *trend*
across rounds, not the pass/fail line. A test that only asserts a threshold
cannot see itself approaching one.

---

## 5. Corrections to earlier logs

- `/status` was described on 08-02 as "cheap and touches no model". It calls
  into ChromaDB. It was the wrong health-check target and caused §4.
- HF Spaces Docker was recommended as free. It is paid.
- The first dropped WebSocket was attributed to auto-deploy without evidence.
  The cause was the health-check timeout.

---

## 6. Configuration added

| Parameter | Default | Purpose |
|---|---|---|
| `MONGODB_URI` | unset | Enables the Mongo store; files otherwise |
| `MONGODB_DB` / `MONGODB_COLLECTION` | `argus` / `debates` | |
| `VITE_API_BASE` | unset | Only when the halves deploy apart |
| `FRONTEND_DIST` | `../dist` | Where the SPA build is served from |
| `PRO_MODEL` / `CON_MODEL` | `llama-3.1-8b-instant` / `llama-3.3-70b-versatile` | Per-side models; separate buckets |
| `WIKI_CONTACT` | repo URL | Wikimedia User-Agent contact |

---

## 7. Next

1. **Score 200+ pairs** — n=56 cannot settle kappa. Groq's ~100k/day token
   budget remains the constraint; the bucket split relieves per-minute
   contention but not the daily total.
2. **WebSocket has no reconnect.** Any drop still ends a debate for the viewer,
   though completed rounds now survive server-side.
3. Human study, to separate judge weakness from task mismatch.
4. Ablations and baselines.
