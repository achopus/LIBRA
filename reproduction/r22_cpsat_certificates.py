"""Verify every certificate with an independent, exact solver.

HiGHS works in floating point with tolerances. Here each model file (certificates/*.mps)
is re-solved with Google OR-Tools CP-SAT, a constraint-programming / SAT solver that shares no code
with HiGHS and works in exact integer arithmetic. The files are read with highspy only to parse the
MPS format; the CP-SAT model is built from the parsed arrays. Every coefficient and bound in these
files is an integer (checked below). The continuous variables (deviation and observer variables)
are declared integer for CP-SAT; this cannot change the answer, because each is bounded below only
by integer-valued expressions and is minimized, so an optimal solution with integer values always
exists (and a feasibility model has no such variables at all).

Output: results/r22_cpsat_certificates.csv
"""
import time
from pathlib import Path

import highspy
import numpy as np
import pandas as pd

from common import RESULTS

CERTS = Path(__file__).parent / "certificates"
BIG = 10 ** 6
LIMIT = 3600.0


def integral(a):
    a = np.asarray(a, float)
    finite = np.isfinite(a) & (np.abs(a) < 1e20)
    return bool(np.all(np.abs(a[finite] - np.round(a[finite])) < 1e-9))


def solve_file(path):
    from ortools.sat.python import cp_model
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.readModel(str(path))
    lp = h.getLp()
    n, m = lp.num_col_, lp.num_row_
    start, index, value = (np.array(lp.a_matrix_.start_), np.array(lp.a_matrix_.index_),
                           np.array(lp.a_matrix_.value_, float))
    cost = np.array(lp.col_cost_, float)
    clo, chi = np.array(lp.col_lower_, float), np.array(lp.col_upper_, float)
    rlo, rhi = np.array(lp.row_lower_, float), np.array(lp.row_upper_, float)
    ok = all(integral(a) for a in (value, cost, clo, chi, rlo, rhi))
    if lp.a_matrix_.format_ != highspy.MatrixFormat.kColwise:
        raise ValueError("expected a column-wise matrix")
    rows = [[] for _ in range(m)]
    for j in range(n):
        for p in range(start[j], start[j + 1]):
            rows[index[p]].append((j, int(round(value[p]))))
    md = cp_model.CpModel()
    big = lambda v, s: int(round(v)) if np.isfinite(v) and abs(v) < 1e20 else s * BIG   # noqa: E731
    x = [md.NewIntVar(big(clo[j], -1), big(chi[j], 1), f"x{j}") for j in range(n)]
    for i, terms in enumerate(rows):
        expr = sum(c * x[j] for j, c in terms)
        if np.isfinite(rlo[i]) and rlo[i] > -1e20:
            md.Add(expr >= int(round(rlo[i])))
        if np.isfinite(rhi[i]) and rhi[i] < 1e20:
            md.Add(expr <= int(round(rhi[i])))
    has_obj = bool(np.any(cost != 0))
    if has_obj:
        md.Minimize(sum(int(round(c)) * x[j] for j, c in enumerate(cost) if c))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = LIMIT
    solver.parameters.num_workers = 8
    t0 = time.time()
    st = solver.Solve(md)
    name = solver.StatusName(st)
    obj = solver.ObjectiveValue() if has_obj and st in (cp_model.OPTIMAL, cp_model.FEASIBLE) else None
    return {"file": path.name, "integer_data": ok, "variables": n, "rows": m, "cpsat_status": name,
            "cpsat_objective": obj, "cpsat_bound": solver.BestObjectiveBound() if has_obj else None,
            "seconds": round(time.time() - t0, 1)}


def main():
    ref = pd.read_csv(RESULTS / "r08_certificates.csv").set_index("file") \
        if (RESULTS / "r08_certificates.csv").exists() else None
    out = []
    for path in sorted(CERTS.glob("*.mps")):
        r = solve_file(path)
        if ref is not None and path.name in ref.index:
            r["highs_status"] = ref.loc[path.name, "status"]
            r["highs_objective"] = ref.loc[path.name, "objective"]
            hs, ho = str(r["highs_status"]), r["highs_objective"]
            if r["cpsat_status"] == "INFEASIBLE":
                r["agrees"] = "nfeasible" in hs
            elif r["cpsat_status"] == "OPTIMAL":
                r["agrees"] = pd.notna(ho) and abs(float(ho) - float(r["cpsat_objective"] or 0)) < 1e-6
            else:
                r["agrees"] = None
        print(r, flush=True)
        out.append(r)
    pd.DataFrame(out).to_csv(RESULTS / "r22_cpsat_certificates.csv", index=False)


if __name__ == "__main__":
    main()
