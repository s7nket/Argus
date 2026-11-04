# ARGUS: Mathematical Formulations, Algorithms, & Technical Reference

This document compiles the formal mathematical models, algorithmic procedures, loss formulations, and evaluation metrics used throughout the ARGUS Multi-Agent Debate and Automated Adjudication System.

---

## 1. Distribution-Free Conformal Prediction
**Source:** `backend/debate/conformal.py`

Traditional LLM judges output forced binary verdicts with unquantified uncertainty. ARGUS implements **Split Conformal Prediction** to map continuous evaluation margins into set-valued predictions $C(X) \subseteq \{\text{PRO}, \text{CON}, \text{TIE}\}$ that satisfy a distribution-free marginal coverage guarantee.

### 1.1 Non-Conformity Function
Let $S_{\text{pro}}, S_{\text{con}} \in [0, 10]$ denote the total round or debate scores assigned to PRO and CON respectively. The signed margin is defined as:

$$\Delta = S_{\text{pro}} - S_{\text{con}}$$

The non-conformity function $s(X, y)$ measures how poorly the observation $X = (S_{\text{pro}}, S_{\text{con}})$ conforms to a hypothesized outcome $y \in \{\text{PRO}, \text{CON}, \text{TIE}\}$:

$$s(X, y) = \begin{cases} 
-\Delta = S_{\text{con}} - S_{\text{pro}}, & \text{if } y = \text{PRO} \\ 
+\Delta = S_{\text{pro}} - S_{\text{con}}, & \text{if } y = \text{CON} \\ 
|\Delta| = |S_{\text{pro}} - S_{\text{con}}|, & \text{if } y = \text{TIE} 
\end{cases}$$

A confident correct call produces a large negative value; an error produces a positive value. For $\text{TIE}$, any separation in either direction penalizes conformity.

### 1.2 Finite-Sample Quantile Calibration
Given a calibration dataset $\mathcal{D}_{\text{cal}} = \{(X_i, Y_i^*)\}_{i=1}^n$ of $n$ debate rounds with human crowd ground-truth labels $Y_i^*$:

1. Compute ground-truth non-conformity scores:
   $$s_i = s(X_i, Y_i^*), \quad \forall i \in \{1, \dots, n\}$$
2. Sort in ascending order:
   $$s_{(1)} \le s_{(2)} \le \dots \le s_{(n)}$$
3. Compute the finite-sample corrected empirical quantile rank $k$ for target significance level $\alpha \in (0, 1)$ (where $1 - \alpha$ is the desired coverage, e.g., $90\%$ for $\alpha = 0.10$):
   $$k = \left\lceil (n + 1)(1 - \alpha) \right\rceil$$

4. The calibrated critical quantile $\hat{q}$ is:
   $$\hat{q} = \begin{cases} 
   s_{(k)}, & \text{if } k \le n \\ 
   +\infty, & \text{if } k > n \text{ (insufficient sample size)} 
   \end{cases}$$

> **Sample Size Requirement:** To construct any prediction set narrower than the trivial set of all outcomes, the calibration set must satisfy:
> $$n \ge \left\lceil \frac{1}{\alpha} \right\rceil - 1$$
> For $\alpha = 0.10$, $n \ge 9$ calibration rounds.

### 1.3 Prediction Set Construction & Abstention Rule
At test time, the calibrated prediction set $C(X_{\text{test}})$ is:

$$C(X_{\text{test}}) = \left\{ y \in \{\text{PRO}, \text{CON}, \text{TIE}\} \;\middle|\; s(X_{\text{test}}, y) \le \hat{q} \right\}$$

**Marginal Coverage Theorem:** Under exchangeability of calibration and test distributions:

$$\mathbb{P}\left(Y_{\text{test}}^* \in C(X_{\text{test}})\right) \ge 1 - \alpha$$

**Decision & Abstention Logic:**
$$\text{Verdict}(X) = \begin{cases} 
y, & \text{if } C(X) = \{y\} \text{ (Certified Winner)} \\ 
\text{ABSTAIN}, & \text{if } |C(X)| > 1 \text{ (Insufficient Separation / Epistemic Ambiguity)} \\ 
\text{OUTLIER}, & \text{if } C(X) = \emptyset \text{ (Out-of-Distribution Exchange)} 
\end{cases}$$

---

## 2. Swap-Invariant Fine-Tuning of ArguScore-4B
**Source:** `notebooks/argus_train_swap_invariant.ipynb` & `backend/eval/build_training_set.py`

### 2.1 Model & Adapter Configuration
* **Base Architecture:** `unsloth/Llama-3.1-Nemotron-Nano-4B-v1.1-bnb-4bit`
* **Context Budget ($L_{\max}$):** 8,192 tokens (accommodates 97.4% of debates without truncation)
* **Quantization:** 4-bit NormalFloat (NF4) with Double Quantization
* **LoRA Rank & Scaling:** $r = 32$, $\alpha_{\text{lora}} = 32$, Dropout $= 0.0$
* **Target Weight Modules:**
  $$\mathcal{W}_{\text{target}} = \{W_q, W_k, W_v, W_o, W_{\text{gate}}, W_{\text{up}}, W_{\text{down}}\}$$
  $$\Delta W = \frac{\alpha_{\text{lora}}}{r} B A, \quad A \in \mathbb{R}^{r \times d_{\text{in}}}, \; B \in \mathbb{R}^{d_{\text{out}} \times r}$$

### 2.2 Swap Invariance Formulation
Standard LLM judges exhibit presentation/label bias where swapping debater labels causes verdict reversals in over $80\%$ of cases. ArguScore forces permutation symmetry during training by creating exact mirror pairs:

$$\mathcal{D}_{\text{train}} = \bigcup_{i=1}^M \left\{ \left(X_i, Y_i\right), \; \left(X_i^{\text{swapped}}, \text{flip}(Y_i)\right) \right\}$$

$$\text{where } \text{flip}(Y) = \begin{cases} 
\text{CON}, & \text{if } Y = \text{PRO} \\ 
\text{PRO}, & \text{if } Y = \text{CON} \\ 
\text{TIE}, & \text{if } Y = \text{TIE} 
\end{cases}$$

### 2.3 Supervised Target Formulation
Given a human crowd vote margin $\Delta_{\text{vote}} \in [-1.0, 1.0]$, scores are scaled symmetrically about baseline midpoint $6.0$:

$$\text{gap} = \min\left(2.5, \; 0.5 + 0.25 \cdot |\Delta_{\text{vote}}|\right)$$

$$S_{\text{high}} = \text{round}\left(6.0 + \frac{\text{gap}}{2}, 1\right), \quad S_{\text{low}} = \text{round}\left(6.0 - \frac{\text{gap}}{2}, 1\right)$$

$$(S_{\text{pro}}^*, S_{\text{con}}^*) = \begin{cases} 
(S_{\text{high}}, S_{\text{low}}), & \text{if } Y = \text{PRO} \\ 
(S_{\text{low}}, S_{\text{high}}), & \text{if } Y = \text{CON} \\ 
(6.0, 6.0), & \text{if } Y = \text{TIE} 
\end{cases}$$

Target response tokens:
$$\mathcal{Y}_{\text{target}} = \text{JSON}\left(\{\text{"winner"}: Y, \text{"pro\_total"}: S_{\text{pro}}^*, \text{"con\_total"}: S_{\text{con}}^*\}\right)$$

### 2.4 Optimization Objective
The model is trained via token-level causal language modeling cross-entropy over target tokens $\mathcal{Y}$:

$$\mathcal{L}_{\text{SFT}}(\theta) = -\frac{1}{|\mathcal{Y}|} \sum_{t=1}^{|\mathcal{Y}|} \log P_{\theta}\left(y_t \;\middle|\; y_{<t}, X\right)$$

* **Optimizer:** 8-bit AdamW ($\beta_1 = 0.9, \beta_2 = 0.999, \epsilon = 10^{-8}$)
* **Learning Rate Schedule:** Cosine decay with 3% warmup:
  $$\eta_t = \eta_{\min} + \frac{1}{2}\left(\eta_{\max} - \eta_{\min}\right)\left(1 + \cos\left(\frac{t - t_{\text{warm}}}{T - t_{\text{warm}}}\pi\right)\right), \quad \eta_{\max} = 10^{-4}$$
* **Batch Size:** Effective batch size $= 8$ (per-device batch $= 1$, accumulation $= 8$).

---

## 3. Retrieval-Augmented Fact-Checking & Grounding Verification
**Source:** `backend/debate/verifier.py` & `backend/agents/fact_checker_agent.py`

### 3.1 Dense Embedding Retrieval
Extracted claims $c_i$ are matched against evidence documents $d_j$ in ChromaDB using cosine similarity:

$$\text{sim}(c_i, d_j) = \cos(\mathbf{e}_{c_i}, \mathbf{e}_{d_j}) = \frac{\mathbf{e}_{c_i} \cdot \mathbf{e}_{d_j}}{\|\mathbf{e}_{c_i}\|_2 \|\mathbf{e}_{d_j}\|_2}$$

$$\text{Passages}(c_i) = \text{Top-}k \left( \arg\max_{d_j} \text{sim}(c_i, d_j) \right), \quad k = 2$$

### 3.2 Natural Language Inference (NLI)
For each claim $c_i$ and retrieved evidence $\mathcal{P}_i = \text{Passages}(c_i)$, an NLI model outputs a discrete classification:

$$P(\text{label} \mid c_i, \mathcal{P}_i) \in \{\text{SUPPORTED}, \text{REFUTED}, \text{NEI}\}$$

### 3.3 Grounding Coverage & Precision
Let $N_{\text{total}}$ be the total extracted claims, with counts $N_{\text{sup}}$, $N_{\text{ref}}$, and $N_{\text{nei}}$:

$$N_{\text{adj}} = N_{\text{sup}} + N_{\text{ref}} \quad \text{(Adjudicable Claims)}$$

$$\text{Coverage} = \begin{cases} \frac{N_{\text{adj}}}{N_{\text{total}}}, & \text{if } N_{\text{total}} > 0 \\ 0.0, & \text{otherwise} \end{cases}$$

$$\text{Precision} = \begin{cases} \frac{N_{\text{sup}}}{N_{\text{adj}}}, & \text{if } N_{\text{adj}} > 0 \\ 1.0, & \text{if } N_{\text{adj}} = 0 \end{cases}$$

### 3.4 Evidence Score Ceiling & Fabrication Penalty
To ensure debaters cannot fabricate facts or inflate evidence scores without verifiable grounding:

$$\text{Cap}_{\text{evidence}} = \begin{cases} 
\text{Floor} + (10.0 - \text{Floor}) \cdot \text{Precision}, & \text{if } N_{\text{adj}} > 0 \\ 
10.0, & \text{if } N_{\text{adj}} = 0 
\end{cases} \quad (\text{Floor} = 3.0)$$

$$\text{Penalty}_{\text{fab}} = \min\left(\text{MaxPenalty}, \; N_{\text{ref}} \cdot w_{\text{fab}}\right) \quad (w_{\text{fab}} = 1.0, \; \text{MaxPenalty} = 3.0)$$

$$S_{\text{evidence}}^{\text{grounded}} = \max\left(0.0, \; \min\left(S_{\text{evidence}}, \text{Cap}_{\text{evidence}}\right) - \text{Penalty}_{\text{fab}}\right)$$

---

## 4. Judge Scoring, Debiasing, & Repetition Control
**Source:** `backend/agents/judge_agent.py`

### 4.1 Cyclic Label Rotation (Blind Passes)
To cancel LLM bias toward specific label names or presentation order, the judge executes blind scoring passes with rotated labels:

**3-Way Cyclic Permutation Matrix:**
$$\text{Pass 1}: \quad \begin{pmatrix} \text{PRO} \\ \text{CON} \\ \text{SYN} \end{pmatrix} \mapsto \begin{pmatrix} \text{DEBATER-X} \\ \text{DEBATER-Y} \\ \text{DEBATER-Z} \end{pmatrix}, \quad \text{Pass 2}: \quad \begin{pmatrix} \text{PRO} \\ \text{CON} \\ \text{SYN} \end{pmatrix} \mapsto \begin{pmatrix} \text{DEBATER-Y} \\ \text{DEBATER-Z} \\ \text{DEBATER-X} \end{pmatrix}$$

Averaged across $K$ blind passes ($K \in \{1, 2\}$):
$$\bar{S}_{\text{criterion}}(\text{agent}) = \frac{1}{K} \sum_{k=1}^K S_{\text{criterion}}^{(k)}(\text{agent}), \quad \forall \text{criterion} \in \{\text{evidence}, \text{logic}, \text{relevance}\}$$

### 4.2 Repetition Penalty ($n$-gram Overlap)
Prevents debaters from repeating memorized phrasing across sub-rounds. Let $\mathcal{G}_5(T)$ denote the multiset of 5-grams in text $T$:

$$R = \frac{|\mathcal{G}_5(\text{Current Round}) \cap \mathcal{G}_5(\text{Prior Rounds})|}{|\mathcal{G}_5(\text{Current Round})|}$$

$$\text{Penalty}_{\text{rep}} = \begin{cases} 
0.0, & \text{if } R \le 0.30 \\ 
\min\left(1.5, \; (R - 0.30) \times 5.0\right), & \text{if } R > 0.30 
\end{cases}$$

### 4.3 Total Score & Decision Rule
$$S_{\text{base}} = \frac{S_{\text{evidence}} + S_{\text{logic}} + S_{\text{relevance}}}{3}$$

$$S_{\text{total}} = \text{clamp}\left( S_{\text{base}} - \text{Penalty}_{\text{rep}} - \text{Penalty}_{\text{fab}}, \; 0.0, \; 10.0 \right)$$

**Tie-Band Threshold ($\tau_{\text{tie}} = 0.5$):**
Let $S_{(1)} \ge S_{(2)} \ge S_{(3)}$ denote sorted totals:
$$\text{Winner} = \begin{cases} 
\text{TIE}, & \text{if } (S_{(1)} - S_{(2)}) \le \tau_{\text{tie}} \\ 
\arg\max_i S_{\text{total}}^{(i)}, & \text{if } (S_{(1)} - S_{(2)}) > \tau_{\text{tie}} 
\end{cases}$$

### 4.4 Longest-Substring Claim Deduplication
Extracted factual claims are deduplicated to avoid counting redundant fragments:
$$\text{KeptClaims} = \left\{ c_i \;\middle|\; \neg \exists c_j \text{ s.t. } \text{norm}(c_i) \subset \text{norm}(c_j) \land \text{len}(c_j) > \text{len}(c_i) \right\}$$

---

## 5. Statistical Benchmark & Evaluation Metrics
**Source:** `backend/eval/metrics.py` & `backend/eval/ft_eval.py`

### 5.1 Cohen's Kappa ($\kappa$)
Measures inter-annotator / judge agreement with human crowd ground truth corrected for chance agreement:

$$\kappa = \frac{P_o - P_e}{1 - P_e}$$

$$P_o = \frac{1}{N} \sum_{i=1}^N \mathbb{I}(\hat{y}_i = y_i^*), \quad P_e = \sum_{c \in \{\text{pro}, \text{con}, \text{tie}\}} P(\hat{y} = c) \cdot P(y^* = c)$$

### 5.2 Verdict Flip Rate
Quantifies model sensitivity to label permutation (swap vulnerability):

$$\text{FlipRate} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}\left( \hat{y}(X_i) \neq \text{flip}\left(\hat{y}(X_i^{\text{swapped}})\right) \right)$$

### 5.3 Pearson Margin Correlation ($r$)
Correlation between the judge's score margin $\Delta = S_{\text{pro}} - S_{\text{con}}$ and the true human vote margin $\Delta^*$:

$$r = \frac{\sum_{i=1}^N (\Delta_i - \bar{\Delta})(\Delta_i^* - \bar{\Delta}^*)}{\sqrt{\sum_{i=1}^N (\Delta_i - \bar{\Delta})^2 \sum_{i=1}^N (\Delta_i^* - \bar{\Delta}^*)^2}}$$

### 5.4 Score Compression Metric
Detects rubric degeneration where scores collapse into a narrow band:

$$\text{Compression} = \frac{1}{N} \sum_{i=1}^N \mathbb{I}\left( 7.0 \le S_i \le 8.5 \right)$$

---

## 6. Mathematical Nomenclature & Parameter Reference

| Symbol | Default Value | Description |
|---|---|---|
| $\alpha$ | $0.10$ | Conformal prediction significance level ($90\%$ coverage guarantee) |
| $\hat{q}$ | Empirical | Conformal critical non-conformity threshold |
| $\tau_{\text{tie}}$ | $0.5$ | Score separation threshold below which a round is declared a TIE |
| $R_{\text{free}}$ | $0.30$ | Repetition ratio tolerance before repetition penalty ramps up |
| $\text{Penalty}_{\text{rep}}^{\max}$ | $1.5$ | Maximum repetition penalty subtracted from round score |
| $\text{Floor}$ | $3.0$ | Minimum evidence cap when all adjudicable claims are refuted |
| $w_{\text{fab}}$ | $1.0$ | Score deduction per refuted factual claim |
| $\text{MaxPenalty}_{\text{fab}}$ | $3.0$ | Maximum fabrication penalty |
| $r, \alpha_{\text{lora}}$ | $32, 32$ | ArguScore-4B LoRA rank and scaling factor |
| $\eta_{\max}$ | $10^{-4}$ | Maximum learning rate for AdamW cosine decay |
| $k$ | $2$ | Top-$k$ evidence passages retrieved from ChromaDB |

