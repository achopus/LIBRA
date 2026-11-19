"""Step 3 side question: how low can full-list predictability (G3) go at all?

Exact ILP: period balance and carry-over balance required (as in the app when they are
achievable), spread off, objective = N * sum_k G3_k (k = 1..p-2), via the linear form in
ext_solver._add_predict (one variable per prefix >= every continuation count). Also the variant
that minimizes only G3 after two observed periods (k = 2), the value reported in the paper.
Reports the best design found, its G3 profile and the solver's proven lower bound.

Usage: python x03_g3_bound.py CONFIG MODE SECONDS     (MODE = sum | k2)
       python x03_g3_bound.py                          (every case in RUNS, 600 s each, in parallel)
Output: printed; with no arguments also written to results/x03_g3_bound.txt.
"""
import sys
import time

import highspy
import numpy as np

from common import CONFIGS, guess_accuracy, ilp_spec
from ext_solver import _build
from randomizer import solver as S


def solve_with_bound(model, cost, limit, start=None):
    """Same as randomizer's _Model.solve, but also returns the MIP dual bound."""
    lb, ub = np.concatenate(model._lb), np.concatenate(model._ub)
    indptr, indices, data = S._csc(np.concatenate(model._ri), np.concatenate(model._rj),
                                   np.concatenate(model._rv), len(model.lo), model.n)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = model.n, len(model.lo)
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = np.asarray(cost, float), lb, ub
    lp.row_lower_, lp.row_upper_ = np.array(model.lo, float), np.array(model.hi, float)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = indptr, indices, data
    integ = np.concatenate(model._int)
    lp.integrality_ = [highspy.HighsVarType.kInteger if v else highspy.HighsVarType.kContinuous
                       for v in integ]
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", float(limit))
    h.setOptionValue("mip_rel_gap", 0.0)
    h.passModel(lp)
    if start is not None:
        sol = highspy.HighsSolution()
        sol.col_value = np.asarray(start, float).tolist()
        sol.value_valid = True
        h.setSolution(sol)
    h.run()
    info = h.getInfo()
    x = np.array(h.getSolution().col_value) if info.primal_solution_status == 2 else None
    return x, h.modelStatusToString(h.getModelStatus()), info.objective_function_value, info.mip_dual_bound


def main():
    c, mode, limit = sys.argv[1], sys.argv[2], float(sys.argv[3])
    cfg = CONFIGS[c]
    spec = ilp_spec(cfg, 1, limit, spread=False)
    ctx = S._prepare(spec, np.random.default_rng(1))
    levels = {"period": "required", "carryover": "required", "cooccurrence": "off",
              "spread": "off", "nested": "off", "predict_w": 1.0}
    model, form, _ = _build(ctx, ctx.members, ctx.units, levels)
    cost = model.cost.copy()
    if mode == "k2":
        # keep only the prefix variables of length 2: rebuild costs by counting prefix groups
        p = form.seqs.shape[1]
        sizes = [len({tuple(s[:k]) for s in form.seqs}) for k in range(1, p - 1)]
        first = int(np.flatnonzero(cost)[0])
        keep = np.zeros_like(cost)
        start_k2 = first + sizes[0]
        keep[start_k2:start_k2 + sizes[1]] = 1.0
        cost = keep
    start_rows = S._williams_start(ctx, np.random.default_rng(1))
    x0 = S._complete_solution(model, form, ctx.members, start_rows, 1)
    t0 = time.time()
    x, status, obj, bound = solve_with_bound(model, cost, limit, start=x0)
    print(f"{c} mode={mode}: status={status} best={obj:.2f} bound={bound:.2f} "
          f"(divide by N={cfg.N}) seconds={time.time() - t0:.0f}")
    if x is not None:
        D = np.vstack([form.extract(x, cc) for cc in range(len(ctx.members))])
        g = guess_accuracy(D, cfg.t)
        print("  G3 by k:", np.round(g["G3"], 3), " G2 by k:", np.round(g["G2"], 3),
              " chance:", np.round(g["chance"], 3))


RUNS = [("B", "k2"), ("A", "k2"), ("A", "sum"), ("D", "k2"), ("D", "sum"), ("C", "sum"), ("C", "k2")]


def run_all(limit=600):
    """No arguments: run every case above in parallel (one process each)
    and collect the output in results/x03_g3_bound.txt."""
    import os
    import subprocess
    from pathlib import Path
    here = Path(__file__).resolve().parent
    env = dict(os.environ, PYTHONUNBUFFERED="1")
    procs = [subprocess.Popen([sys.executable, __file__, c, m, str(limit)], cwd=here, env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
             for c, m in RUNS]
    outs = [p.communicate()[0] for p in procs]
    text = "".join(outs)
    print(text)
    (here / "results" / "x03_g3_bound.txt").write_text(text, encoding="utf-8")
    if any(p.returncode for p in procs):
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) == 1:
        run_all()
    else:
        main()
