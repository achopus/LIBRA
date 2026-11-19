"""Command line for project files (the same .libra files the desktop app uses).

    python -m randomizer new study.libra --example rat-crossover
    python -m randomizer info study.libra
    python -m randomizer run study.libra [--seed 123] [--time-limit 60] [--note "pilot"]
    python -m randomizer export study.libra [--run final] [--format xlsx|csv] [--png] [--experiment] [--out folder]
    python -m randomizer verify study.libra [--run final]
    python -m randomizer final study.libra R2
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .project import Project, SpecError
from .solver import DesignError


def _say(msg):
    print(f"  {msg}", flush=True)


def _pick_run(proj: Project, which: str):
    if which == "final":
        run = proj.final_run
        if run is None:
            sys.exit("No run is marked final. Use --run latest or a run ID such as R1.")
        return run
    if which == "latest":
        if not proj.runs:
            sys.exit("This project has no runs yet. Create one with: run")
        return proj.runs[-1]
    run = proj.run(which)
    if run is None:
        sys.exit(f"No run called {which}. Runs: {', '.join(r.id for r in proj.runs) or 'none'}")
    return run


def cmd_new(a):
    from .examples import EXAMPLES
    path = Path(a.project)
    if path.exists() and not a.force:
        sys.exit(f"{path} exists. Use --force to overwrite.")
    if a.example:
        if a.example not in EXAMPLES:
            sys.exit(f"Unknown example. Choose one of: {', '.join(EXAMPLES)}")
        proj = EXAMPLES[a.example]()
    else:
        proj = Project(name=path.stem)
    proj.event("Project created", "command line")
    proj.save(path)
    print(f"Created {path}")


def cmd_info(a):
    from .prechecks import precheck, summary_line
    proj = Project.load(a.project)
    print(f"{proj.name}\n  {summary_line(proj.settings, proj.subjects)}")
    for f in precheck(proj.settings, proj.subjects):
        print(f"  [{f.level}] {f.text}")
    for r in proj.runs:
        res = r.view()
        flag = "  FINAL" if r.final else ""
        print(f"  {r.label:24} {r.created}  seed {res.spec.seed:<7} {r.fingerprint}  {res.status}{flag}")


def cmd_run(a):
    from .prechecks import precheck
    from .runner import solve_isolated
    proj = Project.load(a.project)
    if a.seed is not None:
        proj.settings["seed"] = a.seed
    if a.time_limit is not None:
        proj.settings["time_limit"] = a.time_limit
    errors = [f for f in precheck(proj.settings, proj.subjects) if f.level == "error"]
    if errors:
        sys.exit("Cannot generate:\n" + "\n".join(f"  - {f.text}" for f in errors))
    try:
        spec, cluster = proj.build_spec()
        print(f"Solving (seed {spec.seed}, up to {spec.time_limit:.0f} s)...")
        res = solve_isolated(spec, progress=_say) if not a.in_process else __import__(
            "randomizer.solver", fromlist=["solve"]).solve(spec, progress=_say)
    except (SpecError, DesignError) as e:
        sys.exit(f"No design: {e}")
    run = proj.add_run(res, note=a.note or "", cluster=cluster)
    proj.save()
    print(f"{run.id}: {res.status}, fingerprint {run.fingerprint}. Saved to {proj.path}")
    from .export import check_outcomes_text
    if check_outcomes_text(res):
        print(f"  {check_outcomes_text(res)}.")
    for w in res.warnings:
        print(f"  [warning] {w}")


def cmd_export(a):
    from .export import write_outputs
    from .dates import check as cal_check
    proj = Project.load(a.project)
    run = _pick_run(proj, a.run)
    res = run.view()
    cal = proj.settings["calendar"] if a.dates else None
    if cal:
        problems = cal_check(cal, res)
        if problems:
            sys.exit("Calendar: " + " ".join(problems))
    out = Path(a.out or Path(a.project).parent)
    stem = a.name or f"{Path(a.project).stem}_{run.id}"
    import pandas as pd
    extra = {"Audit log": pd.DataFrame(proj.log)} if a.format == "xlsx" else None
    dpi = a.dpi or int(proj.settings.get("picture_dpi", 300))
    paths = write_outputs(res, out, stem, fmt=a.format, png=a.png, balance_png=a.balance_png, dpi=dpi,
                          calendar=cal, extra=extra, experiment=a.experiment, run_id=run.id)
    proj.event("Exported", f"{run.id} as {a.format} (command line)")
    proj.save()
    for p in paths:
        print(p)


def cmd_verify(a):
    from .project import fingerprint, result_to_dict, df_from_json
    from .runner import solve_isolated
    proj = Project.load(a.project)
    run = _pick_run(proj, a.run)
    spec = run.solver_spec()
    print(f"Re-running {run.id} (seed {spec.seed}, up to {spec.time_limit:.0f} s)...")
    res = solve_isolated(spec, progress=_say)
    fp = fingerprint(df_from_json(result_to_dict(res)["schedule"]))
    same = fp == run.raw_fingerprint
    proj.event("Verified" if same else "Verification differed", f"{run.id}: {fp} vs {run.raw_fingerprint}")
    run.verifications.append({"fingerprint": fp, "same": same})
    proj.save()
    if same:
        print(f"Identical: the same settings and seed reproduce {run.id} ({fp}).")
    else:
        print(f"Different ({fp} instead of {run.raw_fingerprint}). Designs that stop at the time limit can "
              f"differ between runs and computers; the saved schedule remains the record.")
        sys.exit(1)


def cmd_final(a):
    proj = Project.load(a.project)
    run = _pick_run(proj, a.run)
    proj.mark_final(run.id)
    proj.save()
    print(f"{run.id} is now the final schedule ({run.fingerprint}).")


def main(argv=None):
    from . import APP_TITLE
    ap = argparse.ArgumentParser(prog="libra", description=f"{APP_TITLE} {__version__}")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("new", help="create a project file")
    p.add_argument("project"); p.add_argument("--example"); p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_new)
    p = sub.add_parser("info", help="show settings checks and runs")
    p.add_argument("project"); p.set_defaults(fn=cmd_info)
    p = sub.add_parser("run", help="generate a new schedule and save it in the project")
    p.add_argument("project"); p.add_argument("--seed", type=int); p.add_argument("--time-limit", type=float)
    p.add_argument("--note"); p.add_argument("--in-process", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("export", help="write CSV/Excel (and PNG) files for a run")
    p.add_argument("project"); p.add_argument("--run", default="latest", help="final, latest or an ID like R2")
    p.add_argument("--format", choices=["xlsx", "csv"], default="xlsx")
    p.add_argument("--png", action="store_true", help="schedule picture")
    p.add_argument("--balance-png", action="store_true", help="balance pictures")
    p.add_argument("--dpi", type=int, help="picture resolution (default: the project's, 300)")
    p.add_argument("--dates", action="store_true", help="add dates from the project's calendar settings")
    p.add_argument("--experiment", action="store_true",
                   help="files and code for PsychoPy, OpenSesame, jsPsych and lab.js")
    p.add_argument("--out"); p.add_argument("--name"); p.set_defaults(fn=cmd_export)
    p = sub.add_parser("verify", help="re-run a schedule from its seed and compare")
    p.add_argument("project"); p.add_argument("--run", default="final"); p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("final", help="mark a run as the final schedule")
    p.add_argument("project"); p.add_argument("run"); p.set_defaults(fn=cmd_final)
    a = ap.parse_args(argv)
    try:
        a.fn(a)
    except (ValueError, OSError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    main()
