---

## EDITS TO APPLY

---

### 1. REMOVE
Delete **Section 6 — SDK / API Integration** entirely. Renumber all sections after it.

---

### 2. SPACING — Global Rule
Section vertical padding: `80px` top/bottom max. No `120px` or `160px` gaps. Sections should feel connected. Mobile: `48px` top/bottom.

---

### 3. IMAGE PLACEMENT — Strict
- `layout1.png` → Section 4 "Debate in Action" — left half, as-is, no crop, no filter
- `layout2.png` → Section 7 "Agent Face-Off" — full-bleed background, right-anchored, as-is
- Both must actually appear. No placeholders.

---

### 4. HERO IMAGE VISIBILITY FIX
Layer order must be strictly:
1. `hero.png` — bottom, full viewport, 100% opacity, no dark overlay on top
2. Grid overlay — `opacity: 3%`
3. Radial glow — blend mode `Screen`, `opacity: 15%`
4. Dashed arc
5. Text + glass cards — topmost

> Figma fix: `hero.png` fill opacity → `100%` → frame background → `None` → confirm it sits below all text/card layers. Do NOT place any dark rectangle fill above the image.

---

### 5. GLASSMORPHISM — Every Card Strictly
Every card, table, chip, panel, score card, model card — must use:
```
background: rgba(255,255,255,0.05);
backdrop-filter: blur(24px) saturate(180%);
border: 1px solid rgba(255,255,255,0.08);
border-radius: 20px;
box-shadow: 0 8px 32px rgba(0,0,0,0.6), inset 0 1px 0 rgba(255,255,255,0.06);
```
No solid fills. No flat dark cards. Everything floats.

---

### 6. NO EXPORT — Replace Results Content

**Section 4 — bullet chips — replace with:**
- `✓ Real-time argument generation`
- `✓ Fallacy detection engine`
- `✓ Multi-round debate flow`
- `✓ Live scoring per argument`

**Section 4 — body text — replace with:**
*ARGUS processes any debate topic, assigns agents to opposing sides, generates structured arguments round by round, scores each move, and reveals the winner with full reasoning — all inside the platform.*

**Add new Section after "How It Works" — "Results & Verdict" (glass score card):**
```
RESULTS & SCORING

Who won. Why they won. How every
argument was scored — in real time.

Round | Agent   | Argument Summary        | Score
──────────────────────────────────────────────────
  1   | Agent A | Cited empirical data    |  8.4
  1   | Agent B | Logical counter, weak   |  6.1
  2   | Agent A | Strong rebuttal         |  9.2
  2   | Agent B | Fallacy detected ⚠️     |  4.0

WINNER: AGENT A ✓
Winning argument: "Round 2 rebuttal — empirical
evidence + structural logic with zero fallacies."
```
Winner line: full white, bold. Loser rows: 50% opacity. Full glassmorphism card.

**Section 7 "Agent Face-Off" — replace bullets with:**
- `✓ Sub-second argument generation`
- `✓ Transparent scoring per round`
- `✓ Full winning argument breakdown`

**Footer CTA — second button replace with:**
`View Sample Debate →` — ghost, white outline

---

### 7. ENCOURAGE USER TO DEBATE — Throughout Page

- **Navbar:** `DEBATE` link — slightly brighter than other items + small pulsing dot `●` before it
- **Hero CTA:** `Start Debate` — primary white pill, largest button on page
- **Section 3 "How It Works":** Add below cards — `[ Ready to see it live? → Go to Debate ]` ghost pill, centered
- **Section 4 "Debate in Action":** End with `[ Watch a Live Debate → ]` white pill
- **Section 5 "Results & Scoring":** Add `[ See a Real Verdict → ]` ghost CTA below score table
- **Section 6 "Models":** Subtitle — *"Pick your model. Start your debate."* + `[ Begin → ]` chip
- **Section 7 "Agent Face-Off":** Glass card CTA — `[ Start the Face-Off → ]` white pill
- **Section 9 Footer:** `Start Debate` — 96px Orbitron Bold, undeniable final push

> **Design rule:** Every scroll should make the user feel the debate is one click away. Page builds tension — agents introduced → scoring shown → verdict revealed → *you* start one.