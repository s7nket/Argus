# ARGUS IEEE paper — claim-to-evidence map

Every claim in the paper traces to a command you can run or a file you have. This
is the map, so a seminar question is answered by running something rather than
from memory.

Files: `ARGUS-IEEE-Paper.docx` (source) · `ARGUS-IEEE-Paper.pdf` (10 pages)

## The headline result

> The fine-tuned scorer changes its verdict on **81.2%** of debates when the two
> side labels are exchanged — it reads the label, not the argument. Training with
> every debate entered once in each labelling drops that to **7.3%**, and raises
> agreement with the audience from **62.3% to 90.6%** on identical debates
> (exact McNemar, **p = 3.4 × 10⁻⁵**). On a larger held-out set it scores **79.5%**.

That is the paper. Everything else supports it.

## Reproducing each number

| Where | Claim | How to reproduce |
|---|---|---|
| §VIII-B, Fig. 3 | Baseline: 81.2% flip, 62.3% accuracy | `python -m eval.ft_eval --compare` — offline, no API |
| §VIII-B, Table III | ArguScore: 7.3% flip, 90.6% accuracy | `data/v3_on_v2_testset.json`, produced by the Kaggle eval cell |
| §VIII-B | McNemar p = 3.4×10⁻⁵ | Paired from `ft_scored.json` + `v3_on_v2_testset.json` |
| §VIII-B | 79.5% on 234 held-out debates | Training notebook, final cell |
| §VIII-B | 90.1% on topics never seen in training | Same two files, split by topic overlap |
| §VII-C | 3,304 debates, 140 held out, 0 leak | `python -m eval.build_training_set` prints all three |
| Table IV | Conformal coverage 0.955 / 0.905 / 0.806 | `python test_conformal.py` — synthetic, offline, ~5 s |
| Table V | n=57, agreement 0.544, κ 0.108 | `python -m eval.calibrate --report` — offline |
| Table VI | Baselines with bootstrap CIs | `python -m eval.baselines` — offline |
| Table VII | Ablation vs the original rubric | `python -m eval.ablation --report` — offline |
| Tables VIII, IX | Corpus growth, confirmation requirement | `docs/2026-08-01-calibration-and-conformal.md` |
| Table I | Evidence rubric bands | `agents/judge_agent.py:122-126`, verbatim |
| §IV-D | Tie band 0.5, evidence cap 3.0, repetition 0.30 / 1.5 | `config.py` |

Live corpus count:

```bash
python -c "import chromadb,config;c=chromadb.PersistentClient(path=config.CHROMA_DB_PATH);[print(x.name,c.get_collection(x.name).count()) for x in c.list_collections()]"
```

## The four questions you will be asked

**"Isn't 90.6% just a lucky sample? Your other number is 79.5%."**
Both are reported, and the gap is stated as unexplained — it is not length, vote
margin, or topic overlap, all three checked. The comparison is still sound
because it is *paired*: same 86 debates through both models, and McNemar only
counts the debates where they disagree — 27 to 4. A sample effect would have to
favour one model over the other on identical inputs, which is not what a sample
effect does.

**"Did the model just memorise the topics?"**
No. Accuracy on debates whose topic never appeared in training is 90.1%, against
100% on the five seen topics. Removing the seen ones barely moves it. Five is too
small to matter either way.

**"You beat GPT-4 then?"**
**No — do not claim this.** Fig. 4 plots 79.5%, not 90.6%, precisely so the chart
never puts you above GPT-4. Liu et al. measured a different sample under a
protocol that decides every debate, while ArguScore's headline set is balanced
50/50. Open markers vs filled markers in Fig. 4 carry that distinction and the
caption states it. The defensible sentence is "comparable to the 77–79% reported
for human annotators, on a different sample."

**"Why is Fig. 4 not a line chart?"**
Model names have no ordering, so a line would draw a slope between GPT-3.5 and
ArguScore as though something continuous connected them. Stems give the ranking
without inventing a trend.

## What the paper deliberately does not claim

Stated as limitations because they were not done. Do not add them back.

- **No ablation of the three training changes.** Real outcomes, length
  decorrelation and swap pairing were changed together. Which one produced the
  accuracy gain is unknown; only the flip-rate result isolates cleanly.
- **The cross-encoder NLI backend has never run** — `torch` is not installed. All
  figures use the general-model backend.
- **No mirrored-order runs**, so structural position bias is unmeasured. The label
  swap cancels preference for a *name*, not for speaking order.
- **Verification never engaged on the argument-quality pairs** — 1 extractable
  specific in 114 sides. Tables VIII and IX are the only evidence for §V, on
  twelve claims.
- **Labels are audience votes**, not expert adjudication. The corpus authors
  themselves find voters' prior beliefs predict their votes.

## The one claim without a measurement

§I contribution 3: conformal prediction here is *"to our knowledge the first
application to automated debate adjudication."* Hedged, which is standard. If
challenged: the method is standard [15], [16]; the novelty claimed is the
application; the literature search was not exhaustive.

## Before the seminar

1. **Test the serving notebook end to end.** It was changed for v3 — new adapter
   path, `max_seq_length=8192`, new output schema, rewritten `fix_scores`, and a
   self-test that now checks swap-invariance instead of hallucination. None of
   that has been run against a live session yet. Do not find out during a demo.
2. Run the four offline commands above once, so you have seen the output.
3. Have `v3_on_v2_testset.json` open — per-debate verdicts answer most
   "but what about…" questions directly.
