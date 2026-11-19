"""Plain-language checks before solving: what cannot work, and what can only be balanced
approximately. Each finding names the page ("step") where it can be fixed."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from .project import SpecError, build_spec, randomized_count, treatment_names
from .spec import plural_of, soft_lower, validate

STEPS = ("subjects", "treatments", "rules", "balance", "generate")


@dataclass
class Finding:
    level: str      # "error" | "warning" | "info"
    step: str       # one of STEPS
    text: str


def _step_of(message: str) -> str:
    m = message.lower()
    if any(w in m for w in ("rule", "forbidden", "order")):
        return "rules"
    if any(w in m for w in ("treatment", "period", "ratio", "fixed")):
        return "treatments"
    if "block" in m:
        return "balance"
    if any(w in m for w in ("seed", "solver", "randomization")):
        return "generate"
    return "subjects"


def _order_cycle(rules):
    """A treatment that must come both before and after another (directly or through others)."""
    graph = {}
    for a, b in rules:
        graph.setdefault(a, set()).add(b)
    state = {}

    def visit(v, path):
        state[v] = 1
        for w in graph.get(v, ()):
            if state.get(w) == 1:
                return path + [v, w]
            if w not in state:
                found = visit(w, path + [v])
                if found:
                    return found
        state[v] = 2
        return None

    for v in list(graph):
        if v not in state:
            cyc = visit(v, [])
            if cyc:
                return cyc
    return None


def precheck(settings: dict, subjects: pd.DataFrame) -> list[Finding]:
    out: list[Finding] = []
    s = settings
    names = treatment_names(s)
    one = soft_lower(s["subject_noun"].strip() or "subject")
    many = soft_lower(s["subject_plural"].strip() or plural_of(one))
    per = soft_lower(s["period_name"].strip() or "period")

    # ------------------------------------------------ rules that contradict each other
    cyc = _order_cycle(s.get("order_rules", []))
    if cyc:
        out.append(Finding("error", "rules", "The order rules contradict each other: "
                                             + " before ".join(cyc) + "."))
    unknown = {x for r in s.get("forbidden_transitions", []) + s.get("order_rules", []) for x in r} | \
              {a for a, _ in s.get("forbidden_periods", [])}
    unknown -= set(names)
    if unknown:
        out.append(Finding("error", "rules", f"Some rules mention treatments that no longer exist: "
                                             f"{', '.join(sorted(map(str, unknown)))}. Edit or remove them."))
    if len(names) < 2 and s["design"] != "parallel":
        out.append(Finding("error", "treatments", "Add at least two treatments."))
    if s.get("blocks_enabled"):
        bs = s.get("block_sizes", [])
        if not bs or any(int(b) < 1 for b in bs):
            out.append(Finding("error", "balance", "Enter one or more block sizes (whole numbers)."))

    try:
        spec, cluster = build_spec(s, subjects)
    except SpecError as e:
        return out + [Finding("error", e.step, str(e))]
    except (ValueError, TypeError) as e:
        return out + [Finding("error", "subjects", str(e))]

    errors, warnings = validate(spec)
    for e in errors:
        e = e.replace("Subject table", f"The {one} table").replace("subject IDs", f"{one} IDs")
        out.append(Finding("error", _step_of(e), e))
    for w in warnings:
        if "not a multiple" in w:
            continue                                  # reported per group below
        out.append(Finding("warning", _step_of(w), w))
    if any(f.level == "error" for f in out):
        return out

    t, p = len(spec.treatments), len(spec.randomized_periods)
    unit_word = spec.noun()
    complete = spec.is_complete and spec.max_per_subject == 1

    # ------------------------------------------------ allowed orders
    if p > 1 and (spec.forbidden_transitions or spec.forbidden_periods or spec.order_rules) \
            and math.perm(t, min(p, t)) <= 200_000:
        from .solver import _prepare, DesignError
        import numpy as np
        try:
            ctx = _prepare(spec, np.random.default_rng(0))
            if ctx.seqs is not None:
                total = math.perm(t, p) if spec.max_per_subject == 1 else None
                txt = f"The rules allow {len(ctx.seqs)} different treatment orders"
                txt += f" (of {total})." if total else "."
                level = "info" if len(ctx.seqs) > 1 else "warning"
                if len(ctx.seqs) == 1:
                    txt += f" Every {one} will get the same order, so nothing is randomized."
                out.append(Finding(level, "rules", txt))
                # rules can make some treatments impossible in some periods (High never first, ...)
                possible = {(k, int(a)) for k in range(p) for a in set(ctx.seqs[:, k].tolist())}
                never = [(k, a) for k in range(p) for a in range(t)
                         if (k, a) not in possible and (k, a) not in set(ctx.forbidden_pos)]
                if never and spec.period_balance == "required":
                    rp = spec.randomized_periods
                    k, a = never[0]
                    out.append(Finding("error", "balance",
                                       f"With these rules, {spec.treatments[a]} can never be in "
                                       f"{spec.period_name} {rp[k] + 1}"
                                       + (f" (and {len(never) - 1} more such cases)" if len(never) > 1 else "")
                                       + ", so period balance cannot be required. "
                                       f"Set it to Preferred."))
        except DesignError as e:
            out.append(Finding("error", "rules", str(e)))
            return out

    # ------------------------------------------------ what can be balanced exactly
    units = [("all " + unit_word, len(spec.subjects))]
    for c in spec.strata:
        for lvl, n in spec.subjects[c].astype(str).value_counts(sort=False).items():
            units.append((f"{c} = {lvl}", int(n)))
        if spec.subjects[c].nunique() < 2:
            out.append(Finding("info", "subjects", f"'{c}' has only one value, so balancing within it "
                                                   f"changes nothing."))
    if spec.period_balance != "off" and t > 1:
        odd = [(u, n) for u, n in units if n % t]
        if odd:
            u, n = odd[0]
            more = f" (and {len(odd) - 1} more group{'s' if len(odd) > 2 else ''})" if len(odd) > 1 else ""
            out.append(Finding("info", "subjects",
                               f"{u}: {n} {unit_word} is not a multiple of {t} treatments{more}, so each "
                               f"{per} can only be balanced to within ±1 {spec.noun(False)}."))
    if complete and p > 1 and spec.carryover_balance != "off":
        scope = units if spec.balance_scope == "groups" else units[:1]
        odd = [(u, n) for u, n in scope if n % t]
        if odd:
            u, n = odd[0]
            out.append(Finding("info", "balance",
                               f"Exact carry-over balance needs a multiple of {t} {unit_word} per group "
                               f"({u} has {n}). The counts will differ by at most about 1."))
        elif t % 2 == 1 and t <= 7 and any(n == t for _, n in scope):
            out.append(Finding("info", "balance",
                               f"With an odd number of treatments, a group of exactly {t} {unit_word} "
                               f"cannot be carry-over balanced; {2 * t} can."))
    if spec.block_sizes:
        if complete and any(b % t for b in spec.block_sizes):
            out.append(Finding("info", "balance", f"Blocks that are not a multiple of {t} can only be "
                                                  f"balanced to within ±1 in each {per}."))
        smallest = min(n for _, n in units)
        if min(spec.block_sizes) > smallest:
            out.append(Finding("warning", "balance", f"Blocks are larger than the smallest group "
                                                     f"({smallest} {unit_word})."))
    if cluster:
        out.append(Finding("info", "subjects",
                           f"{len(spec.subjects)} {unit_word} will be randomized; all {len(cluster['subjects'])} "
                           f"{many} in a {spec.noun(False)} get the same sequence."))

    # ------------------------------------------------ time
    size = len(spec.subjects) * p * t
    if t >= 7 and spec.time_limit < 300:
        out.append(Finding("warning", "generate", "With seven or more treatments, allow several minutes "
                                                  "(for example 300 seconds) for the best balance."))
    elif size > 4000 and spec.time_limit < 60:
        out.append(Finding("warning", "generate", "This is a large design. Allow at least 60 seconds "
                                                  "for the best balance."))
    return out


def summary_line(settings: dict, subjects: pd.DataFrame) -> str:
    """'24 animals · 4 treatments · 4 weeks' (best effort, never raises)."""
    try:
        n = len(subjects.dropna(how="all"))
        t = len(treatment_names(settings))
        p = randomized_count(settings) + len([f for f in settings.get("fixed", []) if str(f.get("label", "")).strip()])
        one = settings["period_name"].strip() or "period"
        per = soft_lower(one if p == 1 else (settings.get("period_plural", "").strip() or plural_of(one)))
        subj = settings["subject_noun"] if n == 1 else (settings["subject_plural"].strip()
                                                        or plural_of(settings["subject_noun"]))
        return f"{n} {soft_lower(subj)} · {t} treatment{'s' if t != 1 else ''} · {p} {per}"
    except Exception:  # noqa: BLE001
        return ""
