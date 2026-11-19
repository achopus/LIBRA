"""Evaluate the hard rules and an incomplete design.

Cases (the app's own solve(), default settings, 60 s, 24 seeds, one solve per fresh process):
  A0   configuration A without rules (reference for the cost of rules)
  R1   A with two forbidden transitions: HIGH -> OTHER and OTHER -> HIGH
  R2   A with an order rule: HIGH never before LOW (dose escalation); exact period balance is
       then impossible (the app says so), so period balance is set to "preferred"
  R3   incomplete design: t = 6 treatments, p = 4 periods, N = 30, one stratum (co-occurrence balance)
Treatments in A are named VEHICLE, LOW, HIGH, NOMINAL, OTHER (+ fixed MAX in period 6).

Balance is measured against the targets implied by the rules (allowed ordered pairs only).
Randomization space: number of distinct designs (up to the order of subjects) among the 24 runs;
relabelling is disabled by the app whenever rules are present.
Rejection sampling: share of 200 randomizations from each comparison method's pool (configuration
A) that happen to satisfy the rule.

Output: results/r04_rules.csv, results/r04_rules_rejection.csv (printed)
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import math
import multiprocessing as mp

import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, a_efficiency, load_pool

TREAT = ["VEHICLE", "LOW", "HIGH", "NOMINAL", "OTHER"]
SEEDS = range(1, 25)
LIMIT = __import__('common').BENCH_SECONDS


def spec_for(case, seed):
    from randomizer import DesignSpec
    if case == "R3":
        subj = pd.DataFrame({"subject": [f"s{i + 1}" for i in range(30)]})
        return DesignSpec(subjects=subj, treatments=[f"T{i}" for i in range(6)], n_periods=4,
                          min_per_subject=0, max_per_subject=1, seed=seed, time_limit=LIMIT)
    subj = pd.DataFrame({"subject": [f"s{i + 1}" for i in range(15)]})
    kw = {}
    if case == "R1":
        kw["forbidden_transitions"] = [("HIGH", "OTHER"), ("OTHER", "HIGH")]
    if case == "R2":
        # HIGH never before LOW. Exact period balance is impossible with this rule (HIGH can never
        # be given in week 1), as the app reports; we use its suggested fallback.
        kw["order_rules"] = [("LOW", "HIGH")]
        kw["period_balance"] = "preferred"
    return DesignSpec(subjects=subj, treatments=TREAT, n_periods=6, fixed={6: "MAX"},
                      seed=seed, time_limit=LIMIT, **kw)


def task(args):
    case, seed = args
    from randomizer import solve
    res = solve(spec_for(case, seed))
    return {"case": case, "seed": seed, "assign": res.assign, "levels": dict(res.levels),
            "proven": bool(res.proven_optimal), "seconds": None}


def allowed_pairs(case, t):
    pairs = [(a, b) for a in range(t) for b in range(t) if a != b]
    if case == "R1":
        hi, oth = TREAT.index("HIGH"), TREAT.index("OTHER")
        pairs = [q for q in pairs if q not in ((hi, oth), (oth, hi))]
    if case == "R2":
        lo, hi = TREAT.index("LOW"), TREAT.index("HIGH")
        pairs = [q for q in pairs if q != (hi, lo)]   # HIGH directly before LOW is impossible
    return pairs


def band_dev(x, target):
    lo, hi = math.floor(target + 1e-9), math.ceil(target - 1e-9)
    return float(np.clip(np.asarray(x) - hi, 0, None).sum() + np.clip(lo - np.asarray(x), 0, None).sum())


def metrics(case, D):
    t = 6 if case == "R3" else 5
    N, p = D.shape
    out = {}
    pc = np.stack([np.bincount(D[:, k], minlength=t) for k in range(p)])
    out["period_dev"] = band_dev(pc, N / t) if case != "R3" else band_dev(pc, N / t)
    pairs = allowed_pairs(case, t)
    C = np.zeros((t, t), int)
    Cj = np.zeros((p - 1, t, t), int)
    for k in range(p - 1):
        np.add.at(C, (D[:, k], D[:, k + 1]), 1)
        np.add.at(Cj[k], (D[:, k], D[:, k + 1]), 1)
    vals = np.array([C[a, b] for a, b in pairs])
    out["carry_dev"] = band_dev(vals, N * (p - 1) / len(pairs))
    out["carry_range"] = int(vals.max() - vals.min())
    out["spread_dev"] = sum(band_dev([Cj[k, a, b] for a, b in pairs], N / len(pairs)) for k in range(p - 1))
    out["rule_violations"] = int(sum(C[a, b] for a in range(t) for b in range(t)
                                     if a != b and (a, b) not in pairs)) if case in ("R1",) else 0
    if case == "R2":
        lo, hi = TREAT.index("LOW"), TREAT.index("HIGH")
        out["rule_violations"] = int(sum(np.where(r == hi)[0][0] < np.where(r == lo)[0][0] for r in D))
    if case == "R3":
        co = np.zeros((t, t), int)
        for r in D:
            for a in r:
                for b in r:
                    if a < b:
                        co[a, b] += 1
        vals = np.array([co[a, b] for a in range(t) for b in range(a + 1, t)])
        lam = N * p * (p - 1) / (t * (t - 1))
        out["cooc_dev"] = band_dev(vals, lam)
        out["cooc_range"] = int(vals.max() - vals.min())
    else:
        out["eff_M2"] = a_efficiency(D, t, True)[0]
    out["design_key"] = tuple(sorted(map(tuple, D)))
    return out


def rejection():
    """Share of comparison-method randomizations of configuration A that satisfy each rule."""
    rows = []
    for m in ("simple", "latin", "williams", "rerand", "classical", "ilp"):
        try:
            pool = load_pool("A", m)
        except FileNotFoundError:
            continue
        for case in ("R1", "R2"):
            ok = [metrics(case, D)["rule_violations"] == 0 for D in pool]
            rows.append({"method": m, "case": case, "designs": len(pool), "share_satisfying_rule": np.mean(ok)})
    return pd.DataFrame(rows)


def main():
    tasks = [(c, s) for c in ("A0", "R1", "R2", "R3") for s in SEEDS]
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        out = list(pool.imap_unordered(task, tasks, chunksize=1))
    rows = []
    for r in out:
        m = metrics("A0" if r["case"] == "A0" else r["case"], r["assign"])
        rows.append({"case": r["case"], "seed": r["seed"], "proven": r["proven"],
                     **{f"level_{k}": v for k, v in r["levels"].items()}, **m})
    per = pd.DataFrame(rows)
    summ = per.drop(columns=["design_key"]).groupby("case").agg(
        lambda s: s.mean() if s.dtype.kind in "fib" else s.mode().iloc[0])
    summ["distinct_designs"] = per.groupby("case").design_key.nunique()
    summ = summ.drop(columns=["seed"]).reset_index()
    per.drop(columns=["design_key"]).to_csv(RESULTS / "r04_rules.csv", index=False)
    summ.to_csv(RESULTS / "r04_rules_summary.csv", index=False)
    print(summ.round(3).to_string(index=False), flush=True)
    rej = rejection()
    rej.to_csv(RESULTS / "r04_rules_rejection.csv", index=False)
    print(rej.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
