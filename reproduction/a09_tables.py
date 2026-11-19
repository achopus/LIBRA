"""Build markdown tables for RESULTS.md directly from the result CSVs (no hand transcription).

Output results/tables.md
"""
import json

import pandas as pd

from common import CONFIGS, METHOD_LABELS, METHODS, RESULTS

LBL = {m: METHOD_LABELS[m] for m in METHODS}


def md(df, floatfmt="{:.2f}"):
    def fmt(v):
        if isinstance(v, float):
            return floatfmt.format(v)
        return str(v)
    head = "| " + " | ".join(map(str, df.columns)) + " |"
    sep = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows = ["| " + " | ".join(fmt(v) for v in r) + " |" for r in df.itertuples(index=False)]
    return "\n".join([head, sep, *rows])


def by_method(df, value, configs=None, fmt="{:.2f}"):
    t = df.pivot_table(index="method", columns="config", values=value, sort=False)
    t = t.loc[[m for m in METHODS if m in t.index]]
    if configs:
        t = t[configs]
    t.index = [LBL[m] for m in t.index]
    t = t.reset_index().rename(columns={"index": "Method"})
    return md(t, fmt)


def main():
    out = []
    v = pd.read_csv(RESULTS / "verification_existence.csv")
    out += ["## T1 Existence and certificates", md(v[["case", "expected", "status", "seconds"]])]
    j = json.loads((RESULTS / "verification.json").read_text())
    out += [f"HiGHS (highspy) {j['highspy']}; Williams squares t=2..12 balanced: {j['williams_all_balanced']}; "
            f"diagnostics cross-check: {j['diagnostics_cross_check']}"]

    b = pd.read_csv(RESULTS / "balance_summary.csv")
    out += ["## T2 Carry-over count range, worst unit (mean over randomizations; 0 = perfect, 1 = as even as possible)"]
    b["carry_worst"] = b[["carry_range_all_mean", "carry_range_worststratum_mean"]].max(axis=1)
    out += [by_method(b, "carry_worst")]
    out += ["## T3 Period imbalance (mean deviation count, all subjects)", by_method(b, "period_dev_all_mean")]
    out += ["## T4 Spread deviation (all subjects; lower = subjects sharing a treatment diverge more)",
            by_method(b, "spread_dev_all_mean")]
    out += ["## T5 Mutual information between consecutive periods, per change (bits)",
            by_method(b, "mi_per_change_mean", fmt="{:.3f}")]

    p = pd.read_csv(RESULTS / "predictability.csv")
    for obs, title in [("G1", "pooled transition table"), ("G2", "transition table of that change"),
                       ("G3", "complete allocation list")]:
        for k in (1, 2):
            q = p[p.known_periods == k]
            out += [f"## T6 Guess accuracy, observer knows {title}, after {k} observed period(s)",
                    by_method(q, obs, fmt="{:.3f}")]
            if obs == "G1":
                ch = q[q.method == "simple"].set_index("config")["chance"]
                out += ["Chance: " + ", ".join(f"{c} {ch[c]:.3f}" for c in ch.index)]

    e = pd.read_csv(RESULTS / "efficiency_per_design.csv")
    em = e.groupby(["config", "method"], sort=False).mean(numeric_only=True).reset_index()
    for col, title in [("eff_M1", "model without carry-over"), ("eff_M2", "model with carry-over"),
                       ("eff_M1_last20", "20% miss last period"), ("eff_M1_random10", "10% observations missing"),
                       ("eff_M1_drop1", "one subject per stratum leaves halfway")]:
        out += [f"## T7 Efficiency ({title})", by_method(em, col, fmt="{:.3f}")]

    s = pd.read_csv(RESULTS / "simulation.csv", keep_default_na=False)
    for sc, col, title in [("no_effect", "reject_F", "Type I error, global F (nominal 0.05; MCSE 0.005)"),
                           ("effect", "reject_F", "Power, global F (dose-response, 1 SD)"),
                           ("effect", "emp_se", "Empirical SE of high-vs-vehicle contrast"),
                           ("carry_unmodelled", "bias", "Bias with unmodelled carry-over (true theta = 1)"),
                           ("carry_modelled", "emp_se", "Empirical SE with carry-over modelled"),
                           ("effect", "coverage", "Coverage of 95% CI")]:
        out += [f"## T8 {title}", by_method(s[s.scenario == sc], col, fmt="{:.3f}")]

    pt = pd.read_csv(RESULTS / "validity_permutation_tests.csv")
    out += ["## T9 Permutation tests (rejection rate at 0.05; 1000 datasets; MCSE ~0.007 under null)",
            md(pt.pivot_table(index=["config", "scenario"], columns="reference", values="rejection_rate")
               .reset_index(), "{:.3f}")]
    ex = pd.read_csv(RESULTS / "validity_exchangeability.csv")
    out += ["## T10 Exchangeability (Monte Carlo p-values; large = consistent with exact symmetry)",
            md(ex.pivot_table(index="method", columns="config", values="mc_p_value").reset_index(), "{:.3f}")]
    rep = RESULTS / "validity_exchangeability_replication.csv"
    if rep.exists():
        out += ["Replication on fresh pools (120 designs, new seeds):",
                md(pd.read_csv(rep)[["config", "method", "designs", "mc_p_value"]], "{:.3f}")]
    dv = pd.read_csv(RESULTS / "validity_diversity.csv")
    out += ["## T11 Distinct design skeletons among 60 randomizations (up to relabelling/re-ordering)",
            by_method(dv, "distinct_skeletons", fmt="{:.0f}")]
    un = pd.read_csv(RESULTS / "validity_uniformity.csv")
    out += ["## T12 Uniformity among all optimal designs (exhaustive enumeration, 300 seeds)",
            md(un, "{:.3f}")]

    sc = RESULTS / "scalability.csv"
    if sc.exists():
        d = pd.read_csv(sc)
        out += ["## T13 Scalability (60 s limit)",
                md(d[["t", "N", "strata", "seconds", "proven_optimal", "formulation", "level_carryover",
                      "level_spread", "period_dev", "carry_range_worst", "spread_dev_all"]], "{:.1f}")]
    cs = pd.read_csv(RESULTS / "case_study_vs_williams.csv")
    keep = ["design", "carry_range[stratum 1]", "carry_range[stratum 2]", "carry_range[all]", "spread_dev[all]",
            "spread_dev[stratum 1]", "mi_per_change", "eff_M2", "G2_after1", "G3_after2"]
    out += ["## T14 Case study vs Williams (200 randomizations)", md(cs[keep], "{:.3f}")]
    (RESULTS / "tables.md").write_text("\n\n".join(out) + "\n", encoding="utf-8")
    print("wrote results/tables.md")


if __name__ == "__main__":
    main()
