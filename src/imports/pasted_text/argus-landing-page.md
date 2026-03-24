---

## 🧠 Figma Design Prompt — AI Multi-Agent Debate System

---

### PROJECT OVERVIEW

Design a **responsive, production-grade web3 landing page** for **ARGUS** — an AI Multi-Agent Debate System where autonomous agents argue, a judge AI evaluates, and structured debate reports are generated. The visual language is **dark cyberpunk × Apple-grade minimalism × Web3 glassmorphism**. Every section should feel like it belongs in a high-end product launch, not a hackathon project.

---

### BRAND & THEME

- **Product Name:** `ARGUS` *(Autonomous Reasoning & Generative Utility System)*
- **Tagline:** *"Two minds. One truth."*
- **Color Palette:**
  - Background: `#050505` → `#0a0a0f` (near-black, not pure black)
  - Accent: `#ffffff` (white), `#c8c8c8` (cool gray)
  - Glass tint: `rgba(255,255,255,0.04)` to `rgba(255,255,255,0.08)`
  - Glow: `rgba(255,255,255,0.15)` radial for hero backdrop
  - Border glass: `rgba(255,255,255,0.08)`
- **Typography:**
  - Display/Hero: `Orbitron` or `Neue Haas Grotesk Display` — all-caps, heavy weight
  - Body: `DM Sans` or `Suisse Int'l` — light weight, max 14–15px
  - Mono labels: `JetBrains Mono` — for agent tags, status chips
- **Grid:** 12-column, 1440px max-width, 80px gutters desktop / 24px mobile

---

### GLASSMORPHISM RULES (STRICT)

Apply to: cards, nav, modals, feature tiles, side panels.

```
background: rgba(255, 255, 255, 0.05);
backdrop-filter: blur(24px) saturate(180%);
-webkit-backdrop-filter: blur(24px);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: 20px;
box-shadow: 0 8px 32px rgba(0, 0, 0, 0.6), inset 0 1px 0 rgba(255,255,255,0.06);
```

**Do NOT use colored glass.** Only neutral/white-tinted. No purple, no blue. This is monochrome luxury.

---

### SECTION-BY-SECTION LAYOUT

---

#### 1. NAVBAR (Sticky, Glassmorphic)

- **Left:** `▲` logo mark (geometric triangle glyph) + `ARGUS`
- **Center:** `DEBATE MODULE` · `AGENTS` · `PRICING` · `API`
- **Right:** `Try now` — white pill button, black text, hover: invert
- **Style:** Full-width glass bar, `blur(20px)`, `border-bottom: 1px solid rgba(255,255,255,0.06)`

---

#### 2. HERO SECTION (Full Viewport)

- **Background:** Two robots facing each other — full-bleed, dark, centered
- **Radial white glow** behind both robot heads
- **Subtle grid overlay:** 1px white lines at 80px intervals, `opacity: 3%`
- **Center title (massive):** `ARGUS` — Orbitron Bold, ~120px, white, letter-spacing: 0.08em
- **Below title (small label):** `MULTI-AGENT DEBATE SYSTEM` — monospace, 11px, `opacity: 50%`
- **Dashed circular arc** behind hero robots

**Left-bottom glass card:**
```
DEBATE-1 × DEBATE-2

Two autonomous AI agents, engineered for
logic, precision, and adversarial reasoning —
debating any topic in real time.

[  Start Debate  ]
```

**Right-side floating glass card:**
```
[small robot thumbnail]

JUDGE-0

An impartial AI evaluator that scores arguments,
detects fallacies, and delivers the final verdict.

[  Learn More  ]
```

Both CTA buttons: white pill, black text.

---

#### 3. SECTION — "How It Works" (3-column glassmorphic cards)

**Section label (top center):** `SYSTEM ARCHITECTURE` — monospace, 10px, 40% opacity
**Heading:** `Intelligence that argues.`
**Subhead:** *Two agents. One judge. Zero bias.*

**Cards (glass, horizontal scroll on mobile):**

| Icon | Title | Body |
|------|-------|------|
| `⟡` | Agent A · Proponent | Constructs structured arguments, pulls evidence, adapts in real-time. |
| `⊗` | Agent B · Opponent | Deconstructs claims, exposes logical gaps, counter-argues with precision. |
| `◈` | Judge-0 · Evaluator | Scores each round. Detects fallacies. Delivers an unbiased final verdict. |

Each card: `rgba(255,255,255,0.05)` glass, `1px` white border, `border-radius: 20px`, 40px internal padding.

---

#### 4. SECTION — "Debate in Action" (split layout)

- **Left:** Single robot image — left-edge cropped, dramatic
- **Right:** Text stack
  - Eyebrow label: `FOR RESEARCHERS & BUILDERS`
  - Heading: `Run any argument. At scale.`
  - Body: *ARGUS processes complex topics, generates structured debate transcripts, evaluates winner logic, and exports full reports — automatically.*
  - 4 bullet chips (glass pill tags):
    - `✓ Real-time argument generation`
    - `✓ Fallacy detection engine`
    - `✓ Multi-language support`
    - `✓ Export to PDF / PPT`

---

#### 5. SECTION — "Performance Benchmark" (dark glass table)

**Section label:** `OUTPERFORMING`
**Heading:** `Fastest debate resolution engine`
**Sub:** *Built for speed. Optimized for clarity.*

Glass-bordered benchmark table:
```
MODEL           | Arguments/min | Accuracy | Latency
─────────────────────────────────────────────────────
ARGUS-3 (ours)  |     312       |  94.2%   |  0.8s
GPT-4 Chain     |     198       |  89.1%   |  2.1s
LangGraph       |     241       |  91.3%   |  1.4s
```

Table background: `rgba(255,255,255,0.03)`, header row slightly brighter glass.

---

#### 6. SECTION — "SDK / API Integration" (split code panel)

- **Left glass panel:** `Try ARGUS SDK for free`
  - Bullet list:
    - Plug-in SDK for local + cloud debate
    - Argument generation + scoring handled
    - Local-first for text, audio, structured data
    - One developer can go live in minutes
  - CTA: `Try SDK` + `Explore docs →`
- **Right glass panel:** Dark code block (terminal style)
```bash
pip install argus-debate
from argus import DebateEngine
engine = DebateEngine(topic="AGI Safety")
engine.run(rounds=5, export="pdf")
```

---

#### 7. SECTION — "Models Supported" (tab filter + grid)

**Heading:** `All key LLMs supported`
**Tab pills (glass):** `Gemini` · `GPT-4o` · `Claude` · `Mistral` · `LLaMA`
**Below:** 3×2 model card grid — each glass card with model name, logo placeholder, compatibility tag.

---

#### 8. SECTION — "Agent Face-Off" (cinematic, full-bleed)

- **Background:** Two robots facing each other — wide shot, full-bleed
- Overlay: `rgba(0,0,0,0.5)`
- **Center glass card:**
```
Users don't care who wins.
They care how it's argued.

ARGUS delivers debate-native experiences — fast,
structured, and brutally fair.

✓ Sub-second response per argument
✓ Offline-capable, no network breaks
✓ Consistent scoring, zero drift
```

---

#### 9. SECTION — Partnership / Integrations Banner

```
ARGUS × Open Ecosystem

Built on open-source LLM infrastructure.
Integrates with your existing AI stack.

[ Explore Integrations → ]
```

Minimal centered layout. `opacity: 60%` text. Small glass pill. Clean and product-focused.

---

#### 10. CTA FOOTER HERO

- Large text: `Run any debate.`
- Subtext: `Free your reasoning.`
- Two buttons: `Start Debate` (white pill) · `Explore API →` (ghost)
- Below: minimal footer grid — `Plan` · `Company` · `Links` columns, 11px text

---

### RESPONSIVE BREAKPOINTS

| Breakpoint | Behavior |
|------------|----------|
| 1440px | Full layout as designed |
| 1024px | Collapse split sections to stack |
| 768px | Single column, hidden nav links → hamburger |
| 375px | Full mobile, hero text scales to 48px, cards scroll horizontal |

---

### ANIMATION HINTS (for Figma Prototype / Dev handoff)

- Hero robots: fade-in + subtle upward translate on load (600ms ease-out)
- Glow behind robots: pulsing radial opacity (1.5s loop, 0.4→0.7 opacity)
- Glass cards: hover → `scale(1.02)` + `border: 1px solid rgba(255,255,255,0.15)`
- Nav: blur intensifies on scroll past 80px
- Grid lines: fade in on page load (opacity 0→3%, 1s delay)

---

### REFERENCE MAPPING

| Reference Image | Used In |
|----------------|---------|
| `hero.png` (two robots facing) | Hero section background |
| `layout1.png` (single robot side) | Section 4 — "Debate in Action" |
| `layout2.png` (single robot side alt) | Section 8 — "Agent Face-Off" |
| `reference.webp` (mirai site) | Overall scroll structure + section density |
| `text.webp` (TRONIX-5 layout) | Hero layout composition, card placement, nav structure |

---

> **Figma tip:** Use **Auto Layout** for all cards and sections. Set **Clip content OFF** on hero frame so robot images bleed naturally. Use **Blur** effect (not fill) for all glass components. Keep all text on `#FFFFFF` with opacity variance — never use gray hex values directly.