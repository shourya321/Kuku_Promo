"""Small, dependency-free agreement statistics (written out so every line can be explained)."""
from __future__ import annotations

from itertools import combinations


def ranks(xs: list[float]) -> list[float]:
    """Rank values 1..n; tied values share the average of their ranks (needed for 1-5 scores)."""
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        for k in range(i, j + 1):
            r[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return r


def pearson(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ma, mb = sum(a) / n, sum(b) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    va = sum((x - ma) ** 2 for x in a) ** 0.5
    vb = sum((y - mb) ** 2 for y in b) ** 0.5
    return round(cov / (va * vb), 3) if va and vb else None


def spearman(a: list[float], b: list[float]) -> float | None:
    """Spearman rho = Pearson correlation of the ranks (handles ties correctly)."""
    return pearson(ranks(a), ranks(b))


def kendall_tau(order_a: list[str], order_b: list[str]) -> float:
    """Kendall tau between two orderings of the same ids: +1 identical, -1 reversed."""
    pos_b = {x: i for i, x in enumerate(order_b)}
    conc = disc = 0
    for x, y in combinations(order_a, 2):           # in order_a, x comes before y
        if pos_b[x] < pos_b[y]:
            conc += 1
        else:
            disc += 1
    n = conc + disc
    return round((conc - disc) / n, 3) if n else 1.0


def pair_agreement(a: list[float], b: list[float]) -> dict:
    """Of all clip pairs that BOTH judges separate (no tie in either), in what % do they agree which is better?"""
    agree = total = 0
    for i, j in combinations(range(len(a)), 2):
        da, db = a[i] - a[j], b[i] - b[j]
        if da == 0 or db == 0:
            continue
        total += 1
        agree += (da > 0) == (db > 0)
    return {"pairs_compared": total, "agree_pct": round(100 * agree / total, 1) if total else None}
