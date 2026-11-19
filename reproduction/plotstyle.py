"""Shared matplotlib style for the analysis figures."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from common import METHOD_COLORS  # noqa: E402

SURFACE, INK, INK2, MUTED, GRID = "#ffffff", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"


def apply():
    plt.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "font.family": "sans-serif", "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 9, "text.color": INK, "axes.labelcolor": INK2, "axes.edgecolor": "#c3c2b7",
        "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 9.5, "axes.titleweight": "bold",
        "axes.titlelocation": "left", "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.6,
        "legend.frameon": False,
    })


def strip(ax, groups, values, order, jitter=0.18, rng=np.random.default_rng(0)):
    """Jittered dots per method plus a mean bar."""
    for i, m in enumerate(order):
        v = np.asarray(values[groups == m], float)
        if not len(v):
            continue
        x = i + rng.uniform(-jitter, jitter, len(v))
        ax.scatter(x, v, s=9, color=METHOD_COLORS[m], alpha=0.55, linewidths=0)
        ax.plot([i - 0.3, i + 0.3], [v.mean()] * 2, color=INK, lw=1.6)
    ax.set_xlim(-0.6, len(order) - 0.4)
