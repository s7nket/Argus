<div align="center">

# ⚖️ ARGUS
### Autonomous Reasoning & Generative Utility System
**Verification-Grounded Multi-Agent Debate with Conformal Calibrated Auditing**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Vite](https://img.shields.io/badge/Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vitejs.dev/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Groq LPU](https://img.shields.io/badge/Inference-Groq%20LPU-F55036?style=for-the-badge)](https://groq.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

<p align="center">
  <em>"Two minds argue. One synthesizes. A grounded auditor verifies. An invariant judge decides."</em>
</p>

[Key Innovations](#-key-architectural-pillars) •
[Architecture](#-system-architecture) •
[Quickstart](#-quickstart) •
[Arena Topology](#-arena-topology) •
[Research & Paper](#-research--evaluation) •
[Repository Layout](#-repository-structure)

</div>

---

## 💡 Overview

Most LLM-as-a-Judge systems suffer from **first-speaker bias**, **hallucination blindness**, and **uncalibrated overconfidence** — they arbitrarily reward persuasive rhetoric over factual truth and declare a winner even when arguments are indistinguishable.

**ARGUS** redefines automated dialectic deliberation. It is an end-to-end framework where autonomous AI agents (or humans) debate contentious resolutions under rigorous, checkable constraints:

1. **Evidence is never taken at face value**: Citations must be grounded against an indexed retrieval corpus via independent natural language inference (NLI).
2. **First-speaker and position bias are eliminated**: Scored via blind label-swapped evaluation passes where systematic bias cancels out.
3. **Statistical guarantees replace raw intuition**: A split-conformal prediction layer computes non-conformity scores and abstains when results are statistically ambiguous.
4. **Verdicts are deterministic**: Scores, repetitions, penalties, and tie bands are computed in pure Python logic — language models formulate reasoning, but code computes the outcome.

---

## ⚡ Key Architectural Pillars

```
                     ┌──────────────────────────────────────────────┐
                     │           DEBATE TOPIC RESOLUTION            │
                     └──────────────────────┬───────────────────────┘
                                            ▼
               ┌────────────────────────────────────────────────────────┐
               │              DYNAMIC 3-AGENT PIPELINE                  │
               │   [Agent-01: PRO]   [Agent-02: CON]   [Agent-03: SYN]  │
               └──────────┬──────────────────┬──────────────────┬───────┘
                          │                  │                  │
                          └──────────────────┼──────────────────┘
                                             ▼
                     ┌──────────────────────────────────────────────┐
                     │       AGENT-04: INDEPENDENT VERIFIER         │
                     │  Retriever (ChromaDB) + NLI Entailment Engine│
                     │  [SUPPORTED]      [REFUTED]     [NEI]        │
                     └──────────────────────┬───────────────────────┘
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │        AGENT-05: INVARIANT JUDGE DUAL-PASS   │
                     │  Pass A: (PRO, CON)  │  Pass B: (CON, PRO)   │
                     │  Fine-Tuned ArguScore-4B (or Groq Fallback)  │
                     └──────────────────────┬───────────────────────┘
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │          DETERMINISTIC EVALUATION            │
                     │  • Evidence Verification Weighting           │
                     │  • Repetition Penalties                      │
                     │  • Conformal Prediction Abstention Band      │
                     └──────────────────────┬───────────────────────┘
                                            ▼
                     ┌──────────────────────────────────────────────┐
                     │     AUDITABLE VERDICT & INTERACTIVE REPORT   │
                     └──────────────────────────────────────────────┘
```

### 1. 🔍 Retrieval-Grounded NLI Fact-Checking
Every factual claim made in an exchange is extracted and checked against a dedicated vector corpus (ChromaDB) built from domain-validated sources:
- **`SUPPORTED`**: Entailed by retrieved evidence. Full credit awarded.
- **`REFUTED`**: Contradicted by retrieved text with strict burden-of-proof. Fabrications trigger mandatory score deductions.
- **`NEI` (Not Enough Information)**: Outside the corpus scope. Neither credited nor penalized — avoiding unjust penalties for external facts.

### 2. 🔄 Blind Label-Swapped Position Invariance
LLMs inherently favor whichever candidate appears first in context (position bias). ARGUS executes **two blind scoring passes** for each round:
$$\text{Score}_{\text{final}} = \frac{\text{Score}(A, B) + \text{Score}_{\text{swapped}}(B, A)}{2}$$
The residual disagreement ($\delta_{\text{bias}}$) is logged to the dashboard and audit logs in real time rather than hidden.

### 3. 🛡️ Conformal Prediction & Calibrated Abstention
Rather than blindly picking a winner in razor-thin debates, ARGUS deploys **inductive conformal prediction**:
- Calibrated against empirical human argument-quality datasets.
- Computes non-conformity scores and outputs prediction sets with a distribution-free coverage guarantee:
$$P(Y \in \mathcal{C}(X)) \ge 1 - \alpha$$
- If the difference does not meet significance bounds, the judge **abstains** (`"Draw / Too close to separate"`), preventing false certainty.

### 4. 🧮 Deterministic Rule Engine
The language model never directly assigns final round winners. LLM outputs provide intermediate scoring criteria (logic, rhetoric, citations), while Python calculates:
- Verifiable evidence coverage multipliers
- Semantic repetition penalties across rounds
- Deterministic tie-bands and marginal delta thresholds

---

## 🏛️ Arena Topology

| Agent | Role | Default Engine | Responsibilities |
|---|---|---|---|
| **Agent-01 (PRO)** | Affirmative Debater | `gpt-oss-120b` / Groq | Opening, rebuttal, and closing justification affirming the topic. |
| **Agent-02 (CON)** | Negative Debater | `gpt-oss-20b` / Groq | Systematic counter-arguments, premise refutation, and impact calculus. |
| **Agent-03 (SYN)** | Dialectic Synthesis | `qwen3.8-27b` / Groq | Synthesizes opposing poles; discovers common ground and trade-offs. |
| **Agent-04 (VERIFIER)** | Evidence Auditor | NLI + ChromaDB | Real-time claim extraction, vector search, and entailment scoring. |
| **Agent-05 (JUDGE)** | Adjudicator | `ArguScore-4B` / `Llama-3.3-70b` | Dual-pass blind scoring, argument audit receipts, and final verdict. |
| **Human Debater** | Interactive Challenger | Browser / Keyboard | Take the stand as **PRO**, **CON**, or **SYN** with live turn management. |

---

## 🚀 Quickstart

### Prerequisites
- **Python 3.11+**
- **Node.js 18+** & npm
- A [Groq Cloud API Key](https://console.groq.com/) (free tier supported)

### 1. Clone the Repository
```bash
git clone https://github.com/s7nket/Argus.git
cd Argus
```

### 2. Configure Environment
Create `backend/.env`:
```env
GROQ_API_KEY=gsk_your_groq_api_key_here
# Optional: Fine-Tuned Kaggle ArguScore-4B Scorer
# FT_JUDGE_URL=https://your-ngrok-tunnel.ngrok-free.app
```

### 3. Run Locally

#### Option A: Development Mode (Hot Reload)
```bash
# Terminal 1 — Backend (FastAPI + WebSocket Engine)
cd backend
python -m venv .venv
# On Windows: .venv\Scripts\activate | On Unix: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — Frontend (Vite + React Dashboard)
cd ..
npm install
npm run dev
```
Open **`http://localhost:5173`** in your browser.

#### Option B: Unified Production Build
The FastAPI backend serves the compiled static production assets on a single port:
```bash
# Build frontend
npm install
npm run build

# Launch unified backend
cd backend
uvicorn main:app --host 127.0.0.1 --port 8000
```
Open **`http://localhost:8000`** in your browser.

---

## 🐳 Docker Deployment

ARGUS includes a multi-stage Docker build that bundles the TypeScript frontend compilation and FastAPI service into a lean container compliant with **Hugging Face Spaces**, **Render**, and **AWS ECS**:

```bash
docker build -t argus-debate .
docker run -p 7860:7860 -e GROQ_API_KEY="your_api_key" argus-debate
```

### Environment Variables

| Variable | Type | Required | Description |
|---|---|---|---|
| `GROQ_API_KEY` | Secret | **Yes** | Powers the debater pipeline, synthesis agent, and Groq fallback judge. |
| `FT_JUDGE_URL` | String | No | URL to remote fine-tuned `ArguScore-4B` LoRA endpoint (e.g. via ngrok/RunPod). |
| `JUDGE_MODEL` | String | No | Fallback judge model (defaults to `llama-3.3-70b-versatile`). |
| `BLIND_PASSES` | Integer | No | `2` for label-swapped invariance (default), `1` for speed. |
| `PORT` | Integer | No | Container port (defaults to `7860` for Hugging Face Spaces). |

---

## 📁 Repository Structure

```
Argus/
├── backend/
│   ├── agents/              # Autonomous agent definitions (PRO, CON, SYN, Rebuttal)
│   ├── debate/              # Orchestrator, fact-checking NLI, ChromaDB evidence, judge
│   ├── scripts/             # Model diagnostic and diagnostic utilities
│   ├── tests/               # End-to-end integration test suite
│   ├── data/                # Vector store evidence seed datasets
│   └── main.py              # FastAPI server, WebSocket endpoints, static mount
├── research/
│   ├── paper/               # IEEE research paper manuscript, notes, and figures
│   └── notebooks/           # ArguScore LoRA training & swap-invariance notebooks
├── src/
│   ├── app/
│   │   ├── components/      # UI views (DebateDashboard, Replay, Landing, Benchmark)
│   │   ├── hooks/           # useDebateSocket, useDebateHistory custom hooks
│   │   ├── types/           # Strongly typed domain models (DebateMessage, JudgeLog)
│   │   └── lib/             # WebSocket resolvers, client API, PDF generator
│   └── index.html           # Main SPA entrypoint
├── docs/                    # Architectural diagrams, system slides, engineering logs
├── Dockerfile               # Multi-stage production container build
├── package.json             # Frontend dependencies & Vite scripts
└── vite.config.ts           # Vite build and proxy configuration
```

---

## 🔬 Research & Evaluation

ARGUS was developed alongside rigorous empirical research into multi-agent debate dynamics and automated adjudication:

- **IEEE Research Manuscript**: Complete publication drafts, notes, and experimental data are located in [`research/paper/`](research/paper/).
- **Fine-Tuning Notebooks**: [`research/notebooks/argus_train_swap_invariant.ipynb`](research/notebooks/argus_train_swap_invariant.ipynb) documents the dataset curation, preference pairs, and LoRA fine-tuning for position invariance.
- **Judge Server Deployment**: [`research/notebooks/argus_judge_server.ipynb`](research/notebooks/argus_judge_server.ipynb) provides the reference deployment script for serving `ArguScore-4B` with continuous ngrok tunneling.

---

## 🤝 Contributing

Contributions to ARGUS are welcome! Whether you are interested in expanding the NLI verification corpus, optimizing agent prompting strategies, or enhancing the dashboard UI:

1. **Fork the Project**
2. **Create a Feature Branch** (`git checkout -b feature/GroundedVerificationMetric`)
3. **Commit your Changes** (`git commit -m 'Add support for dense retrieval reranking'`)
4. **Push to the Branch** (`git push origin feature/GroundedVerificationMetric`)
5. **Open a Pull Request**

Please ensure that `npm run build` succeeds and backend tests pass before opening a PR.

---

## 📜 License

Distributed under the **MIT License**. See `LICENSE` for more information.

---

<div align="center">
  <sub>Built with ❤️ by the ARGUS Contributors. Powered by Groq, ChromaDB, and open-source foundation models.</sub>
</div>
