"""Reference values and harmonized sums.

(1) Lower bound on the per-change mutual information between consecutive treatments, given period
    balance: H(next) = log2 t (uniform), and H(next | current) is at most the entropy of the n = N/t
    subjects sharing a current treatment spread as evenly as possible over the t - 1 others.
    Compared with the ILP and with simple randomization (the "chance" reference).
(2) Share of ILP randomizations reaching the proven minimum spread deviation (configuration A: 1).
(3) Spread deviation and period imbalance summed over all units (all subjects + each stratum), the
    definition used in the result tables, for every method.
(4) Spread of A-efficiency across randomizations (SD, min, max).

Output: results/r09_reference_values.csv, results/r09_balance_units.csv, results/r09_eff_spread.csv
"""
import numpy as np
import pandas as pd

from common import CONFIGS, RESULTS, units_of


def even_entropy(n, k):
    """Entropy (bits) of n items spread as evenly as possible over k bins."""
    base, extra = divmod(n, k)
    counts = np.array([base + 1] * extra + [base] * (k - extra), float)
    counts = counts[counts > 0]
    p = counts / n
    return float(-(p * np.log2(p)).sum())


def main():
    bal = pd.read_csv(RESULTS / "balance_per_design.csv")
    ref = []
    for c, cfg in CONFIGS.items():
        n = cfg.N / cfg.t
        if abs(n - round(n)) < 1e-9:
            bound = np.log2(cfg.t) - even_entropy(int(round(n)), cfg.t - 1)
        else:
            bound = np.nan
        g = bal[bal.config == c].groupby("method")
        units = [u for u, _ in units_of(cfg)]
        a = bal[(bal.config == c) & (bal.method == "ilp")]
        ref.append({"config": c, "mi_lower_bound": bound,
                    "mi_ilp": g.mi_per_change.mean()["ilp"], "mi_simple": g.mi_per_change.mean()["simple"],
                    "share_ilp_at_min_spread": float((a["spread_dev[all]"] == a["spread_dev[all]"].min()).mean()),
                    "min_spread_seen": a["spread_dev[all]"].min()})
    pd.DataFrame(ref).to_csv(RESULTS / "r09_reference_values.csv", index=False)
    print(pd.DataFrame(ref).round(3).to_string(index=False))

    rows = []
    for c, cfg in CONFIGS.items():
        units = [u for u, _ in units_of(cfg)]
        g = bal[bal.config == c].copy()
        g["spread_units"] = g[[f"spread_dev[{u}]" for u in units]].sum(1)
        g["period_units"] = g[[f"period_dev[{u}]" for u in units]].sum(1)
        s = g.groupby("method")[["spread_units", "period_units"]].mean()
        for m, r in s.iterrows():
            rows.append({"config": c, "method": m, **r.round(2).to_dict()})
    pd.DataFrame(rows).to_csv(RESULTS / "r09_balance_units.csv", index=False)
    print(pd.DataFrame(rows).pivot(index="method", columns="config", values="spread_units").to_string())
    print(pd.DataFrame(rows).pivot(index="method", columns="config", values="period_units").to_string())

    eff = pd.read_csv(RESULTS / "efficiency_per_design.csv")
    es = eff.groupby(["config", "method"]).eff_M2.agg(["mean", "std", "min", "max"]).round(4).reset_index()
    es.to_csv(RESULTS / "r09_eff_spread.csv", index=False)


if __name__ == "__main__":
    main()
