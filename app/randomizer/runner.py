"""Run a design solve in a fresh worker process.

HiGHS gets measurably slower after several large solves in the same process (seen with
both highspy and SciPy's bundled HiGHS), so a long-running app would drift towards worse
designs. A fresh process per design keeps timing (and therefore results) consistent,
keeps the UI responsive, and contains solver crashes.
"""
from __future__ import annotations

import multiprocessing as mp
import queue
import sys
import traceback
import types

from .solver import DesignError, Result, solve


class Cancelled(Exception):
    """The user stopped the solve."""


def _worker(spec, q):
    try:
        res = solve(spec, progress=lambda msg: q.put(("progress", msg)))
        q.put(("result", res))
    except DesignError as e:
        q.put(("error", str(e)))
    except Exception:  # noqa: BLE001 - report anything to the parent
        q.put(("crash", traceback.format_exc()))


def solve_isolated(spec, progress=None, grace: float = 120.0, cancel=None) -> Result:
    """Same as solver.solve(), but in a separate process. Raises DesignError on failure and
    Cancelled when `cancel()` returns True (the solver process is stopped at once)."""
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(spec, q), daemon=True)
    # Under Streamlit the app script is registered as __main__, and "spawn" would re-run it
    # in the child. Hide it while starting so the child only imports this package.
    main = sys.modules.get("__main__")
    sys.modules["__main__"] = types.ModuleType("__main__")
    try:
        proc.start()
    finally:
        if main is not None:
            sys.modules["__main__"] = main
    say = progress or (lambda msg: None)
    # Reproducible mode may run up to its own wall-clock safety cap; wait at least that long.
    from . import solver as _solver
    limit = (spec.time_limit * _solver.SAFETY_FACTOR + 120.0 if getattr(spec, "deterministic", False)
             else spec.time_limit * 2) + grace
    waited = 0.0
    try:
        while True:
            if cancel is not None and cancel():
                raise Cancelled()
            try:
                kind, payload = q.get(timeout=0.25)
            except queue.Empty:
                waited += 0.25
                if not proc.is_alive():
                    raise DesignError("The solver process stopped unexpectedly.")
                if waited > limit:
                    raise DesignError("The solver did not finish in time.")
                continue
            if kind == "progress":
                say(payload)
            elif kind == "result":
                return payload
            elif kind == "error":
                raise DesignError(payload)
            else:
                raise RuntimeError("Solver crashed:\n" + payload)
    finally:
        if proc.is_alive():
            proc.join(timeout=0.2 if cancel is not None and cancel() else 5)
            if proc.is_alive():
                proc.terminate()
                proc.join(timeout=5)
