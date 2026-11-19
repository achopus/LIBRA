"""Quality checks computed from the final schedule (independent of the solver)."""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .solver import Result


def transition_matrix(assign: np.ndarray, t: int, adj, rows=None, which=None) -> np.ndarray:
    """Count treatment a (row) directly followed by b (column)."""
    A = assign if rows is None else assign[rows]
    M = np.zeros((t, t), dtype=int)
    for j, (k1, k2) in enumerate(adj):
        if which is None or j in which:
            np.add.at(M, (A[:, k1], A[:, k2]), 1)
    return M


def period_counts(assign: np.ndarray, t: int, rows=None) -> np.ndarray:
    """(treatments × randomized periods) count table."""
    A = assign if rows is None else assign[rows]
    out = np.zeros((t, A.shape[1]), dtype=int)
    for k in range(A.shape[1]):
        out[:, k] = np.bincount(A[:, k], minlength=t)
    return out


def best_guess_rate(M: np.ndarray) -> float:
    """Share of transitions predicted correctly by always guessing the most common successor."""
    total = M.sum()
    return float(M.max(axis=1).sum() / total) if total else float("nan")


def mutual_information(M: np.ndarray) -> float:
    total = M.sum()
    if not total:
        return float("nan")
    P = M / total
    E = P.sum(1, keepdims=True) @ P.sum(0, keepdims=True)
    nz = P > 0
    return float((P[nz] * np.log2(P[nz] / E[nz])).sum())


def cooccurrence(assign: np.ndarray, t: int, rows=None) -> np.ndarray:
    A = assign if rows is None else assign[rows]
    has = np.zeros((len(A), t), dtype=int)
    for k in range(A.shape[1]):
        has[np.arange(len(A)), A[:, k]] = 1
    return has.T @ has


def period_deviation(spec, C: np.ndarray, size: int) -> int:
    """Largest distance of a period count from its ideal [floor, ceil] range."""
    t = len(spec.treatments)
    tix = {n: i for i, n in enumerate(spec.treatments)}
    pos = {k + 1: j for j, k in enumerate(spec.randomized_periods)}
    forb = {(pos[k], tix[a]) for a, k in spec.forbidden_periods if k in pos}
    w = np.array([spec.weight(n) for n in spec.treatments])
    worst = 0.0
    for k in range(C.shape[1]):
        allowed = np.array([(k, a) not in forb for a in range(t)])
        target = size * w * allowed / (w * allowed).sum()
        dev = np.maximum(C[:, k] - np.ceil(target - 1e-9), np.floor(target + 1e-9) - C[:, k])
        worst = max(worst, float(dev.clip(min=0).max()))
    return int(worst)


SPREAD = "Spread within each period change"


@dataclass
class Check:
    name: str            # shown to users, in their own words ("Session balance")
    ok: bool
    detail: str
    key: str = ""        # stable English name for code ("Period balance"); defaults to name

    def __post_init__(self):
        self.key = self.key or self.name


def checks(res: Result) -> list[Check]:
    spec, A = res.spec, res.assign
    t, T = len(spec.treatments), spec.treatments
    adj = spec.adjacent_pairs
    out = []

    # per-subject rules
    counts = np.stack([np.bincount(row, minlength=t) for row in A])
    ok = counts.min() >= spec.min_per_subject and counts.max() <= spec.max_per_subject
    one = spec.noun(False)
    if A.shape[1] == 1:
        txt = f"Every {one} receives exactly one treatment."
    elif spec.min_per_subject == spec.max_per_subject == 1:
        txt = f"Every {one} receives every treatment exactly once."
    elif spec.max_per_subject == 1:
        txt = f"Every {one} receives {A.shape[1]} different treatments (none twice)."
    else:
        txt = f"Each treatment given {spec.min_per_subject}–{spec.max_per_subject}× per {one}."
    out.append(Check(f"Per-{one} rule", bool(ok), txt, key="Per-subject rule"))

    bad = []
    tix = {n: i for i, n in enumerate(T)}
    for a, b in spec.forbidden_transitions:
        n = transition_matrix(A, t, adj)[tix[a], tix[b]]
        if n:
            bad.append(f"{a}→{b} ×{n}")
    pos = {k + 1: j for j, k in enumerate(spec.randomized_periods)}
    for a, k in spec.forbidden_periods:
        if k in pos and (A[:, pos[k]] == tix[a]).any():
            bad.append(f"{a} in {spec.period_name} {k}")
    for a, b in spec.order_rules:
        for row in A:
            ia = np.flatnonzero(row == tix[a]); ib = np.flatnonzero(row == tix[b])
            if len(ia) and len(ib) and ia.max() > ib.min():
                bad.append(f"{a} after {b}")
                break
    if spec.forbidden_transitions or spec.forbidden_periods or spec.order_rules:
        out.append(Check("Forbidden patterns", not bad, "None occur." if not bad else "; ".join(bad)))

    # period balance per unit: target share per period follows the allocation ratio
    worst = max(period_deviation(spec, period_counts(A, t, rows), u.size)
                for u, rows in zip(res.units, res.subject_unit_ids))
    out.append(Check(f"{spec.period(cap=True)} balance", worst == 0,
                     f"Every {spec.period()} has each treatment as evenly as possible (exactly "
                     f"equal, or ±1 when not divisible), overall and within every group/block." if worst == 0
                     else f"Some {spec.period()} counts are off by up to {worst:.0f} beyond the ideal.",
                     key="Period balance"))

    # carry-over
    if adj:
        M = transition_matrix(A, t, adj)
        allowed = np.ones((t, t), bool)
        if not (spec.allow_back_to_back and spec.max_per_subject > 1):
            allowed &= ~np.eye(t, dtype=bool)
        for a, b in spec.forbidden_transitions:
            allowed[tix[a], tix[b]] = False
        for a, b in spec.order_rules:
            allowed[tix[b], tix[a]] = False
        vals = M[allowed]
        detail = f"Each treatment is followed by each other (allowed) treatment {vals.min()}–{vals.max()} times"
        worst_range = int(vals.max() - vals.min())
        groups = [(u, rows) for u, rows in zip(res.units, res.subject_unit_ids) if u.kind == "group"]
        if groups and spec.balance_scope == "groups":
            ranges = []
            for u, rows in groups:
                g = transition_matrix(A, t, adj, rows)[allowed]
                ranges.append((int(g.max() - g.min()), u.name, int(g.min()), int(g.max())))
            r, name, lo, hi = max(ranges)
            worst_range = max(worst_range, r)
            detail += (" overall; within every group the counts differ by at most 1" if r <= 1 else
                       f" overall and {lo}–{hi} times in the least even group ({name})")
        detail += "."
        if worst_range > 1 and res.checks.get("carryover") == "impossible":
            even = [v for k, v in res.criteria.items() if k.startswith("carryover")]
            if even and all(v["proven"] for v in even):
                detail += (" Equal counts are impossible under your rules; these counts are as even as the "
                           "rules allow (proven).")
            else:
                detail += (" Equal counts are impossible under your rules; a longer time limit may make "
                           "them more even.")
        out.append(Check("Carry-over balance", bool(worst_range <= 1), detail))
        cap = math.ceil(len(A) / allowed.sum() - 1e-9)
        per = [transition_matrix(A, t, adj, which={j}) for j in range(len(adj))]
        bad = [(j, P) for j, P in enumerate(per) if (P[allowed] > cap).any()]
        if not bad:
            detail = (f"{spec.noun(cap=True)} sharing a treatment always move on to different treatments."
                      if cap == 1 else f"No single switch is made by more than {cap} {spec.noun()} in any "
                                       f"{spec.period()} change.")
        else:
            # the worst case, in words: how many make the same switch, where, and why
            j, P = max(bad, key=lambda jp: jp[1][allowed].max())
            worst = int(P[allowed].max())
            a, b = np.unravel_index(np.argmax(np.where(allowed, P, -1)), P.shape)
            rp = spec.randomized_periods
            k1, k2 = adj[j]
            detail = (f"Up to {worst} {spec.noun()} make the same switch within one {spec.period()} change "
                      f"(ideal: at most {cap}), e.g. {T[a]} → {T[b]} from {spec.period_name} {rp[k1] + 1} to "
                      f"{rp[k2] + 1}. This happens in {len(bad)} of {len(per)} {spec.period()} changes.")
            if spec.spread_balance == "off":
                detail += " Spread was set to Off, so it was not balanced."
            elif res.proven_optimal:
                detail += " With these settings it cannot be avoided entirely."
            else:
                detail += " A longer time limit may reduce it."
        out.append(Check(f"Spread within each {spec.period()} change", not bad, detail, key=SPREAD))

    # co-occurrence (incomplete designs): how often two treatments are given to the same subject
    if spec.max_per_subject == 1 and 2 <= A.shape[1] < t:
        Co = cooccurrence(A, t)
        v = Co[np.triu_indices(t, 1)]
        out.append(Check("Co-occurrence balance", bool(v.max() - v.min() <= 1),
                         f"Every pair of treatments is given to the same {spec.noun(False)} "
                         f"{v.min()}–{v.max()} times."))
    return out


def predictability(res: Result) -> pd.DataFrame:
    spec, A = res.spec, res.assign
    t, adj = len(spec.treatments), spec.adjacent_pairs
    rows = []
    rp = spec.randomized_periods
    for j, (k1, k2) in enumerate(adj):
        M = transition_matrix(A, t, adj, which={j})
        rows.append({"Change": f"{spec.period_name} {rp[k1] + 1} → {rp[k2] + 1}",
                     "Best-guess accuracy": best_guess_rate(M),
                     "Mutual information (bits)": mutual_information(M)})
    M = transition_matrix(A, t, adj)
    rows.append({"Change": "All changes combined", "Best-guess accuracy": best_guess_rate(M),
                 "Mutual information (bits)": mutual_information(M)})
    return pd.DataFrame(rows)


def period_table(res: Result, unit_index: int = 0) -> pd.DataFrame:
    spec = res.spec
    C = period_counts(res.assign, len(spec.treatments), res.subject_unit_ids[unit_index])
    cols = [f"{spec.period_name} {k + 1}" for k in spec.randomized_periods]
    return pd.DataFrame(C, index=spec.treatments, columns=cols)


def transition_table(res: Result, unit_index: int = 0) -> pd.DataFrame:
    spec = res.spec
    M = transition_matrix(res.assign, len(spec.treatments), spec.adjacent_pairs,
                          res.subject_unit_ids[unit_index])
    return pd.DataFrame(M, index=[f"{t} →" for t in spec.treatments], columns=spec.treatments)


def allowed_mask(spec) -> np.ndarray:
    """Which transitions a -> b are possible under the design rules."""
    t = len(spec.treatments)
    tix = {n: i for i, n in enumerate(spec.treatments)}
    M = np.ones((t, t), bool)
    if not (spec.allow_back_to_back and spec.max_per_subject > 1):
        M &= ~np.eye(t, dtype=bool)
    for a, b in spec.forbidden_transitions:
        M[tix[a], tix[b]] = False
    for a, b in spec.order_rules:
        M[tix[b], tix[a]] = False
    return M


def chance_floor(spec) -> float:
    """Accuracy of guessing at random among the allowed successors (not attainable in general)."""
    n = allowed_mask(spec).sum(axis=1)
    n = n[n > 0]
    return float(np.mean(1 / n)) if len(n) else float("nan")


def guess_floor(res: Result, which=None, rows=None) -> float:
    """Lowest best-guess accuracy that any schedule with the same period counts could have.

    Session balance fixes, for every period change, how often each treatment comes before and after
    it (the margins of that change's transition table), and the rules fix which transitions are
    allowed. The smallest possible sum over treatments of the most common successor, given those
    margins, is a small integer program. Its value is a lower bound: no schedule can be less
    predictable, and chance (1 / number of allowed successors) is lower than this whenever the
    margins or the rules force some transitions to be common."""
    from .solver import _Model, INF
    spec, A = res.spec, res.assign
    t, adj = len(spec.treatments), spec.adjacent_pairs
    js = [j for j in range(len(adj)) if which is None or j in which]
    if not js:
        return float("nan")
    allowed = allowed_mask(spec)
    pairs = [(a, b) for a in range(t) for b in range(t) if allowed[a, b]]
    m = _Model()
    total = 0
    Y = {}
    for j in js:
        Mj = transition_matrix(A, t, adj, rows, which={j})
        total += int(Mj.sum())
        v = m.add_vars(len(pairs), integer=True)
        Y[j] = v
        for a in range(t):
            out = [v[q] for q, (x, _) in enumerate(pairs) if x == a]
            into = [v[q] for q, (_, y) in enumerate(pairs) if y == a]
            if out:
                m.add_row(out, 1.0, Mj[a].sum(), Mj[a].sum())
            if into:
                m.add_row(into, 1.0, Mj[:, a].sum(), Mj[:, a].sum())
    top = m.add_vars(t, cost=1.0)
    for q, (a, b) in enumerate(pairs):
        m.add_row(np.r_[top[a], [Y[j][q] for j in js]], np.r_[1.0, -np.ones(len(js))], 0.0, INF)
    x, _, _ = m.solve(m.cost, 10.0, 0.0, 1)
    if x is None or not total:
        return float("nan")
    return float(np.round(x[top]).sum() / total)


def full_list_exposure(res: Result, step: int = 2) -> dict | None:
    """Accuracy of someone who holds the whole list and sees a subject's first `step` treatments,
    guessing the most common continuation among matching rows: pooled over all subjects, and
    within the subject's group (when the list shows groups). None when the design is too short."""
    A = res.assign
    if A.shape[1] < step + 2:
        return None

    def hits(rows):
        tab = {}
        for r in A[rows]:
            key = tuple(r[:step])
            tab.setdefault(key, {}).setdefault(int(r[step]), 0)
            tab[key][int(r[step])] += 1
        return sum(max(c.values()) for c in tab.values())

    n = len(A)
    pooled = hits(np.arange(n)) / n
    groups = [rows for u, rows in zip(res.units, res.subject_unit_ids) if u.kind == "group"]
    aware = sum(hits(rows) for rows in groups) / n if groups else pooled
    return {"pooled": float(pooled), "group_aware": float(aware), "step": step}


def unit_summary(res: Result) -> pd.DataFrame:
    """One row per balance unit (all subjects, each group, each block)."""
    spec, A = res.spec, res.assign
    t, adj = len(spec.treatments), spec.adjacent_pairs
    mask = allowed_mask(spec)
    out = []
    for u, rows in zip(res.units, res.subject_unit_ids):
        C = period_counts(A, t, rows)
        dev = period_deviation(spec, C, u.size)
        row = {"Unit": u.name, spec.noun(cap=True): u.size,
               f"{spec.period(cap=True)} counts (min–max)": f"{C.min()}–{C.max()}",
               f"{spec.period(cap=True)} balance": "as even as possible" if dev == 0 else f"off by {dev}"}
        if adj and u.kind != "block":
            M = transition_matrix(A, t, adj, rows)
            v = M[mask]
            row["Carry-over counts (min–max)"] = f"{v.min()}–{v.max()}"
            row["Best-guess accuracy"] = best_guess_rate(M)
        out.append(row)
    return pd.DataFrame(out)


def sequence_table(res: Result) -> pd.DataFrame:
    T = np.array(res.spec.treatments, dtype=object)
    seqs = [" → ".join(T[row]) for row in res.assign]
    s = pd.Series(seqs).value_counts()
    return pd.DataFrame({"Sequence": s.index, res.spec.noun(cap=True): s.to_numpy()})
