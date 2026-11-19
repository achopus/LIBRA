"""The full-list observer conditional on stratum.

An observer who sees a participant's stratum (for example sex, which is visible) uses only the
rows of that stratum. Its accuracy is the size-weighted mean of the per-stratum G3 values, so its
minimum over designs that are balanced within every stratum is bounded below by the sum of the
per-stratum minima. This script computes the per-stratum minima of G3 after two observed periods,
under the same within-stratum constraints as the tool (period balance and carry-over balance
required, spread off), with the exact linear model of x03_g3_bound:
  t = 5, 15 per stratum  -> identical to configuration A (certificate 10/15, see x03/r08)
  t = 4,  8 per stratum  -> one stratum of C
  t = 6, 10 per stratum  -> one stratum of D (600 s limit; may end with a gap)

Usage: python r13_stratum_g3_bound.py [SECONDS]
Output: results/r13_stratum_g3_bound.txt
"""
import sys
import time

import numpy as np

from common import RESULTS, Config, guess_accuracy, ilp_spec
from ext_solver import _build
from randomizer import solver as S
from x03_g3_bound import solve_with_bound

CASES = [Config("C1", 4, (8,), False, "one stratum of C"), Config("D1", 6, (10,), False, "one stratum of D")]


def run(cfg, limit):
    spec = ilp_spec(cfg, 1, limit, spread=False)
    ctx = S._prepare(spec, np.random.default_rng(1))
    levels = {"period": "required", "carryover": "required", "cooccurrence": "off",
              "spread": "off", "nested": "off", "predict_w": 1.0}
    model, form, _ = _build(ctx, ctx.members, ctx.units, levels)
    cost = model.cost.copy()
    p = form.seqs.shape[1]
    sizes = [len({tuple(s[:k]) for s in form.seqs}) for k in range(1, p - 1)]
    first = int(np.flatnonzero(cost)[0])
    keep = np.zeros_like(cost)
    keep[first + sizes[0]:first + sizes[0] + sizes[1]] = 1.0          # prefixes of length 2 only
    start_rows = S._williams_start(ctx, np.random.default_rng(1))
    x0 = S._complete_solution(model, form, ctx.members, start_rows, 1)
    t0 = time.time()
    x, status, obj, bound = solve_with_bound(model, keep, limit, start=x0)
    line = (f"{cfg.name} (t={cfg.t}, N={cfg.N}, {cfg.label}): status={status} best={obj:.2f} "
            f"bound={bound:.2f} -> G3 after 2 periods: best {obj / cfg.N:.3f}, lower bound "
            f"{bound / cfg.N:.3f}; seconds={time.time() - t0:.0f}")
    if x is not None:
        D = np.vstack([form.extract(x, c) for c in range(len(ctx.members))])
        g = guess_accuracy(D, cfg.t)
        line += f"\n  G3 by k: {np.round(g['G3'], 3)}  G2 by k: {np.round(g['G2'], 3)}"
    return line


def main():
    limit = float(sys.argv[1]) if len(sys.argv) > 1 else 600
    lines = ["t=5, 15 per stratum: identical to configuration A; proven minimum 10/15 (x03_g3_bound, r08)."]
    for cfg in CASES:
        lines.append(run(cfg, limit))
        print(lines[-1], flush=True)
    (RESULTS / "r13_stratum_g3_bound.txt").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
