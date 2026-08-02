"""Small stats helpers. No third-party dependencies."""

import math

WINNERS = ("pro", "con", "tie")


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def agreement(pred: list[str], gold: list[str]) -> float:
    """Fraction of rounds where the scorer picked the same outcome as the label."""
    if not pred:
        return 0.0
    return sum(1 for p, g in zip(pred, gold) if p == g) / len(pred)


def cohens_kappa(pred: list[str], gold: list[str]) -> float:
    """
    Agreement corrected for chance. 0 means no better than guessing at the base
    rate; raw agreement alone looks impressive when one outcome dominates.
    """
    n = len(pred)
    if n == 0:
        return 0.0
    po = agreement(pred, gold)
    pe = sum(
        (pred.count(c) / n) * (gold.count(c) / n)
        for c in WINNERS
    )
    return 0.0 if pe >= 1.0 else (po - pe) / (1 - pe)


def pearson(xs: list[float], ys: list[float]) -> float:
    """Correlation between scorer margins and label-implied direction."""
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = mean(xs), mean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    return 0.0 if dx == 0 or dy == 0 else num / (dx * dy)


def histogram(values: list[float], lo: float = 0.0, hi: float = 10.0, buckets: int = 10) -> str:
    """One-line ASCII spread. A scorer using its full range looks flat and wide."""
    if not values:
        return "(no data)"
    width = (hi - lo) / buckets
    counts = [0] * buckets
    for v in values:
        idx = min(buckets - 1, max(0, int((v - lo) / width)))
        counts[idx] += 1
    peak = max(counts) or 1
    # ASCII ramp — the Windows console defaults to cp1252 and cannot encode
    # block-drawing characters.
    ramp = " .:-=+*#%@"
    bar = "".join(ramp[min(len(ramp) - 1, round(c / peak * (len(ramp) - 1)))] for c in counts)
    return f"{lo:g}[{bar}]{hi:g}"


def compression(values: list[float], lo: float = 7.0, hi: float = 8.5) -> float:
    """
    Fraction of scores inside the narrow band the old rubric collapsed into.
    High means the scorer is not discriminating, whatever its accuracy looks like.
    """
    if not values:
        return 0.0
    return sum(1 for v in values if lo <= v <= hi) / len(values)
