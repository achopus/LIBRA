"""Extension 2: nested carry-over balance (robustness to early stopping and dropout).

Nested balance asks that carry-over is balanced not only over the whole schedule but also over
every prefix of it (periods 1-2, 1-3, ..., 1-(p-1)). If the study stops early, or subjects leave
before the end, the periods actually observed are still balanced.

Compared, per configuration A-D (E has a single prefix, already covered by spread):
  williams  Williams-square designs from the existing pools (reference)
  ilp       the research solver with the app's settings (nested off)
  nested    the same with nested balance "preferred" (priority after full carry-over)
24 seeds, 20 s per design, one solve per fresh process, 6 in parallel.

Per design:
  prefix_dev_k      carry-over deviation from the ideal band within the first k periods
                    (summed over all subjects and each stratum), k = 2..p-1
  eff_M1/M2_stop_k  precision if the whole study stopped after period k (k = 3..p-1)
  eff_M1/M2_drop    precision when 20% of subjects drop out after a random period (30 patterns)
  plus the cost side: spread deviation, carry range, predictability (G2, G3), MI, full-data
  efficiency, design skeleton.

Outputs results/x02_nested_per_design.csv, results/x02_nested_summary.csv,
        figures/fig_x02_nested.png
"""
from common import WORKERS  # noqa: E402  (BENCH_WORKERS; also sets one solver thread)
import hashlib
import multiprocessing as mp

import numpy as np
import pandas as pd

from common import (CONFIGS, FIGURES, RESULTS, a_efficiency, band_deviation, design_metrics,
                    guess_accuracy, ilp_spec, load_pool, transitions, units_of)
from a06_randomization_validity import canonical
import plotstyle as ps

SEEDS = range(1, 25)
CFGS = ["A", "B", "C", "D"]
VARIANTS = ["williams", "ilp", "nested"]

N_PATTERNS = 30
DROP_SHARE = 0.2


def task(args):
    c, variant, seed = args
    from ext_solver import Options, solve_ext
    r = solve_ext(ilp_spec(CONFIGS[c], seed, 20), Options(nested="preferred" if variant == "nested" else "off"))
    return {"config": c, "variant": variant, "seed": seed, "assign": r.assign, "seconds": r.seconds,
            "carry_locked": r.levels["carryover"] == "required",
            "nested_locked": r.levels.get("nested") == "required"}


def prefix_devs(D, cfg):
    t, off = cfg.t, ~np.eye(cfg.t, dtype=bool)
    out = {}
    for k in range(2, D.shape[1]):
        out[k] = sum(int(band_deviation(transitions(D[rows], t, range(k - 1))[off],
                                        len(rows) * (k - 1) / (t * (t - 1))).sum())
                     for _, rows in units_of(cfg))
    return out


def dropout_masks(cfg, p, rng):
    """20% of subjects leave after a random period (they keep periods 1..d, d uniform in 1..p-1)."""
    keep = np.ones((cfg.N, p), bool)
    for i in rng.choice(cfg.N, max(1, round(DROP_SHARE * cfg.N)), replace=False):
        keep[i, rng.integers(1, p):] = False
    return keep.ravel()


def evaluate(c, variant, seed, D, extra):
    cfg = CONFIGS[c]
    p = D.shape[1]
    units = [n for n, _ in units_of(cfg)]
    m = design_metrics(D, cfg)
    g = guess_accuracy(D, cfg.t)
    rec = {"config": c, "variant": variant, "seed": seed, **extra,
           "spread_dev_total": sum(m[f"spread_dev[{u}]"] for u in units),
           "carry_range_worst": max(m[f"carry_range[{u}]"] for u in units),
           "period_dev_total": sum(m[f"period_dev[{u}]"] for u in units),
           "mi_per_change": m["mi_per_change"], "G2_after1": g["G2"][0], "G3_after2": g["G3"][1],
           "eff_M1": a_efficiency(D, cfg.t, False)[0], "eff_M2": a_efficiency(D, cfg.t, True)[0],
           "skeleton": hashlib.md5(repr(canonical(D, cfg)).encode()).hexdigest()[:16]}
    pd_ = prefix_devs(D, cfg)
    for k, v in pd_.items():
        rec[f"prefix_dev_{k}"] = v
    rec["prefix_dev_total"] = sum(pd_.values())
    for k in range(3, p):
        rec[f"eff_M1_stop_{k}"] = a_efficiency(D[:, :k], cfg.t, False)[0]
        rec[f"eff_M2_stop_{k}"] = a_efficiency(D[:, :k], cfg.t, True)[0]
    rng = np.random.default_rng(1000 + seed)          # same dropout patterns for every variant
    masks = [dropout_masks(cfg, p, rng) for _ in range(N_PATTERNS)]
    rec["eff_M1_drop"] = float(np.mean([a_efficiency(D, cfg.t, False, keep=k)[0] for k in masks]))
    rec["eff_M2_drop"] = float(np.mean([a_efficiency(D, cfg.t, True, keep=k)[0] for k in masks]))
    return rec


def main():
    tasks = [(c, v, s) for c in CFGS for v in ("ilp", "nested") for s in SEEDS]
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        out = list(pool.imap(task, tasks, chunksize=1))   # chunksize 1: one solve per process
    rows = [evaluate(r["config"], r["variant"], r["seed"], r["assign"],
                     {k: r[k] for k in ("seconds", "carry_locked", "nested_locked")}) for r in out]
    for c in CFGS:
        for i, D in enumerate(load_pool(c, "williams")[:len(SEEDS)]):
            rows.append(evaluate(c, "williams", i + 1, D, {}))
    per = pd.DataFrame(rows).sort_values(["config", "variant", "seed"])
    per.to_csv(RESULTS / "x02_nested_per_design.csv", index=False)

    num = [c for c in per.columns if c not in ("config", "variant", "seed", "skeleton")]
    summ = per.groupby(["config", "variant"], sort=False)[num].mean()
    summ["distinct_skeletons"] = per.groupby(["config", "variant"], sort=False)["skeleton"].nunique()
    summ = summ.reindex([(c, v) for c in CFGS for v in VARIANTS]).reset_index()
    summ.to_csv(RESULTS / "x02_nested_summary.csv", index=False)
    show = ["config", "variant", "carry_locked", "nested_locked", "prefix_dev_total", "carry_range_worst",
            "spread_dev_total", "eff_M2", "eff_M1_drop", "eff_M2_drop", "G2_after1", "G3_after2",
            "distinct_skeletons"]
    print(summ[show].round(3).to_string(index=False))
    stop_cols = [c for c in summ.columns if c.startswith("prefix_dev_") and c != "prefix_dev_total"
                 or "_stop_" in c]
    print(summ[["config", "variant"] + stop_cols].round(3).to_string(index=False))
    figure(per)


def figure(per):
    ps.apply()
    colors = {"williams": "#009E73", "ilp": "#0072B2", "nested": "#D55E00"}   # Okabe-Ito
    labels = {"williams": "Williams squares", "ilp": "ILP (current)", "nested": "ILP + nested balance"}
    fig, axes = ps.plt.subplots(1, 4, figsize=(15, 3.6))
    # panel 1: carry-over imbalance if the study stops after period k (config A and D lines)
    ax = axes[0]
    for c, ls in (("A", "-"), ("D", "--")):
        g = per[per.config == c]
        ks = sorted(int(x.split("_")[-1]) for x in g.columns if x.startswith("prefix_dev_")
                    and x != "prefix_dev_total" and g[x].notna().any())
        for v in VARIANTS:
            ax.plot(ks, [g[g.variant == v][f"prefix_dev_{k}"].mean() for k in ks], ls, marker="o",
                    color=colors[v], label=f"{c}: {labels[v]}" if c == "A" else None)
        ax.annotate(c, (ks[-1], g[f"prefix_dev_{ks[-1]}"].mean()), xytext=(4, 0),
                    textcoords="offset points", fontsize=8, color=ps.MUTED)
    ax.set_xticks(range(2, 6))
    ax.set_xlabel("Study stops after session k")
    ax.set_title("Carry-over imbalance in the\nperiods observed (0 = perfect)")
    ax.legend(fontsize=7)
    # panels 2-4: per-config grouped bars
    x = np.arange(len(CFGS))
    for ax, col, title in ((axes[1], "eff_M2_drop", "Precision with 20% dropout\n(model with carry-over)"),
                           (axes[2], "spread_dev_total", "Spread deviation\n(cost, lower is better)"),
                           (axes[3], "G3_after2", "Two-step guess accuracy\n(cost, lower is better)")):
        for i, v in enumerate(VARIANTS):
            vals = [per[(per.config == c) & (per.variant == v)][col].mean() for c in CFGS]
            ax.bar(x + (i - 1) * 0.27, vals, 0.25, color=colors[v], label=labels[v])
        ax.set_xticks(x, CFGS)
        ax.set_xlabel("Configuration")
        ax.set_title(title)
    lo = per.eff_M2_drop.min()
    axes[1].set_ylim(max(0, lo - 0.05), None)
    fig.tight_layout()
    fig.savefig(FIGURES / "fig_x02_nested.png", dpi=200)


if __name__ == "__main__":
    main()
