"""Design specification: everything the user chooses, plus validation."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Literal

import pandas as pd

def plural_of(word: str) -> str:
    """English plural of the last word: week -> weeks, batch -> batches, study day -> study days."""
    w = word.strip()
    if not w:
        return w
    low = w.lower()
    if len(w) > 1 and w.split()[-1].isupper():          # acronyms: NHP -> NHPs, MRI -> MRIs
        return w + "s"
    if low.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    if low.endswith("y") and len(low) > 1 and low[-2] not in "aeiou":
        return w[:-1] + "ies"
    return w + "s"


def soft_lower(word: str) -> str:
    """Lower-case the first letter for use inside a sentence, unless it starts an acronym (MRI scan)."""
    if len(word) > 1 and word[0].isupper() and word[1].isupper():
        return word
    return word[:1].lower() + word[1:]


def cap_first(word: str) -> str:
    return word[:1].upper() + word[1:]


Level = Literal["required", "preferred", "off"]
Scope = Literal["overall", "groups"]
Mode = Literal["variety", "speed"]


@dataclass
class DesignSpec:
    # --- subjects -------------------------------------------------------------
    subjects: pd.DataFrame                    # must contain `id_column`; other columns = attributes
    id_column: str = "subject"
    strata: list[str] = field(default_factory=list)   # columns to balance within (e.g. sex, cohort)

    # --- treatments & periods -------------------------------------------------
    treatments: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)   # allocation ratio (parallel / incomplete)
    n_periods: int = 1                        # total periods, including fixed ones
    fixed: dict[int, str] = field(default_factory=dict)       # 1-based period -> label given to everyone
    period_name: str = "Period"               # as typed; used in column headers ("Week 1")
    period_plural: str = ""                   # empty: made from period_name ("Weeks")

    # --- per-subject rules ----------------------------------------------------
    min_per_subject: int = 1                  # times each subject gets each treatment (min)
    max_per_subject: int = 1                  # ... and max
    allow_back_to_back: bool = False          # same treatment in two consecutive periods

    # --- forbidden patterns ---------------------------------------------------
    forbidden_transitions: list[tuple[str, str]] = field(default_factory=list)  # A directly followed by B
    forbidden_periods: list[tuple[str, int]] = field(default_factory=list)      # treatment not in period
    order_rules: list[tuple[str, str]] = field(default_factory=list)            # A never after B

    # --- balance --------------------------------------------------------------
    period_balance: Level = "required"
    carryover_balance: Level = "preferred"
    spread_balance: Level = "preferred"       # within each consecutive period pair
    cooccurrence_balance: Level = "preferred" # incomplete designs: pairs given to the same subject
    # Full-list criterion: limit how well someone who holds the whole list (and knows a subject's
    # group) can predict the rest of a subject's schedule after two periods. Off by default; it
    # comes after co-occurrence and before spread, and can only be "preferred" or "off".
    fulllist_balance: Level = "off"
    balance_scope: Scope = "groups"           # carry-over/spread: overall only, or also per group

    # --- enrollment blocks (clinical) -----------------------------------------
    block_sizes: list[int] = field(default_factory=list)      # empty = no blocking

    # --- randomization & solver -----------------------------------------------
    seed: int = 1
    time_limit: float = 60.0
    blind: bool = False
    # "variety": the final choice lists all equally balanced designs when there are few and draws one
    #            with equal probability (otherwise a random walk among them); uses the full time limit.
    # "speed":   a short random-objective choice among the best designs (faster, less varied).
    randomization: Mode = "variety"
    solver: Literal["highs", "gurobi"] = "highs"   # gurobi only when gurobipy is installed and licensed
    # Reproducible mode: the search is limited by solver work instead of wall-clock time, so the same
    # seed and settings give the same schedule on any computer (time_limit is then the nominal effort,
    # about that many seconds on a 2024 laptop).
    deterministic: bool = True

    # --- wording used in reports ----------------------------------------------
    subject_noun: str = "subject"             # e.g. animal, participant, patient
    subject_plural: str = "subjects"

    # --- extending an existing schedule ----------------------------------------
    # subject ID -> treatment labels of the randomized periods. These subjects keep their sequence;
    # the solver only places the others, balancing the whole design.
    locked: dict[str, list[str]] = field(default_factory=dict)
    locked_blocks: dict[str, str] = field(default_factory=dict)   # their enrollment block labels

    # ------------------------------------------------------------------------
    @property
    def randomized_periods(self) -> list[int]:
        """0-based indices of periods that are randomized (not fixed)."""
        return [k for k in range(self.n_periods) if (k + 1) not in self.fixed]

    @property
    def adjacent_pairs(self) -> list[tuple[int, int]]:
        """Pairs of positions (into randomized_periods) that are consecutive in time."""
        rp = self.randomized_periods
        return [(j, j + 1) for j in range(len(rp) - 1) if rp[j + 1] == rp[j] + 1]

    @property
    def n_subjects(self) -> int:
        return len(self.subjects)

    @property
    def is_complete(self) -> bool:
        """Every subject receives every treatment equally often."""
        p, t = len(self.randomized_periods), len(self.treatments)
        return self.min_per_subject == self.max_per_subject and p == t * self.max_per_subject

    def noun(self, plural: bool = True, cap: bool = False) -> str:
        """The word for a subject in reports ('animals', 'Participant', ...)."""
        one = self.subject_noun.strip() or "subject"
        w = (self.subject_plural.strip() or plural_of(one)) if plural else one
        return cap_first(w) if cap else soft_lower(w)

    def period(self, plural: bool = False, cap: bool = False) -> str:
        """The word for one step of the schedule in sentences ('week', 'Sessions', 'MRI scans', ...)."""
        one = self.period_name.strip() or "Period"
        w = (self.period_plural.strip() or plural_of(one)) if plural else one
        return cap_first(w) if cap else soft_lower(w)

    def weight(self, t: str) -> float:
        if self.is_complete:
            return 1.0
        return float(self.weights.get(t, 1.0))

    def summary(self) -> dict:
        d = asdict(self)
        d.pop("subjects")
        d["n_subjects"] = self.n_subjects
        return d


def validate(spec: DesignSpec) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    errors, warnings = [], []
    T = spec.treatments
    p = len(spec.randomized_periods)
    df = spec.subjects

    if spec.id_column not in df.columns:
        errors.append(f"Subject table has no '{spec.id_column}' column.")
    elif df[spec.id_column].duplicated().any():
        dup = df.loc[df[spec.id_column].duplicated(), spec.id_column].tolist()[:5]
        errors.append(f"Duplicate subject IDs: {dup}")
    if len(df) == 0:
        errors.append("No subjects.")
    for s in spec.strata:
        if s not in df.columns:
            errors.append(f"Grouping column '{s}' not found in the subject table.")
        elif df[s].isna().any():
            errors.append(f"Grouping column '{s}' has empty values.")

    if len(T) == 0:
        errors.append("Add at least one treatment.")
    if len(set(T)) != len(T):
        errors.append("Treatment names must be unique.")
    if any(not str(t).strip() for t in T):
        errors.append("Treatment names cannot be empty.")
    if spec.n_periods < 1:
        errors.append("Need at least one period.")
    for k in spec.fixed:
        if not 1 <= k <= spec.n_periods:
            errors.append(f"Fixed period {k} is outside 1..{spec.n_periods}.")
    if p == 0:
        errors.append("All periods are fixed: nothing to randomize.")

    if spec.min_per_subject > spec.max_per_subject:
        errors.append("Minimum times per treatment exceeds the maximum.")
    if T and p:
        if p > len(T) * spec.max_per_subject:
            errors.append(f"{p} randomized periods but only {len(T)} treatments × max "
                          f"{spec.max_per_subject} per subject. Raise the maximum or add treatments.")
        if p < len(T) * spec.min_per_subject:
            errors.append(f"{p} randomized periods cannot fit {len(T)} treatments × min "
                          f"{spec.min_per_subject} per subject.")

    names = set(T)
    for a, b in spec.forbidden_transitions + spec.order_rules:
        for x in (a, b):
            if x not in names:
                errors.append(f"Rule refers to unknown treatment '{x}'.")
    for t, k in spec.forbidden_periods:
        if t not in names:
            errors.append(f"Rule refers to unknown treatment '{t}'.")
        if k in spec.fixed:
            warnings.append(f"Period {k} is fixed; the rule for '{t}' there has no effect.")

    if spec.weights and spec.is_complete and len({spec.weights.get(t, 1.0) for t in T}) > 1:
        warnings.append("Allocation ratios are ignored: every subject receives every treatment.")
    if any(w <= 0 for w in spec.weights.values()):
        errors.append("Allocation ratios must be positive.")
    if any(b < 1 for b in spec.block_sizes):
        errors.append("Block sizes must be positive.")
    if spec.randomization not in ("variety", "speed"):
        errors.append("Randomization must be 'variety' or 'speed'.")
    if spec.fulllist_balance not in ("off", "preferred"):
        errors.append("The full-list criterion can only be 'preferred' or 'off'.")
    if spec.solver not in ("highs", "gurobi"):
        errors.append("Solver must be 'highs' or 'gurobi'.")
    if spec.locked and spec.id_column in df.columns:
        ids = set(df[spec.id_column].astype(str))
        missing = [k for k in spec.locked if k not in ids]
        if missing:
            errors.append(f"Kept sequences refer to unknown subjects: {missing[:5]}")
        bad = [k for k, seq in spec.locked.items()
               if len(seq) != p or any(x not in names for x in seq)]
        if bad:
            errors.append(f"Kept sequences do not match the current treatments and periods: {bad[:5]}")
        if len(spec.locked) == len(df):
            errors.append("Every subject already has a sequence: add new subjects to place.")

    if not errors and spec.period_balance == "required":
        # check divisibility to warn that 'required' means "as even as possible"
        n = spec.n_subjects
        if p >= 1 and n % len(T) and spec.is_complete:
            warnings.append(f"{n} subjects is not a multiple of {len(T)} treatments, so periods "
                            f"can only be balanced to within ±1 subject.")
    return errors, warnings
