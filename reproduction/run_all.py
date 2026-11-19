"""Run every analysis of the article with LIBRA.

    python run_all.py                 # run everything; designs already in pools/ are reused
    python run_all.py --fresh         # delete the generated designs first and regenerate them
    python run_all.py --from r15      # resume at a stage (earlier stages are skipped)
    python run_all.py --only a02 r16  # run selected stages only

Each stage is a script run in its own process; its output goes to results/logs/<stage>.log. A stage
that fails is recorded and the run continues. results/run_all_status.md is rewritten after every
stage (stage, status, minutes), so progress can be followed while the run is going.

Settings for every stage: BENCH_SECONDS=60 (the app's default budget for every ILP and annealing
design), BENCH_WORKERS (default 20 parallel processes), LIBRA_THREADS=1 (one solver thread per
process). The ILP runs in the app's default reproducible mode, so the designs do not depend on the
machine or its load.
"""
import argparse
import hashlib
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS, POOLS, FIGURES = HERE / "results", HERE / "pools", HERE / "figures"
LOGS = RESULTS / "logs"

H = 3600
STAGES = [   # (name, script and arguments, timeout in seconds)
    ("a02", ["a02_generate_pools.py"], 4 * H),
    ("r02", ["r02_comparators.py"], 2 * H),
    ("r12", ["r12_sa_warm.py"], 2 * H),
    ("a01", ["a01_verification.py"], 3 * H),
    ("a03", ["a03_balance_predictability.py"], 1 * H),
    ("a04", ["a04_efficiency_dropout.py"], 1 * H),
    ("a05", ["a05_simulation.py"], 2 * H),
    ("a06", ["a06_randomization_validity.py"], 3 * H),
    ("a06b", ["a06b_exchangeability.py"], 1 * H),
    ("a06c", ["a06c_exchangeability_replication.py"], 2 * H),
    ("a07", ["a07_scalability.py"], 2 * H),
    ("a08", ["a08_case_study.py"], 1 * H),
    ("r01", ["r01_exchangeability_check.py"], 1 * H),
    ("r01b", ["r01b_regenerate_check.py"], 1 * H),
    ("r01c", ["r01c_log_permutations.py"], 1 * H),
    ("r03", ["r03_reachability.py"], 2 * H),
    ("r03b", ["r03b_reachability_ilp.py"], 2 * H),
    ("r04", ["r04_rules.py"], 2 * H),
    ("r05", ["r05_aopt.py"], 1 * H),
    ("r06", ["r06_sim_strata.py"], 2 * H),
    ("r07", ["r07_partial_observer.py"], 1 * H),
    ("r08", ["r08_certificates.py"], 3 * H),
    ("r09", ["r09_reference_values.py"], 1 * H),
    ("r10", ["r10_eval_comparators.py"], 1 * H),
    ("r11", ["r11_williams_check.py"], 1 * H),
    ("r13", ["r13_stratum_g3_bound.py"], 2 * H),
    ("r15", ["r15_human_example.py"], 1 * H),
    ("r14", ["r14_exact_power.py"], 2 * H),
    ("r16", ["r16_table_stats.py"], 2 * H),
    ("r17", ["r17_figures.py"], 1 * H),
    ("x02f", ["x02_feasibility.py"], 1 * H),
    ("x02i", ["x02_independent_check.py"], 1 * H),
    ("x05", ["x05_early_stopping.py"], 1 * H),
    ("x03b", ["x03_g3_bound.py"], 2 * H),
    ("x03", ["x03_predict.py"], 2 * H),
    ("x04e", ["x04_enumerate_e.py"], 1 * H),
    ("r20", ["r20_variety_uniformity.py"], 3 * H),
    ("r19", ["r19_worked_example.py"], 1 * H),
    ("r21", ["r21_design_limits.py"], 4 * H),
    ("r22", ["r22_cpsat_certificates.py"], 6 * H),
    ("a09", ["a09_tables.py"], 1 * H),
    ("r18", ["r18_latex_tables.py"], 1 * H),
]


def clear_designs():
    """Delete the generated designs, so that a02 and the stages after it regenerate them."""
    for f in list(POOLS.glob("*.npz")) + list((POOLS / "ilp_runs").glob("*.npz")):
        f.unlink()
    for f in (POOLS / "ilp_runs.csv", POOLS / "SHA256SUMS.txt"):
        if f.exists():
            f.unlink()


def write_checksums():
    lines = [f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(POOLS).as_posix()}"
             for p in sorted(POOLS.rglob("*.npz"))]
    (POOLS / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_status(rows, started):
    out = [f"# run_all status", "", f"Started {started:%Y-%m-%d %H:%M}, updated {datetime.now():%Y-%m-%d %H:%M}.",
           "", "| Stage | Script | Status | Minutes |", "|---|---|---|---|"]
    out += [f"| {n} | {s} | {st} | {m} |" for n, s, st, m in rows]
    (RESULTS / "run_all_status.md").write_text("\n".join(out) + "\n", encoding="utf-8")


def keep_awake():
    """Ask Windows not to sleep while this process runs (released automatically when it exits).
    Closing a laptop's lid can still suspend it, depending on the power settings."""
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | 0x00000001)   # CONTINUOUS | SYSTEM


def main():
    keep_awake()
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="start", default=None)
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--fresh", action="store_true", help="delete the generated designs first")
    args = ap.parse_args()
    names = [n for n, _, _ in STAGES]
    todo = STAGES
    if args.only:
        todo = [s for s in STAGES if s[0] in args.only]
    elif args.start:
        todo = STAGES[names.index(args.start):]
    if args.fresh:
        clear_designs()
    LOGS.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.setdefault("BENCH_SECONDS", "60")
    env.setdefault("BENCH_WORKERS", "20")
    env["LIBRA_THREADS"] = "1"
    env.setdefault("LIBRA_SAFETY_FACTOR", "40")   # parallel load slows solves; see solver.SAFETY_FACTOR
    env["PYTHONUNBUFFERED"] = "1"
    env.pop("ANALYSIS_SOLVER", None)              # always the current LIBRA
    env.pop("ANALYSIS_POOLS", None)
    started = datetime.now()
    rows = [(n, " ".join(cmd), "pending", "") for n, cmd, _ in todo]
    write_status(rows, started)
    for i, (name, cmd, timeout) in enumerate(todo):
        rows[i] = (name, " ".join(cmd), "running", "")
        write_status(rows, started)
        t0 = time.time()
        with open(LOGS / f"{name}.log", "w", encoding="utf-8") as log:
            log.write(f"# {' '.join(cmd)}  started {datetime.now():%Y-%m-%d %H:%M:%S}\n")
            log.flush()
            try:
                p = subprocess.run([sys.executable, *cmd], cwd=HERE, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, timeout=timeout)
                status = "ok" if p.returncode == 0 else f"FAILED (exit {p.returncode})"
            except subprocess.TimeoutExpired:
                status = f"TIMEOUT after {timeout // 60} min"
        minutes = f"{(time.time() - t0) / 60:.1f}"
        rows[i] = (name, " ".join(cmd), status, minutes)
        write_status(rows, started)
        print(f"{datetime.now():%H:%M} {name}: {status} ({minutes} min)", flush=True)
        if name == "a02":
            write_checksums()
    print("done", flush=True)


if __name__ == "__main__":
    main()
