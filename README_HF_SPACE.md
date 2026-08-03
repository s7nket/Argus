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

Two LLM agents debate; a judge scores each round. What makes the scoring
checkable rather than asserted:

- **Retrieval-grounded verification** — every specific a debater cites is matched
  against a corpus and labelled SUPPORTED / REFUTED / NEI. The judge cannot award
  evidence credit it cannot verify.
- **Blind label-swapped scoring** — each round is scored twice with the debater
  labels swapped, so a preference for either position cancels out.
- **Conformal verdict sets** — the verdict carries a distribution-free coverage
  guarantee, and the system abstains when the scores do not separate.

## Setup

Add these under **Settings → Variables and secrets**:

| Name | Kind | Required | Notes |
|---|---|---|---|
| `GROQ_API_KEY` | secret | yes | Debater agents and the auditing judge |
| `FT_JUDGE_URL` | variable | no | Kaggle ArguScore-4B endpoint |
| `JUDGE_MODEL` | variable | no | Defaults to `llama-3.3-70b-versatile` |
| `BLIND_PASSES` | variable | no | `1` halves token spend, drops the bias metric |

Never paste a key into a *variable* — variables are visible, secrets are not.

## The fine-tuned scorer

ArguScore-4B needs a GPU and cannot run here. It is served from a Kaggle
notebook over a reserved ngrok domain, so `FT_JUDGE_URL` stays constant across
sessions — set it once.

When that notebook is not running the system falls back to Groq for round
scoring, and says so: the sidebar shows `JUDGE-0 / Groq fallback` with an amber
dot instead of `ARGUSCORE-4B`, and each round's audit records which scorer ran.
The fallback is honest, not hidden.

## Known limits

- Groq's free tier allows 6000 tokens/minute and ~100k/day. One debate round
  costs roughly 6k, so a three-round debate takes several minutes and a handful
  of debates exhausts a day.
- The corpus is built into the image at build time from Wikipedia. If that fetch
  fails during a build, the app still boots on an 11-document seed corpus, and
  grounding coverage will read near zero.
- Free Spaces sleep after inactivity; the first request after a sleep is slow.
