# ARGUS — AI Multi-Agent Debate System

> **Autonomous Reasoning & Generative Utility System**
> _"Two minds. One truth."_

A full-stack AI debate platform where two autonomous LLM agents argue opposing viewpoints on any topic, a judge AI evaluates each argument in real time using a fine-tuned ML model, and structured debate reports are generated automatically.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Frontend](#frontend)
- [Backend](#backend)
- [ML Model](#ml-model)
- [Database](#database)
- [Getting Started](#getting-started)
- [Expected Outcomes](#expected-outcomes)

---

## Overview

ARGUS simulates structured debates between two opposing AI agents — a Proponent (Agent A) and an Opponent (Agent B). After each round, Judge-0, powered by a fine-tuned language model, evaluates every argument on logic, evidence, relevance, and persuasiveness, then declares a winner with a full verdict summary.

The system is built for critical thinking education, AI research, and automated argument analysis.

---

## Architecture

```
User
  │
  ▼
React Frontend (Vite + Tailwind)
  ─ Landing page  →  /
  ─ Debate arena  →  /dashboard
  │
  ▼  HTTP + JWT Auth
Python Backend (FastAPI)
  ─ Debate Controller
  ─ Topic Selection Engine
  ─ Debate Round Manager
  ─ Score Aggregation Module
  │
  ├──────────────────────────────┐
  ▼                              ▼
Debate Prep &              Multi-Agent LLM Layer
Context Structuring        ─ Agent A  (Proponent)
─ Normalization            ─ Agent B  (Opponent)
─ JSON schema mapping      ─ Rebuttal Generator
─ Semantic equivalence     ─ Closing Statement Generator
                           ─ Fine-tuned local LLM service
                                 │
                                 ▼
                      ML Argument Evaluation (Judge-0)
                      Fine-tuned: Nemotron-3 / Qwen / LLaMA
                      ─ Logic score
                      ─ Evidence score
                      ─ Relevance score
                      ─ Persuasion score
                      ─ Fallacy detection
                                 │
                                 ▼
                      Post-Processing & QA
                      ─ Bias correction (historical patterns)
                      ─ Confidence scoring & threshold check
                      ─ Final verdict generation
                                 │
                                 ▼
                         ChromaDB (Vector Database)
                      ─ debate_topics (embedded)
                      ─ arguments + embeddings
                      ─ argument_scores
                      ─ debate_results
                      ─ semantic search over past debates
```

---

## Project Structure

```
Argusv6/                                    ← Frontend root
├── index.html                              # App entry point
├── package.json                            # Dependencies & scripts
├── vite.config.ts                          # Vite build config
├── postcss.config.mjs                      # PostCSS config
├── ATTRIBUTIONS.md                         # Asset attributions
├── guidelines/
│   └── Guidelines.md                       # Design system guidelines
└── src/
    ├── main.tsx                            # React entry point
    ├── styles/
    │   ├── index.css                       # Global styles
    │   ├── tailwind.css                    # Tailwind imports
    │   ├── theme.css                       # CSS variables & design tokens
    │   └── fonts.css                       # Font declarations (Orbitron, JetBrains Mono, DM Sans)
    ├── assets/                             # Static images (hero robots, thumbnails)
    ├── imports/
    │   └── pasted_text/
    │       ├── argus-landing-page.md       # Full design specification
    │       ├── design-edits.md             # Design revision notes
    │       └── debate-arena-page.html      # Debate arena reference layout
    └── app/
        ├── App.tsx                         # Root app component
        ├── routes.tsx                      # React Router config
        ├── lib/
        │   └── utils.ts                    # Utility helpers (cn, classnames)
        └── components/
            ├── ArgusLanding.tsx            # Landing page root layout
            ├── Navbar.tsx                  # Sticky glassmorphic navbar
            ├── Hero.tsx                    # Full-viewport hero (parallax + glow)
            ├── HowItWorks.tsx              # 3-card system architecture section
            ├── DebateInAction.tsx          # Feature highlights split section
            ├── ResultsAndVerdict.tsx       # Live scoring table + winner display
            ├── Benchmark.tsx               # Performance benchmark table
            ├── ModelsSupported.tsx         # Tab-filtered LLM compatibility grid
            ├── AgentFaceOff.tsx            # Cinematic full-bleed agent section
            ├── Partnerships.tsx            # Integrations banner
            ├── FooterHero.tsx              # CTA footer + site nav
            ├── GlassCard.tsx               # Reusable glassmorphic card component
            ├── DebateDashboard.tsx         # Full interactive debate arena (/dashboard)
            ├── figma/
            │   └── ImageWithFallback.tsx   # Image component with graceful fallback
            └── ui/                         # shadcn/ui component library (30+ components)
                ├── button.tsx
                ├── dialog.tsx
                ├── input.tsx
                ├── tabs.tsx
                ├── card.tsx
                ├── badge.tsx
                ├── chart.tsx
                └── ...
```

---

## Tech Stack

### Frontend

| Layer         | Technology                          |
| ------------- | ----------------------------------- |
| Framework     | React 18 + TypeScript               |
| Build Tool    | Vite 6                              |
| Styling       | Tailwind CSS v4                     |
| Routing       | React Router v7                     |
| Animation     | Motion (Framer Motion)              |
| UI Components | shadcn/ui + Radix UI primitives     |
| Icons         | Lucide React                        |
| Charts        | Recharts                            |
| Fonts         | Orbitron · JetBrains Mono · DM Sans |

### Backend

| Layer          | Technology   |
| -------------- | ------------ |
| Language       | Python 3.11+ |
| API Framework  | FastAPI      |
| ML Framework   | PyTorch      |
| Authentication | JWT          |

### ML Model

| Layer                   | Technology                                              |
| ----------------------- | ------------------------------------------------------- |
| Base Models             | Nemotron-3 / Qwen / LLaMA (fine-tuned)                  |
| Fine-tuning Method      | Supervised fine-tuning on debate/argument datasets      |
| Evaluation Tasks        | Argument scoring, fallacy detection, verdict generation |
| Training Infrastructure | Google Colab / local GPU                                |

### Database

| Layer           | Technology                                                           |
| --------------- | -------------------------------------------------------------------- |
| Vector Database | ChromaDB                                                             |
| Embeddings      | Sentence-Transformers / model-native embeddings                      |
| Use Cases       | Semantic search over debates, argument retrieval, similarity scoring |

---

## Frontend

The frontend is a dark cyberpunk × glassmorphism SPA with two routes.

### Routes

| Path         | Component         | Description                      |
| ------------ | ----------------- | -------------------------------- |
| `/`          | `ArgusLanding`    | Marketing & product landing page |
| `/dashboard` | `DebateDashboard` | Full interactive debate arena    |

### Landing Page Sections

1. **Navbar** — Sticky glass bar with logo, nav links, and session auth state
2. **Hero** — Full-viewport section with dual-robot background, parallax scroll, pulsing radial glow, and two glassmorphic CTA cards (Agent intro + Judge-0 intro)
3. **How It Works** — Three glassmorphic cards: Agent A (Proponent), Agent B (Opponent), Judge-0 (Evaluator)
4. **Results & Verdict** — Live scoring table showing per-round argument scores with winner declaration
5. **Debate in Action** — Feature highlights: real-time generation, fallacy detection, multi-language support, PDF/PPT export
6. **Models Supported** — Tab-filtered grid showing GPT-4o, Claude 3.5, Gemini 1.5 Pro, LLaMA 3, Mistral, and custom model support
7. **Agent Face-Off** — Full-bleed cinematic section with performance stats
8. **Footer Hero** — Final CTA + site navigation columns

### Design System

```css
/* Glassmorphism — applied to all cards, nav, modals */
background: rgba(255, 255, 255, 0.05);
backdrop-filter: blur(24px) saturate(180%);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: 20px;
box-shadow:
  0 8px 32px rgba(0, 0, 0, 0.6),
  inset 0 1px 0 rgba(255, 255, 255, 0.06);

/* Color palette */
--bg-primary:
  #050505 → #0a0a0f /* near-black gradient */ --bg-surface: #161618
    /* sidebar, input bar */ --accent: #ffffff --grid-overlay: 80px × 80px,
  3% opacity white lines;
```

### Debate Dashboard (`/dashboard`)

The arena UI (`DebateDashboard.tsx`) includes:

- **Sidebar** — Active Debates, Debate History, Judge Logs navigation with active-state indicator; OPERATOR-01 profile with live session badge
- **Arena header** — `SIMULATION PROTOCOL V4.2.0` label + ghost-stroke title that switches from `INITIALIZING ARENA...` to `ARENA ACTIVE` on debate start
- **Awaiting state** — Brain icon + prompt to enter a topic before debate starts
- **Debate thread** — Turn-based argument view: Agent-01 on the left, Agent-02 on the right, each tagged with hash ID and latency metadata
- **Judge panel** — `Request ML Verdict` button triggers a slide-in modal (Judge-0 Omni) showing per-agent logic scores, fallacy flags, and a full verdict summary
- **Input bar** — Fixed bottom prompt bar with topic input and `Start Debate ⚡` button

---

## Backend

### Modules

#### Topic Selection Module

Maintains a dataset of debate topics across technology, society, and economics. Topics are selected or entered at session start and normalized before being passed to the agent generation pipeline.

Example topics:

- _"Artificial Intelligence should replace traditional teaching methods"_
- _"Social media should be regulated by governments"_
- _"Remote work is more productive than office work"_

#### Multi-Agent Debate Generation Module

Two fine-tuned LLM agents generate structured responses in turn:

- **Opening arguments** — each agent states their position
- **Rebuttals** — agents directly counter the opposing argument
- **Closing statements** — summary of each agent's strongest points

Each response is tagged with a hash ID and latency for audit logging.

#### Argument Evaluation Module (Judge-0)

A fine-tuned model scores each argument on four criteria:

| Criterion         | Description                                   |
| ----------------- | --------------------------------------------- |
| Logical Reasoning | Structural coherence and internal consistency |
| Relevance         | Alignment with the stated debate topic        |
| Evidence          | Presence and quality of supporting facts      |
| Persuasiveness    | Effectiveness of argument delivery            |

Fallacy detection flags weak arguments (e.g., ad hominem, strawman, false equivalence) with a ⚠️ indicator in the results table.

#### Result Aggregation Module

- Calculates total weighted score per debate side per round
- Determines the winning agent and the single strongest argument
- Formats the verdict summary for the Judge-0 panel

#### Debate Quality Assurance Module

- Applies bias correction based on historical scoring patterns retrieved from ChromaDB
- Runs confidence threshold checks — low-confidence verdicts are flagged
- Feeds bias-corrected scores back to the database

---

## ML Model

Judge-0 is a fine-tuned language model. The base model is selected from:

- **Nemotron-3** (NVIDIA) — strong structured reasoning, efficient inference
- **Qwen** (Alibaba) — multilingual support, good for local deployment
- **LLaMA 3** (Meta) — widely supported open-source fine-tuning ecosystem

### Fine-tuning Approach

The model is fine-tuned on a curated dataset of debate transcripts, argument quality annotations, and fallacy-labeled samples targeting three tasks:

- Argument quality scoring (regression output per criterion)
- Fallacy classification (multi-label classification)
- Verdict generation (structured text generation)

Training is run on Google Colab with PyTorch. The fine-tuned model is served locally via a FastAPI inference endpoint.

```python
from transformers import AutoModelForSequenceClassification, Trainer, TrainingArguments

model = AutoModelForSequenceClassification.from_pretrained("meta-llama/Llama-3-8b")

training_args = TrainingArguments(
    output_dir="./argus-judge",
    num_train_epochs=3,
    per_device_train_batch_size=8,
    evaluation_strategy="epoch",
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
)

trainer.train()
```

---

## Database

ARGUS uses **ChromaDB** as its primary data store — a vector database that enables semantic search and similarity retrieval over all debate content.

### Collections

| Collection        | Contents                                                         |
| ----------------- | ---------------------------------------------------------------- |
| `debate_topics`   | Topic text + embeddings for semantic deduplication and retrieval |
| `arguments`       | All generated arguments + vector embeddings per session          |
| `argument_scores` | Evaluation scores linked to each argument document               |
| `debate_results`  | Final verdicts, winning agent, strongest argument per session    |

### Why ChromaDB

- Enables semantic search over historical debates — find similar past arguments to provide context to agents
- Supports bias correction by retrieving historically similar argument patterns for score calibration
- Allows retrieval-augmented generation (RAG) so agents can reference past strong arguments
- Lightweight and runs fully locally with no external service dependencies

### Setup

```python
import chromadb

client = chromadb.PersistentClient(path="./argus_db")

topics    = client.get_or_create_collection("debate_topics")
arguments = client.get_or_create_collection("arguments")
scores    = client.get_or_create_collection("argument_scores")
results   = client.get_or_create_collection("debate_results")
```

---

## Getting Started

### Prerequisites

- Node.js 18+
- Python 3.11+
- npm or pnpm

### Frontend

```bash
cd Argusv6

# Install dependencies
npm install

# Start development server
npm run dev
# → http://localhost:5173

# Build for production
npm run build
```

### Backend

```bash
# Install dependencies
pip install fastapi uvicorn torch transformers chromadb sentence-transformers

# Run API server
uvicorn main:app --reload --port 8000
```

---

## Expected Outcomes

- A working AI multi-agent debate system with two opposing agents generating structured, turn-based debates
- Coherent arguments organized into opening statements, rebuttals, and closing statements with per-round scoring
- A fine-tuned Judge-0 model (Nemotron-3 / Qwen / LLaMA) evaluating logic, relevance, evidence, and persuasiveness with fallacy detection
- Automatic score aggregation and winner determination via ChromaDB-backed bias-corrected scoring
- Semantic search over historical debates enabling retrieval-augmented argument generation
- A web-based arena interface with real-time debate display, judge verdict overlay, and debate history review
- Export support for debate reports (PDF / PPT)
