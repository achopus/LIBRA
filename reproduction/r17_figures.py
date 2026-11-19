"""The balance and predictability figures, with the comparators and definitions of the result tables
(spread deviation summed over all units, carry-over range in the worst unit) and psychology terms
(participants, conditions, sessions, groups).

Inputs: results/r16_per_design.csv (balance figure); G2 and G3 for every observation point are
computed here from the pools (predictability figure).
Output: figures/fig_balance.png, figures/fig_predictability.png, results/r17_predictability_curves.csv
"""
import numpy as np
import pandas as pd

import plotstyle as ps
from common import CONFIGS, FIGURES, RESULTS, guess_accuracy, load_pool

ORDER = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "sa_ws", "ilp_nospread", "ilp"]
SHORT = {"simple": "Simple", "latin": "Latin squares", "williams": "Williams", "williams_best": "Williams, best of 500",
         "rerand": "Rerandomization", "classical": "Best classical", "sa": "SA, random start",
         "sa_ws": "SA, Williams start", "ilp_nospread": "LIBRA, no spread", "ilp": "LIBRA"}
LONG = {"simple": "Simple randomization", "latin": "Random Latin squares", "williams": "Williams squares",
        "williams_best": "Williams squares, best of 500",
        "rerand": "Rerandomization", "classical": "Best classical design", "sa": "Annealing, random start",
        "sa_ws": "Annealing, Williams start", "ilp_nospread": "LIBRA without spread", "ilp": "LIBRA"}
# Figures are drawn at their printed size (text width about 6.3 in), so the font sizes below are
# the sizes on the page.
WIDTH = 7.0
FONT = 7.5
COLORS = {"simple": "#56B4E9", "latin": "#E69F00", "williams": "#009E73", "williams_best": "#7FC9B0", "rerand": "#D55E00",
          "classical": "#000000", "sa": "#B3B3B3", "sa_ws": "#6E6E6E", "ilp_nospread": "#CC79A7",
          "ilp": "#0072B2"}
ps.METHOD_COLORS.update(COLORS)


def title(c):
    cfg = CONFIGS[c]
    g = len(cfg.strata_sizes)
    grp = "" if g == 1 else f" ({g}×{cfg.strata_sizes[0]})"
    return f"{c}: t = {cfg.t}, N = {cfg.N}{grp}"


def hstrip(ax, values_by_method, order, rng):
    """Horizontal strip plot: one row per method (top to bottom), jittered dots and a mean bar."""
    for i, m in enumerate(order):
        v = values_by_method.get(m)
        if v is None or not len(v):
            continue
        y = i + rng.uniform(-0.18, 0.18, len(v))
        ax.scatter(v, y, s=5, color=COLORS[m], alpha=0.5, linewidths=0)
        ax.plot([np.mean(v)] * 2, [i - 0.32, i + 0.32], color=ps.INK, lw=1.3)
    ax.set_ylim(len(order) - 0.5, -0.5)
    ax.grid(axis="x", color=ps.GRID, lw=0.5)
    ax.grid(axis="y", visible=False)


def fig_balance():
    per = pd.read_csv(RESULTS / "r16_per_design.csv")
    cfgs = list(CONFIGS)
    rng = np.random.default_rng(0)
    fig, axes = ps.plt.subplots(2, len(cfgs), figsize=(WIDTH, 5.6), sharey=True, squeeze=False)
    for j, c in enumerate(cfgs):
        g = per[per.config == c]
        for i, col in enumerate(("carry_range", "spread_dev")):
            ax = axes[i, j]
            hstrip(ax, {m: g[g.method == m][col].to_numpy(float) for m in ORDER}, ORDER, rng)
            ax.tick_params(labelsize=FONT - 0.5)
            ax.set_xlim(left=-0.05 * max(1.0, g[col].max()))
        axes[0, j].set_title(title(c), fontsize=FONT)
    axes[0, 0].set_yticks(range(len(ORDER)), [SHORT[m] for m in ORDER], fontsize=FONT)
    axes[1, 0].set_yticks(range(len(ORDER)), [SHORT[m] for m in ORDER], fontsize=FONT)
    fig.text(0.6, 0.505, "Carry-over range in the worst stratum (0 = perfect)", ha="center", fontsize=FONT)
    fig.text(0.6, 0.01, "Spread deviation, summed over all subjects and strata", ha="center", fontsize=FONT)
    fig.tight_layout(rect=(0, 0.03, 1, 1), h_pad=2.2)
    fig.savefig(FIGURES / "fig_balance.png", dpi=300)


def curves():
    rows = []
    for c, cfg in CONFIGS.items():
        for m in ORDER:
            try:
                pool = load_pool(c, m)
            except FileNotFoundError:
                continue
            acc = np.array([[guess_accuracy(D, cfg.t)[g] for g in ("G2", "G3", "chance")] for D in pool])
            for k in range(acc.shape[2]):
                rows.append({"config": c, "method": m, "known_sessions": k + 1, "G2": acc[:, 0, k].mean(),
                             "G3": acc[:, 1, k].mean(), "chance": acc[:, 2, k].mean()})
        print(c, flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "r17_predictability_curves.csv", index=False)
    return df


def fig_predictability(pr):
    shown = ["simple", "williams", "williams_best", "rerand", "classical", "sa_ws", "ilp_nospread", "ilp"]
    # E is left out, as in the balance table: with three conditions only one observation point is informative.
    cfgs = [c for c in CONFIGS if CONFIGS[c].t > 3]
    # The last observation point is left out: with all but one condition seen, the last one is known
    # (accuracy 1 for every method), and the common end point pulls all lines together.
    pr = pr[pr.known_sessions < pr.groupby("config").known_sessions.transform("max")]
    fig, axes = ps.plt.subplots(2, len(cfgs), figsize=(WIDTH, 4.9), sharey="row", squeeze=False)
    for j, c in enumerate(cfgs):
        g = pr[pr.config == c]
        for i, obs in enumerate(["G2", "G3"]):
            ax = axes[i, j]
            for m in shown:
                h = g[g.method == m]
                if len(h):
                    ax.plot(h.known_sessions, h[obs], marker="o", ms=3 if m == "ilp" else 2.5,
                            lw=1.6 if m == "ilp" else 1.0,
                            color=COLORS[m], label=LONG[m], ls="--" if m == "classical" else "-",
                            zorder=3 if m == "ilp" else 2)
            ch = g[g.method == "simple"]
            ax.plot(ch.known_sessions, ch.chance, color=ps.MUTED, lw=1.0, ls=":", marker="_" if len(ch) == 1 else None,
                    ms=8, label="Chance")
            ax.set_xticks(ch.known_sessions)
            lo, hi = ch.known_sessions.min(), ch.known_sessions.max()
            ax.set_xlim(lo - 0.3, hi + 0.3)
            ax.tick_params(labelsize=FONT - 0.5)
            if i == 0:
                ax.set_title(title(c), fontsize=FONT)
            else:
                ax.set_xlabel("Periods observed", fontsize=FONT)
    axes[0, 0].set_ylabel("Accuracy, knows the plan\nfor this change (G2)", fontsize=FONT)
    axes[1, 0].set_ylabel("Accuracy, holds\nthe full list (G3)", fontsize=FONT)
    for i, obs in enumerate(["G2", "G3"]):
        vals = pd.concat([pr[obs], pr.chance])[pr.config.isin(cfgs).tolist() * 2].round(6)
        axes[i, 0].set_ylim(np.floor(vals.min() * 10) / 10 - 0.02, min(1.02, np.ceil(vals.max() * 10) / 10 + 0.02))
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.tight_layout(rect=(0, 0.11, 1, 1))
    fig.legend(handles, labels, loc="lower center", ncol=3, fontsize=FONT, frameon=False)
    fig.savefig(FIGURES / "fig_predictability.png", dpi=300)


if __name__ == "__main__":
    import sys
    ps.apply()
    if "--predictability-only" in sys.argv:     # redraw the predictability figure from the saved curves
        fig_predictability(pd.read_csv(RESULTS / "r17_predictability_curves.csv"))
    else:
        fig_balance()
        fig_predictability(curves())
