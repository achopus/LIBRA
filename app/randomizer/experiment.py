"""Files for experiment software (PsychoPy, OpenSesame, jsPsych, lab.js).

Each session script needs one thing from the schedule: the condition of this participant in this
session. This module writes that lookup in the forms these programs read, plus a README with
copy-paste code. The column names are fixed (id, session, condition) so that the code never depends
on the words chosen in the app. With blinding, only codes are written; the code key stays elsewhere.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from . import __version__
from .solver import Result

FOLDER_SUFFIX = "_experiment"


def conditions_table(res: Result) -> pd.DataFrame:
    """One row per subject and session: id, the group columns, session (1, 2, ...), condition."""
    spec = res.spec
    sched = res.schedule
    groups = [c for c in spec.strata if c in sched.columns]
    rows = []
    for _, r in sched.iterrows():
        for k, col in enumerate(res.period_columns, 1):
            value = r[col]
            if res.codes:
                value = res.codes.get(value, value)
            rows.append({"id": str(r[spec.id_column]), **{g: r[g] for g in groups},
                         "session": k, "condition": value})
    return pd.DataFrame(rows, columns=["id", *groups, "session", "condition"])


def _file_name(subject_id: str) -> str:
    """A safe file name for a subject ID (letters, digits, - and _ kept)."""
    name = re.sub(r"[^A-Za-z0-9_-]+", "_", subject_id).strip("_")
    return name or "id"


def conditions_json(res: Result, run_id: str = "") -> dict:
    table = conditions_table(res)
    spec = res.spec
    groups = [c for c in table.columns if c not in ("id", "session", "condition")]
    participants = {sid: g.sort_values("session")["condition"].tolist() for sid, g in table.groupby("id", sort=False)}
    out = {"generated_by": f"LIBRA {__version__}", "run": run_id,
           "sessions": len(res.period_columns), "session_word": spec.period(),
           "blinded": bool(res.codes),
           "conditions": sorted(set(table["condition"])),
           "participants": participants}
    if groups:
        first = table.drop_duplicates("id").set_index("id")
        out["groups"] = {sid: {g: str(first.at[sid, g]) for g in groups} for sid in participants}
    return out


README = """\
{title}
{rule}

all_conditions.csv   one row per {one} and {period}: id, {group_text}session, condition
conditions.json      the same for JavaScript: participants -> list of conditions, session 1 first
conditions/          one file per {one} (rows = {periods}), named after the ID
{blind_text}
Every script needs the {one}'s ID exactly as in the schedule (for example "{example_id}") and the
{period} number (1, 2, ...). {example_id} in {period} 1 gets "{example_cond}".


PsychoPy (Builder: add a Code component, tab "Begin Experiment"; put all_conditions.csv next to
the .psyexp file. Then use $condition anywhere in the experiment.)
-----------------------------------------------------------------------------------------------
import csv, os
with open(os.path.join(_thisDir, 'all_conditions.csv'), newline='', encoding='utf-8-sig') as f:
    rows = [r for r in csv.DictReader(f)
            if r['id'] == expInfo['participant'] and int(r['session']) == int(expInfo['session'])]
if len(rows) != 1:
    raise ValueError('No condition for this participant and session in all_conditions.csv')
condition = rows[0]['condition']
thisExp.addData('condition', condition)


OpenSesame (add all_conditions.csv to the file pool; ask for participant and session first, for
example with a form_text_input; then an inline_script, Prepare phase. Use [condition] afterwards.)
-----------------------------------------------------------------------------------------------
import csv
with open(pool['all_conditions.csv'], newline='', encoding='utf-8-sig') as f:
    rows = [r for r in csv.DictReader(f)
            if r['id'] == str(var.participant) and int(r['session']) == int(var.session)]
if len(rows) != 1:
    raise ValueError('No condition for this participant and session in all_conditions.csv')
var.condition = rows[0]['condition']


jsPsych (put conditions.json next to the experiment; open it as
experiment.html?participant={example_id}&session=1)
-----------------------------------------------------------------------------------------------
const participant = jsPsych.data.getURLVariable('participant');
const session = Number(jsPsych.data.getURLVariable('session'));
const libra = await (await fetch('conditions.json')).json();   // inside an async function
const condition = libra.participants[participant][session - 1];
jsPsych.data.addProperties({{participant, session, condition}});


lab.js and other browser experiments (plain JavaScript, same URL as above)
-----------------------------------------------------------------------------------------------
const url = new URLSearchParams(window.location.search);
const participant = url.get('participant');
const session = Number(url.get('session'));
const libra = await (await fetch('conditions.json')).json();   // inside an async function
const condition = libra.participants[participant][session - 1];
// lab.js: store it, for example this.parameters.condition = condition (in a component's script)


Note for online studies: these files assume that each {one}'s ID is known before the first
{period}. If a recruitment platform assigns IDs as people arrive, give each newcomer the next
unused ID of the schedule, in table order, and pass that ID to the experiment.
"""


def write_experiment_files(res: Result, folder, stem: str, run_id: str = "") -> list[Path]:
    """Write <stem>_experiment/ with the lookup files and the README; return the paths written."""
    spec = res.spec
    base = Path(folder) / f"{stem}{FOLDER_SUFFIX}"
    (base / "conditions").mkdir(parents=True, exist_ok=True)
    table = conditions_table(res)
    out = []
    p = base / "all_conditions.csv"
    table.to_csv(p, index=False, encoding="utf-8-sig")
    out.append(p)
    p = base / "conditions.json"
    p.write_text(json.dumps(conditions_json(res, run_id), indent=2, ensure_ascii=False), encoding="utf-8")
    out.append(p)
    used: dict[str, int] = {}
    for sid, g in table.groupby("id", sort=False):
        name = _file_name(sid)
        used[name] = used.get(name, 0) + 1
        if used[name] > 1:                         # two IDs that differ only in unsafe characters
            name = f"{name}_{used[name]}"
        p = base / "conditions" / f"{name}.csv"
        g.drop(columns="id").to_csv(p, index=False, encoding="utf-8-sig")
        out.append(p)
    groups = [c for c in table.columns if c not in ("id", "session", "condition")]
    first = table.iloc[0]
    blind_text = ("\nBlinding is on: the conditions are codes. The code key is not in this folder; it stays "
                  "with the person\nwho holds the full schedule.\n" if res.codes else "")
    p = base / "README.txt"
    title = f"Files for experiment software, made by LIBRA {__version__}" + (f" (run {run_id})" if run_id else "")
    p.write_text(README.format(
        title=title, rule="=" * len(title),
        one=spec.noun(False), period=spec.period(), periods=spec.period(True),
        group_text="".join(f"{g}, " for g in groups), blind_text=blind_text,
        example_id=first["id"], example_cond=first["condition"]), encoding="utf-8")
    out.append(p)
    return out
