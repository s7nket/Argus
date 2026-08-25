---
title: ARGUS
emoji: ⚖️
colorFrom: gray
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

# ARGUS — Verification-Grounded Multi-Agent Debate

> **Autonomous Reasoning & Generative Utility System**
> _"Two minds. One truth."_

Two LLM agents debate a resolution over three rounds; a judge scores each round
and delivers a verdict. The contribution is not the debate — it is what makes
the scoring checkable rather than asserted.

## Why the scores can be trusted

**Retrieval-grounded verification.** Every specific a debater cites is matched
against a corpus and labelled SUPPORTED / REFUTED / NEI by an entailment check
independent of the scorer. The judge cannot award evidence credit it cannot
verify. A claim the corpus contradicts is penalised as fabrication; a claim it
simply cannot reach is not held against the debater.

**Refutation carries a burden of proof.** An accusation of fabrication must cite
verbatim contradicting text traceable to a retrieved passage, and must survive a
second check in isolation. Absence of evidence is never treated as contradiction
— that mistake once flipped a verdict.

**Blind label-swapped scoring.** Each round is scored twice with the debater
labels swapped, so a preference for either position cancels out. The residual
disagreement is reported rather than hidden.

**Conformal verdict sets.** The verdict carries a distribution-free coverage
guarantee, and the system abstains when the scores do not separate. Most judges
always name a winner; this one says when it cannot.

**Deterministic scoring layer.** Evidence caps, repetition penalties and the tie
band are computed in Python from the scores. The language model describes the
outcome; it never decides it.

## Running it locally

```bash
# backend
cd backend && pip install -r requirements.txt
python -m debate.build_corpus          # optional: expands the corpus from Wikipedia
uvicorn main:app --port 8000

# frontend, in a second shell
npm install && npm run dev
```

Create `backend/.env` with at least `GROQ_API_KEY`. With no frontend build
present the backend serves its API only, and `/` returns the status payload.

Building the frontend (`npm run build`) makes the backend serve it at `/`, which
is how the deployed image runs — one process, one origin, no CORS.

## Deploying

The Dockerfile builds the frontend and serves both halves from one container. It
honours `$PORT`, so the same image runs on Spaces (7860), Render and Koyeb
unchanged.

| Name | Kind | Required | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | secret | yes | Debater agents and the auditing judge |
| `FT_JUDGE_URL` | variable | no | Kaggle ArguScore-4B endpoint |
| `JUDGE_MODEL` | variable | no | Defaults to `llama-3.3-70b-versatile` |
| `BLIND_PASSES` | variable | no | `1` halves token spend, drops the bias metric |

Never put a key in a *variable* — variables are readable, secrets are not.

## The fine-tuned scorer

ArguScore-4B is a LoRA fine-tune served from a Kaggle notebook, because it needs
a GPU that free hosting does not provide. It is reached over a reserved ngrok
domain, so `FT_JUDGE_URL` stays constant across sessions.

When that notebook is not running, round scoring falls back to Groq and the
interface says so: the sidebar reads `JUDGE-0 / Groq fallback` with an amber dot
instead of `ARGUSCORE-4B`, and each round's audit records which scorer ran. The
fallback is visible, not silent — an earlier version hid it, and two of three
rounds were scored by a different judge with nothing on screen to say so.

## Known limits

- Groq's free tier allows 6000 tokens/minute and ~100k/day. One round costs
  roughly 6k, so a three-round debate takes several minutes and a few debates
  exhaust a day.
- The corpus is built into the image at build time. If that fetch fails, the app
  still boots on an 11-document seed corpus and grounding coverage reads near
  zero.
- Free Spaces sleep after inactivity; the first request after a sleep is slow.
- Against human argument-quality labels the judge currently reaches Cohen's
  kappa ≈ 0.11 (n=56) — weak. The conformal layer responds correctly by
  abstaining on most rounds. See `docs/` for the measurements.

## Documentation

`docs/` carries dated engineering logs organised by paper section: what was
built, what was measured, and the configurations known to be broken.

Hero imagery is AI-generated.
