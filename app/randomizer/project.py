"""Projects: the study settings, the subject list and every generated schedule in one readable
JSON file (.libra). Used by the desktop app and the command line; no GUI code here.

A project holds a list of runs. Each run keeps the exact solver input (spec) and output, so it can
be shown, exported and re-checked later. A run marked final is locked: settings can still change,
but they only affect new runs.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__
from .solver import Result, Unit
from .spec import DesignSpec, plural_of

EXT = ".libra"
FORMAT = "libra-project"
FORMAT_VERSION = 1

DESIGNS = {
    "crossover": ("Crossover", "Every {one} gets every treatment once, in its own order."),
    "incomplete": ("Incomplete crossover", "Every {one} gets some of the treatments, one per {period}."),
    "replicated": ("Replicated crossover", "Every {one} gets every treatment more than once."),
    "parallel": ("Parallel groups", "Every {one} gets a single treatment."),
}

# wording presets
TERMS = {                    # name -> (one subject, several, one period, several periods)
    "Animals · Weeks": ("animal", "animals", "Week", "Weeks"),
    "Animals · Days": ("animal", "animals", "Day", "Days"),
    "Mice · Days": ("mouse", "mice", "Day", "Days"),
    "Participants · Sessions": ("participant", "participants", "Session", "Sessions"),
    "Patients · Visits": ("patient", "patients", "Visit", "Visits"),
    "Subjects · Periods": ("subject", "subjects", "Period", "Periods"),
}
LEVELS = ("required", "preferred", "off")


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_seed() -> int:
    return random.SystemRandom().randint(1, 999_999)


def default_settings() -> dict:
    return {
        "design": "crossover",
        "treatments": [{"name": n, "ratio": 1.0} for n in ("Vehicle", "Low dose", "High dose")],
        "periods_per_subject": 2,          # incomplete designs
        "repeats": 2,                      # replicated designs
        "back_to_back": False,
        "fixed": [],                       # [{"period": 6, "label": "MAX"}]
        "terms": "Animals · Weeks",
        "subject_noun": "animal", "subject_plural": "animals", "period_name": "Week", "period_plural": "Weeks",
        "id_column": "ID",
        "strata": [],
        "cluster_column": "",              # e.g. "Cage": all animals of a cage get the same sequence
        "forbidden_transitions": [], "forbidden_periods": [], "order_rules": [],
        "period_balance": "required", "carryover_balance": "preferred",
        "cooccurrence_balance": "preferred", "spread_balance": "preferred", "fulllist_balance": "off",
        "balance_scope": "groups",
        "blocks_enabled": False, "block_sizes": [4],
        "picture_dpi": 300,                # resolution of exported and shown pictures
        "export_experiment": False,        # also write files for experiment software when exporting
        "seed": new_seed(), "time_limit": 60, "randomization": "variety", "blind": False,
        "solver": "highs", "deterministic": True,
        "calendar": {"start_date": "", "days_between": 7, "skip_weekends": True, "holidays": [],
                     "start_column": ""},
    }


# ----------------------------------------------------------------------------- JSON helpers
def _plain(o):
    """json.dumps default: numpy and pandas scalars to plain Python."""
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if np.isnan(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serializable: {type(o)}")


def df_to_json(df: pd.DataFrame) -> dict:
    d = json.loads(df.to_json(orient="split", index=False, date_format="iso"))
    return {"columns": d["columns"], "data": d["data"]}


def df_from_json(d: dict) -> pd.DataFrame:
    return pd.DataFrame(d.get("data", []), columns=d.get("columns", []))


def fingerprint(df: pd.DataFrame) -> str:
    """Short checksum of a schedule (e.g. 3F9A-0C21-77BE) for preregistration and audits."""
    clean = df.astype(object).where(df.notna(), "").astype(str)
    h = hashlib.sha256(clean.to_csv(index=False, lineterminator="\n").encode("utf-8")).hexdigest().upper()
    return f"{h[:4]}-{h[4:8]}-{h[8:12]}"


def spec_to_dict(spec: DesignSpec) -> dict:
    d = {f.name: getattr(spec, f.name) for f in dataclasses.fields(spec) if f.name != "subjects"}
    d["fixed"] = {str(k): v for k, v in spec.fixed.items()}
    d["subjects"] = df_to_json(spec.subjects)
    return json.loads(json.dumps(d, default=_plain))


def spec_from_dict(d: dict) -> DesignSpec:
    d = dict(d)
    d.setdefault("deterministic", False)    # project files without this field used wall-clock time limits
    names = {f.name for f in dataclasses.fields(DesignSpec)}
    subjects = df_from_json(d.pop("subjects"))
    d = {k: v for k, v in d.items() if k in names}
    d["fixed"] = {int(k): v for k, v in d.get("fixed", {}).items()}
    d["forbidden_transitions"] = [tuple(x) for x in d.get("forbidden_transitions", [])]
    d["forbidden_periods"] = [(a, int(k)) for a, k in d.get("forbidden_periods", [])]
    d["order_rules"] = [tuple(x) for x in d.get("order_rules", [])]
    return DesignSpec(subjects=subjects, **d)


def result_to_dict(res: Result) -> dict:
    d = {"schedule": df_to_json(res.schedule), "period_columns": res.period_columns,
         "assign": res.assign.tolist(), "units": [dataclasses.asdict(u) for u in res.units],
         "subject_unit_ids": [np.asarray(a).tolist() for a in res.subject_unit_ids],
         "codes": res.codes, "status": res.status, "proven_optimal": res.proven_optimal,
         "formulation": res.formulation, "violations": res.violations, "solve_seconds": res.solve_seconds,
         "warnings": res.warnings, "levels": res.levels, "randomization": res.randomization,
         "notes": res.notes, "checks": res.checks, "criteria": res.criteria,
         "reproducible": res.reproducible, "work_seconds": res.work_seconds}
    return json.loads(json.dumps(d, default=_plain))


def result_from_dict(d: dict, spec: DesignSpec) -> Result:
    return Result(spec=spec, schedule=df_from_json(d["schedule"]), period_columns=d["period_columns"],
                  assign=np.array(d["assign"], dtype=int).reshape(len(d["assign"]), -1),
                  units=[Unit(**u) for u in d["units"]],
                  subject_unit_ids=[np.array(a, dtype=int) for a in d["subject_unit_ids"]],
                  codes=d.get("codes"), status=d["status"], proven_optimal=d["proven_optimal"],
                  formulation=d["formulation"], violations=d.get("violations", {}),
                  solve_seconds=d.get("solve_seconds", 0.0), warnings=d.get("warnings", []),
                  levels=d.get("levels", {}), randomization=d.get("randomization", {}),
                  notes=d.get("notes", []), checks=d.get("checks", {}), criteria=d.get("criteria", {}),
                  reproducible=d.get("reproducible"), work_seconds=d.get("work_seconds"))


# ----------------------------------------------------------------------------- spec building
class SpecError(ValueError):
    """The settings cannot be turned into a design; `step` says which page to fix."""

    def __init__(self, step: str, message: str):
        super().__init__(message)
        self.step = step


def treatment_names(settings: dict) -> list[str]:
    return [str(t.get("name", "")).strip() for t in settings["treatments"] if str(t.get("name", "")).strip()]


def randomized_count(settings: dict) -> int:
    """Number of randomized periods per subject implied by the design type."""
    t = max(1, len(treatment_names(settings)))
    design = settings["design"]
    if design == "crossover":
        return t
    if design == "incomplete":
        return int(min(max(1, settings.get("periods_per_subject", 2)), max(1, t - 1)))
    if design == "replicated":
        return t * max(2, int(settings.get("repeats", 2)))
    return 1


def build_spec(settings: dict, subjects: pd.DataFrame, locked=None, locked_blocks=None):
    """Turn project settings into a DesignSpec. Returns (spec, cluster) where cluster is None or
    {"column": name, "subjects": the full subject table} when cages (etc.) are the unit."""
    s = settings
    df = subjects.copy()
    df = df.loc[~df.apply(lambda r: all(str(v).strip() in ("", "nan", "None") for v in r), axis=1)]
    df = df.reset_index(drop=True)
    idc = s["id_column"]
    if df.empty:
        raise SpecError("subjects", f"Add {s['subject_plural'] or 'subjects'} on the first page.")
    if idc not in df.columns:
        raise SpecError("subjects", f"Choose the column that holds the {s['subject_noun']} IDs.")
    df[idc] = df[idc].astype(str).str.strip()
    names = treatment_names(s)
    ratios = {str(t["name"]).strip(): float(t.get("ratio") or 1.0) for t in s["treatments"]
              if str(t.get("name", "")).strip()}
    design = s["design"]
    n_rand = randomized_count(s)
    mn, mx, b2b = 1, 1, False
    if design == "incomplete":
        mn = 0
    elif design == "replicated":
        mn = mx = max(2, int(s.get("repeats", 2)))
        b2b = bool(s.get("back_to_back", False))
    elif design == "parallel":
        mn = 0
    fixed = {}
    for f in s.get("fixed", []):
        lab = str(f.get("label", "")).strip()
        if lab:
            try:
                fixed[int(f["period"])] = lab
            except (TypeError, ValueError):
                raise SpecError("treatments", "Fixed periods need a whole-number position.") from None
    multi = n_rand > 1
    strata = [c for c in s.get("strata", []) if c in df.columns and c != idc]
    blocks = [int(b) for b in s.get("block_sizes", [])] if s.get("blocks_enabled") else []
    cluster = None
    cl = s.get("cluster_column", "")
    noun, plural, id_col = s["subject_noun"], s["subject_plural"], idc
    if cl:
        if cl not in df.columns:
            raise SpecError("subjects", f"The unit column '{cl}' is not in the table.")
        key = df[cl].astype(str).str.strip()
        if (key.isin(["", "nan", "None"])).any():
            raise SpecError("subjects", f"Every {noun} needs a value in the '{cl}' column.")
        strata = [c for c in strata if c != cl]
        for c in strata:
            mixed = df.groupby(key)[c].nunique()
            if (mixed > 1).any():
                raise SpecError("subjects", f"'{cl}' {mixed[mixed > 1].index[0]} mixes different values of "
                                            f"'{c}'. All members of a '{cl}' must share their group.")
        units = df.assign(**{cl: key}).groupby(cl, sort=False)[strata].first().reset_index() \
            if strata else pd.DataFrame({cl: list(dict.fromkeys(key))})
        cluster = {"column": cl, "subjects": df}
        df, id_col = units, cl
        noun, plural = cl.strip(), plural_of(cl.strip())
    spec = DesignSpec(
        subjects=df, id_column=id_col, strata=strata, treatments=names, weights=ratios,
        n_periods=n_rand + len(fixed), fixed=fixed, period_name=s["period_name"].strip() or "Period",
        period_plural=str(s.get("period_plural", "")).strip(),
        min_per_subject=mn, max_per_subject=mx, allow_back_to_back=b2b,
        forbidden_transitions=[tuple(x) for x in s.get("forbidden_transitions", [])],
        forbidden_periods=[(a, int(k)) for a, k in s.get("forbidden_periods", [])],
        order_rules=[tuple(x) for x in s.get("order_rules", [])],
        period_balance=s["period_balance"],
        carryover_balance=s["carryover_balance"] if multi else "off",
        spread_balance=s["spread_balance"] if multi else "off",
        cooccurrence_balance=s["cooccurrence_balance"] if design == "incomplete" else "off",
        fulllist_balance=s.get("fulllist_balance", "off") if multi else "off",
        balance_scope=s.get("balance_scope", "groups"), block_sizes=blocks,
        seed=int(s["seed"]), time_limit=float(s["time_limit"]), blind=bool(s.get("blind")),
        randomization=s.get("randomization", "variety"), solver=s.get("solver", "highs"),
        deterministic=bool(s.get("deterministic", True)),
        subject_noun=noun, subject_plural=plural,
        locked=dict(locked or {}), locked_blocks=dict(locked_blocks or {}))
    return spec, cluster


# ----------------------------------------------------------------------------- display transforms
def expand_clusters(res: Result, cluster: dict) -> Result:
    """Unit-level result (one row per cage) -> one row per member, with the unit's sequence."""
    col = cluster["column"]
    members = cluster["subjects"] if isinstance(cluster["subjects"], pd.DataFrame) \
        else df_from_json(cluster["subjects"])
    sched = res.schedule
    extra = [c for c in ("Block",) if c in sched.columns]
    per = sched.assign(_k=sched[col].astype(str)).set_index("_k")[extra + res.period_columns]
    out = members.copy()
    key = out[col].astype(str).str.strip()
    for c in per.columns:
        out[c] = key.map(per[c]).to_numpy()
    n_members = len(out)
    note = (f"The {res.spec.noun(False)} was the unit of randomization: all {n_members} "
            f"{cluster.get('noun', 'members')} received the sequence of their {res.spec.noun(False)}.")
    member_id = cluster.get("id_column") or out.columns[0]
    spec = dataclasses.replace(res.spec, id_column=member_id)
    return dataclasses.replace(res, spec=spec, schedule=out, notes=list(res.notes) + [note])


def apply_replacements(res: Result, replacements: list[dict]) -> Result:
    """Add a row for each replacement subject, who takes over the sequence of a dropout."""
    if not replacements:
        return res
    idc = res.spec.id_column
    df = res.schedule.copy()
    df["Status"] = df.get("Status", "")
    df["Status"] = df["Status"].fillna("")
    for r in replacements:
        hit = np.flatnonzero(df[idc].astype(str).to_numpy() == str(r["old"]))
        if not len(hit):
            continue
        i = hit[0]
        new = df.iloc[[i]].copy()
        new[idc] = r["new"]
        new["Status"] = f"Replaces {r['old']}"
        df.loc[df.index[i], "Status"] = f"Dropped out; replaced by {r['new']}"
        df = pd.concat([df.iloc[:i + 1], new, df.iloc[i + 1:]], ignore_index=True)
    note = (f"{len(replacements)} {res.spec.noun(len(replacements) != 1)} who dropped out "
            f"{'was' if len(replacements) == 1 else 'were'} replaced; each replacement received the "
            f"sequence of the {res.spec.noun(False)} it replaced.")
    return dataclasses.replace(res, schedule=df, notes=list(res.notes) + [note])


# ----------------------------------------------------------------------------- runs and projects
@dataclass
class Run:
    id: str
    created: str
    kind: str                      # "generated" | "extension" | "replacement"
    note: str
    parent: str | None
    settings: dict                 # project settings used
    spec: dict                     # exact solver input
    result: dict                   # exact solver output
    raw_fingerprint: str           # fingerprint of the solver's schedule (what "verify" re-creates)
    cluster: dict | None = None    # {"column", "id_column", "noun", "subjects"} when units were randomized
    replacements: list = field(default_factory=list)
    final: bool = False
    verifications: list = field(default_factory=list)
    app_version: str = __version__
    _cache: object = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        d = {f.name: getattr(self, f.name) for f in dataclasses.fields(self) if not f.name.startswith("_")}
        return json.loads(json.dumps(d, default=_plain))

    @classmethod
    def from_dict(cls, d: dict) -> "Run":
        names = {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}
        return cls(**{k: v for k, v in d.items() if k in names})

    def solver_spec(self) -> DesignSpec:
        return spec_from_dict(self.spec)

    def raw_result(self) -> Result:
        return result_from_dict(self.result, self.solver_spec())

    def view(self) -> Result:
        """The schedule as shown and exported (cages expanded, replacements added)."""
        if self._cache is None:
            res = self.raw_result()
            if self.cluster:
                res = expand_clusters(res, self.cluster)
            res = apply_replacements(res, self.replacements)
            self._cache = res
        return self._cache

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.view().schedule)

    def invalidate(self):
        self._cache = None

    @property
    def label(self) -> str:
        kinds = {"extension": "added subjects", "replacement": "replacement"}
        return self.id + (f" ({kinds[self.kind]})" if self.kind in kinds else "")


@dataclass
class Project:
    name: str = "Untitled study"
    settings: dict = field(default_factory=default_settings)
    subjects: pd.DataFrame = field(default_factory=lambda: pd.DataFrame({"ID": pd.Series(dtype=str)}))
    runs: list = field(default_factory=list)
    log: list = field(default_factory=list)
    notes: str = ""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    created: str = field(default_factory=now)
    modified: str = field(default_factory=now)
    path: str | None = None        # where it was loaded from / saved to (not stored in the file)

    # -------------------------------------------------------------- persistence
    def to_dict(self) -> dict:
        d = {"format": FORMAT, "format_version": FORMAT_VERSION, "app_version": __version__,
             "id": self.id, "name": self.name, "created": self.created, "modified": self.modified,
             "notes": self.notes, "settings": self.settings, "subjects": df_to_json(self.subjects),
             "runs": [r.to_dict() for r in self.runs], "log": self.log}
        return json.loads(json.dumps(d, default=_plain))

    @classmethod
    def from_dict(cls, d: dict) -> "Project":
        if d.get("format") != FORMAT:
            raise ValueError("This is not a LIBRA project file.")
        if int(d.get("format_version", 1)) > FORMAT_VERSION:
            raise ValueError("This project was saved by a newer version of the app. Please update the app.")
        settings = default_settings()
        settings.update(d.get("settings", {}))
        if "period_plural" not in d.get("settings", {}):        # older files: derive it from the name
            settings["period_plural"] = plural_of(settings["period_name"])
        cal = default_settings()["calendar"]
        cal.update(settings.get("calendar") or {})
        settings["calendar"] = cal
        return cls(name=d.get("name", "Untitled study"), settings=settings,
                   subjects=df_from_json(d.get("subjects", {"columns": ["ID"], "data": []})),
                   runs=[Run.from_dict(r) for r in d.get("runs", [])], log=d.get("log", []),
                   notes=d.get("notes", ""), id=d.get("id", uuid.uuid4().hex),
                   created=d.get("created", now()), modified=d.get("modified", now()))

    def save(self, path: str | os.PathLike | None = None):
        path = Path(path or self.path)
        self.modified = now()
        text = json.dumps(self.to_dict(), indent=1, ensure_ascii=False)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)            # never leaves a half-written project behind
        self.path = str(path)

    @classmethod
    def load(cls, path) -> "Project":
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"The project file is damaged ({e}).") from None
        p = cls.from_dict(d)
        p.path = str(path)
        return p

    # -------------------------------------------------------------- runs
    def event(self, what: str, detail: str = ""):
        self.log.append({"time": now(), "event": what, "detail": detail})

    def build_spec(self, **kw):
        return build_spec(self.settings, self.subjects, **kw)

    def run(self, run_id: str) -> Run | None:
        return next((r for r in self.runs if r.id == run_id), None)

    @property
    def final_run(self) -> Run | None:
        return next((r for r in self.runs if r.final), None)

    def next_run_id(self) -> str:
        nums = [int(r.id[1:]) for r in self.runs if r.id[1:].isdigit()]
        return f"R{max(nums, default=0) + 1}"

    def add_run(self, res: Result, *, kind="generated", note="", parent=None, cluster=None,
                replacements=None, settings=None) -> Run:
        res_d = result_to_dict(res)
        raw_fp = fingerprint(df_from_json(res_d["schedule"]))
        cl = None
        if cluster:
            cl = {"column": cluster["column"], "id_column": self.settings["id_column"],
                  "noun": self.settings["subject_plural"], "subjects": df_to_json(cluster["subjects"])}
        run = Run(id=self.next_run_id(), created=now(), kind=kind, note=note, parent=parent,
                  settings=json.loads(json.dumps(settings or self.settings, default=_plain)),
                  spec=spec_to_dict(res.spec), result=res_d, raw_fingerprint=raw_fp, cluster=cl,
                  replacements=list(replacements or []))
        self.runs.append(run)
        many = self.settings["subject_plural"] or "subjects"
        what = {"generated": "Schedule generated", "extension": f"{many[:1].upper() + many[1:]} added",
                "replacement": "Dropout replaced"}.get(kind, "Run added")
        self.event(what, f"{run.id}, seed {res.spec.seed}, fingerprint {run.fingerprint}"
                         + (f", from {parent}" if parent else ""))
        return run

    def mark_final(self, run_id: str):
        for r in self.runs:
            r.final = r.id == run_id
        self.event("Marked final", f"{run_id}, fingerprint {self.run(run_id).fingerprint}")

    def unmark_final(self, reason: str):
        fr = self.final_run
        if fr:
            fr.final = False
            self.event("Final mark removed", f"{fr.id}: {reason}")

    def delete_run(self, run_id: str):
        r = self.run(run_id)
        if r is None:
            return
        if r.final:
            raise ValueError("The final schedule cannot be deleted. Remove the final mark first.")
        self.runs.remove(r)
        self.event("Run deleted", run_id)

    # -------------------------------------------------------------- changes to a final design
    def replacement_run(self, run_id: str, old: str, new: str, note: str = "") -> Run:
        """New run: `new` takes over the sequence of dropout `old` (balance is unchanged)."""
        src = self.run(run_id)
        res = src.view()
        idc = res.spec.id_column
        ids = res.schedule[idc].astype(str)
        if str(old) not in set(ids):
            raise ValueError(f"'{old}' is not in this schedule.")
        if str(new).strip() == "" or str(new) in set(ids):
            raise ValueError(f"Choose a new, unused ID for the replacement (not '{new}').")
        reps = list(src.replacements) + [{"old": str(old), "new": str(new).strip(), "time": now()}]
        run = Run(id=self.next_run_id(), created=now(), kind="replacement", note=note or f"{new} replaces {old}",
                  parent=src.id, settings=src.settings, spec=src.spec, result=src.result,
                  raw_fingerprint=src.raw_fingerprint, cluster=src.cluster, replacements=reps)
        self.runs.append(run)
        self.event("Dropout replaced", f"{run.id}: {new} replaces {old} (from {src.id}), fingerprint {run.fingerprint}")
        return run

    def extension_spec(self, run_id: str, new_subjects: pd.DataFrame, seed: int | None = None) -> DesignSpec:
        """Spec that keeps every subject of `run_id` and places `new_subjects` (same columns)."""
        src = self.run(run_id)
        if src.cluster:
            raise ValueError("Adding subjects is not available when cages (or other units) are randomized.")
        res = src.raw_result()
        spec = src.solver_spec()
        idc = spec.id_column
        new = new_subjects.copy()
        if idc not in new.columns:
            raise ValueError(f"The new {spec.noun()} need an '{idc}' column.")
        new[idc] = new[idc].astype(str).str.strip()
        clash = set(new[idc]) & set(spec.subjects[idc].astype(str))
        clash |= {r["new"] for r in src.replacements} & set(new[idc])
        if clash:
            raise ValueError(f"These IDs are already used: {sorted(clash)[:5]}")
        for c in spec.strata:
            if c not in new.columns or new[c].isna().any():
                raise ValueError(f"Give every new {spec.noun(False)} a value for '{c}'.")
        rp = [res.period_columns[k] for k in spec.randomized_periods]
        sched = res.schedule
        ids = sched[idc].astype(str)
        locked = {i: [str(v) for v in row] for i, row in zip(ids, sched[rp].to_numpy())}
        blocks = dict(zip(ids, sched["Block"].astype(str))) if "Block" in sched.columns else {}
        subjects = pd.concat([spec.subjects, new[[c for c in spec.subjects.columns if c in new.columns]]],
                             ignore_index=True)
        return dataclasses.replace(spec, subjects=subjects, locked=locked, locked_blocks=blocks,
                                   seed=int(seed if seed is not None else new_seed()))
