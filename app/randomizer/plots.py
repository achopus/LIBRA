"""Figures for biologists / clinicians (matplotlib)."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Patch

from .diagnostics import allowed_mask, best_guess_rate, period_counts, transition_matrix
from .solver import Result

SURFACE, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
# colorblind-checked categorical palette (fixed order); MAX-like fixed labels use neutral grey
PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
DARK_TEXT_ON = {"#eda100"}
NEUTRAL, OVERFLOW = "#c3c2b7", "#9ec5f4"
BLUES = LinearSegmentedColormap.from_list(          # warm ramp of the LIBRA logo (name kept)
    "libra", ["#fff5ee", "#fdd5b4", "#f9a465", "#f26a1a", "#d6301c", "#9e0a1f"])

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10, "text.color": INK, "axes.labelcolor": INK2,
    "xtick.color": INK2, "ytick.color": INK2, "axes.titlesize": 12,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
})


def treatment_colors(spec) -> dict[str, tuple[str, str]]:
    """label -> (fill, text color). More than 8 treatments share one fill (labels carry identity)."""
    out = {}
    many = len(spec.treatments) > len(PALETTE)
    for i, name in enumerate(spec.treatments):
        fill = OVERFLOW if many else PALETTE[i]
        out[name] = (fill, INK if fill in DARK_TEXT_ON or many else "#ffffff")
    for lab in spec.fixed.values():
        out.setdefault(lab, (NEUTRAL, INK))
    return out


def _clean(ax):
    ax.tick_params(length=0)
    for s in ax.spines.values():
        s.set_visible(False)


def save_png(res: Result, folder, stem: str, schedule: bool = True, balance: bool = False,
             dpi: int = 300) -> list:
    """Schedule grid (every subject) and, optionally, a balance overview. Returns the paths."""
    from pathlib import Path
    out = []
    if schedule:
        fig = schedule_figure(res, max_subjects=None)
        p = Path(folder) / f"{stem}_schedule.png"
        fig.savefig(p, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        out.append(p)
    if balance:
        figs = [period_balance_figure(res)]
        if res.spec.adjacent_pairs:
            figs.append(carryover_figure(res))
        for i, fig in enumerate(figs):
            p = Path(folder) / f"{stem}_balance{'' if i == 0 else '_carryover'}.png"
            fig.savefig(p, dpi=dpi, bbox_inches="tight")
            plt.close(fig)
            out.append(p)
    return out


MAX_SCREEN_PIXELS = 30_000_000       # per picture shown in the app (a very long schedule at 300 dpi is huge)


def screen_dpi(fig, dpi: int) -> int:
    """The requested resolution, lowered only if the picture would be too large to show."""
    w, h = fig.get_size_inches()
    return int(max(72, min(dpi, (MAX_SCREEN_PIXELS / max(1e-6, w * h)) ** 0.5)))


def figure_png(fig, dpi: int = 110) -> bytes:
    """Render a figure to PNG bytes (for display in the app) and close it."""
    import io
    buf = io.BytesIO()
    fig.savefig(buf, dpi=dpi, bbox_inches="tight", format="png")
    plt.close(fig)
    return buf.getvalue()


def schedule_figure(res: Result, max_subjects: int | None = 80):
    spec = res.spec
    df = res.schedule if max_subjects is None else res.schedule.head(max_subjects)
    n, P = len(df), len(res.period_columns)
    colors = treatment_colors(spec)
    fig, ax = plt.subplots(figsize=(1.5 + 1.3 * P, 1.2 + 0.36 * n))
    for r in range(n):
        for k, col in enumerate(res.period_columns):
            lab = str(df[col].iloc[r])
            fill, ink = colors.get(lab, (NEUTRAL, INK))
            ax.add_patch(plt.Rectangle((k + .04, r + .07), .92, .86, color=fill, lw=0))
            ax.text(k + .5, r + .5, lab, ha="center", va="center", color=ink, fontsize=8.5, clip_on=True)
    ax.set_xlim(0, P); ax.set_ylim(n, 0)
    ax.set_xticks(np.arange(P) + .5, res.period_columns, fontsize=9)
    ax.set_yticks(np.arange(n) + .5, df[spec.id_column].astype(str), fontsize=8.5)
    ax.xaxis.tick_top()
    _clean(ax)
    title = "Treatment schedule"
    if len(res.schedule) > n:
        title += f" (first {n} of {len(res.schedule)} {spec.noun()})"
    ax.set_title(title, pad=28)
    fig.tight_layout()
    return fig


def period_balance_figure(res: Result, unit_index: int = 0):
    spec = res.spec
    rows = res.subject_unit_ids[unit_index]
    C = period_counts(res.assign, len(spec.treatments), rows)
    colors = treatment_colors(spec)
    labels = [f"{spec.period_name} {k + 1}" for k in spec.randomized_periods]
    fig, ax = plt.subplots(figsize=(max(6, 1.1 * len(labels) + 2.5), 3.6))
    bottom = np.zeros(len(labels))
    gap = 0.04 * len(rows) / 15
    for i, name in enumerate(spec.treatments):
        fill, ink = colors[name]
        h = C[i]
        ax.bar(range(len(labels)), np.maximum(h - gap, 0), bottom=bottom + gap / 2, width=0.6, color=fill, lw=0)
        for k in range(len(labels)):
            if h[k] and h[k] / max(1, len(rows)) > 0.06:
                ax.text(k, bottom[k] + h[k] / 2, h[k], ha="center", va="center", color=ink, fontsize=8.5)
        bottom += h
    ax.set_xticks(range(len(labels)), labels)
    ax.set_ylabel(spec.noun(cap=True))
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    _clean(ax)
    ax.legend(handles=[Patch(color=colors[n][0], label=n) for n in spec.treatments],
              frameon=False, loc="upper left", bbox_to_anchor=(1, 1))
    ax.set_title(f"Treatments per {spec.period()} — {res.units[unit_index].name}", pad=10)
    fig.tight_layout()
    return fig


def _matrix(ax, M, mask, names, vmax, small=False):
    t = len(names)
    for a in range(t):
        for b in range(t):
            if not mask[a, b]:
                color, text, ink = GRID, "–", MUTED
            else:
                color, text = BLUES(M[a, b] / max(vmax, 1)), M[a, b]
                ink = "#ffffff" if M[a, b] / max(vmax, 1) > 0.55 else INK
            ax.add_patch(plt.Rectangle((b + .03, a + .03), .94, .94, color=color, lw=0))
            ax.text(b + .5, a + .5, text, ha="center", va="center", fontsize=8.5 if small else 10, color=ink)
    ax.set_xlim(0, t); ax.set_ylim(t, 0); ax.set_aspect("equal")
    ax.set_xticks(np.arange(t) + .5, names, rotation=45, ha="right", rotation_mode="anchor",
                  fontsize=8.5 if small else 9.5)
    ax.set_yticks(np.arange(t) + .5, names, fontsize=8.5 if small else 9.5)
    _clean(ax)


def carryover_figure(res: Result, unit_index: int = 0):
    """Overall transition counts: this design next to a simple rotation for comparison."""
    spec = res.spec
    t = len(spec.treatments)
    adj = spec.adjacent_pairs
    rows = res.subject_unit_ids[unit_index]
    M = transition_matrix(res.assign, t, adj, rows)
    rot = np.array([[(r + k) % t for k in range(res.assign.shape[1])] for r in range(len(rows))])
    R = transition_matrix(rot, t, adj)
    mask = allowed_mask(spec)
    vmax = max(R.max(), M.max())
    fig, axes = plt.subplots(1, 2, figsize=(4.4 + 1.1 * t, 0.9 + 0.62 * t))
    for ax, mat, title in [(axes[0], R, "Simple rotation (for comparison)"), (axes[1], M, "This design")]:
        _matrix(ax, mat, mask | (mat > 0), spec.treatments, vmax)
        ax.set_title(title, fontsize=11, pad=22)
        ax.text(0, 1.02, f"Next treatment guessed right {best_guess_rate(mat):.0%} of the time",
                transform=ax.transAxes, color=INK2, fontsize=8.5, va="bottom")
        ax.set_xlabel(f"Next {spec.period()}")
        ax.set_ylabel(f"This {spec.period()}")
    fig.suptitle(f"How often each treatment follows another — {res.units[unit_index].name}",
                 x=0.02, ha="left", fontweight="bold", fontsize=12)
    fig.tight_layout()
    return fig


def changes_figure(res: Result, unit_index: int = 0, max_panels: int = 8):
    """Transition counts for each single change between consecutive periods."""
    spec = res.spec
    t = len(spec.treatments)
    adj = spec.adjacent_pairs[:max_panels]
    rows = res.subject_unit_ids[unit_index]
    rp = spec.randomized_periods
    mats = [transition_matrix(res.assign, t, spec.adjacent_pairs, rows, which={j}) for j in range(len(adj))]
    vmax = max(3, max(m.max() for m in mats))
    cols = min(4, len(adj))
    nrow = int(np.ceil(len(adj) / cols))
    size = 0.42 * t + 0.9
    fig, axes = plt.subplots(nrow, cols, figsize=(cols * size + 0.8, nrow * size + 1.0), squeeze=False)
    mask = allowed_mask(spec)
    for j, ax in enumerate(axes.ravel()):
        if j >= len(adj):
            ax.axis("off")
            continue
        k1, k2 = adj[j]
        _matrix(ax, mats[j], mask | (mats[j] > 0), spec.treatments, vmax, small=True)
        ax.set_title(f"{spec.period_name} {rp[k1] + 1} → {rp[k2] + 1}", fontsize=10)
    fig.suptitle(f"Each single change between consecutive {spec.period(True)} — "
                 f"{res.units[unit_index].name}", x=0.02, ha="left", fontweight="bold", fontsize=12)
    fig.tight_layout()
    return fig
