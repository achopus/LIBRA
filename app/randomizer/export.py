"""Excel / CSV export and an auto-generated methods paragraph."""
from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd

from . import CITE_SHORT, __version__
from .diagnostics import SPREAD, checks, predictability, sequence_table, transition_table, unit_summary
from .solver import Result
from .spec import soft_lower


def long_format(res: Result) -> pd.DataFrame:
    spec = res.spec
    id_cols = [c for c in res.schedule.columns if c not in res.period_columns]
    df = res.schedule.melt(id_vars=id_cols, value_vars=res.period_columns,
                           var_name=spec.period_name, value_name="Treatment")
    df[spec.period_name] = df[spec.period_name].str.replace(f"{spec.period_name} ", "").astype(int)
    if spec.fixed:
        df["Fixed period"] = df[spec.period_name].isin(list(spec.fixed))
    if res.codes:
        df["Code"] = df["Treatment"].map(res.codes).fillna(df["Treatment"])
    return df.sort_values([spec.id_column, spec.period_name]).reset_index(drop=True)


def blinded_schedule(res: Result) -> pd.DataFrame:
    df = res.schedule.copy()
    for col in res.period_columns:
        df[col] = df[col].map(lambda v: res.codes.get(v, v))
    return df


def settings_table(res: Result) -> pd.DataFrame:
    s = res.spec.summary()
    s.update({"status": res.status, "formulation": res.formulation,
              "solve_seconds": round(res.solve_seconds, 1),
              "final choice": getattr(res, "randomization", {}),
              "final criterion levels": res.levels,
              "perfect-balance checks": res.checks, "criteria (remaining deviation, proven)": res.criteria,
              "reproducible mode": res.spec.deterministic, "reproducible": res.reproducible,
              "search effort (nominal s)": res.work_seconds,
              "app_version": __version__, "generated": datetime.now().isoformat(timespec="seconds")})
    return pd.DataFrame({"Setting": list(s), "Value": [json.dumps(v, default=str) if not isinstance(v, str)
                                                         else v for v in s.values()]})


def checks_table(res: Result) -> pd.DataFrame:
    """The balance report: the checks recomputed from the schedule, the perfect-balance checks made
    before optimizing, how the final design was chosen, and any warnings."""
    rows = [{"Check": c.name, "OK": c.ok, "Detail": c.detail} for c in checks(res)]
    if check_outcomes_text(res):
        rows.append({"Check": "Before optimizing", "OK": "", "Detail": check_outcomes_text(res) + "."})
    rows.append({"Check": "Final choice", "OK": "", "Detail": choice_text(res) + "."})
    rows += [{"Check": "Warning", "OK": False, "Detail": w} for w in res.warnings or []]
    return pd.DataFrame(rows)


def code_key(res: Result) -> pd.DataFrame:
    return pd.DataFrame({"Code": list(res.codes.values()), "Treatment": list(res.codes)}).sort_values("Code")


def _autofit(xw):
    for ws in xw.book.worksheets:
        for col in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col)
            ws.column_dimensions[col[0].column_letter].width = min(60, max(9, width + 2))


def to_excel(res: Result, extra: dict[str, pd.DataFrame] | None = None, key: bool = True) -> bytes:
    """The full record: schedule, checks, methods text, settings (and `extra` sheets)."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        res.schedule.to_excel(xw, sheet_name="Schedule", index=False)
        long_format(res).to_excel(xw, sheet_name="Long format", index=False)
        if res.codes:
            blinded_schedule(res).to_excel(xw, sheet_name="Blinded schedule", index=False)
            if key:
                code_key(res).to_excel(xw, sheet_name="Code key (keep separate)", index=False)
        checks_table(res).to_excel(xw, sheet_name="Checks", index=False)
        unit_summary(res).to_excel(xw, sheet_name="Balance by group", index=False)
        if res.spec.adjacent_pairs:
            transition_table(res).to_excel(xw, sheet_name="Carry-over counts")
            predictability(res).to_excel(xw, sheet_name="Predictability", index=False)
        sequence_table(res).to_excel(xw, sheet_name="Sequences", index=False)
        pd.DataFrame({"Methods text": [methods_text(res)]}).to_excel(xw, sheet_name="Methods text", index=False)
        settings_table(res).to_excel(xw, sheet_name="Settings", index=False)
        for name, df in (extra or {}).items():
            df.to_excel(xw, sheet_name=name[:31], index=False)
        _autofit(xw)
    return buf.getvalue()


def blinded_excel(res: Result, daily: pd.DataFrame | None = None) -> bytes:
    """For experimenters: codes only, no treatment names."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        blinded_schedule(res).to_excel(xw, sheet_name="Blinded schedule", index=False)
        lf = long_format(res).drop(columns=["Treatment"])
        lf.to_excel(xw, sheet_name="Long format", index=False)
        if daily is not None:
            daily.to_excel(xw, sheet_name="By date", index=False)
        _autofit(xw)
    return buf.getvalue()


def write_outputs(res: Result, folder, stem: str, fmt: str = "xlsx", long: bool = True,
                  png: bool = False, balance_png: bool = False, calendar: dict | None = None,
                  extra: dict[str, pd.DataFrame] | None = None, dpi: int = 300,
                  experiment: bool = False, run_id: str = "") -> list:
    """Write the chosen files to `folder` and return their paths.

    xlsx: one workbook with everything (`stem`.xlsx). csv: the schedule, plus the long format, a
    text file with the methods paragraph, the checks, the balance by group and the settings. With blinding, the experimenters' files (codes only) and
    the code key are separate files. With `calendar`, a dated schedule is added. With `experiment`, a
    folder of files and code for experiment software (see experiment.py)."""
    from pathlib import Path
    from .dates import dated_schedule
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    dated = dated_schedule(res, calendar) if calendar else None
    dated_blind = dated_schedule(res, calendar, blinded=True) if calendar and res.codes else None
    if fmt == "xlsx":
        sheets = dict(extra or {})
        if dated is not None:
            sheets = {"By date": dated, **sheets}
        p = folder / f"{stem}.xlsx"
        p.write_bytes(to_excel(res, sheets, key=False))
        out.append(p)
        if res.codes:
            p = folder / f"{stem}_BLINDED_for_experimenters.xlsx"
            p.write_bytes(blinded_excel(res, dated_blind))
            out.append(p)
    else:
        p = folder / f"{stem}.csv"
        res.schedule.to_csv(p, index=False, encoding="utf-8-sig")
        out.append(p)
        if long:
            p = folder / f"{stem}_long.csv"
            long_format(res).to_csv(p, index=False, encoding="utf-8-sig")
            out.append(p)
        if dated is not None:
            p = folder / f"{stem}_by_date.csv"
            dated.to_csv(p, index=False, encoding="utf-8-sig")
            out.append(p)
        p = folder / f"{stem}_methods.txt"
        p.write_text(methods_text(res) + "\n", encoding="utf-8")
        out.append(p)
        for name, df in (("checks", checks_table(res)), ("balance_by_group", unit_summary(res)),
                         ("settings", settings_table(res))):
            p = folder / f"{stem}_{name}.csv"
            df.to_csv(p, index=False, encoding="utf-8-sig")
            out.append(p)
        if res.codes:
            p = folder / f"{stem}_BLINDED_for_experimenters.csv"
            blinded_schedule(res).to_csv(p, index=False, encoding="utf-8-sig")
            out.append(p)
            if dated_blind is not None:
                p = folder / f"{stem}_BLINDED_by_date.csv"
                dated_blind.to_csv(p, index=False, encoding="utf-8-sig")
                out.append(p)
    if res.codes:
        p = folder / f"{stem}_CODE_KEY_keep_separate.csv"
        code_key(res).to_csv(p, index=False, encoding="utf-8-sig")
        out.append(p)
    if png or balance_png:
        from .plots import save_png
        out += save_png(res, folder, stem, schedule=png, balance=balance_png, dpi=int(dpi))
    if experiment:
        from .experiment import write_experiment_files
        out += write_experiment_files(res, folder, stem, run_id)
    return out


def choice_text(res: Result) -> str:
    """How the final design was chosen among the equally balanced ones (one sentence, no period)."""
    info = getattr(res, "randomization", None) or {}
    if info.get("method") == "uniform":
        n = info.get("designs")
        return (f"All {n} designs that were equally well balanced were listed, and one was drawn so that every "
                f"possible allocation of these orders to {res.spec.noun()} was equally likely"
                if n and n > 1 else "Only one design was equally well balanced, and it was used")
    if info.get("method") == "random walk":
        why = {"time": "listing them did not finish within the time limit",
               "not listable": "this design is too large to list them"}.get(info.get("reason"),
                                                                          "there were too many such designs to list")
        return ("One of the equally balanced designs was chosen at random by a random walk among them; the "
                f"choice was random but not uniform, because {why}")
    return ("One of the equally balanced designs was chosen at random with a random objective; the choice "
            "was random but not uniform over these designs")


CHECK_WORDS = {"met": "met", "impossible": "impossible (proven)",
               "not settled": "not settled (the check ran out of time)"}


def check_outcomes_text(res: Result) -> str:
    """Outcome of each "can this criterion be met perfectly?" check, in order (one sentence, no period).
    Empty when nothing was checked (e.g. every criterion required or off)."""
    from .solver import LABELS
    done = [f"{LABELS[k]} {CHECK_WORDS.get(v, v)}" for k, v in (res.checks or {}).items()]
    if not done:
        return ""
    last = list(res.checks.values())[-1]
    tail = ("; the remaining criteria were then made as good as possible, one at a time"
            if last != "met" else "")
    return "Perfect " + "; ".join(done) + tail


def methods_text(res: Result) -> str:
    spec = res.spec
    n, t, p = spec.n_subjects, len(spec.treatments), len(spec.randomized_periods)
    per, pers = spec.period(), spec.period(True)
    T = ", ".join(spec.treatments)
    parts = []
    subj, Subj, one = spec.noun(), spec.noun(cap=True), spec.noun(False)
    if p == 1:
        ratio = ":".join(f"{spec.weights.get(x, 1):g}" for x in spec.treatments)
        parts.append(f"{n} {subj} were allocated to {t} groups ({T}) in a {ratio} ratio.")
    elif spec.is_complete and spec.max_per_subject == 1:
        parts.append(f"In a crossover design, each of {n} {subj} received all {t} treatments ({T}), "
                     f"one per {per}, over {p} randomized {pers}.")
    elif spec.max_per_subject == 1:
        parts.append(f"In an incomplete crossover design, each of {n} {subj} received {p} of the "
                     f"{t} treatments ({T}), one per {per}.")
    else:
        parts.append(f"In a replicated crossover design, each of {n} {subj} received {p} {pers} of "
                     f"treatment ({T}), each treatment {spec.min_per_subject}–{spec.max_per_subject} times.")
    if spec.fixed:
        fx = "; ".join(f"{lab} in {per} {k}" for k, lab in sorted(spec.fixed.items()))
        parts.append(f"Fixed {pers} were identical for all {subj} ({fx}).")
    if spec.strata:
        parts.append(f"Randomization was stratified by {', '.join(spec.strata)}.")
    if spec.block_sizes:
        parts.append(f"{Subj} were randomized in consecutive blocks of "
                     f"{' or '.join(str(b) for b in spec.block_sizes)} (in enrollment order), "
                     f"with block sizes chosen at random.")
    crit = []
    if spec.period_balance != "off":
        crit.append(f"each treatment occurring equally often in every {per}"
                    + (" within every stratum" + (" and block" if spec.block_sizes else "")
                       if spec.strata or spec.block_sizes else ""))
    if p > 1 and spec.carryover_balance != "off":
        crit.append("each treatment being directly preceded by every other treatment equally often "
                    "(first-order carry-over balance)")
    if p > 1 and not spec.is_complete and spec.max_per_subject == 1 and spec.cooccurrence_balance != "off":
        crit.append(f"every pair of treatments being given to the same {one} equally often")
    if p > 1 and spec.fulllist_balance != "off" and res.levels.get("fulllist", "off") != "off":
        crit.append(f"the complete list revealing as little as possible about a {one}'s later treatments "
                    f"once their first two are known")
    if p > 1 and spec.spread_balance != "off":
        crit.append(f"{subj} sharing a treatment in one {per} receiving different treatments in the next")
    rules = []
    if spec.forbidden_transitions:
        rules.append("forbidden direct sequences (" + ", ".join(f"{a}→{b}" for a, b in spec.forbidden_transitions) + ")")
    if spec.forbidden_periods:
        rules.append("treatments excluded from specific " + per + "s (" +
                     ", ".join(f"{a} not in {per} {k}" for a, k in spec.forbidden_periods) + ")")
    if spec.order_rules:
        rules.append("required orderings (" + ", ".join(f"{a} before {b}" for a, b in spec.order_rules) + ")")
    libra = f"LIBRA {__version__} ({CITE_SHORT})"
    solver = "Gurobi" if spec.solver == "gurobi" else "HiGHS"
    s = (f"Treatment sequences were generated by constrained randomization with {libra}: an integer linear "
         f"program (solved with {solver}) selected sequences that "
         + ("respect " + "; ".join(rules) + " and " if rules else "")
         + "optimize balance, with the criteria optimized one at a time in order of priority: "
         + "; then ".join(crit) + ". " if crit else "")
    parts.append(s.strip() if s else f"The schedule was generated with {libra}.")
    achieved = [soft_lower(c.name) for c in checks(res)
                if c.ok and c.key in ("Period balance", "Carry-over balance", SPREAD)]
    if achieved:
        listed = achieved[0] if len(achieved) == 1 else ", ".join(achieved[:-1]) + " and " + achieved[-1]
        parts.append(f"The final design achieved ideal {listed}.")
    carry = next((c for c in checks(res) if c.key == "Carry-over balance"), None)
    if carry is not None and not carry.ok and "as even as the rules allow" in carry.detail:
        parts.append("Because of the rules, carry-over could not be equal for all pairs of treatments; the "
                     "counts were made as even as the rules allow.")
    rules_set = bool(spec.forbidden_transitions or spec.forbidden_periods or spec.order_rules)
    equal_ratios = len({spec.weight(x) for x in spec.treatments}) == 1
    permuted = not rules_set and equal_ratios and not spec.locked     # as in the solver
    parts += list(getattr(res, "notes", []) or [])
    parts.append(choice_text(res) + f" (seed {spec.seed}); {subj} were randomly assigned to sequences "
                 f"within strata" + (" and treatment labels were randomly permuted." if permuted else "."))
    if not permuted and p > 1:
        why = ("the rules distinguish some treatments from the others" if rules_set else
               "the allocation ratios differ between treatments" if not equal_ratios else
               f"the sequences of the {subj} already enrolled were kept")
        parts.append(f"Treatment labels were not permuted, because {why}.")
    if res.reproducible:
        parts.append("The search was limited by solver work rather than by time, so the same settings and "
                     "seed reproduce the schedule exactly.")
    if res.codes:
        parts.append("Treatments were coded for blinding; the code key was held separately.")
    return " ".join(parts)
