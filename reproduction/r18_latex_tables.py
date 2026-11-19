"""Write the result tables of the manuscript and supplement from the result files, so every number
in them comes from the analysis output.

Writes each table body to results/latex/<NAME>.tex (one file per table) and prints every block.
Inputs: r16_summary.csv, r14_exact.csv, simulation.csv, r14_sim_new.csv, r06_sim_strata.csv,
        r14_sim_strata_new.csv, r08_certificates.csv, r12_tuning.csv
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from common import RESULTS

MS = Path(__file__).resolve().parents[2] / "manuscript"
ORDER = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "sa_ws", "ilp_nospread", "ilp"]
LABEL = {"simple": "Simple randomization", "latin": "Random Latin squares", "williams": "Williams squares",
        "williams_best": "Williams squares, best of 500",
         "rerand": "Rerandomization", "classical": "Best classical design", "sa": "Annealing, random start",
         "sa_ws": "Annealing, Williams start", "ilp_nospread": "LIBRA without spread", "ilp": "LIBRA"}
CFG5, CFG4 = list("ABCDE"), list("ABCD")


def p3(x):
    """APA style for values that cannot exceed 1: no leading zero."""
    s = f"{x:.3f}"
    return s.replace("0.", ".", 1) if s.startswith("0.") else s.replace("-0.", "$-$.", 1) if s.startswith("-0.") else s


def cell(summ, c, m, col, fmt):
    r = summ[(summ.config == c) & (summ.method == m)]
    if r.empty or pd.isna(r[f"{col}_mean"].iloc[0]):
        return "--"
    mu, sd = r[f"{col}_mean"].iloc[0], r[f"{col}_std"].iloc[0]
    return f"{fmt(mu)} ({fmt(sd)})"


def block(summ, title, col, fmt, cfgs, methods=ORDER, extra=None):
    n = len(methods) + (len(extra) if extra else 0)
    lines = []
    for i, m in enumerate(methods):
        head = f"\\multirow{{{n}}}{{*}}{{\\shortstack[l]{{{title}}}}}" if i == 0 else ""
        lines.append(f"{head} & {LABEL[m]:24} & " + " & ".join(cell(summ, c, m, col, fmt) for c in cfgs) + r" \\")
    for lab, vals in (extra or []):
        lines.append(f" & \\emph{{{lab}}} & " + " & ".join(f"\\emph{{{v}}}" for v in vals) + r" \\")
    return "\n".join(lines)


def tab_balance(summ):
    f2 = lambda x: f"{x:.2f}"
    f1 = lambda x: f"{x:.1f}"
    return "\n\\midrule\n".join([block(summ, "Carry-over range,\\\\ worst stratum", "carry_range", f2, CFG5),
                                 block(summ, "Period\\\\ imbalance", "period_dev", f1, CFG5),
                                 block(summ, "Spread\\\\ deviation", "spread_dev", f1, CFG5)])


def g2_floors():
    """Attainable floor of G2 after one session (r21 floors), as the mean over LIBRA's designs."""
    f = RESULTS / "r21_floors.csv"
    if not f.exists():
        return ["--"] * 4
    d = pd.read_csv(f).groupby("config").G2_floor.mean()
    return [p3(d[c]) if c in d.index else "--" for c in CFG4]


def tab_pred(summ):
    ch2 = [".333", ".333", ".500", ".250"]
    return "\n\\midrule\n".join([
        block(summ, "G2: this period\\\\ change's table", "G2", p3, CFG4,
              extra=[("Attainable floor", g2_floors())]),
        block(summ, "G3: full list,\\\\ strata pooled", "G3_2", p3, CFG4, extra=[("Chance", ch2)]),
        block(summ, "G3: full list,\\\\ stratum known", "G3s_2", p3, CFG4)])


def tab_pred_g1(summ):
    ch1 = [".250", ".250", ".333", ".200"]
    return block(summ, "G1: pooled\\\\ transition table", "G1", p3, CFG4, extra=[("Chance", ch1)])


def tab_scale():
    d = pd.read_csv(RESULTS / "scalability.csv")
    out = []
    for t, g in d.groupby("t"):
        n = len(g)
        form = {"sequence counts": "sequence counts", "per-subject": "per subject"}.get(g.formulation.iloc[0],
                                                                                          g.formulation.iloc[0])
        out.append(f"{t} & {form} & {int((g.period_dev == 0).sum())}/{n} & "
                   f"{int((g.level_carryover == 'required').sum())}/{n} & {int(g.carry_range_worst.max())} & "
                   f"{int(g.proven_optimal.astype(bool).sum())}/{n} & {g.seconds.median():.1f} & "
                   f"{int(g.reproducible.astype(str).eq('True').sum())}/{n} \\\\")
    return "\n".join(out)


def tab_rules():
    d = pd.read_csv(RESULTS / "r04_rules_summary.csv").set_index("case")
    names = {"A0": "A, no rules", "R1": "A, two transitions forbidden", "R2": "A, intense never before mild",
             "R3": "Incomplete, $t = 6$, $p = 4$, $N = 30$"}
    out = []
    for k, lab in names.items():
        if k not in d.index:
            continue
        r = d.loc[k]
        f = lambda v, fmt="{:.0f}": "--" if pd.isna(v) else fmt.format(v)
        out.append(f"{lab:38} & {f(r.period_dev)} & {f(r.carry_dev)} & {f(r.carry_range, '{:.1f}')} & "
                   f"{f(r.spread_dev)} & {'--' if pd.isna(r.eff_M2) else p3(r.eff_M2)} & {r.proven:.2f} & "
                   f"{int(r.distinct_designs)} \\\\")
    return "\n".join(out)


def tab_cert():
    df = pd.read_csv(RESULTS / "r08_certificates.csv").set_index("file")
    cp = RESULTS / "r22_cpsat_certificates.csv"
    agree = pd.read_csv(cp).set_index("file").agrees if cp.exists() else None
    fmt = lambda s: "$< 1$" if s < 1 else f"{s:.0f}" if s >= 10 else f"{s:.1f}"
    rows = [("t5n15_carry_spread", "$t = 5$, $N = 15$: carry-over balance + perfect spread", "impossible"),
            ("t5n15_min_spread", "$t = 5$, $N = 15$: minimum spread excess with carry-over balance", "1"),
            ("t5n15_nested", "$t = 5$, $N = 15$: period + carry-over + nested balance", "impossible"),
            ("t5n15_min_g3_k2", "Minimum G3 after two periods, $t = 5$, $N = 15$", "10/15 = .667"),
            ("t4n8_min_g3_k2", "\\quad $t = 4$, $N = 8$", "7/8 = .875"),
            ("t6n10_min_g3_k2", "\\quad $t = 6$, $N = 10$", "6/10 = .600"),
            ("t5n2x15_min_g3_k2", "\\quad $t = 5$, $2 \\times 15$, strata pooled", "10/30 = .333"),
            ("t4n2x8_min_g3_k2", "\\quad $t = 4$, $2 \\times 8$, strata pooled", "11/16 = .688"),
            ("t3n9_carry", "$t = 3$, $N = 9$: carry-over balance", "impossible")]
    out = []
    for f, q, a in rows:
        ok = "" if agree is None else (" & yes" if bool(agree.get(f + ".mps", False)) else " & NO")
        out.append(f"{q} & {a} & {fmt(df.loc[f + '.mps', 'seconds'])}{ok} \\\\")
    return "\n".join(out)


def tab_eff(summ):
    def mean_block(title, col, extra=None):
        n = len(ORDER) + (1 if extra else 0)
        out = []
        for i, m in enumerate(ORDER):
            head = f"\\multirow{{{n}}}{{*}}{{\\shortstack[l]{{{title}}}}}" if i == 0 else ""
            vals = []
            for c in CFG5:
                r = summ[(summ.config == c) & (summ.method == m)]
                vals.append("--" if r.empty else p3(r[f"{col}_mean"].iloc[0]))
            out.append(f"{head} & {LABEL[m]:24} & " + " & ".join(vals) + r" \\")
        if extra:
            out.append(" & \\emph{Best found, no balance constraints} & "
                       + " & ".join(f"\\emph{{{v}}}" for v in extra) + r" \\")
        return "\n".join(out)
    aopt = pd.read_csv(RESULTS / "r05_aopt.csv").set_index("config").aopt_eff_M2
    best = [p3(aopt[c]) if c in aopt.index else "--" for c in CFG5]
    return mean_block("M1: without\\\\ carry-over", "eff_M1") + "\n\\midrule\n" + \
        mean_block("M2: with\\\\ carry-over", "eff_M2", extra=best)


def tab_sim():
    sim = pd.concat([pd.read_csv(RESULTS / "simulation.csv"), pd.read_csv(RESULTS / "r14_sim_new.csv")])
    t1 = sim[sim.scenario == "no_effect"].set_index(["config", "method"]).reject_F
    ex = pd.read_csv(RESULTS / "r14_exact.csv").set_index(["config", "method"]).power_F
    out = []
    for title, src in (("Type I error", t1), ("Power (exact)", ex)):
        ms = [m for m in ORDER if any((c, m) in src.index for c in CFG5)]
        for i, m in enumerate(ms):
            head = f"\\multirow{{{len(ms)}}}{{*}}{{{title}}}" if i == 0 else ""
            vals = [p3(src[(c, m)]) if (c, m) in src.index else "--" for c in CFG5]
            out.append(f"{head} & {LABEL[m]:24} & " + " & ".join(vals) + r" \\")
        out.append("\\midrule")
    return "\n".join(out[:-1])


def tab_simstrata():
    ex = pd.read_csv(RESULTS / "r14_exact.csv").set_index(["config", "method"])
    st = pd.concat([pd.read_csv(RESULTS / "r06_sim_strata.csv"), pd.read_csv(RESULTS / "r14_sim_strata_new.csv")])
    t1 = st[(st.scenario == "ar1_null") & (st.analysis == "M1")].set_index(["config", "method"]).reject
    out = []
    for m in ORDER:
        vals = []
        for c in ("B", "D"):
            if (c, m) not in ex.index:
                vals += ["--"] * 4
                continue
            r = ex.loc[(c, m)]
            vals += [p3(r.SE_sexperiod_M1), p3(r.S2_power_M2), p3(r.S2_bias_M1),
                     p3(t1[(c, m)]) if (c, m) in t1.index else "--"]
        if all(v == "--" for v in vals):
            continue
        out.append(f"{LABEL[m]:24} & " + " & ".join(vals) + r" \\")
    return "\n".join(out)


def tab_div(summ):
    out = []
    for m in ORDER:
        vals = []
        for c in CFG5:
            r = summ[(summ.config == c) & (summ.method == m)]
            vals.append("--" if r.empty else str(int(r.skeletons60.iloc[0])))
        out.append(f"{LABEL[m]:24} & " + " & ".join(vals) + r" \\")
    return "\n".join(out)


def cert_times():
    df = pd.read_csv(RESULTS / "r08_certificates.csv").set_index("file")
    files = ["t5n15_carry_spread", "t5n15_min_spread", "t5n15_nested", "t5n15_min_g3_k2", "t4n8_min_g3_k2",
             "t6n10_min_g3_k2", "t5n2x15_min_g3_k2", "t4n2x8_min_g3_k2"]
    fmt = lambda s: "$< 1$" if s < 1 else f"{s:.0f}" if s >= 10 else f"{s:.1f}"
    rep = {f"@@S{i + 1}@@": fmt(df.loc[f + ".mps", "seconds"]) for i, f in enumerate(files)}
    rows = []
    for f, r in df.iterrows():
        res = r.status if pd.isna(r.objective) else f"{r.status}, objective {r.objective:.0f}"
        rows.append(f"\\texttt{{{f.replace('_', chr(92) + '_')}}} & {res} & {r.variables} & {r.rows} & {fmt(r.seconds)} \\\\")
    rep["@@MPSROWS@@"] = "\n".join(rows)
    return rep


def tune_table():
    files = [RESULTS / "r12_tuning.csv"] + ([RESULTS / "r12b_tuning.csv"] if (RESULTS / "r12b_tuning.csv").exists() else [])
    t = pd.concat([pd.read_csv(f) for f in files]).drop_duplicates(["config", "seed", "T0"])
    t = t.groupby(["config", "T0"]).penalty.mean().unstack()
    cols = list(t.columns)
    head = "\\begin{tabular}{l" + "r" * len(cols) + "l}\n\\toprule\nConfiguration & " + \
        " & ".join(f"{c:,.0f}" for c in cols) + " & Chosen \\\\\n\\midrule\n"
    body = "\n".join(f"{c} & " + " & ".join("--" if pd.isna(v) else f"{v:.0f}" for v in row)
                     + f" & {cols[int(np.nanargmin(row.values))]:,.0f} \\\\" for c, row in t.iterrows())
    return head + body + "\n\\bottomrule\n\\end{tabular}"


def tab_perm():
    d = pd.read_csv(RESULTS / "validity_permutation_tests.csv")
    out = []
    for (c, s), g in d.groupby(["config", "scenario"], sort=False):
        r = g.set_index("reference").rejection_rate
        out.append(f"{c} & {'No effect' if s == 'no_effect' else 'Effect'} & {p3(r['pipeline'])} & "
                   f"{p3(r['orbit'])} & {p3(r['naive'])} \\\\")
    return "\n".join(out)


def tab_fulllist():
    d = pd.read_csv(RESULTS / "x03_predict_summary.csv").set_index(["config", "variant"])
    rows = [("G3 after 1 period", "G3_after1", p3), ("G3 after 2 periods", "G3_after2", p3),
            ("G3 after 2 periods, stratum known", "G3g_after2", p3), ("G3, mean over periods", "G3_mean", p3),
            ("Spread deviation", "spread_dev_total", lambda v: f"{v:.1f}"),
            ("Efficiency M2", "eff_M2", p3), ("Distinct skeletons (of 16)", "distinct_skeletons", lambda v: f"{v:.0f}")]
    out = []
    for c in CFG4:
        out.append(f"\\multicolumn{{4}}{{@{{}}l}}{{\\emph{{Configuration {c}}}}} \\\\")
        for lab, col, f in rows:
            vals = [f(d.loc[(c, v), col]) if (c, v) in d.index and not pd.isna(d.loc[(c, v), col]) else "--"
                    for v in ("williams", "default", "g3first")]
            out.append(f"\\quad {lab} & " + " & ".join(vals) + r" \\")
    return "\n".join(out)


def tab_unif():
    d = pd.read_csv(RESULTS / "r20_variety_uniformity.csv", dtype={"case": str})
    names = {"58": "$t = 4$, $N = 12$, spread off", "S12": "$t = 4$, $N = 16$, spread on"}
    out = []
    for _, r in d.sort_values(["case", "variant"], ascending=[True, False]).iterrows():
        p = r.chi2_p_exact if "chi2_p_exact" in r and not pd.isna(r.get("chi2_p_exact")) else r.chi2_p
        ps = "$< .001$" if p < 0.001 else p3(p)
        mx = f"{r.max_over_expected:,.1f}"
        out.append(f"{names.get(r.case, r.case)} & {'Variety (listing)' if r.variant == 'variety' else 'Random walk'} & "
                   f"{int(r.designs)} & {int(r.seeds):,} & {r.reached} & {ps} & {mx} \\\\")
    return "\n".join(out)


def tab_early():
    d = pd.read_csv(RESULTS / "x05_early_stopping.csv")
    lab = {"williams": "Williams squares", "williams_best": "Williams, best of 500", "classical": "Best classical design",
           "sa_ws": "Annealing, Williams start", "ilp_nospread": "LIBRA without spread", "ilp": "LIBRA"}
    out = []
    for c in CFG4:
        g = d[d.config == c]
        for i, (_, r) in enumerate(g.iterrows()):
            out.append(f"{c if i == 0 else ''} & {lab.get(r.variant, r.variant)} & {r.prefix_dev_total:.1f} & "
                       f"{p3(r.eff_M2_stop_3)} & {p3(r.eff_M2_drop)} \\\\")
        out.append("\\midrule")
    return "\n".join(out[:-1])


def tab_partial():
    d = pd.read_csv(RESULTS / "r07_partial_observer.csv")
    order = ["simple", "latin", "williams", "williams_best", "rerand", "classical", "sa", "ilp_nospread", "ilp"]
    lab = LABEL
    out = []
    for m in order:
        vals = []
        for c in ("A", "B"):
            for split in ("one", "strong"):
                r = d[(d.config == c) & (d.method == m) & (d.split == split)]
                vals += ["--", "--"] if r.empty else [p3(r.table.iloc[0]), p3(r.list.iloc[0])]
        out.append(f"{lab[m]:24} & " + " & ".join(vals) + r" \\")
    base = []
    for c in ("A", "B"):
        for split in ("one", "strong"):
            r = d[(d.config == c) & (d.split == split)]
            b = r.baseline.mean()
            base += [p3(b), p3(b)]
    out.append("\\emph{Baseline} & " + " & ".join(f"\\emph{{{v}}}" for v in base) + r" \\")
    return "\n".join(out)


def tab_minrange():
    d = pd.read_csv(RESULTS / "r21_minrange.csv")
    return "\n".join(f"{r.t} & {r.N} & {r.groups} & {r.min_worst_range} & {'yes' if r.proven else 'no'} & "
                     f"{r.achieved_worst_range} & {r.seconds:.1f} \\\\" for _, r in d.iterrows())


def tab_williams():
    rows = []
    for line in (RESULTS / "r11_williams_check.txt").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[0] in CFG5 and parts[1] in ("per-copy", "shared"):
            c, kind = parts[0], "per copy" if parts[1] == "per-copy" else "shared"
            nums = parts[-4:]
            rows.append(f"{c} & {kind} & {p3(float(nums[0]))} & {p3(float(nums[1]))} & {p3(float(nums[2]))} & {nums[3]} \\\\")
    return "\n".join(rows)


def tab_schedule():
    """The worked example's schedule (seed 1) with one-letter condition codes, both sites side by side."""
    d = pd.read_csv(RESULTS / "r15_example_schedule.csv")
    w = d.pivot(index=["participant", "site"], columns="Session", values="Treatment").reset_index()
    # The article presents the example as a clinical crossover trial: PLACEBO, LOW, MEDIUM, HIGH,
    # ACTIVE in place of CONTROL, EASY, MEDIUM, HARD, DUAL (same order, so the same schedule; checked
    # by solving seed 1 with both sets of labels).
    code = {"CONTROL": "P", "EASY": "L", "MEDIUM": "M", "HARD": "H", "DUAL": "A"}
    abbr = lambda s: code.get(str(s), str(s)[0])
    sites = [g.sort_values("participant") for _, g in w.groupby("site", sort=True)]
    sess = [c for c in w.columns if c not in ("participant", "site")]
    out = []
    for r1, r2 in zip(sites[0].itertuples(index=False), sites[1].itertuples(index=False)):
        a = [r1.participant] + [abbr(getattr(r1, f"_{i + 2}")) for i in range(len(sess))]
        b = [r2.participant] + [abbr(getattr(r2, f"_{i + 2}")) for i in range(len(sess))]
        out.append(" & ".join(a + b) + r" \\")
    return "\n".join(out)


def main():
    summ = pd.read_csv(RESULTS / "r16_summary.csv")
    rep = {"@@TAB_BALANCE@@": tab_balance(summ), "@@TAB_PRED@@": tab_pred(summ), "@@TAB_EFF@@": tab_eff(summ),
           "@@TAB_SIM@@": tab_sim(), "@@TAB_SIMSTRATA@@": tab_simstrata(), "@@TAB_DIV@@": tab_div(summ),
           "@@TAB_PRED_G1@@": tab_pred_g1(summ), "@@TAB_SCALE@@": tab_scale(), "@@TAB_RULES@@": tab_rules(),
           "@@TAB_CERT@@": tab_cert()}
    for name, fn in (("TAB_PERM", tab_perm), ("TAB_FULLLIST", tab_fulllist), ("TAB_UNIF", tab_unif),
                     ("TAB_EARLY", tab_early), ("TAB_PARTIAL", tab_partial), ("TAB_MINRANGE", tab_minrange),
                     ("TAB_WILLIAMS", tab_williams), ("TAB_SCHEDULE", tab_schedule)):
        try:
            rep[f"@@{name}@@"] = fn()
        except FileNotFoundError as e:          # an optional analysis that has not been run
            print(f"skipped {name}: {e}")
    rep.update(cert_times())
    rep["@@TUNETABLE@@"] = tune_table()
    # The table bodies are written to results/latex/<NAME>.tex (one file per table) and pasted
    # into the manuscript from there.
    out = RESULTS / "latex"
    out.mkdir(exist_ok=True)
    for k, v in rep.items():
        name = k.strip("@")
        (out / f"{name}.tex").write_text(v + "\n", encoding="utf-8")
        print(f"--- {name}\n{v}\n")
    print(f"{len(rep)} table blocks written to {out}")


if __name__ == "__main__":
    main()
