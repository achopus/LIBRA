"""Correctness checks.

1. Williams squares from the package are period- and carry-over-balanced (t = 2..12).
2. The package's diagnostics agree with the independent metrics in common.py (random designs).
3. Known existence results reproduced with the package's ILP (exact feasibility, HiGHS):
   - row-complete Latin squares (N = t, carry-over balanced) do not exist for t = 3, 5, 7
     but do for t = 2, 4, 6, 8;
   - t = 3 requires an even number of sequence sets (lambda = N/3);
   - t = 5, N = 15 admits perfect first-order carry-over balance (Prescott 1999).
4. Certificates for the motivating case (t = 5, N = 15):
   - carry-over balance + perfect spread is infeasible;
   - with carry-over balance fixed, the minimum spread excess is exactly 1 (proven optimal).
"""
import json
import time
from importlib.metadata import version

import numpy as np
import pandas as pd

from common import RESULTS, Config, design_metrics, ilp_spec, period_counts, transitions
from randomizer import diagnostics as dg
from randomizer import solver as S


def check_williams():
    rows = []
    for t in range(2, 13):
        W = S.williams_square(t)
        pc = period_counts(W, t)
        M = transitions(W, t)
        off = M[~np.eye(t, dtype=bool)]
        rows.append({"t": t, "rows": len(W), "period_balanced": bool(pc.min() == pc.max()),
                     "carryover_balanced": bool(off.min() == off.max()), "pair_count": int(off[0])})
    return pd.DataFrame(rows)


def check_diagnostics(n=500):
    rng = np.random.default_rng(1)
    bad = 0
    for _ in range(n):
        t = int(rng.integers(3, 8))
        N = int(rng.integers(t, 4 * t))
        D = np.stack([rng.permutation(t) for _ in range(N)])
        adj = [(k, k + 1) for k in range(t - 1)]
        a = dg.transition_matrix(D, t, adj)
        b = transitions(D, t)
        c = dg.period_counts(D, t)
        d = period_counts(D, t)
        e = [dg.transition_matrix(D, t, adj, which={j}) for j in range(t - 1)]
        f = [transitions(D, t, [j]) for j in range(t - 1)]
        bad += int(not (np.array_equal(a, b) and np.array_equal(c, d)
                        and all(np.array_equal(x, y) for x, y in zip(e, f))))
    return {"random_designs_checked": n, "mismatches": bad}


def feasibility(t, strata_sizes, levels, time_limit=600, objective=False):
    """Solve the package's ILP with the given criterion levels; return status and design."""
    cfg = Config("tmp", t, tuple(strata_sizes))
    spec = ilp_spec(cfg, seed=1, time_limit=time_limit)
    rng = np.random.default_rng(1)
    ctx = S._prepare(spec, rng)
    model, form, pen = S._build(ctx, ctx.members, ctx.units, levels)
    cost = model.cost if objective else np.zeros(model.n)
    t0 = time.time()
    x, text, proven = model.solve(cost, time_limit, 0.0, 1)
    out = {"status": text, "seconds": round(time.time() - t0, 2), "proven": bool(proven),
           "formulation": form.name}
    if x is not None:
        D = np.vstack([form.extract(x, c) for c in range(len(ctx.members))])
        out["design"] = D
        out["objective"] = float(cost @ x)
        out["penalty_counts"] = S.deviation_counts(x, pen)
    return out


def main():
    report = {"highspy": version("highspy"), "numpy": version("numpy")}
    print("HiGHS (highspy)", report["highspy"])

    W = check_williams()
    print(W.to_string(index=False))
    report["williams_all_balanced"] = bool(W.period_balanced.all() and W.carryover_balanced.all())

    report["diagnostics_cross_check"] = check_diagnostics()
    print("diagnostics cross-check:", report["diagnostics_cross_check"])

    req = {"period": "required", "carryover": "required", "cooccurrence": "off", "spread": "off"}
    rows = []
    for t in range(2, 9):                                    # row-complete Latin squares
        r = feasibility(t, (t,), req, time_limit=900)
        rows.append({"case": f"row-complete Latin square, t={t}", "t": t, "N": t,
                     "expected": "exists" if t % 2 == 0 else "does not exist",
                     "status": r["status"], "seconds": r["seconds"], "formulation": r["formulation"]})
        print(rows[-1], flush=True)
    for lam in range(1, 7):                                  # t = 3, lambda copies
        r = feasibility(3, (3 * lam,), req)
        rows.append({"case": f"t=3, lambda={lam}", "t": 3, "N": 3 * lam,
                     "expected": "exists" if lam % 2 == 0 else "does not exist",
                     "status": r["status"], "seconds": r["seconds"], "formulation": r["formulation"]})
        print(rows[-1], flush=True)
    r = feasibility(5, (15,), req)
    D = r.get("design")
    rows.append({"case": "t=5, N=15 carry-over balance (Prescott 1999)", "t": 5, "N": 15,
                 "expected": "exists", "status": r["status"], "seconds": r["seconds"],
                 "formulation": r["formulation"]})
    if D is not None:
        m = design_metrics(D, Config("A", 5, (15,)))
        report["prescott_design_check"] = {k: m[k] for k in ("period_dev[all]", "carry_range[all]")}
        report["prescott_design"] = D.tolist()

    both = dict(req, spread="required")
    r = feasibility(5, (15,), both)
    rows.append({"case": "t=5, N=15 carry-over balance + perfect spread", "t": 5, "N": 15,
                 "expected": "(new) does not exist", "status": r["status"], "seconds": r["seconds"],
                 "formulation": r["formulation"]})
    r = feasibility(5, (15,), dict(req, spread="preferred"), time_limit=1800, objective=True)
    rows.append({"case": "t=5, N=15 carry-over balance, minimum spread excess", "t": 5, "N": 15,
                 "expected": "(new) minimum = 1", "status": r["status"], "seconds": r["seconds"],
                 "formulation": r["formulation"],
                 "result": json.dumps(r.get("penalty_counts")), "proven": r["proven"]})
    print(rows[-2], rows[-1], sep="\n", flush=True)

    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "verification_existence.csv", index=False)
    W.to_csv(RESULTS / "verification_williams.csv", index=False)
    (RESULTS / "verification.json").write_text(json.dumps(report, indent=1))
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
