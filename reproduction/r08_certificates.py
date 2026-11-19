"""Export every certificate as a solver-neutral model file (MPS) and re-solve each one, so readers
can re-verify the results with any MIP solver.

Each model uses the sequence-count formulation: integer n_s = number of subjects receiving order s
(per stratum), with period, carry-over, spread, nested and predictability constraints as described
in the paper. A file with an all-zero objective is a feasibility question (expected: infeasible);
a file with an objective is a minimization (expected optimum stated below).

Output: certificates/*.mps, certificates/README.md, results/r08_certificates.csv
"""
import time
from pathlib import Path

import highspy
import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, Config, ilp_spec
from ext_solver import _build
from randomizer import solver as S

OUT = Path(__file__).parent / "certificates"
OUT.mkdir(exist_ok=True)

CASES = [
    # name, config, levels, objective, expected, description
    ("t5n15_carry_spread", "A", {"period": "required", "carryover": "required", "spread": "required"},
     None, "infeasible", "t=5, N=15: period + carry-over balance + perfect spread"),
    ("t5n15_min_spread", "A", {"period": "required", "carryover": "required", "spread": "preferred"},
     "penalty", "optimum 10 (= one spread deviation at weight 10)",
     "t=5, N=15: minimum spread excess with period and carry-over balance"),
    ("t5n15_nested", "A", {"period": "required", "carryover": "required", "nested": "required"},
     None, "infeasible", "t=5, N=15: period + carry-over + nested (prefix) carry-over balance"),
    ("t5n15_min_g3_k2", "A", {"period": "required", "carryover": "required", "predict_w": 1.0,
                              "predict_k": (2,)},
     "penalty", "optimum 10 (G3 after two periods = 10/15)",
     "t=5, N=15: minimum full-list predictability after two observed periods"),
    ("t5n2x15_min_g3_k2", "B", {"period": "required", "carryover": "required", "predict_w": 1.0,
                                "predict_k": (2,)},
     "penalty", "optimum 10 (G3 after two periods = 10/30)",
     "t=5, N=2x15: minimum full-list predictability after two observed periods"),
    ("t4n2x8_min_g3_k2", "C", {"period": "required", "carryover": "required", "predict_w": 1.0,
                               "predict_k": (2,)},
     "penalty", "optimum 11 (G3 after two periods = 11/16)",
     "t=4, N=2x8: minimum full-list predictability after two observed periods"),
    ("t3n9_carry", "E", {"period": "required", "carryover": "required"},
     None, "infeasible", "t=3, N=9: period + carry-over balance (so a carry-over range of 2 is the minimum)"),
    # one stratum of C and of D, for the observer who knows the stratum
    ("t4n8_min_g3_k2", "C1", {"period": "required", "carryover": "required", "predict_w": 1.0,
                              "predict_k": (2,)},
     "penalty", "optimum 7 (G3 after two periods = 7/8)",
     "t=4, N=8 (one stratum of C): minimum full-list predictability after two observed periods"),
    ("t6n10_min_g3_k2", "D1", {"period": "required", "carryover": "required", "predict_w": 1.0,
                               "predict_k": (2,)},
     "penalty", "optimum 6 (G3 after two periods = 6/10)",
     "t=6, N=10 (one stratum of D): minimum full-list predictability after two observed periods"),
]
EXTRA = {"C1": Config("C1", 4, (8,)), "D1": Config("D1", 6, (10,))}


def to_lp(model, cost):
    lb, ub = np.concatenate(model._lb), np.concatenate(model._ub)
    indptr, indices, data = S._csc(np.concatenate(model._ri), np.concatenate(model._rj),
                                   np.concatenate(model._rv), len(model.lo), model.n)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = model.n, len(model.lo)
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = np.asarray(cost, float), lb, ub
    lp.row_lower_, lp.row_upper_ = np.array(model.lo, float), np.array(model.hi, float)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
    lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = indptr, indices, data
    lp.integrality_ = [highspy.HighsVarType.kInteger if v else highspy.HighsVarType.kContinuous
                       for v in np.concatenate(model._int)]
    return lp


def main():
    rows = []
    for name, c, lv, obj, expected, desc in CASES:
        cfg = CONFIGS[c] if c in CONFIGS else EXTRA[c]
        ctx = S._prepare(ilp_spec(cfg, 1, 600, spread=False), np.random.default_rng(1))
        levels = {"period": "off", "carryover": "off", "cooccurrence": "off", "spread": "off",
                  "nested": "off", **lv}
        model, form, _ = _build(ctx, ctx.members, ctx.units, levels)
        cost = model.cost if obj else np.zeros(model.n)
        lp = to_lp(model, cost)
        h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        h.setOptionValue("time_limit", 900.0)
        h.setOptionValue("mip_rel_gap", 0.0)
        h.passModel(lp)
        h.writeModel(str(OUT / f"{name}.mps"))
        t0 = time.time()
        h.run()
        info = h.getInfo()
        status = h.modelStatusToString(h.getModelStatus())
        val = info.objective_function_value if info.primal_solution_status == 2 else None
        rows.append({"file": f"{name}.mps", "question": desc, "expected": expected, "status": status,
                     "objective": val, "dual_bound": info.mip_dual_bound if obj else None,
                     "seconds": round(time.time() - t0, 1), "variables": model.n, "rows": len(model.lo)})
        print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "r08_certificates.csv", index=False)
    lines = ["# Certificates", "",
             "Each file is a mixed-integer model in MPS format. Variables `n_s` count the subjects "
             "receiving each treatment order (per stratum); auxiliary variables are deviation or "
             "maximum variables. Re-solve with any MIP solver and compare with the expected result.",
             "", "| File | Question | Expected | Status (HiGHS " + highspy.Highs().version() + ") | Objective | Seconds |",
             "| --- | --- | --- | --- | --- | --- |"]
    for r in rows:
        lines.append(f"| {r['file']} | {r['question']} | {r['expected']} | {r['status']} | "
                     f"{'' if r['objective'] is None else round(r['objective'], 3)} | {r['seconds']} |")
    (OUT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(df.to_string(index=False))


if __name__ == "__main__":
    main()
