"""Projects, runs, pre-checks, calendar, exports and the command line (no GUI)."""
import json

import numpy as np
import pandas as pd
import pytest

from randomizer import solve
from randomizer.dates import dated_schedule, working_day
from randomizer.examples import EXAMPLES
from randomizer.prechecks import precheck
from randomizer.project import Project, build_spec, fingerprint


def quick(project: Project, limit=5, **kw):
    project.settings["time_limit"] = limit
    project.settings.update(kw)
    spec, cluster = project.build_spec()
    return project.add_run(solve(spec), cluster=cluster)


@pytest.mark.parametrize("key", list(EXAMPLES))
def test_examples_have_no_errors_and_solve(key):
    p = EXAMPLES[key]()
    errors = [f for f in precheck(p.settings, p.subjects) if f.level == "error"]
    assert not errors, errors
    run = quick(p)
    assert len(run.view().schedule) == len(p.subjects)


def test_save_load_keeps_runs_and_fingerprint(tmp_path):
    p = EXAMPLES["rat-crossover"]()
    run = quick(p)
    p.mark_final(run.id)
    f = tmp_path / "study.libra"
    p.save(f)
    q = Project.load(f)
    assert q.final_run.id == run.id
    assert q.final_run.fingerprint == run.fingerprint
    assert q.final_run.view().schedule.equals(run.view().schedule)
    assert json.loads(f.read_text(encoding="utf-8"))["format"] == "libra-project"
    with pytest.raises(ValueError):
        q.delete_run(run.id)                       # the final schedule is locked


def test_fingerprint_changes_with_any_cell():
    df = pd.DataFrame({"ID": ["a", "b"], "Week 1": ["X", "Y"]})
    other = df.copy()
    other.iat[1, 1] = "X"
    assert fingerprint(df) != fingerprint(other)
    assert fingerprint(df) == fingerprint(df.copy())


def test_extension_keeps_everyone_and_stays_balanced():
    p = EXAMPLES["rat-crossover"]()
    run = quick(p)
    new = pd.DataFrame({"ID": [f"N{i}" for i in range(8)], "Sex": ["male", "female"] * 4})
    spec = p.extension_spec(run.id, new, seed=5)
    spec.time_limit = 5
    res = solve(spec)
    ext = p.add_run(res, kind="extension", parent=run.id)
    old = run.view().schedule.set_index("ID")
    now = ext.view().schedule.set_index("ID")
    cols = run.view().period_columns
    assert (now.loc[old.index, cols] == old[cols]).all().all()
    assert len(now) == 32
    counts = now[cols].apply(lambda c: c.value_counts()).to_numpy()
    assert counts.min() == counts.max() == 8          # 32 animals, 4 doses: 8 per dose per week


def test_replacement_takes_the_dropouts_sequence():
    p = EXAMPLES["human-crossover"]()
    run = quick(p)
    rep = p.replacement_run(run.id, "P003", "P101", "withdrew")
    sch = rep.view().schedule
    a, b = sch[sch.ID == "P003"].iloc[0], sch[sch.ID == "P101"].iloc[0]
    cols = rep.view().period_columns
    assert list(a[cols]) == list(b[cols])
    assert a["Status"].startswith("Dropped out") and b["Status"] == "Replaces P003"
    assert rep.fingerprint != run.fingerprint and rep.raw_fingerprint == run.raw_fingerprint
    with pytest.raises(ValueError):
        p.replacement_run(rep.id, "P004", "P101")   # ID already used in that run


def test_cages_share_a_sequence():
    p = EXAMPLES["cages"]()
    run = quick(p)
    sch = run.view().schedule
    cols = run.view().period_columns
    assert len(sch) == 48
    assert (sch.groupby("Cage")[cols].nunique() == 1).all().all()
    assert len(run.raw_result().schedule) == 12
    assert "unit of randomization" in " ".join(run.view().notes)


def test_cage_mixing_groups_is_reported():
    p = EXAMPLES["cages"]()
    p.subjects["Sex"] = ["male", "female"] * 24      # every cage mixes sexes
    p.settings["strata"] = ["Sex"]
    errs = [f for f in precheck(p.settings, p.subjects) if f.level == "error"]
    assert errs and "mixes" in errs[0].text


def test_prechecks_find_contradictions():
    p = EXAMPLES["dose-escalation"]()
    p.settings["order_rules"] = [["Low", "High"], ["High", "Low"]]
    f = precheck(p.settings, p.subjects)
    assert any(x.level == "error" and "contradict" in x.text for x in f)
    p = EXAMPLES["dose-escalation"]()
    p.settings["period_balance"] = "required"
    f = precheck(p.settings, p.subjects)
    assert any(x.level == "error" and "Preferred" in x.text for x in f)


def test_calendar_moves_weekends_and_holidays():
    from datetime import date
    assert working_day(date(2026, 11, 7), True, set()) == date(2026, 11, 9)      # Sat -> Mon
    assert working_day(date(2026, 12, 24), True, {date(2026, 12, 24)}) == date(2026, 12, 25)
    p = EXAMPLES["rat-crossover"]()
    run = quick(p)
    cal = {"start_date": "2026-11-02", "days_between": 7, "skip_weekends": True,
           "holidays": ["2026-11-16"], "start_column": ""}
    df = dated_schedule(run.view(), cal)
    days = sorted(df["Date"].unique())
    assert [d.isoformat() for d in days] == ["2026-11-02", "2026-11-09", "2026-11-17", "2026-11-23"]


def test_exports_keep_the_blinding_separate(tmp_path):
    from randomizer.export import write_outputs
    p = EXAMPLES["human-crossover"]()
    run = quick(p)
    res = run.view()
    paths = write_outputs(res, tmp_path, "s", fmt="csv", png=True)
    names = {q.name for q in paths}
    assert {"s.csv", "s_BLINDED_for_experimenters.csv", "s_CODE_KEY_keep_separate.csv",
            "s_schedule.png"} <= names
    blinded = (tmp_path / "s_BLINDED_for_experimenters.csv").read_text(encoding="utf-8-sig")
    assert not any(t in blinded for t in ("Placebo", "10 mg", "20 mg"))
    paths = write_outputs(res, tmp_path, "x", fmt="xlsx", extra={"Audit log": pd.DataFrame(p.log)})
    xl = pd.ExcelFile(tmp_path / "x.xlsx")
    assert "Audit log" in xl.sheet_names and "Code key (keep separate)" not in xl.sheet_names


def test_command_line(tmp_path, capsys):
    from randomizer.cli import main
    f = str(tmp_path / "s.libra")
    main(["new", f, "--example", "parallel-blocks"])
    main(["run", f, "--time-limit", "5", "--seed", "7", "--in-process"])
    main(["final", f, "R1"])
    main(["export", f, "--run", "final", "--format", "csv", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "R1" in out and (tmp_path / "out" / "s_R1.csv").exists()
    assert Project.load(f).final_run.id == "R1"


def test_custom_words_reach_the_methods_text():
    from randomizer.export import methods_text
    p = EXAMPLES["human-crossover"]()
    run = quick(p)
    txt = methods_text(run.view())
    assert "18 participants" in txt and "session" in txt and "subjects" not in txt


def test_any_words_work():
    from randomizer.export import methods_text
    from randomizer.spec import plural_of, soft_lower
    assert [plural_of(w) for w in ("Week", "Batch", "Study day", "Assay", "Box", "MRI scan")] == \
        ["Weeks", "Batches", "Study days", "Assays", "Boxes", "MRI scans"]
    assert soft_lower("MRI scan") == "MRI scan" and soft_lower("Session") == "session"
    p = EXAMPLES["rat-crossover"]()
    p.settings.update({"subject_noun": "Mouse", "subject_plural": "Mice", "period_name": "Test batch",
                       "period_plural": "Test batches"})
    txt = methods_text(quick(p).view())
    assert "24 mice" in txt and "test batches" in txt and "Test batchs" not in txt


def test_old_projects_get_a_period_plural(tmp_path):
    p = EXAMPLES["parallel-blocks"]()
    d = p.to_dict()
    del d["settings"]["period_plural"]
    assert Project.from_dict(d).settings["period_plural"] == "Days"


def test_pictures_use_the_chosen_resolution(tmp_path):
    from PIL import Image
    from randomizer.export import write_outputs
    p = EXAMPLES["rat-crossover"]()
    assert p.settings["picture_dpi"] == 300
    res = quick(p).view()
    for dpi in (300, 150):
        f = write_outputs(res, tmp_path, f"d{dpi}", fmt="csv", png=True, dpi=dpi)[-1]
        assert round(Image.open(f).info["dpi"][0]) == dpi
    big, small = (Image.open(tmp_path / f"d{d}_schedule.png").size[0] for d in (300, 150))
    assert abs(big / small - 2) < 0.05


# ----------------------------------------------------------------------------- citation and experiment files
def test_methods_text_names_and_cites_libra():
    from randomizer import CITE_SHORT, __version__
    from randomizer.export import methods_text
    run = quick(EXAMPLES["two-sites"](), randomization="speed")
    text = methods_text(run.view())
    assert f"LIBRA {__version__} ({CITE_SHORT})" in text
    assert "solved with HiGHS" in text


def _snippet(readme: str, title: str) -> str:
    """The code block under a heading of the experiment README."""
    block = readme.split(title, 1)[1].split("-" * 20, 1)[1]
    return block.split("\n", 1)[1].split("\n\n\n", 1)[0]


def test_experiment_files_and_their_code(tmp_path):
    from types import SimpleNamespace
    from randomizer.export import write_outputs
    run = quick(EXAMPLES["two-sites"](), randomization="speed")
    res = run.view()
    paths = write_outputs(res, tmp_path, "study", fmt="csv", experiment=True, run_id=run.id)
    folder = tmp_path / "study_experiment"
    table = pd.read_csv(folder / "all_conditions.csv", dtype={"id": str})
    assert list(table.columns) == ["id", "Site", "session", "condition"]
    assert len(table) == 30 * 5
    data = json.loads((folder / "conditions.json").read_text(encoding="utf-8"))
    p03 = res.schedule.set_index("ID").loc["P03", res.period_columns].tolist()
    assert data["participants"]["P03"] == p03
    assert data["groups"]["P20"] == {"Site": "Site 2"}
    assert len(list((folder / "conditions").glob("*.csv"))) == 30
    assert folder / "README.txt" in paths

    # the PsychoPy and OpenSesame code in the README really finds the right condition
    readme = (folder / "README.txt").read_text(encoding="utf-8")
    ns = {"_thisDir": str(folder), "expInfo": {"participant": "P03", "session": "002"},
          "thisExp": SimpleNamespace(addData=lambda *a: None)}
    exec(_snippet(readme, "PsychoPy ("), ns)
    assert ns["condition"] == p03[1]
    var = SimpleNamespace(participant="P03", session=5)
    ns = {"pool": {"all_conditions.csv": str(folder / "all_conditions.csv")}, "var": var}
    exec(_snippet(readme, "OpenSesame ("), ns)
    assert var.condition == p03[4]


def test_experiment_files_use_codes_when_blinded(tmp_path):
    from randomizer.export import write_outputs
    p = EXAMPLES["human-crossover"]()
    run = quick(p, randomization="speed")
    res = run.view()
    assert res.codes
    write_outputs(res, tmp_path, "blind", fmt="csv", experiment=True)
    folder = tmp_path / "blind_experiment"
    text = "".join(f.read_text(encoding="utf-8") for f in folder.rglob("*") if f.is_file())
    for name in res.spec.treatments:
        assert name not in text.replace("generated_by", "")
    assert set(json.loads((folder / "conditions.json").read_text(encoding="utf-8"))["conditions"]) \
        == set(res.codes.values())
