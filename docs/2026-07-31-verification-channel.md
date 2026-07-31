# ARGUS engineering log — 2026-07-31

Verification channel implementation, and the diagnosis of a four-layer failure in
the fine-tuned judge path.

Sections are labelled by where the material belongs in the paper.

---

## 1. Summary

Two things happened today.

**Built** the retrieval-grounded verification channel: extracted claims are
matched against a corpus and labelled SUPPORTED / REFUTED / NEI by an entailment
check independent of the scorer. The result bounds the evidence score from above.

**Found** that the fine-tuned judge (ArguScore-4B) had never successfully scored a
single round in the project's history, and that when it did run it was scoring
debates it had hallucinated rather than the ones supplied. Fixed.

Final state: full hybrid path working, 12.7s per 6-turn round, all tests passing.

---

## 2. System description → *Methods*

### 2.1 Pipeline position

Verification runs **after** extraction and **before** the symbolic scoring layer.
It consumes the specifics the blind-swap auditor extracted, not the raw
transcript — the scorer says what was cited, the corpus says whether it holds.

```
transcript
   ├─> ArguScore-4B (Kaggle)          -> raw criterion scores
   ├─> blind-swap auditor x2 (Groq)   -> extracted claims + independent scores
   │        └─> retrieval (ChromaDB) -> entailment -> SUPPORTED/REFUTED/NEI
   └─> symbolic layer: evidence caps, repetition penalty, TIE_BAND -> verdict
```

Both sides are verified concurrently. Total added latency is one batched
entailment call per round.

### 2.2 Entailment backends

Three, selected by `NLI_BACKEND`, identical contract `(claim, passages) -> (label, confidence, quote)`:

| Backend | Model | Notes |
|---|---|---|
| `groq` (default) | `llama-3.1-8b-instant` | No local dependency; one batched call per round |
| `local` | `cross-encoder/nli-deberta-v3-small` | Deterministic, free per call — **use for paper eval runs** |
| `lexical` | none | Content-word overlap. Floor baseline; cannot detect contradiction |

The `local` backend is the reproducible one and should generate the reported
numbers. `groq` exists so the system runs on a RAM-constrained laptop.

### 2.3 Grounding score

Let `S` = supported, `R` = refuted, `N` = NEI, and `A = S + R` (adjudicable claims).

```
coverage  = A / (S + R + N)
precision = S / A                               (undefined when A = 0)
ceiling   = 10.0                                if A = 0
          = GROUNDING_FLOOR + (10 - FLOOR)·precision   otherwise
penalty   = min(FABRICATION_MAX, R · FABRICATION_WEIGHT)

evidence_final = max(0, min(evidence_raw, ceiling) − penalty)
```

**NEI is excluded from the precision denominator by design.** A corpus that
cannot speak to a claim is a gap in the corpus, not a fault of the debater. With
`A = 0` the ceiling is 10.0 and the module is provably a no-op. The ceiling
tightens only in proportion to what the corpus can actually adjudicate, so
coverage rises with corpus size — making *coverage vs corpus size* the headline
scaling plot.

### 2.4 Two complementary caps

Verification does not subsume the pre-existing extraction cap. They catch
different defects:

| Defect | Caught by | Mechanism |
|---|---|---|
| Pure hand-wave, nothing extractable | `NO_EVIDENCE_CAP` = 3.0 | Empty extraction list |
| Specifics cited, corpus contradicts | grounding ceiling + penalty | REFUTED labels |

A vague gesture produces **zero adjudicable claims**, so grounding stays a no-op
and the extraction cap is what bites. Both layers are required.

### 2.5 Asymmetric burden of proof

**This is a design contribution, not a patch.** See §4.2 for the incident.

Refutation must be positively evidenced; support need not be. A REFUTED label
survives only if the backend supplies verbatim contradicting text **and** that
text is traceable to a retrieved passage. Otherwise it is downgraded to NEI,
which is inert.

Rationale: a missed fabrication costs a little precision; an invented one
corrupts the verdict. The asymmetry is deliberate and should be stated as such.

---

## 3. Motivation material → *Introduction / Motivation*

### 3.1 The four-layer failure

Presented in discovery order. Each layer concealed the one beneath it.

| Layer | Symptom | Reality |
|---|---|---|
| 1 | Occasional "FT scoring failed" with an empty message | `httpx` timeouts stringify to `""`; every call was timing out |
| 2 | `ft_online: true`, health check green | The 12s timeout was shorter than any call had ever taken — FT had **never** run |
| 3 | When forced to run, output was well-formed JSON | The ChatML prompt was invalid for a Llama-3 vocab |
| 4 | Scores looked plausible | The model was scoring a debate **it invented** |

**The observable signals were healthy at every layer.** `/judge/health` reported
`ft_online: true`, `status: online`, and the system returned confident,
well-formed, plausible scores throughout.

### 3.2 The decisive evidence

Input supplied to the model:

> PRO: Cleisthenes established the Athenian democratic assembly in **508 BCE**…
> CON: Sparta resisted Persia at **Thermopylae in 480 BCE**…

What the model generated and then scored:

> PRO: Athens implemented the **Delian League** victory in **500 BCE**…
> CON: Sparta's military dominance at **Peloponneses in 404 BCE**…

No overlap with the supplied text. Because `<|im_start|>` is absent from the
Llama-3 vocabulary, the model never saw a turn boundary, treated the prompt as
noise, and fell back to regenerating a training example.

### 3.3 The claim this supports

> An LLM judge scoring hallucinated content produces output statistically
> indistinguishable from one scoring real content. Score values alone cannot
> detect the failure. Only grounding against an external corpus can.

This is a real incident, not a hypothetical, and it is the strongest available
argument for the verification channel.

---

## 4. Empirical observations → *Results / Limitations*

### 4.1 ArguScore-4B is miscalibrated on the evidence axis

On a round where CON's entire case was *"the archaeological record clearly shows
historians agree Spartan society was more stable"* — zero named specifics, the
exact pattern the rubric defines as not-evidence:

| Config | CON evidence score |
|---|---|
| Reasoning enabled (1483 tok) | **9.0 / 10** |
| Reasoning skipped (185 tok) | 6.0 / 10 |

`NO_EVIDENCE_CAP` catches it downstream, but the underlying model is
miscalibrated on precisely the axis the paper concerns. **State this as a
limitation, do not hide it** — it also motivates the caps.

### 4.2 Absence-as-contradiction flipped a verdict

The claim *"Athens paid jurors so the poor could serve"* is **historically true**
(Pericles, *misthophoria*, c. 451 BCE) but absent from the 11-document corpus.
The `groq` NLI backend labelled it REFUTED.

| Stage | PRO total | CON total | Verdict |
|---|---|---|---|
| Before verification | 7.5 | 6.8 | PRO (margin 0.7) |
| With unguarded verification | 7.0 | 6.8 | **tie** ← wrong |
| With refutation guard | 7.5 | 6.8 | PRO (margin 0.7) |

A false fabrication penalty of 1.0 plus a ceiling of 6.5 changed the outcome.
Fix in §2.5. Regression test committed.

### 4.3 Reasoning changes the verdict

Same round, same greedy decoding, differing only in whether the think block ran:

| Variant | Tokens | Time | PRO | CON | Model's `round_winner` |
|---|---|---|---|---|---|
| H1 skip reasoning | 185 | 11.6s | 7.33 | 6.33 | `con` |
| H2 reasoning | 1483 | 90.1s | 8.0 | 9.0 | `con` |

Two observations:

1. **They disagree on which side scored higher.** Unresolved at n=1. Queued as an
   ablation (§5).
2. **H1's `round_winner` contradicts its own scores** — it reports `con` while
   giving PRO the higher total. Vindicates the existing design decision to
   recompute the winner in Python from totals via `TIE_BAND` and discard the
   model's field.

H1 shipped on feasibility grounds: H2 at 90.1s × 3 rounds × 500 debates ≈ 37
GPU-hours, exceeding Kaggle's ~30 h/week quota for a single eval pass. H2 also
sits exactly on the timeout and would fail intermittently.

### 4.4 Extraction quality gates verification quality

Before the extraction-prompt rewrite, the auditor emitted bare spans:

```
PRO: ['Cleisthenes', '508 BCE', 'democratic assembly',
      'Athenian juries numbered in the hundreds, drawn by lot',
      'Thermopylae', '480 BCE', 'Salamis', 'Athenian juries']
CON: ['Thermopylae', '480 BCE', 'Thermopylae in 480 BCE']
```

Three defects: fragments are not checkable propositions (`'508 BCE'` cannot be
entailed or contradicted, forcing NEI); `Thermopylae` was misattributed to PRO,
who mentioned it only to call it a defeat; and one claim was counted three times.

After rewriting for complete propositions, attribution-by-reliance, and
deduplication:

```
PRO: ['Cleisthenes established the democratic assembly in 508 BCE, giving
       ordinary citizens a direct vote and trial by jury.',
      'Athenian juries numbered in the hundreds, drawn by lot, making bribery
       impractical.',
      'Athens funded the fleet at Salamis that turned the war',
      'Athens paid jurors so the poor could serve']
CON: ['The Spartan Agoge produced the force that resisted Persia at Thermopylae
       in 480 BCE',
      'Sparta granted women property rights and physical education unmatched in
       Athens']
```

**Limitation for the paper:** extraction defects propagate directly into the
headline coverage metric.

### 4.5 Coverage is corpus-bound, not method-bound

Final measured coverage on the reference round: PRO **0.25**, CON **0.50**, on an
11-document corpus. PRO's coverage *fell* after the refutation guard (0.5 → 0.25)
because a false REFUTED became an honest NEI. Low coverage is currently the true
state of the world and reflects corpus size, not method quality.

**Implication:** conformal calibration on this corpus would be measuring noise.
Corpus expansion must precede calibration.

### 4.6 Determinism confirmed

Greedy decoding (`temperature=1e-6`, `do_sample=False`) reproduced identical
scores across separate invocations (pro 8.7 / con 7.7 on the 2-turn probe, in
both the notebook and a direct HTTP call). Required for reproducible eval.

`label_disagreement` was **0.0** across both blind-swap passes on every round
tested — no position bias detected at this sample size.

---

## 5. Open questions → *planned ablations*

| Question | Design | Status |
|---|---|---|
| Does inference-time reasoning improve judge–human agreement? | H1 vs H2, n ≥ 50 against gold labels | `REASONING_MODE` switch kept in the notebook for this |
| How does coverage scale with corpus size? | Sweep corpus 11 → 10³ → 10⁵ docs | Blocked on corpus build |
| Does grounding improve agreement with human verdicts? | `VERIFICATION_ENABLED=0/1` | Ready — config flip |
| Groq vs local NLI agreement | `NLI_BACKEND` sweep | Ready — config flip |
| Position bias at scale | `label_disagreement` distribution over n ≥ 100 | Ready |

Every ablation is a config flip, not a code edit — deliberate, for reproducibility.

---

## 6. Reproducibility → *Appendix*

### 6.1 Configuration

All in `backend/config.py`, all env-overridable.

| Parameter | Default | Meaning |
|---|---|---|
| `VERIFICATION_ENABLED` | `1` | `0` restores the pre-verification scoring path exactly |
| `NLI_BACKEND` | `groq` | `groq` / `local` / `lexical` |
| `NLI_MODEL` | `llama-3.1-8b-instant` | Groq entailment model |
| `NLI_LOCAL_MODEL` | `cross-encoder/nli-deberta-v3-small` | Local cross-encoder |
| `NLI_ENTAIL_THRESHOLD` | `0.60` | Local backend, entailment |
| `NLI_CONTRADICT_THRESHOLD` | `0.60` | Local backend, contradiction |
| `VERIFIER_TOP_K` | `3` | Passages retrieved per claim |
| `RETRIEVAL_MAX_DISTANCE` | `1.20` | L2 cutoff; beyond this the corpus is treated as silent |
| `GROUNDING_FLOOR` | `3.0` | Ceiling when every adjudicable claim is refuted |
| `FABRICATION_WEIGHT` | `1.0` | Penalty per refuted claim |
| `FABRICATION_MAX_PENALTY` | `3.0` | Penalty cap |
| `FT_JUDGE_TIMEOUT` | `45.0` | Was hardcoded 12.0 — the root of §3.1 layer 2 |
| `NO_EVIDENCE_CAP` | `3.0` | Pre-existing extraction cap |
| `TIE_BAND` | `0.5` | Margin at or below which a round is a tie |
| `BLIND_PASSES` | `2` | Label-swapped scoring passes |

Retrieval embedding is ChromaDB's default (`all-MiniLM-L6-v2`, L2 distance).
Corpus: 11 seed documents, `backend/debate/seed_evidence.py`.

### 6.2 Kaggle serving configuration

Model `s7nket/ArguScore-4B`, adapter `v2/adapter-final`, LoRA over Llama-3,
Unsloth 4-bit, `max_seq_length=2048`, 2× Tesla T4.

```python
prompt = tokenizer.apply_chat_template(messages, tokenize=False,
                                       add_generation_prompt=True) + PREFILL
# PREFILL = "<think>\n\n</think>\n\n" to skip reasoning, "" to allow it
tokenizer(prompt, return_tensors="pt", add_special_tokens=False)   # template emits BOS
generate(max_new_tokens=400, temperature=1e-6, do_sample=False,
         eos_token_id=tokenizer.convert_tokens_to_ids("<|eot_id|>"))
```

Measured throughput: **16 tok/s**. Production round: 185 tokens, ~12s.

### 6.3 Known-broken configurations, for the record

- `<|im_start|>` / `<|im_end|>` ChatML prompt — **not in this vocab**; produces
  hallucinated input (§3.2)
- `eos_token_id=convert_tokens_to_ids("<|im_end|>")` — resolves to `None`;
  generation never halts, runs the full budget
- `max_new_tokens=1024` with reasoning enabled — truncates on 6-turn rounds
  (`Parse failed after 1024 tok`)
- `add_special_tokens=True` with `apply_chat_template` — emits a second BOS
- `fix_scores` clamping with `max(1.0, …)` — the rubric defines 0–2 as valid, so
  this biases the bottom of the scale on every generated label

### 6.4 Files

| File | Change |
|---|---|
| `backend/debate/verifier.py` | New — retrieval, 3 entailment backends, refutation guard, grounding report |
| `backend/agents/judge_agent.py` | Grounding wired in; extraction prompt rewritten; `_dedup_claims`; FT logging reports exception type + elapsed |
| `backend/config.py` | All verification parameters; `FT_JUDGE_TIMEOUT` |
| `backend/test_verifier.py` | New — retrieval, entailment, invariants, refutation-guard regression |

### 6.5 Test invariants

`python test_verifier.py` asserts:

- Silent corpus is a no-op (ceiling 10.0, penalty 0.0)
- Empty input is a no-op
- One verdict per claim, order preserved
- Grounding only ever lowers a score, never raises it
- True-but-uncovered claims are NEI, never REFUTED
- REFUTED without a traceable quote downgrades to NEI
- REFUTED with a traceable quote survives

---

## 7. Next

1. **Corpus expansion** — coverage is corpus-bound (§4.5); calibration on 11
   documents would measure noise
2. Conformal prediction layer (verdict sets with coverage guarantees)
3. Gold-label evaluation set, then the §5 ablations
