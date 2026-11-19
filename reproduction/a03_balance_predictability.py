"""Balance and predictability of each allocation method (all configurations).

Outputs
  results/balance_per_design.csv     metrics of every design in every pool
  results/balance_summary.csv        mean / SD / share perfect per config x method
  results/predictability.csv         observer guess accuracy by prefix length
  results/ilp_selfreport_check.csv   solver-reported violations vs independent recomputation
  figures/fig_balance.png, figures/fig_predictability.png
"""
import numpy as np
import pandas as pd

from common import (METHOD_SHORT, CONFIGS, METHODS, METHOD_COLORS, METHOD_LABELS, POOLS, RESULTS, FIGURES,
                    design_metrics, guess_accuracy, load_pool, units_of)
import plotstyle as ps


def main():
    rows, pred = [], []
    for c, cfg in CONFIGS.items():
        for m in METHODS:
            designs = load_pool(c, m)
            for i, D in enumerate(designs):
                rows.append({"config": c, "method": m, "design": i, **design_metrics(D, cfg)})
                g = guess_accuracy(D, cfg.t)
                for k in range(cfg.t - 1):
                    pred.append({"config": c, "method": m, "design": i, "known_periods": k + 1,
                                 **{obs: g[obs][k] for obs in g}})
            print(c, m, len(designs), flush=True)
    per = pd.DataFrame(rows)
    per.to_csv(RESULTS / "balance_per_design.csv", index=False)
    pr = pd.DataFrame(pred)
    pr.to_csv(RESULTS / "predictability_per_design.csv", index=False)

    # summary: overall + "worst stratum" metrics
    summ = []
    for (c, m), g in per.groupby(["config", "method"], sort=False):
        cfg = CONFIGS[c]
        strata = [n for n, _ in units_of(cfg)][1:]
        rec = {"config": c, "method": m, "n_designs": len(g)}
        for metric in ("period_dev", "carry_dev", "carry_range", "spread_dev"):
            col = g[f"{metric}[all]"]
            rec[f"{metric}_all_mean"] = col.mean()
            rec[f"{metric}_all_perfect"] = (col == 0).mean() if metric != "carry_range" else (col <= 1).mean()
            if strata:
                worst = g[[f"{metric}[{s}]" for s in strata]].max(axis=1)
                rec[f"{metric}_worststratum_mean"] = worst.mean()
        rec["mi_per_change_mean"] = g.mi_per_change.mean()
        rec["distinct_sequences_mean"] = g.distinct_sequences.mean()
        summ.append(rec)
    summ = pd.DataFrame(summ)
    summ.to_csv(RESULTS / "balance_summary.csv", index=False)

    ps_ = pr.groupby(["config", "method", "known_periods"])[["G1", "G2", "G3", "chance"]].mean().reset_index()
    ps_.to_csv(RESULTS / "predictability.csv", index=False)

    # solver self-report vs independent recomputation
    runs_file = POOLS / "ilp_runs.csv"
    if runs_file.exists():
        runs = pd.read_csv(runs_file)
        chk = []
        for (c, m), g in runs.groupby(["config", "method"]):
            pool = np.load(POOLS / f"{c}_{m}.npz")
            cfg = CONFIGS[c]
            for seed, D in zip(pool["seeds"], pool["designs"]):
                r = g[g.seed == seed].iloc[-1]
                met = design_metrics(D, cfg)
                units = [n for n, _ in units_of(cfg)]
                for crit in ("carryover", "spread"):
                    key = "carry_dev" if crit == "carryover" else "spread_dev"
                    mine = sum(met[f"{key}[{u}]"] for u in units)
                    rep = r.get(f"viol_{crit}")
                    if pd.notna(rep):
                        chk.append({"config": c, "method": m, "seed": seed, "criterion": crit,
                                    "solver_reported": rep, "recomputed": mine})
        chk = pd.DataFrame(chk)
        chk["match"] = np.isclose(chk.solver_reported, chk.recomputed, atol=1e-3)
        chk.to_csv(RESULTS / "ilp_selfreport_check.csv", index=False)
        print("solver self-report matches independent recomputation:",
              f"{chk.match.mean():.1%} of {len(chk)} checks")

    figures(per, ps_)
    print(summ.round(2).to_string(index=False))


def figures(per, pr):
    ps.apply()
    cfgs = list(CONFIGS)
    # --- balance: carry-over range (all + worst stratum) and spread deviation
    fig, axes = ps.plt.subplots(2, len(cfgs), figsize=(3.1 * len(cfgs) + 1, 6.4), sharey="row", squeeze=False)
    for j, c in enumerate(cfgs):
        g = per[per.config == c]
        cfg = CONFIGS[c]
        strata = [n for n, _ in units_of(cfg)][1:]
        cr = g[[f"carry_range[{s}]" for s in ["all"] + strata]].max(axis=1)
        ps.strip(axes[0, j], g.method, cr, METHODS)
        ps.strip(axes[1, j], g.method, g["spread_dev[all]"], METHODS)
        axes[0, j].set_title(f"{c}: {cfg.label.split(' (')[0]}", fontsize=9)
    axes[0, 0].set_ylabel("Carry-over count range\n(max − min, worst unit)")
    axes[1, 0].set_ylabel("Spread deviation\n(all subjects)")
    for ax in axes[1]:
        ax.set_xticks(range(len(METHODS)), [METHOD_SHORT[m] for m in METHODS], rotation=45, ha="right",
                      fontsize=9)
    for ax in axes[0]:
        ax.set_xticks(range(len(METHODS)), [""] * len(METHODS))
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_balance.png", dpi=200)

    # --- predictability curves (G2: per-change table, G3: full design)
    fig, axes = ps.plt.subplots(2, len(cfgs), figsize=(3.1 * len(cfgs) + 1.5, 6.0), sharey=True, squeeze=False)
    for j, c in enumerate(cfgs):
        for i, obs in enumerate(["G2", "G3"]):
            ax = axes[i, j]
            g = pr[pr.config == c]
            for m in METHODS:
                h = g[g.method == m]
                ax.plot(h.known_periods, h[obs], marker="o", ms=4, lw=1.6, color=METHOD_COLORS[m],
                        label=METHOD_LABELS[m])
            ch = g[g.method == METHODS[0]]
            ax.plot(ch.known_periods, ch.chance, color=ps.MUTED, lw=1.2, ls=":", label="Chance")
            ax.set_ylim(0, 1.02)
            ax.set_xticks(ch.known_periods)
            if i == 0:
                ax.set_title(f"{c}: t={CONFIGS[c].t}, N={CONFIGS[c].N}", fontsize=9)
            if i == 1:
                ax.set_xlabel("Periods already observed")
    axes[0, 0].set_ylabel("Guess accuracy\n(knows this change's table)")
    axes[1, 0].set_ylabel("Guess accuracy\n(knows the whole design)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0.07, 1, 1))
    fig.legend(handles, labels, loc="lower center", ncol=len(labels), fontsize=9, frameon=False)
    fig.savefig(FIGURES / "fig_predictability.png", dpi=200)


if __name__ == "__main__":
    main()
