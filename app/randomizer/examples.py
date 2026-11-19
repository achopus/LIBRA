"""Ready-made example projects for the start screen and `python -m randomizer new --example`."""
from __future__ import annotations

import pandas as pd

from .project import TERMS, Project, default_settings


def _terms(s: dict, preset: str):
    s["terms"] = preset
    s["subject_noun"], s["subject_plural"], s["period_name"], s["period_plural"] = TERMS[preset]


def _ids(prefix: str, n: int, start: int = 1, width: int = 2) -> list[str]:
    return [f"{prefix}{i:0{width}d}" for i in range(start, start + n)]


def rat_crossover() -> Project:
    s = default_settings()
    _terms(s, "Animals · Weeks")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("Vehicle", "Low", "Medium", "High")]
    s["strata"] = ["Sex"]
    s["time_limit"] = 30
    subj = pd.DataFrame({"ID": _ids("M", 12) + _ids("F", 12), "Sex": ["male"] * 12 + ["female"] * 12})
    return Project(name="Rat crossover: 4 doses, 2 sexes", settings=s, subjects=subj,
                   notes="24 rats (12 per sex) each receive vehicle and three doses, one per week.")


def human_crossover() -> Project:
    s = default_settings()
    _terms(s, "Participants · Sessions")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("Placebo", "10 mg", "20 mg")]
    s["blind"] = True
    s["time_limit"] = 20
    s["calendar"].update({"days_between": 7})
    subj = pd.DataFrame({"ID": _ids("P", 18, width=3)})
    return Project(name="Human crossover: 3 sessions, blinded", settings=s, subjects=subj,
                   notes="18 participants, three sessions a week apart, blinding codes for the experimenters.")


def two_sites() -> Project:
    """The worked example of the article: two testing sites, a rule against back-to-back load."""
    s = default_settings()
    _terms(s, "Participants · Sessions")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("CONTROL", "EASY", "MEDIUM", "HARD", "DUAL")]
    s["strata"] = ["Site"]
    s["forbidden_transitions"] = [["HARD", "DUAL"], ["DUAL", "HARD"]]
    subj = pd.DataFrame({"ID": _ids("P", 30), "Site": ["Site 1"] * 15 + ["Site 2"] * 15})
    return Project(name="Two testing sites, no back-to-back load", settings=s, subjects=subj,
                   notes="30 participants at two sites, five conditions in five sessions; HARD and DUAL "
                         "never in consecutive sessions.")


def two_centers() -> Project:
    """The worked example of the article as a clinical crossover trial: two centers, placebo, three
    doses and an active comparator; HIGH and ACTIVE never in consecutive periods. Same structure as
    two_sites (the treatment order matches), so it gives the same schedule for the same seed."""
    s = default_settings()
    _terms(s, "Subjects · Periods")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("PLACEBO", "LOW", "MEDIUM", "HIGH", "ACTIVE")]
    s["strata"] = ["Center"]
    s["forbidden_transitions"] = [["HIGH", "ACTIVE"], ["ACTIVE", "HIGH"]]
    subj = pd.DataFrame({"ID": _ids("P", 30), "Center": ["Center 1"] * 15 + ["Center 2"] * 15})
    return Project(name="Two-center crossover trial", settings=s, subjects=subj,
                   notes="30 patients at two centers, five treatments in five periods; HIGH and ACTIVE "
                         "never in consecutive periods.")


def parallel_blocks() -> Project:
    s = default_settings()
    _terms(s, "Animals · Days")
    s["design"] = "parallel"
    s["treatments"] = [{"name": "Vehicle", "ratio": 1.0}, {"name": "Drug", "ratio": 1.0}]
    s["strata"] = ["Sex"]
    s["blocks_enabled"], s["block_sizes"] = True, [4, 6]
    s["time_limit"] = 20
    subj = pd.DataFrame({"ID": _ids("A", 40), "Sex": ["male", "female"] * 20})
    return Project(name="Parallel groups in blocks", settings=s, subjects=subj,
                   notes="40 mice, two groups, randomized in blocks of 4 or 6 in order of arrival.")


def dose_escalation() -> Project:
    s = default_settings()
    _terms(s, "Participants · Sessions")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("Placebo", "Low", "Medium", "High")]
    s["order_rules"] = [["Low", "Medium"], ["Medium", "High"]]
    s["period_balance"] = "preferred"      # High can never be first, so periods cannot be fully even
    s["blind"] = True
    s["time_limit"] = 20
    subj = pd.DataFrame({"ID": _ids("P", 16, width=3)})
    return Project(name="Dose escalation with placebo", settings=s, subjects=subj,
                   notes="Doses always rise (Low, then Medium, then High); the placebo session is randomized.")


def fixed_last_week() -> Project:
    s = default_settings()
    _terms(s, "Animals · Weeks")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("VEHICLE", "LOW", "HIGH", "NOMINAL", "OTHER")]
    s["fixed"] = [{"period": 6, "label": "MAX"}]
    s["strata"] = ["Sex"]
    s["time_limit"] = 60
    subj = pd.DataFrame({"ID": _ids("M", 15) + _ids("F", 15), "Sex": ["male"] * 15 + ["female"] * 15})
    return Project(name="Crossover with a fixed last week", settings=s, subjects=subj,
                   notes="Five randomized weeks, then the maximal dose (MAX) for every animal in week 6.")


def cages_as_units() -> Project:
    s = default_settings()
    _terms(s, "Animals · Weeks")
    s["treatments"] = [{"name": n, "ratio": 1.0} for n in ("Water", "Drug A", "Drug B")]
    s["cluster_column"] = "Cage"
    s["time_limit"] = 20
    cages = [f"C{i:02d}" for i in range(1, 13) for _ in range(4)]
    subj = pd.DataFrame({"ID": _ids("R", 48), "Cage": cages})
    return Project(name="Cages as units (drinking water)", settings=s, subjects=subj,
                   notes="Treatment is given in the drinking water, so all 4 rats of a cage get the same "
                         "sequence; 12 cages are randomized.")


EXAMPLES = {
    "rat-crossover": rat_crossover,
    "human-crossover": human_crossover,
    "two-centers": two_centers,
    "two-sites": two_sites,
    "parallel-blocks": parallel_blocks,
    "dose-escalation": dose_escalation,
    "fixed-last-week": fixed_last_week,
    "cages": cages_as_units,
}
