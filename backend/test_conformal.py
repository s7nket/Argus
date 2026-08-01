"""
Conformal predictor tests.

Run from backend/:  python test_conformal.py

The claim being tested is the guarantee itself: over many random splits,
empirical coverage on held-out rounds should land at or above 1 - alpha. A
conformal implementation that does not clear that bar is worthless, and the
failure is silent — it still returns plausible-looking sets.

Synthetic rounds are used deliberately. Coverage is a property of the method
under exchangeability, so it must hold on data whose ground truth is known
exactly; real debates come later, with human labels.
"""

import random
import statistics
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from debate.conformal import CON, PRO, TIE, ConformalPredictor

ok = True


def check(name, got, want):
    global ok
    good = got == want
    print(f"  {'ok  ' if good else 'FAIL'} {name:<50} {got!r}")
    if not good:
        print(f"       wanted {want!r}")
        ok = False


def make_rounds(n: int, noise: float = 1.5, seed: int = 0) -> list[dict]:
    """
    Rounds with a known true winner and a noisy observed margin.

    Noise is what makes the test meaningful: with none, every round separates
    cleanly and any predictor looks perfect.
    """
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        true = rng.choice([PRO, CON, TIE])
        base = {PRO: 3.0, CON: -3.0, TIE: 0.0}[true]
        margin = base + rng.gauss(0, noise)
        pro = 15 + margin / 2
        out.append({"pro_total": round(pro, 2),
                    "con_total": round(pro - margin, 2),
                    "true_winner": true})
    return out


def main() -> None:
    print("-- nonconformity --")
    nc = ConformalPredictor.nonconformity
    check("confident PRO win scores low", nc(20, 10, PRO), -10)
    check("PRO label on a CON round scores high", nc(10, 20, PRO), 10)
    check("tie scored on absolute margin", nc(20, 10, TIE), 10)
    check("tie on an even round scores 0", nc(15, 15, TIE), 0)
    check("symmetric: CON mirrors PRO", nc(10, 20, CON), nc(20, 10, PRO))

    print("\n-- calibration --")
    p = ConformalPredictor(alpha=0.1).fit(make_rounds(200, seed=1))
    check("calibration size recorded", p.n_calibration, 200)
    check("quantile is finite", p.quantile is not None and p.quantile < float("inf"), True)
    check("min calibration size for alpha=0.1", ConformalPredictor(alpha=0.1).min_calibration_size, 9)

    empty = ConformalPredictor(alpha=0.1).fit([])
    check("uncalibrated predictor abstains", empty.predict(20, 10)["abstain"], True)
    check("uncalibrated returns full set", len(empty.predict(20, 10)["verdict_set"]), 3)

    # Too few rounds to certify 90% coverage: 5 < ceil(1/0.1) - 1 = 9.
    tiny = ConformalPredictor(alpha=0.1).fit(make_rounds(5, seed=2))
    check("too-small calibration set abstains", tiny.predict(20, 10)["abstain"], True)

    print("\n-- THE GUARANTEE: coverage >= 1 - alpha --")
    for alpha in (0.05, 0.1, 0.2):
        covs, sizes, absts = [], [], []
        for trial in range(30):
            data = make_rounds(600, seed=100 + trial)
            split = len(data) // 2
            pred = ConformalPredictor(alpha=alpha).fit(data[:split])
            r = pred.evaluate(data[split:])
            covs.append(r["empirical_coverage"])
            sizes.append(r["mean_set_size"])
            absts.append(r["abstention_rate"])
        mean_cov = statistics.mean(covs)
        target = 1 - alpha
        holds = mean_cov >= target - 0.02          # small-sample slack
        print(f"  {'ok  ' if holds else 'FAIL'} alpha={alpha}  target={target:.2f}  "
              f"mean_coverage={mean_cov:.3f}  min={min(covs):.3f}  "
              f"set_size={statistics.mean(sizes):.2f}  abstain={statistics.mean(absts):.2f}")
        if not holds:
            globals()["ok"] = False

    print("\n-- abstention is doing work --")
    data = make_rounds(800, seed=7)
    split = len(data) // 2
    pred = ConformalPredictor(alpha=0.1).fit(data[:split])
    res = pred.evaluate(data[split:])
    # Accuracy on decided rounds should beat the naive point estimate over all
    # rounds; otherwise abstaining buys nothing and the layer is dead weight.
    naive = sum(1 for r in data[split:]
                if pred.predict(r["pro_total"], r["con_total"])["point_estimate"] == r["true_winner"])
    naive_acc = naive / len(data[split:])
    print(f"  selective accuracy {res['selective_accuracy']}  vs  naive point accuracy {naive_acc:.3f}")
    print(f"  abstention rate {res['abstention_rate']}  mean set size {res['mean_set_size']}")
    check("selective accuracy beats naive", res["selective_accuracy"] > naive_acc, True)

    print("\n-- tighter alpha yields wider sets --")
    d = make_rounds(600, seed=11)
    s = len(d) // 2
    strict = ConformalPredictor(alpha=0.01).fit(d[:s]).evaluate(d[s:])
    loose = ConformalPredictor(alpha=0.3).fit(d[:s]).evaluate(d[s:])
    check("alpha=0.01 sets wider than alpha=0.3",
          strict["mean_set_size"] > loose["mean_set_size"], True)
    print(f"       alpha=0.01 size={strict['mean_set_size']} coverage={strict['empirical_coverage']}")
    print(f"       alpha=0.30 size={loose['mean_set_size']} coverage={loose['empirical_coverage']}")

    print("\n-- persistence --")
    import tempfile, os
    path = os.path.join(tempfile.gettempdir(), "argus_conformal_test.json")
    ConformalPredictor(alpha=0.1).fit(make_rounds(100, seed=3)).save(path)
    back = ConformalPredictor.load(path)
    check("round-trips through disk", back is not None and back.n_calibration, 100)
    os.remove(path)

    print("\nPASS" if ok else "\nFAIL")


if __name__ == "__main__":
    main()
