# ARGUS engineering log — 2026-08-01

Rate-limit retry, corpus expansion, refutation confirmation, the conformal
layer, and the first evaluation against human labels.

Sections are labelled by where the material belongs in the paper. Continues
`2026-07-31-verification-channel.md`.

---

## 1. Summary

Five things shipped. The last one matters most, and it is not good news.

| Work | Outcome |
|---|---|
| Rate-limit retry | Debates complete instead of aborting mid-round |
| Corpus expansion | 11 -> 2298 documents; coverage 0.58 -> 0.75 |
| Refutation confirmation | False refutations 2/12 -> 1/12 |
| Conformal layer | Coverage guarantee verified on synthetic data |
| **First human-label evaluation** | **Cohen's kappa 0.086 — the judge barely beats chance** |

The evaluation result reframes the paper. See §5.

---

## 2. Rate-limit retry → *Methods / Implementation*

Groq's free tier allows 6000 tokens/minute; one debate round costs about that.
Without retry the orchestrator aborted the entire debate mid-round:

    CON agent failed (R2S1): Error code: 429 - Limit 6000, Used 5597,
    Requested 1384. Please try again in 9.81s.

`groq_call()` wraps all nine Groq call sites. It obeys the wait the server
states rather than guessing — Groq puts the number in the error and sometimes in
a `Retry-After` header. Jitter is applied because the two blind scoring passes
fire concurrently through `asyncio.gather`; without it they rate-limit together,
sleep identically, and collide again on every retry.

Result: a 3-round debate that previously died at round 2 completed in 309s.

**Two bugs the tests caught before they reached a sweep:**

- `LLM_BACKOFF_MAX` was clamping the *server-requested* delay. If Groq asks for
  60s and the cap is 45, the retry lands inside the window and earns another 429
  — an infinite loop that never succeeds. Our guess and an explicit instruction
  now have separate ceilings.
- Groq reports an oversized single request as **HTTP 413 but tags it
  `code: rate_limit_exceeded`**, so a string match retried a deterministic
  failure three times before failing anyway.

---

## 3. Corpus expansion → *Methods / Results*

44 Wikipedia articles covering the resolution types the debaters are given,
split into ~180-word passages.

| | Before | After |
|---|---|---|
| Documents | 11 | **2298** |
| Coverage | 0.58 | **0.75** |
| Precision | 0.71 | 0.78 |
| NEI | 5/12 | 3/12 |

Two claims previously labelled REFUTED became correctly SUPPORTED: **retrieval
failure had been masquerading as contradiction.**

This is the *coverage vs corpus size* data point — two points so far (11, 2298).
A third at ~200 articles would make it a curve.

### 3.1 Wikimedia User-Agent (reproducibility trap)

All 44 articles returned **403** on the first attempt. Wikimedia requires a
machine-readable contact in the User-Agent. Rejected: prose
(`"(academic project; contact via github.com/...)"`), httpx's default, and
`Mozilla/5.0`. Accepted: a bracketed URL, `ArgusBot/1.0 (https://github.com/...)`.

### 3.2 NLI batching broke exactly when the corpus became useful

One entailment call per round was fine against one-sentence seed entries. With
Wikipedia passages the same 12 claims produced a **7389-token request against a
6000 ceiling**, failed with 413, and degraded verification to all-NEI. Claims are
now split into budget-fitting batches, run sequentially — they share one TPM
bucket, so issuing them together would only convert a size error into a rate limit.

---

## 4. Refutation confirmation → *Methods (contribution C1)*

REFUTED is the only label that costs a debater anything, and it was the least
reliable label the verifier produced. Two independent defects:

**False positives.** Against 2298 documents the batch screen still labelled true
claims as refuted 2 times in 12. One — *"Athens paid jurors so the poor could
serve"* (Pericles, misthophoria, c. 451 BCE) — had already flipped a round from
a PRO win to a tie.

**Context dependence.** The screen scores every claim of a round in one prompt,
so a label moved with whichever other claims shared the call. The same claim was
observed flipping REFUTED/SUPPORTED between runs. **Published numbers would
drift with how many claims a round happened to produce.**

Refutations now face a second pass, alone, with only their own passages.

| Metric | Off | On |
|---|---|---|
| False refutations | 2/12 | **1/12** |
| Precision | 0.78 | **0.88** |
| Evidence cap | 8.4 | 9.1 |
| Fabrication penalty | 2.0 | 1.0 |
| Coverage | 0.75 | **0.67** |

Coverage falls because a rejected refutation becomes NEI. That is the intended
trade for a penalty that decides verdicts; **report both numbers together.**

Only refutations pay for the extra call, so cost tracks how often the system
accuses rather than corpus size. A confirmer that errors rejects, so an outage
cannot manufacture an accusation.

### 4.1 Limitation: contested claims

The surviving false refutation is not a model failure. *"Rent control reduces
the long-run supply of rental housing"* is contradicted by passages **in the
Wikipedia rent control article itself**, because the article presents both sides.

> On contested empirical questions this architecture measures **corpus stance,
> not truth**, and cannot distinguish "contradicted by evidence" from "debated in
> the literature."

Obvious next step: treat a claim as NEI when retrieved passages disagree with
each other.

---

## 5. Conformal prediction → *Contribution C2, and the central result*

### 5.1 The method works

Split conformal prediction over verdicts. Nonconformity is the negated signed
margin toward the true winner; the quantile uses the finite-sample correction
`ceil((n+1)(1-alpha))/n`.

Verified on synthetic rounds, 30 random splits per alpha:

| alpha | Target | Empirical | Set size | Abstain |
|---|---|---|---|---|
| 0.05 | 0.95 | 0.955 | 1.96 | 48% |
| 0.10 | 0.90 | **0.905** | 1.69 | 34% |
| 0.20 | 0.80 | 0.806 | 1.35 | 18% |

Coverage tracks the diagonal. Selective accuracy 0.908 vs 0.735 naive.

### 5.2 On real data it exposes something worse

**n = 43 rounds, all scored by `kaggle-ft (audited)`** (scorer pinned — see §5.4).

```
verdict agreement       0.558
agreement (non-tie)     0.632
Cohen's kappa           0.086      <- essentially chance
Spearman rho (margins)  0.324

conformal, alpha = 0.1
  empirical_coverage    1.000      <- guarantee holds
  mean_set_size         2.82 / 3
  abstention_rate       0.909      <- abstains on 91% of rounds
  selective_accuracy    1.000
```

**The conformal layer is functioning correctly and revealing that the underlying
judge is close to uninformative.** It achieves coverage by almost never
committing. A set holding 2.82 of 3 possible outcomes is technically valid and
practically empty.

Cohen's kappa of 0.086 means ArguScore-4B's ordering of arguments agrees with
human annotators barely above chance. Raw agreement of 0.558 flatters this —
kappa is the number to report.

### 5.3 How much is the judge, how much is task mismatch

Both, and this cannot yet be separated:

- IBM arguments are **standalone one-to-two sentence claims** scored for
  "quality". ARGUS scores evidence/logic/relevance over **debate rounds with
  rebuttals**. Different task.
- Many IBM arguments are too short to carry the named specifics the rubric
  rewards, so the evidence axis has little to grip.
- 40/254 pairs are ties under the 0.05 WA band, and ties are the hardest class.

**Honest framing for the paper:** if kappa stays near 0.1 on debate-level data,
the contribution is *"calibrated abstention over a weak judge"* — which is still
publishable and arguably more useful than an overconfident one — not *"an
accurate judge"*. Do not claim the latter without evidence.

### 5.4 Scorer confound, found and fixed

The first run pooled **16 `kaggle-ft` rounds with 4 `groq-blind-swap`** rounds,
because the ngrok tunnel dropped partway. Metrics across two different judges
describe neither.

`--require-scorer` now discards any round the requested scorer did not handle,
and the report prints a loud warning if more than one scorer appears. The
pre-fix pooled numbers (kappa 0.224, n=20) are **not comparable** to the
homogeneous ones and should not be cited.

---

## 6. Gold-label data → *Methods / Appendix*

`ibm-research/argument_quality_ranking_30k` (IBM Project Debater): ~30k
arguments with human weighted-average quality (`WA`, 0-1) and stance labels.
Fetched through HuggingFace's datasets-server HTTP API — no `datasets`
dependency — and cached for offline reproducibility.

**254 pairs, 15 topics, 118 pro / 96 con / 40 tie**, mean human margin 0.253.
Pairs are drawn **per topic**, not globally: conformal coverage assumes
exchangeability, and a set dominated by one resolution inflates coverage there
while destroying it elsewhere.

### 6.1 Limitation that must be stated, not footnoted

> Two independently written arguments are **not a debate**. There is no
> rebuttal, no adaptation, no engagement between sides. This calibrates and
> validates the SCORER on argument quality.

Debate-level ground truth needs either debate.org winner labels or the human
annotation study. **debate.org was checked and is unusable** — the
`notaphoenix/debateorg_*` datasets' `label` field is political leaning, not
winner.

---

## 7. Operational limits → *Appendix / threats to validity*

**Groq free tier is the binding constraint on evaluation.**

- 6000 TPM, and ~100k/day. Scoring 20 pairs exhausted a day's budget; the run
  stalled with the retry logic requesting waits beyond its own 120s ceiling.
- One debate round costs ~6k tokens => ~1 round/minute regardless of retry.
- 500 debates x 3 rounds ~= **25 hours wall-clock**, if nothing fails.

Levers, in order of preference: `BLIND_PASSES=1` (halves judge tokens, costs the
position-bias metric), a paid tier, or running the whole eval on Kaggle where
the FT model is already free.

---

## 8. Configuration added

| Parameter | Default | Purpose |
|---|---|---|
| `LLM_MAX_ATTEMPTS` | 4 | Retry attempts |
| `LLM_BACKOFF_BASE` / `_MAX` | 2.0 / 45.0 | Caps OUR guess only |
| `LLM_RATE_LIMIT_MAX_WAIT` | 120.0 | Ceiling on a server-stated wait |
| `FT_MAX_ATTEMPTS` / `FT_RETRY_DELAY` | 3 / 2.0 | Idle ngrok tunnel serves its own 404 |
| `CONFIRM_REFUTATIONS` | 1 | Isolated re-check of refutations |
| `CONFORMAL_ALPHA` | 0.1 | Target miscoverage |
| `CONFORMAL_ENABLED` | 1 | Attach verdict sets |
| `WIKI_CONTACT` | repo URL | Wikimedia User-Agent contact |

Every ablation is a config flip, not a code edit.

---

## 9. Files

| File | Change |
|---|---|
| `backend/llm_retry.py` | New — rate-limit retry |
| `backend/debate/build_corpus.py` | New — Wikipedia corpus builder |
| `backend/debate/conformal.py` | New — split conformal prediction |
| `backend/eval/datasets.py` | New — IBM-Rank-30k loader, pair construction |
| `backend/eval/calibrate.py` | New — scoring, correlation, calibration |
| `backend/debate/verifier.py` | Refutation confirmation, batch chunking |
| `backend/agents/judge_agent.py` | FT tunnel retry |
| `backend/test_llm_retry.py`, `test_conformal.py` | New test suites |

---

## 10. Next

1. **Score 200+ pairs** — n=43 is too few to conclude anything about kappa
2. **Wire conformal into `judge_final_verdict`** — implemented, calibrated,
   but nothing calls it
3. Determine how much of kappa=0.086 is task mismatch vs judge weakness —
   requires debate-level labels, i.e. the human study
4. Ablations (all config flips) and baselines
