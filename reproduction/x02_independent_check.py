"""Independent check (no randomizer code) of the step-2 infeasibility result.

Config A: t=5 treatments, N=15 subjects, every subject gets each treatment once (5 periods).
Question: is there a design with
  - period balance: each treatment exactly 3 times in each period,
  - full carry-over balance: each ordered pair (a, b), a != b, exactly 3 times over the 4 changes,
  - nested balance: over the first m changes (m = 1, 2, 3) each pair occurs
    floor(15m/20) or ceil(15m/20) times?
Variables: n_s = number of subjects receiving permutation s (120 integer variables).
The control (nested off) must be feasible; the test (nested on) is reported.

Output: results/x02_independent_check.txt (printed; redirect it there)
"""
import itertools
import math
import time

import highspy
import numpy as np

t, N = 5, 15
perms = list(itertools.permutations(range(t)))
S = len(perms)
pairs = [(a, b) for a in range(t) for b in range(t) if a != b]


def check(nested):
    rows, lo, hi = [], [], []

    def add(coefs, l, h):
        rows.append(coefs)
        lo.append(l)
        hi.append(h)

    add(np.ones(S), N, N)
    for k in range(t):
        for a in range(t):
            add(np.array([s[k] == a for s in perms], float), N / t, N / t)
    for a, b in pairs:
        cnt = [np.array([s[j] == a and s[j + 1] == b for s in perms], float) for j in range(t - 1)]
        add(sum(cnt), 3, 3)
        for m in (range(1, t - 1) if nested else []):
            target = N * m / len(pairs)
            add(sum(cnt[:m]), math.floor(target), math.ceil(target))

    A = np.array(rows)
    nz = np.nonzero(A)
    lp = highspy.HighsLp()
    lp.num_col_, lp.num_row_ = S, len(rows)
    lp.col_cost_, lp.col_lower_, lp.col_upper_ = np.zeros(S), np.zeros(S), np.full(S, N, float)
    lp.row_lower_, lp.row_upper_ = np.array(lo, float), np.array(hi, float)
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.a_matrix_.start_ = np.r_[0, np.cumsum((A != 0).sum(1))].astype(np.int32)
    lp.a_matrix_.index_ = nz[1].astype(np.int32)
    lp.a_matrix_.value_ = A[nz]
    lp.integrality_ = [highspy.HighsVarType.kInteger] * S
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("time_limit", 600.0)
    h.passModel(lp)
    t0 = time.time()
    h.run()
    print(f"nested balance {'on ' if nested else 'off'}:", h.modelStatusToString(h.getModelStatus()),
          f"{time.time() - t0:.1f}s")


if __name__ == "__main__":
    check(False)   # control: must be feasible (carry-over balanced designs for t=5, N=15 exist)
    check(True)
