"""Extension 3: sequence predictability for an observer who holds the full allocation list (G3).

The observer knows every row of the allocation list (not which subject has which), watches a
subject's first k treatments and guesses the most common continuation among matching rows.
ext_solver models N * G3_k exactly as a linear term (one variable per prefix).

Variants (both ILP variants use the app's own solve()):
  default   the app's default criteria (spread preferred, full-list criterion off)
  g3first   the app's full-list criterion set to Preferred: after co-occurrence and before spread,
            it minimizes the group-aware observer's correct guesses after 2 observed periods
  williams  stratified Williams squares from the existing pools (reference)

Configurations A-D; 16 seeds; 60 s per design (the app's default); each solve in its own fresh
process (chunksize 1); 6 in parallel.

Proven minima of G3 after two observed periods (x03_g3_bound.py; period + carry-over balance
required, spread off): A 10/15, B 10/30, C 11/16; D not settled within 600 s (bound 6/20).

Outputs results/x03_predict_per_design.csv, results/x03_predict_summary.csv,
        figures/fig_x03_predict.png
"""
import hashlib
import multiprocessing as mp

import numpy as np
import pandas as pd

from common import (BENCH_SECONDS, CONFIGS, FIGURES, RESULTS, WORKERS, a_efficiency, design_metrics,
                    guess_accuracy, ilp_spec, load_pool, units_of)
from a06_randomization_validity import canonical
import plotstyle as ps

SEEDS = range(1, 17)
CFGS = ["A", "B", "C", "D"]
VARIANTS = {"default": "off", "g3first": "preferred"}             # level of the full-list criterion
ORDER = ["williams", "default", "g3first"]
LABELS = {"williams": "Williams squares", "default": "LIBRA (default)", "g3first": "LIBRA, full-list criterion"}
COLORS = {"williams": "#009E73", "default": "#0072B2", "g3first": "#D55E00"}   # Okabe-Ito
PROVEN_MIN_G3_2 = {"A": 10 / 15, "B": 10 / 30, "C": 11 / 16}
TIME_LIMIT = BENCH_SECONDS


def task(args):
    c, variant, seed = args
    from randomizer import solve
    spec = ilp_spec(CONFIGS[c], seed, TIME_LIMIT)
    spec.fulllist_balance = VARIANTS[variant]
    r = solve(spec)
    return {"config": c, "variant": variant, "seed": seed, "assign": r.assign, "seconds": r.solve_seconds,
            "carry_locked": r.levels["carryover"] == "required"}


def group_aware_g3(D, cfg, k=2):
    """Full-list observer who also knows the subject's group, after k observed periods."""
    hits = 0
    for _, rows in (units_of(cfg)[1:] or units_of(cfg)):
        tab = {}
        for r in D[rows]:
            tab.setdefault(tuple(r[:k]), {}).setdefault(int(r[k]), 0)
            tab[tuple(r[:k])][int(r[k])] += 1
        hits += sum(max(v.values()) for v in tab.values())
    return hits / len(D)


def evaluate(c, variant, seed, D, extra):
    cfg = CONFIGS[c]
    units = [n for n, _ in units_of(cfg)]
    m = design_metrics(D, cfg)
    g = guess_accuracy(D, cfg.t)
    return {"config": c, "variant": variant, "seed": seed, **extra,
            "G1_after1": g["G1"][0], "G2_after1": g["G2"][0], "G2_after2": g["G2"][1],
            "G3_after1": g["G3"][0], "G3_after2": g["G3"][1],
            "G3_mean": float(np.mean(g["G3"][: D.shape[1] - 2])),
            "G3g_after2": group_aware_g3(D, cfg),
            "distinct_prefixes_2": len({tuple(r[:2]) for r in D}),
            "spread_dev_total": sum(m[f"spread_dev[{u}]"] for u in units),
            "carry_range_worst": max(m[f"carry_range[{u}]"] for u in units),
            "period_dev_total": sum(m[f"period_dev[{u}]"] for u in units),
            "mi_per_change": m["mi_per_change"], "eff_M2": a_efficiency(D, cfg.t, True)[0],
            "skeleton": hashlib.md5(repr(canonical(D, cfg)).encode()).hexdigest()[:16]}


def main():
    tasks = [(c, v, s) for c in CFGS for v in VARIANTS for s in SEEDS]
    rows = []
    with mp.get_context("spawn").Pool(WORKERS, maxtasksperchild=1) as pool:
        for r in pool.imap_unordered(task, tasks, chunksize=1):
            rows.append(evaluate(r["config"], r["variant"], r["seed"], r["assign"],
                                 {k: r[k] for k in ("seconds", "carry_locked")}))
            print(len(rows), "/", len(tasks), flush=True)
    for c in CFGS:
        for i, D in enumerate(load_pool(c, "williams")[:len(SEEDS)]):
            rows.append(evaluate(c, "williams", i + 1, D, {}))
    per = pd.DataFrame(rows).sort_values(["config", "variant", "seed"])
    per.to_csv(RESULTS / "x03_predict_per_design.csv", index=False)
    num = [c for c in per.columns if c not in ("config", "variant", "seed", "skeleton")]
    summ = per.groupby(["config", "variant"])[num].mean()
    summ["distinct_skeletons"] = per.groupby(["config", "variant"])["skeleton"].nunique()
    summ = summ.reindex([(c, v) for c in CFGS for v in ORDER]).reset_index()
    summ.to_csv(RESULTS / "x03_predict_summary.csv", index=False)
    show = ["config", "variant", "carry_locked", "carry_range_worst", "period_dev_total", "G1_after1",
            "G3_after1", "G3_after2", "G3g_after2", "G3_mean", "distinct_prefixes_2", "spread_dev_total",
            "eff_M2", "distinct_skeletons"]
    print(summ[show].round(3).to_string(index=False))
    figure(per)


def figure(per):
    ps.apply()
    shown = ["williams", "default", "g3first"]
    size = {"williams": 40, "default": 80, "g3first": 30}   # nested rings stay visible when means coincide
    ps.plt.rcParams.update({"font.size": 7.5, "axes.titlesize": 7.5})   # drawn at printed size
    fig, axes = ps.plt.subplots(2, 2, figsize=(6.2, 5.4))
    axes = axes.ravel()
    for ax, c in zip(axes, CFGS):
        g = per[per.config == c]
        for v in shown:
            h = g[g.variant == v]
            ax.scatter(h.G3_after1, h.G3_after2, s=8, alpha=0.35, color=COLORS[v], lw=0)
        for v in sorted(shown, key=lambda v: -size[v]):
            h = g[g.variant == v]
            ax.scatter(h.G3_after1.mean(), h.G3_after2.mean(), s=size[v], color=COLORS[v],
                       edgecolor="white", lw=1.2, zorder=3, label=LABELS[v])
        chance1 = 1 / (CONFIGS[c].t - 1)
        ax.axvline(chance1, color=ps.MUTED, lw=0.8, ls=":")
        if c in PROVEN_MIN_G3_2:
            ax.axhline(PROVEN_MIN_G3_2[c], color=ps.MUTED, lw=1, ls="--")
            ax.annotate("proven minimum" + (" (strata pooled)" if c == "B" else ""), (ax.get_xlim()[0], PROVEN_MIN_G3_2[c]), xytext=(14, 3),
                        textcoords="offset points", fontsize=6.5, color=ps.MUTED)
        cfg = CONFIGS[c]
        ax.set_title(f"{c}: t = {cfg.t}, N = {cfg.N}")
        ax.set_xlabel("Accuracy after 1 observed period")
        ax.set_ylabel("Accuracy after 2 periods")
    handles, labels = axes[0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=7.5, frameon=False)
    fig.savefig(FIGURES / "fig_x03_predict.png", dpi=300)


if __name__ == "__main__":
    main()
