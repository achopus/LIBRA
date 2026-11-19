"""Step 4 groundwork: when perfect carry-over balance is impossible, does "as balanced as
possible" coincide with "most precise when carry-over is modelled"?

Configuration E (t = 3, N = 9) is small enough to enumerate every design: a design is a multiset
of 9 of the 6 possible orders (2,002 designs). For each: period deviation, carry-over deviation and
range, spread deviation (band definitions as in the tool) and A-efficiency under M1 and M2.

Output: results/x04_enumerate_e.csv and a printed summary.
"""
import itertools

import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, a_efficiency, design_metrics, model_matrix

cfg = CONFIGS["E"]


def estimable(D, t, carryover):
    """All treatment contrasts estimable: each contrast vector lies in the row space of X."""
    X, tr = model_matrix(D, t, carryover)
    B = np.zeros((X.shape[1], t - 1))
    B[tr, :] = np.eye(t - 1)
    P = np.linalg.pinv(X) @ X                       # projector onto the row space
    return bool(np.allclose(P @ B, B, atol=1e-8))


orders = list(itertools.permutations(range(cfg.t)))
rows = []
for combo in itertools.combinations_with_replacement(range(len(orders)), cfg.N):
    D = np.array([orders[i] for i in combo])
    if not estimable(D, cfg.t, True):
        continue                                    # treatment effects not estimable under M2
    m = design_metrics(D, cfg)
    rows.append({"combo": combo, "period_dev": m["period_dev[all]"], "carry_dev": m["carry_dev[all]"],
                 "carry_range": m["carry_range[all]"], "spread_dev": m["spread_dev[all]"],
                 "eff_M1": a_efficiency(D, cfg.t, False)[0], "eff_M2": a_efficiency(D, cfg.t, True)[0]})
df = pd.DataFrame(rows)
df.to_csv(RESULTS / "x04_enumerate_e.csv", index=False)
print("designs with all contrasts estimable under M2:", len(df), "of 2002")
bal = df[df.period_dev == 0]
print("period-balanced designs:", len(bal))
print(bal.groupby(["carry_dev", "carry_range", "spread_dev"]).agg(
    n=("eff_M2", "size"), eff_M1=("eff_M1", "mean"), eff_M2_min=("eff_M2", "min"),
    eff_M2_max=("eff_M2", "max")).round(4).to_string())
print("\nbest M2 overall:", round(df.eff_M2.max(), 4), " among period-balanced:", round(bal.eff_M2.max(), 4))
print(df.sort_values("eff_M2", ascending=False).head(8).round(4).to_string(index=False))
