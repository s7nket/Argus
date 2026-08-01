"""
Conformal prediction over debate verdicts.

Every judge in the literature returns a winner. None of them return "I do not
know", and none quantify how often they are wrong — which matters here because
the same round has been observed flipping outcome under a single mislabelled
claim, and because a 0.7-point margin on a 30-point scale is not a real result.

Split conformal prediction turns the margin into a verdict SET with a
distribution-free coverage guarantee: given a calibration set of rounds with
known outcomes, the set contains the true winner at least (1 - alpha) of the
time on future rounds, with no assumption about the score distribution and no
assumption that the judge is well calibrated. When the set holds more than one
outcome the system abstains, which is an honest answer rather than a coin flip.

The guarantee is marginal and assumes calibration and test rounds are
exchangeable. It is a statement about the long run, not about any single round.

Method
------
Nonconformity for a round is the negated signed margin toward the true winner:

    s = -(score[true_winner] - score[other])

A confident correct call is very negative, a wrong call positive. With n
calibration rounds, q is the ceil((n+1)(1-alpha))/n empirical quantile of those
scores. At test time an outcome enters the set when its own nonconformity, computed
as if it were true, falls at or below q. That finite-sample correction on the
quantile is what makes the coverage guarantee hold at small n rather than only
asymptotically.
"""

import json
import math
import os
from dataclasses import asdict, dataclass, field
from typing import Any

import config

PRO = "pro"
CON = "con"
TIE = "tie"


@dataclass
class ConformalPredictor:
    """Fitted on completed rounds; predicts verdict sets for new ones."""

    alpha: float = 0.1
    scores: list[float] = field(default_factory=list)
    quantile: float | None = None
    n_calibration: int = 0

    # ── Calibration ──────────────────────────────────────────────────────────

    @staticmethod
    def nonconformity(pro_total: float, con_total: float, outcome: str) -> float:
        """
        How poorly the scores support `outcome`. Larger is worse.

        A tie is scored on absolute margin: the claim being tested is that
        neither side is meaningfully ahead, so any separation counts against it,
        in either direction.
        """
        margin = pro_total - con_total
        if outcome == PRO:
            return -margin
        if outcome == CON:
            return margin
        return abs(margin)

    def fit(self, rounds: list[dict]) -> "ConformalPredictor":
        """
        Calibrate on rounds of {pro_total, con_total, true_winner}.

        The true winner is the human label, never the system's own verdict —
        calibrating against its own output would only measure self-consistency
        and would guarantee nothing.
        """
        self.scores = sorted(
            self.nonconformity(r["pro_total"], r["con_total"], r["true_winner"])
            for r in rounds
        )
        self.n_calibration = len(self.scores)
        if self.n_calibration == 0:
            self.quantile = None
            return self

        # ceil((n+1)(1-alpha))/n — the finite-sample correction. Without it
        # coverage is only asymptotic and undershoots on small calibration sets,
        # which is exactly the regime a student project runs in.
        k = math.ceil((self.n_calibration + 1) * (1 - self.alpha))
        if k > self.n_calibration:
            # Too few rounds to certify this alpha at all; abstain everywhere
            # rather than quietly report a guarantee that does not hold.
            self.quantile = float("inf")
        else:
            self.quantile = self.scores[k - 1]
        return self

    @property
    def min_calibration_size(self) -> int:
        """Rounds needed before any set can be narrower than 'everything'."""
        return math.ceil(1 / self.alpha) - 1

    # ── Prediction ───────────────────────────────────────────────────────────

    def predict(self, pro_total: float, con_total: float,
                outcomes: tuple[str, ...] = (PRO, CON, TIE)) -> dict[str, Any]:
        """
        Verdict set for one round, plus the point estimate for reference.

        An empty set can occur when every outcome is more nonconforming than the
        quantile. That is not a coverage violation — it is the predictor saying
        the round looks unlike anything it was calibrated on — but reporting it
        as a confident nothing would be misleading, so it is surfaced as an
        abstention with a distinct flag.
        """
        margin = round(pro_total - con_total, 2)
        point = TIE if abs(margin) <= config.TIE_BAND else (PRO if margin > 0 else CON)

        if self.quantile is None:
            return {
                "verdict_set": list(outcomes),
                "abstain": True,
                "reason": "not calibrated",
                "point_estimate": point,
                "margin": margin,
                "alpha": self.alpha,
                "n_calibration": 0,
            }

        included = [o for o in outcomes
                    if self.nonconformity(pro_total, con_total, o) <= self.quantile]

        return {
            "verdict_set": included,
            "abstain": len(included) != 1,
            "reason": ("empty set — round unlike the calibration data" if not included
                       else None if len(included) == 1 else "insufficient separation"),
            "point_estimate": point,
            "margin": margin,
            "alpha": self.alpha,
            "quantile": round(self.quantile, 3),
            "n_calibration": self.n_calibration,
        }

    # ── Evaluation ───────────────────────────────────────────────────────────

    def evaluate(self, rounds: list[dict]) -> dict[str, Any]:
        """
        Empirical coverage and set sizes on held-out rounds.

        Coverage should land near 1 - alpha. Materially below it means the
        exchangeability assumption is broken — typically calibration and test
        rounds drawn from different topics or different judge configurations.
        """
        if not rounds:
            return {}
        covered = singleton = abstained = empty = 0
        sizes: list[int] = []
        correct_when_decided = decided = 0

        for r in rounds:
            p = self.predict(r["pro_total"], r["con_total"])
            s = p["verdict_set"]
            sizes.append(len(s))
            if r["true_winner"] in s:
                covered += 1
            if not s:
                empty += 1
            if len(s) == 1:
                singleton += 1
                decided += 1
                if s[0] == r["true_winner"]:
                    correct_when_decided += 1
            else:
                abstained += 1

        n = len(rounds)
        return {
            "n_test": n,
            "target_coverage": round(1 - self.alpha, 3),
            "empirical_coverage": round(covered / n, 3),
            "mean_set_size": round(sum(sizes) / n, 2),
            "singleton_rate": round(singleton / n, 3),
            "abstention_rate": round(abstained / n, 3),
            "empty_set_rate": round(empty / n, 3),
            # Accuracy on the rounds it was willing to decide — the number that
            # says whether abstention is buying anything.
            "selective_accuracy": round(correct_when_decided / decided, 3) if decided else None,
        }

    # ── Persistence ──────────────────────────────────────────────────────────

    def save(self, path: str | None = None) -> str:
        path = path or config.CONFORMAL_STATE_PATH
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=1)
        return path

    @classmethod
    def load(cls, path: str | None = None) -> "ConformalPredictor | None":
        path = path or config.CONFORMAL_STATE_PATH
        if not os.path.exists(path):
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return cls(**json.load(f))
        except Exception:
            return None


_cached: ConformalPredictor | None = None


def get_predictor() -> ConformalPredictor | None:
    """Fitted predictor from disk, or None when the system has never been calibrated."""
    global _cached
    if _cached is None:
        _cached = ConformalPredictor.load()
    return _cached
