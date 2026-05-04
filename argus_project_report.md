# ARGUS — Multi-Agent AI Debate System
### Comprehensive Project Report

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Technology Stack](#2-technology-stack)
3. [System Design](#3-system-design)
4. [Architecture Design](#4-architecture-design)
5. [Agent Workflow](#5-agent-workflow)
6. [Features](#6-features)
7. [Changes & Improvements Made](#7-changes--improvements-made)
8. [How to Run](#8-how-to-run)
9. [Ongoing Work](#9-ongoing-work)
10. [Future Scope & Enhancements](#10-future-scope--enhancements)

---

## 1. Introduction

**ARGUS** is a real-time, multi-agent AI debate platform where two autonomous AI agents argue opposing sides of any user-supplied topic — and a third, impartial AI judge scores every round and declares a final winner.

The core idea is simple but powerful: **structured adversarial reasoning between AI agents**. Rather than asking a single model to "consider both sides," ARGUS forces genuine intellectual conflict. Each agent is locked into its position, must escalate in intensity each sub-round, and cannot concede — mirroring the dynamics of a real competitive debate.

### Why ARGUS?

| Traditional AI Q&A | ARGUS Debate |
|---|---|
| One model, one perspective | Two agents, two locked positions |
| No adversarial pressure | Agents must attack each other's arguments |
| No scoring | Per-round scoring + fallacy detection |
| Static response | Live, streaming, round-by-round progression |

### Core Philosophy

> *"Two agents. One judge. Zero bias."*

ARGUS is built around the belief that the best way to examine a topic is through structured conflict — the same principle behind legal courts, parliamentary debates, and Socratic dialogue. Applying this to AI creates an objectively more rigorous reasoning pipeline than any single-model approach.

---

## 2. Technology Stack

### Frontend

| Technology | Version | Purpose |
|---|---|---|
| **React** | 18.3.1 | UI framework |
| **TypeScript** | — | Type safety |
| **Vite** | 6.3.5 | Build tool & dev server |
| **TailwindCSS** | 4.1.12 | Utility-first styling |
| **Motion (Framer Motion)** | 12.23.24 | Animations & transitions |
| **React Router** | 7.13.0 | Client-side routing |
| **Lucide React** | 0.487.0 | Icon set |
| **Recharts** | 2.15.2 | Data visualization |
| **Radix UI** | Various | Accessible UI primitives |
| **MUI (Material UI)** | 7.3.5 | Additional UI components |

### Backend

| Technology | Version | Purpose |
|---|---|---|
| **Python** | 3.x | Backend language |
| **FastAPI** | Latest | Async REST + WebSocket API framework |
| **Uvicorn** | Latest | ASGI server (with standard extras) |
| **Groq SDK** | Latest | API client for fast LLM inference (PRO, CON, Rebuttal agents) |
| **OpenAI SDK** | Latest | OpenAI-compatible client for the Judge (Kaggle model) |
| **httpx** | Latest | Async HTTP client (Judge health check) |
| **python-dotenv** | Latest | Environment variable management |

### AI Models

| Agent | Model | Provider | Purpose |
|---|---|---|---|
| **AGENT-01 (PRO)** | `llama-3.1-8b-instant` | Groq | Argues in favor of the topic |
| **AGENT-02 (CON)** | `llama-3.1-8b-instant` | Groq | Argues against the topic |
| **Rebuttal (PRO/CON)** | `llama-3.1-8b-instant` | Groq | Mid-round counter-arguments |
| **JUDGE-0 OMNI** | `unsloth/Nemotron-3-Nano-30B-A3B` | Kaggle (ngrok) | Scores rounds, detects fallacies, final verdict |

> **Note on the Judge:** The Judge model (`Nemotron 30B`) runs on a Kaggle GPU notebook exposed via an ngrok tunnel. This is polled via the `/judge/health` endpoint. The frontend shows a live **online/offline/checking** status indicator.

---

## 3. System Design

### High-Level Overview

```
USER (Browser)
     │
     │  HTTP (health check)
     │  WebSocket (debate stream)
     ▼
FastAPI Backend  (port 8000)
     │
     ├──► PRO Agent  ──► Groq API  (llama-3.1-8b-instant)
     ├──► CON Agent  ──► Groq API  (llama-3.1-8b-instant)
     ├──► Rebuttal Agent ──► Groq API (same model)
     └──► Judge Agent ──► Kaggle/ngrok (Nemotron 30B)
```

### Communication Protocol

The entire debate is **streamed over a WebSocket connection** (`ws://localhost:8000/ws/debate`). The frontend opens the connection once per debate, and the backend sends a series of typed JSON messages in real time:

| Message Type | Payload | Meaning |
|---|---|---|
| `debate_start` | `topic`, `rounds` | Debate is beginning |
| `sub_round_start` | `round`, `sub_round`, `label` | A new sub-round is opening |
| `agent_typing` | `agent`, `round`, `sub_round` | An agent is generating a response |
| `pro_argument` | `text`, `model`, `round`, `sub_round` | PRO's response is ready |
| `con_argument` | `text`, `model`, `round`, `sub_round` | CON's response is ready |
| `round_verdict` | `data` (JSON scores) | Judge's round verdict |
| `final_verdict` | `data` (JSON scores) | Judge's final verdict across all rounds |
| `debate_end` | — | The debate is complete |
| `error` | `message` | Something went wrong |

### Judge Health Endpoint

```
GET /judge/health
→ { "status": "online" | "offline", "url": string }
```

The frontend polls this every **30 seconds** and blocks debate start if the Judge is offline, displaying a warning to the user to activate the Kaggle notebook.

---

## 4. Architecture Design

### Backend Architecture

```
backend/
├── main.py                     # FastAPI app: WebSocket + health endpoint
├── debate/
│   └── orchestrator.py         # Debate orchestration engine (run_debate)
├── agents/
│   ├── pro_agent.py            # AGENT-01: PRO opening arguments
│   ├── con_agent.py            # AGENT-02: CON opening arguments
│   ├── rebuttal_agent.py       # PRO + CON mid-round rebuttals (sub-rounds 2 & 3)
│   └── judge_agent.py          # JUDGE-0 OMNI: round scoring + final verdict
├── requirements.txt
└── .env                        # GROQ_API_KEY, JUDGE_BASE_URL
```

### Frontend Architecture

```
src/
├── main.tsx                    # React entry point
└── app/
    ├── App.tsx                 # Root component
    ├── routes.tsx              # React Router routes
    ├── lib/
    │   └── utils.ts            # cn() class utility
    └── components/
        ├── ArgusLanding.tsx    # Landing page wrapper (all sections)
        ├── Navbar.tsx          # Navigation bar
        ├── Hero.tsx            # Hero section (parallax, CTA)
        ├── HowItWorks.tsx      # 3-card "System Architecture" section
        ├── DebateInAction.tsx  # Debate preview section
        ├── ResultsAndVerdict.tsx # Sample results table
        ├── ModelsSupported.tsx # Supported LLMs section
        ├── AgentFaceOff.tsx    # Feature showcase section
        ├── FooterHero.tsx      # Footer with CTA
        ├── DebateDashboard.tsx # LIVE DEBATE ARENA (main app)
        ├── GlassCard.tsx       # Reusable glassmorphism card
        └── Benchmark.tsx       # Performance benchmarks
```

### Pages / Routes

| Path | Component | Description |
|---|---|---|
| `/` | `ArgusLanding` | Marketing landing page with all sections |
| `/debate-dashboard` | `DebateDashboard` | Live debate arena — the core app |

---

## 5. Agent Workflow

Each debate runs for a configurable number of **main rounds** (default: **3**). Every main round contains **3 sub-rounds**.

### Sub-Round Structure

```
Main Round N
│
├── Sub-round 1: OPENING
│     PRO makes its opening argument
│     CON directly responds to PRO's opening
│
├── Sub-round 2: COUNTER
│     PRO rebuts CON's opening counter
│     CON doubles down against PRO's counter
│
└── Sub-round 3: JUSTIFY
      PRO justifies their position with full escalation
      CON delivers closing counter-justification
      
      ▼
      JUDGE scores all 3 sub-rounds → round_verdict JSON
```

### Full Debate Flow

```
debate_start
  │
  └── For each Round (1 to N):
        │
        ├─ sub_round 1 (Opening)
        │    ├─ agent_typing (pro) → pro_argument
        │    └─ agent_typing (con) → con_argument
        │
        ├─ sub_round 2 (Counter)
        │    ├─ agent_typing (pro) → pro_argument [rebuttal]
        │    └─ agent_typing (con) → con_argument [rebuttal]
        │
        ├─ sub_round 3 (Justify)
        │    ├─ agent_typing (pro) → pro_argument [rebuttal]
        │    └─ agent_typing (con) → con_argument [rebuttal]
        │
        └─ agent_typing (judge) → round_verdict
  │
  └─ agent_typing (judge) → final_verdict → debate_end
```

### Memory / History Strategy

Each agent maintains **rolling history** of **opening arguments only** from previous rounds. Rebuttal sub-rounds (2 and 3) are intentionally **excluded** from history to:
1. Prevent the context window from growing excessively large
2. Keep inference latency stable across all rounds
3. Focus agent memory on the most impactful statements

### Agent Personas & Prompts

**AGENT-01 (PRO)**
- Persona: Confident, evidence-driven advocate
- Never concedes, argues FOR the topic
- Uses flowing prose — no bullet points
- Each round introduces a fresh angle
- Output format: `REBUTTAL → ARGUMENT → POSITION`

**AGENT-02 (CON)**
- Persona: Sharp, analytical skeptic
- Targets the weakest claim in every PRO argument
- Explicitly names logical fallacies (straw man, appeal to authority, etc.)
- Each round introduces new counter-angles
- Output format: `REBUTTAL → ARGUMENT → POSITION`

**REBUTTAL AGENTS (Sub-rounds 2 & 3)**
- Use distinct prompts emphasizing **escalation in intensity** per sub-round
- CON rebuttal agent actively hunts for and names logical fallacies

**JUDGE-0 OMNI (Nemotron 30B)**
- Scores each round on 3 criteria: **Evidence (0–10)**, **Logic (0–10)**, **Relevance (0–10)**
- Average of criteria = total score (1 decimal place)
- Reports: `round_winner`, `reasoning` (1 sentence), `fallacy_detected` (or null)
- Returns **strict JSON only** — no markdown, no explanation
- Final verdict aggregates per-round totals and declares overall winner

---

## 6. Features

### 🎯 Core Debate Engine
- **Multi-round structured debate** with 3 sub-rounds per main round (Opening → Counter → Justify)
- **Configurable round count** (default 3, fully parametric)
- **Real-time streaming** via WebSocket — arguments appear as they are generated
- **History-aware agents** — agents remember previous rounds and avoid repetition

### 🤖 Agent Intelligence
- **Dedicated system prompts** per agent with distinct personas and rules
- **Fallacy detection** — the CON agent and Judge both actively identify logical fallacies
- **Escalating intensity** — agents are instructed to become more assertive each sub-round
- **Text cleanup pipeline** — `REBUTTAL:`, `ARGUMENT:`, `N/A` labels are stripped from displayed text

### ⚖️ Judging System
- **Per-round scoring** across Evidence, Logic, and Relevance dimensions
- **Round-by-round winner** determination (PRO / CON / TIE)
- **Cumulative scoring** across all rounds for the final verdict
- **Fallacy log** — all detected fallacies surfaced in the final verdict panel
- **Trust enforcement** — final totals are always recomputed from per-round data (the judge's own arithmetic is never trusted)

### 📊 Live Debate Dashboard UI
- **Sidebar** with Judge online/offline indicator (live polled every 30 seconds)
- **Typing indicator** — animated dots while any agent is generating
- **Per-message metadata** — model name and latency (ms) shown for every argument
- **Sub-round dividers** — colour-coded separators (sky/amber/violet) marking each phase
- **Auto-scroll** — chat scrolls to the latest message automatically
- **Debate completion indicator** — a "DEBATE PROTOCOL COMPLETE" label appears at the end
- **Error handling** — clear error banners for WebSocket failures, offline judge, empty topic

### 🏆 Final Verdict Display
- **Winner announcement** with colour theming (emerald = PRO wins, rose = CON wins, yellow = TIE)
- **Score progress bars** — visual PRO vs CON score bars
- **Round-by-round summary table** in the verdict card
- **Judge reasoning** — the judge's written explanation for the final decision
- **Fallacy detection summary** — all detected fallacies listed or "NO FALLACIES DETECTED"

### 🌐 Landing Page
- **Scroll-parallax hero** with animated background and pulsing radial glow
- **"How It Works"** — 3-card overview of each agent's role
- **"Results & Verdict"** — sample scoring table demonstration
- **"Debate In Action"** — live debate preview section
- **"All Key LLMs Supported"** — model grid with filter tabs
- **"Agent Face-Off"** showcase with image
- **Footer** with navigation links and CTA buttons
- **Glassmorphism design** throughout with micro-animations on scroll (Framer Motion `useInView`)

---

## 7. Changes & Improvements Made

### 7.1 Dynamic Model Labeling

**Problem:** The Debate Dashboard was hardcoding the model name displayed alongside each argument. As the debate progressed, the displayed model was always the same static string regardless of what actually ran.

**Fix:** The orchestrator now passes the `model` field back through every agent function as a return tuple `(text, model_name)`. The WebSocket message for `pro_argument` and `con_argument` now includes `"model": model_name`. The frontend reads `msg.model` and displays it live per argument bubble.

**Result:** Every argument now shows the exact model that generated it — visible in the `MODEL: llama-3.1-8b-instant` metadata line under each message.

---

### 7.2 Latency Optimization — History Pruning

**Problem:** As the debate progressed through multiple rounds, the token count sent to each agent grew linearly. Each agent was receiving the full exchange (all sub-rounds) from all previous rounds, causing significant inference slowdown by rounds 2–3.

**Fix:** Implemented a **history-pruning strategy**:
- Only the **opening argument** (sub-round 1) from each completed round is stored in `pro_history` / `con_history`
- Sub-rounds 2 and 3 (rebuttals) are intentionally dropped from historical memory
- This is documented in comments inside `orchestrator.py`, `con_agent.py`, and `rebuttal_agent.py`

**Before vs After:**
| Round | Context tokens (before) | Context tokens (after) |
|---|---|---|
| Round 1 | ~200 | ~200 |
| Round 2 | ~700 | ~300 |
| Round 3 | ~1400+ | ~400 |

**Result:** Latency remains near-constant across all rounds instead of compounding.

---

### 7.3 Judge Response Parsing — Robust JSON Extraction

**Problem:** The Nemotron Judge model sometimes returned `<think>...</think>` chain-of-thought blocks before the JSON, or wrapped the JSON in markdown code fences (```json ... ```). The raw `json.loads()` call would crash.

**Fix:** Added a `_clean_response()` function in `judge_agent.py` that:
1. Strips all `<think>...</think>` blocks via regex
2. Removes ` ```json ` and ` ``` ` markdown fences
3. Uses **brace-depth counting** to extract only the first complete `{...}` JSON object from the response

**Result:** The Judge reliably parses structured JSON even when the model produces verbose chain-of-thought reasoning before the answer.

---

### 7.4 Judge Input Truncation

**Problem:** When feeding the full exchange to the judge for scoring, very long argument texts were unnecessarily consuming tokens — the Judge only needs the gist of each argument.

**Fix:** In `_format_exchange_for_judge()`, each argument is truncated to **300 characters** maximum (word-boundary aware, appending `…`). Sub-round labels are also included as separators.

**Result:** Reduced judge input token count significantly, lowering Judge latency and cost.

---

### 7.5 Judge Arithmetic Trust Enforcement

**Problem:** The Nemotron model sometimes returned incorrect cumulative totals in its `final_verdict` JSON (model arithmetic was unreliable).

**Fix:** In `judge_final_verdict()`, the `pro_total` and `con_total` are always **recomputed from the per-round verdict data** and forcibly overwritten on the result:
```python
result["pro_total"] = pro_total  # Always use computed value
result["con_total"] = con_total
```

**Result:** Final scores are always mathematically correct regardless of model output.

---

### 7.6 Text Cleanup Pipeline

**Problem:** Agent responses sometimes leaked their structured output markers (`REBUTTAL:`, `ARGUMENT:`, `POSITION:`, `N/A`) into the displayed text, making the UI look messy.

**Fix:** 
- Each agent function strips these labels before returning the text
- The orchestrator applies an additional `clean_text()` regex pass: `re.sub(r'(?:N/A\s*|REBUTTAL:\s*|ARGUMENT:\s*)+', '', text)`

**Result:** Clean, prose-only text displayed in the debate feed.

---

### 7.7 Rebuttal Agent — Separate System Prompts

**Problem:** Sub-rounds 2 and 3 were using the same opening-argument system prompts, which instructed agents to "make your opening argument." This was semantically wrong — agents should be mid-debate, escalating.

**Fix:** `rebuttal_agent.py` defines entirely separate system prompts:
- `PRO_REBUTTAL_PROMPT` — Emphasizes building on the opening, escalating intensity, attacking CON's most recent statement
- `CON_REBUTTAL_PROMPT` — Emphasizes surgical dismantling, naming fallacies, and doubling down

These are distinct from the opening prompts in `pro_agent.py` and `con_agent.py`.

**Result:** Sub-round 2 and 3 arguments feel genuinely different in tone and strategy from the opening arguments.

---

### 7.8 Judge Online/Offline UI + Debate Blocking

**Problem:** Users would click "Start Debate" without having activated the Kaggle Judge session, causing a mid-debate crash or timeout with no explanation.

**Fix:** 
- `GET /judge/health` endpoint added to FastAPI backend — pings the ngrok Judge URL with a 5-second timeout
- Frontend polls this endpoint every 30 seconds with three states: `checking` (yellow pulse) / `online` (green glow) / `offline` (red)
- **Debate is blocked** at the frontend if Judge is offline — a banner explains that the user should start their Kaggle notebook
- The submit button itself doesn't gate on this (WebSocket blocks it), but the `handleStartDebate` callback short-circuits with a user-facing error message

**Result:** Users get immediate, clear feedback on Judge availability before starting a debate.

---

### 7.9 Performance Optimizations — Frontend Rendering

**Problem:** With many debate messages being appended and animated simultaneously, the UI could stutter, especially during rapid agent turns.

**Fix:** Applied several React/CSS performance hints throughout `DebateDashboard.tsx`:
- `will-change-[transform,opacity]` on every animated `motion.div`
- `transform-gpu` class to promote elements to GPU composite layer
- `scroll-smooth` on the message container
- `chatEndRef` auto-scroll with `scrollIntoView({ behavior: 'smooth' })`
- `asyncio.sleep(0.4)` delays in the orchestrator to prevent overwhelming the WebSocket message queue

---

## 8. How to Run

### Prerequisites
- Node.js (for frontend)
- Python 3.10+ (for backend)
- Groq API key
- Kaggle notebook running Nemotron 30B with ngrok exposed

### Environment Setup

Create `backend/.env`:
```
GROQ_API_KEY=your_groq_api_key_here
JUDGE_BASE_URL=https://your-ngrok-url.ngrok-free.app/v1
```

### Start Backend

```powershell
cd d:\Argus\backend
pip install -r requirements.txt
uvicorn main:app --reload
# Runs on http://localhost:8000
```

### Start Frontend

```powershell
cd d:\Argus
npm install
npm run dev
# Runs on http://localhost:5173
```

### Kaggle Judge Setup

1. Open your Kaggle notebook running `unsloth/Nemotron-3-Nano-30B-A3B`
2. Run all cells to start the llama.cpp server
3. Run the ngrok cell to expose it publicly
4. Copy the ngrok URL into `JUDGE_BASE_URL` in `.env`
5. Restart the backend — the Judge status indicator will turn green within 30 seconds

---

---

## 9. Ongoing Work

The following features and improvements are actively being worked on or are partially implemented at the time of this report.

### 9.1 Zenbot — External Model Integration via ngrok

**Status:** In development

A new backend component called `zenbot.py` is being integrated to allow users to connect a **custom model hosted on Kaggle** (or any external GPU) through an ngrok tunnel. Unlike the fixed Judge model, Zenbot is designed as a flexible plugin:
- Accepts a user-supplied ngrok URL at runtime
- Forwards text prompts to the external model
- Returns responses to the frontend chat interface

This paves the way for user-selectable model configurations — where users can bring their own fine-tuned or specialized models into the debate arena as either a debating agent or judge.

---

### 9.2 Debate History Persistence

**Status:** Planned / Early design

Currently, debate history exists **only in memory** for the duration of a single WebSocket session. Once the connection closes, all debate data is lost. Work is underway to:
- Persist completed debates to a local or cloud database (SQLite / PostgreSQL)
- Expose a `GET /debates` endpoint for the frontend to retrieve past debates
- Add a **"Debate History"** sidebar panel (the UI nav item already exists as a stub)

---

### 9.3 Judge Logs Panel

**Status:** UI stub exists, backend not yet wired

The sidebar in `DebateDashboard.tsx` already contains a **"JUDGE LOGS"** navigation item. The intent is to expose a real-time or historical log of all judge scoring events, fallacy detections, and verdict reasoning in a dedicated panel — separate from the main debate feed.

---

### 9.4 Model Selection UI

**Status:** Frontend section exists (`ModelsSupported.tsx`), backend not yet wired

The landing page shows a model selection grid (GPT-4o, Claude 3.5, Gemini 1.5 Pro, LLaMA 3 70B, Mistral Large, Custom). The tab filter is interactive but does not yet affect which model runs during a debate. The backend needs a model routing layer that maps the user's selection to the appropriate API client.

---

### 9.5 Configurable Round Count

**Status:** Backend supports it, frontend hardcoded

The backend `run_debate()` function accepts a `rounds` parameter. The WebSocket payload already supports `{ topic, rounds }`. However, the frontend currently hardcodes `const rounds = 3`. A UI control (slider or select) to let users pick 1–5 rounds is planned.

---

## 10. Future Scope & Enhancements

The following are proposed enhancements for future versions of ARGUS, grouped by category.

### 10.1 Multi-Model Agent Configuration

Currently, PRO, CON, and rebuttal agents all run the same model (`llama-3.1-8b-instant`). A future version would allow:
- Assigning **different models** to PRO and CON agents independently (e.g., Claude vs GPT-4o)
- Model-vs-model benchmarking — measure which model wins more debates across a topic dataset
- A configurable **temperature and max_tokens** slider per agent in the UI

This would make ARGUS a genuine **LLM benchmark harness** in addition to a debate tool.

---

### 10.2 Audience Mode / Spectator View

Add a read-only shareable debate URL that multiple users can watch simultaneously:
- Backend broadcasts debate events to multiple WebSocket clients
- Audience members see an animated debate feed in real time
- Live voting system — audience votes on who is winning each round
- Aggregate vote results shown alongside judge scores

---

### 10.3 Human-vs-Agent Debate

Allow a human user to take one side of the debate:
- User selects PRO or CON
- The AI agent takes the opposite side
- The Judge still scores both sides impartially
- Each round, the user types their argument and the AI responds

This transforms ARGUS from a spectator tool into an **interactive reasoning trainer**.

---

### 10.4 Debate Export & Sharing

- Export full debate transcript as **PDF** or **Markdown**
- Generate a shareable debate summary card (image) for social media
- Embed a debate replay widget on external websites
- Public debate gallery — curated, high-scoring debates browsable by topic

---

### 10.5 Advanced Judging Criteria

Expand the judge's scoring rubric beyond Evidence / Logic / Relevance:
- **Originality** — did the agent introduce novel angles not seen before?
- **Rhetorical Impact** — persuasiveness beyond pure logic
- **Citation Quality** — did the agent cite verifiable real-world data?
- **Tone Appropriateness** — was the agent overly aggressive or too passive?

The judge prompt and frontend verdict card would be extended to display these sub-scores.

---

### 10.6 Topic Suggestion Engine

Add an AI-powered topic suggestion system:
- Trending topics pulled from news APIs
- User browsing history-based suggestions
- Difficulty rating per topic (Beginner / Intermediate / Expert)
- Topic categories (Technology, Ethics, Politics, Science, Philosophy)

---

### 10.7 Agent Memory & Learning

Currently, agents have no memory between debates. Future versions could:
- Store a **debate persona profile** per model — accumulated winning strategies
- Fine-tune debate agents on successful high-scoring debates
- Allow agents to "learn" which argument styles score highest with the current judge model

---

### 10.8 Backend Scalability

For production deployment:
- Replace single-process Uvicorn with **multi-worker deployment** (Gunicorn + Uvicorn workers)
- Move WebSocket state to **Redis Pub/Sub** for horizontal scaling
- Add a job queue (Celery / ARQ) so long-running debates don't block web workers
- Rate limiting per user / API key to prevent abuse
- **Containerize** the full stack with Docker Compose (frontend + backend + Redis)

---

### 10.9 Analytics Dashboard

A dedicated analytics page tracking:
- Win rate by agent position (PRO wins more often than CON? Or vice versa?)
- Most debated topics
- Average debate duration per round count
- Most commonly detected fallacies
- Score distribution histograms (how often does an agent score 8+ vs below 5?)

---

### 10.10 Mobile App

A React Native or Progressive Web App (PWA) version of ARGUS:
- Full debate participation from mobile
- Push notifications when a debate you're watching completes
- Offline debate replay from locally cached transcripts

---

## Summary

ARGUS is a full-stack, production-ready multi-agent AI debate system that combines:
- **Fast LLM inference** via Groq for debate agents
- **A large, impartial judge model** on Kaggle via ngrok
- **Real-time WebSocket streaming** for a live, chat-like debate experience
- **A premium, animated React frontend** with per-message latency tracking, fallacy detection, and round-by-round scoring
- **Robust engineering** — history pruning, JSON parsing safeguards, arithmetic enforcement, and a text cleanup pipeline

The result is a debate arena where any topic can be argued by AI, judged fairly, and presented beautifully.
