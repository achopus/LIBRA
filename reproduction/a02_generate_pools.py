"""Generate pools of designs (independent randomizations) for every configuration and method.

Comparators: 200 designs each. ILP variants: one solve per seed in a fresh process
(HiGHS slows down after many solves in one process), several in parallel. Every finished
solve is saved immediately to pools/ilp_runs/, so an interrupted run resumes where it stopped.

    python analysis/a02_generate_pools.py [--n-ilp 60] [--time-limit 20] [--workers 6]
"""
import argparse
import json
import multiprocessing as mp
import time
import traceback

import numpy as np
import pandas as pd

from common import BENCH_SECONDS, CONFIGS, GENERATORS, POOLS, WORKERS, ilp_spec, pool_path

RUNS = POOLS / "ilp_runs"


def run_file(c, method, seed):
    return RUNS / f"{c}_{method}_{seed:03d}.npz"


def ilp_task(args):
    cfg_name, seed, time_limit, spread = args
    method = "ilp" if spread else "ilp_nospread"
    try:
        from randomizer import solve
        cfg = CONFIGS[cfg_name]
        t0 = time.time()
        res = solve(ilp_spec(cfg, seed, time_limit, spread))
        meta = {"config": cfg_name, "method": method, "seed": seed, "status": res.status,
                "proven": bool(res.proven_optimal), "formulation": res.formulation,
                "seconds": time.time() - t0, "work_seconds": res.work_seconds,
                "reproducible": res.reproducible, "checks": json.dumps(res.checks),
                "criteria": json.dumps(res.criteria), "choice": res.randomization.get("method"),
                "designs_listed": res.randomization.get("designs"),
                **{f"viol_{k}": v for k, v in res.violations.items()},
                **{f"level_{k}": v for k, v in res.levels.items()}}
        np.savez_compressed(run_file(cfg_name, method, seed), assign=res.assign, meta=json.dumps(meta))
        return meta
    except Exception:  # noqa: BLE001 - record and continue
        return {"config": cfg_name, "method": method, "seed": seed, "error": traceback.format_exc()}


def assemble(n_ilp):
    metas = []
    for c in CONFIGS:
        for m in ("ilp", "ilp_nospread"):
            files = [run_file(c, m, s) for s in range(1, n_ilp + 1) if run_file(c, m, s).exists()]
            if len(files) < n_ilp:
                print(f"{c} {m}: only {len(files)}/{n_ilp} solves present; pool not written")
                continue
            loaded = [np.load(f) for f in files]
            np.savez_compressed(pool_path(c, m), designs=np.stack([z["assign"] for z in loaded]),
                                seeds=np.arange(1, n_ilp + 1))
            metas += [json.loads(str(z["meta"])) for z in loaded]
    if metas:
        pd.DataFrame(metas).to_csv(POOLS / "ilp_runs.csv", index=False)
        print(pd.DataFrame(metas).groupby(["config", "method"])["seconds"].describe().round(1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="".join(CONFIGS))
    ap.add_argument("--n-comparator", type=int, default=200)
    ap.add_argument("--n-ilp", type=int, default=60)
    ap.add_argument("--time-limit", type=float, default=BENCH_SECONDS)
    ap.add_argument("--workers", type=int, default=WORKERS)
    args = ap.parse_args()
    RUNS.mkdir(parents=True, exist_ok=True)

    for c in args.configs:
        cfg = CONFIGS[c]
        for m, gen in GENERATORS.items():
            if pool_path(c, m).exists():
                continue
            rng = np.random.default_rng(1000 + ord(c))
            designs = np.stack([gen(cfg, rng) for _ in range(args.n_comparator)])
            np.savez_compressed(pool_path(c, m), designs=designs)
            print(f"{c} {m}: {len(designs)} designs", flush=True)

    tasks = [(c, seed, args.time_limit, spread)
             for seed in range(1, args.n_ilp + 1) for c in args.configs for spread in (True, False)
             if not run_file(c, "ilp" if spread else "ilp_nospread", seed).exists()]
    print(f"{len(tasks)} ILP solves to run, {args.workers} at a time", flush=True)
    t0, errors = time.time(), []
    with mp.get_context("spawn").Pool(args.workers, maxtasksperchild=1) as pool:
        for i, r in enumerate(pool.imap_unordered(ilp_task, tasks), 1):
            if "error" in r:
                errors.append(r)
                print("ERROR", r["config"], r["method"], r["seed"], r["error"].splitlines()[-1], flush=True)
            if i % 20 == 0:
                print(f"  {i}/{len(tasks)} done, {(time.time() - t0) / i * args.workers:.0f} s per solve",
                      flush=True)
    print(f"{len(errors)} errors")
    assemble(args.n_ilp)


if __name__ == "__main__":
    main()
