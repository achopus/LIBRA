"""Case study: the rodent study of the article (30 rats, 2 sexes x 15, five treatments, fixed final MAX week).

Generates the design with the app's defaults (120 s), and compares it with the best of
200 stratified Williams randomizations on balance, predictability and efficiency.

Outputs results/case_study_*.csv, figures/case_*.png, results/case_study_methods.txt
"""
import numpy as np
import pandas as pd

from common import (CONFIGS, FIGURES, RESULTS, a_efficiency, design_metrics, guess_accuracy, ilp_spec,
                    load_pool)
from randomizer import diagnostics as dg
from randomizer import export, plots
from randomizer.runner import solve_isolated

TREATMENTS = ["VEHICLE", "LOW", "HIGH", "NOMINAL", "OTHER"]


def main():
    cfg = CONFIGS["B"]
    spec = ilp_spec(cfg, seed=2026, time_limit=120)
    spec.treatments = TREATMENTS
    spec.subjects = pd.DataFrame({"subject": [f"{s}_{i + 1}" for s in ("male", "female") for i in range(15)],
                                  "sex": ["male"] * 15 + ["female"] * 15})
    spec.strata = ["sex"]
    spec.period_name = "Week"
    res = solve_isolated(spec)
    res.schedule.to_csv(RESULTS / "case_study_schedule.csv", index=False)
    dg.unit_summary(res).to_csv(RESULTS / "case_study_balance.csv", index=False)
    dg.predictability(res).to_csv(RESULTS / "case_study_predictability.csv", index=False)
    (RESULTS / "case_study_methods.txt").write_text(export.methods_text(res), encoding="utf-8")

    williams = load_pool("B", "williams")
    rows = []
    for name, D in [("ILP (case study)", res.assign)] + [(f"Williams #{i}", W) for i, W in enumerate(williams)]:
        m = design_metrics(D, cfg)
        g = guess_accuracy(D, cfg.t)
        rows.append({"design": name, **m, "eff_M1": a_efficiency(D, cfg.t)[0],
                     "eff_M2": a_efficiency(D, cfg.t, True)[0],
                     "G2_after1": g["G2"][0], "G3_after1": g["G3"][0], "G3_after2": g["G3"][1]})
    df = pd.DataFrame(rows)
    comp = pd.concat([df.iloc[[0]].assign(design="ILP (case study)"),
                      df.iloc[1:].mean(numeric_only=True).to_frame().T.assign(design="Williams (mean of 200)"),
                      df.iloc[1:].sort_values(["carry_range[stratum 1]", "spread_dev[all]"]).iloc[[0]]
                        .assign(design="Williams (best of 200)")])
    comp.to_csv(RESULTS / "case_study_vs_williams.csv", index=False)
    print(res.status, res.violations, f"{res.solve_seconds:.0f}s")
    print(comp.T.to_string())

    for name, fig in [("schedule", plots.schedule_figure(res)), ("period", plots.period_balance_figure(res, 1)),
                      ("carryover", plots.carryover_figure(res)), ("changes", plots.changes_figure(res, 1))]:
        fig.savefig(FIGURES / f"case_{name}.png", dpi=200, bbox_inches="tight")


if __name__ == "__main__":
    main()
