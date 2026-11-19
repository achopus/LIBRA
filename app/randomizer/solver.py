"""Constrained randomization of treatment sequences by integer linear programming (HiGHS).

Two equivalent formulations:

* sequence formulation - one integer variable per (subject cell, allowed treatment
  order) counting how many subjects of that cell get that order. Compact and fast;
  used while the number of allowed orders stays manageable.
* subject formulation - binary x[subject, period, treatment] plus transition
  variables. Scales to many treatments / periods.

A "cell" is a set of exchangeable subjects (same group levels and enrollment block).

Pipeline:
  0. warm start - subjects are split into small chunks which are added one at a
     time, each chunk solved as a small ILP given the chunks already placed,
  1. global ILP - minimize weighted balance violations ("preferred" rules are
     penalized, "required" rules are hard constraints), starting from step 0,
  2. randomization - keep that quality fixed and minimize a random objective so
     the seed picks a random design among the equally good ones; then subjects
     are shuffled within their cell and, when every rule is symmetric in the
     treatments, treatment labels are randomly permuted.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import highspy
import numpy as np
import pandas as pd

from .spec import DesignSpec, validate

SEQUENCE_VAR_LIMIT = 20_000      # max (cells × allowed orders) for the sequence formulation
INF = highspy.kHighsInf
BACKEND = "highs"                # "highs" (bundled) or "gurobi" (if gurobipy is installed); set by solve()


# ------------------------------------------------------------------ clock
# Reproducible mode measures the search in units of solver work instead of wall-clock seconds:
# every solve gets a node limit, and the work it did (simplex iterations, scaled by model size) is
# added to a virtual clock. Node and iteration counts do not depend on the computer or its load, so
# the same seed and settings give the same schedule everywhere. One unit of work is calibrated to
# take about one second on a 2024 laptop (Intel i7-14700HX, one solver thread): the three rates
# below were fitted by least squares to the real time of about 1,700 solves from runs on ten design
# sizes (t = 3-8) and then scaled by 1.2 so that typical whole runs take about their budget. A
# single solve of a very large model can still overrun its share (HiGHS cannot limit the work at the
# root of the search). A wall-clock safety cap stops runaway solves; if it is ever reached, the run
# is reported as not reproducible.
WORK_PER_ITER = 1.087e-6         # seconds per simplex iteration per sqrt(nonzeros)
WORK_PER_COL = 1.14e-4           # seconds per variable for setting up each solve (presolve, probing)
WORK_PER_NNZ = 1.086e-5          # seconds per nonzero for setting up each solve
SOLVE_OVERHEAD = 2e-3            # seconds per solve call (model transfer)
ITERS_PER_NODE = 200             # typical simplex iterations per search node (turns a budget into a node limit)
SAFETY_FACTOR = float(__import__("os").environ.get("LIBRA_SAFETY_FACTOR", "10"))
# wall-clock cap = SAFETY_FACTOR * time limit + 120 s (runaway guard only; benchmarks running many
# solves in parallel raise it, because a busy computer slows every solve without changing its result)


class _Clock:
    def __init__(self, deterministic=False, limit=math.inf):
        self.det = bool(deterministic)
        self.t0 = time.time()
        self.used = 0.0
        self.wall_cap = self.t0 + SAFETY_FACTOR * limit + 120.0 if self.det else math.inf
        self.cap_hit = False

    def now(self):
        """Current time on the search clock: virtual work in reproducible mode, else wall time."""
        return self.t0 + self.used if self.det else time.time()

    def wall_left(self):
        return max(0.5, self.wall_cap - time.time())

    @staticmethod
    def per_node(nnz):
        return ITERS_PER_NODE * math.sqrt(max(nnz, 1)) * WORK_PER_ITER

    def node_limit(self, budget, nnz):
        return int(max(1, budget / self.per_node(nnz)))

    def charge(self, iterations, nnz, nodes=0, cols=0):
        """Work of one solve: its simplex iterations (whose cost grows with the model) and a set-up
        cost that grows with the number of variables and nonzeros. Search nodes are limited (see
        node_limit) but not charged separately: their cost is in their iterations."""
        self.used += (iterations * math.sqrt(max(nnz, 1)) * WORK_PER_ITER
                      + cols * WORK_PER_COL + nnz * WORK_PER_NNZ + SOLVE_OVERHEAD)


_CLOCK = _Clock()                # replaced by solve() for the duration of one run
THREADS = int(__import__("os").environ.get("LIBRA_THREADS", "0"))   # 0 = HiGHS default (benchmarks use 1)


def gurobi_available() -> bool:
    """True when gurobipy can be imported and a license is found."""
    try:
        import gurobipy as gp
        with gp.Env(empty=True) as env:
            env.setParam("OutputFlag", 0)
            env.start()
        return True
    except Exception:  # noqa: BLE001 - missing package or license
        return False

# Objective weight per unit of deviation outside the ideal [floor, ceil] range.
PENALTY = {
    ("period", "overall"): 1000.0, ("period", "group"): 1000.0, ("period", "block"): 1000.0,
    ("carryover", "overall"): 100.0, ("carryover", "group"): 30.0,
    ("cooccurrence", "overall"): 30.0, ("cooccurrence", "group"): 10.0,
    ("spread", "overall"): 10.0, ("spread", "group"): 3.0,
    ("carryover_even", "overall"): 0.01, ("carryover_even", "group"): 0.01,
    ("fulllist", "overall"): 5.0, ("fulllist", "group"): 5.0,
}
# The weights above only steer the warm starts (and the research copy of the solver). The search
# itself optimizes the criteria one at a time in this order (preemptive goal programming): each tier
# is minimized, its best value is fixed as a cap, and the next tier is minimized under that cap, so a
# lower tier can never cost a higher one.
TIERS = [
    ("period", ("overall", "group", "block")),
    ("carryover", ("group",)), ("carryover", ("overall",)),
    ("carryover_even", ("group",)), ("carryover_even", ("overall",)),
    ("cooccurrence", ("group",)), ("cooccurrence", ("overall",)),
    ("fulllist", ("group",)), ("fulllist", ("overall",)),
    ("spread", ("group",)), ("spread", ("overall",)),
]
EVEN_WINDOW = 4                  # integer points on each side of the target modelled exactly


LABELS = {"period": "period balance", "carryover": "carry-over balance",
          "cooccurrence": "co-occurrence balance", "spread": "spread within period changes",
          "carryover_even": "evenness of carry-over", "fulllist": "full-list predictability"}


class DesignError(Exception):
    """No design could be produced; the message is meant for the user."""


@dataclass
class Unit:
    """A set of subjects over which balance is evaluated."""
    name: str
    kind: str            # "overall" | "group" | "block"
    cells: list[int]
    size: int


@dataclass
class Result:
    spec: DesignSpec
    schedule: pd.DataFrame               # subject table + one column per period (labels)
    period_columns: list[str]
    assign: np.ndarray                   # (n_subjects, n_randomized) treatment indices
    units: list[Unit]
    subject_unit_ids: list[np.ndarray]   # per unit: subject row indices
    codes: dict[str, str] | None
    status: str
    proven_optimal: bool
    formulation: str
    violations: dict[str, float]
    solve_seconds: float
    warnings: list[str] = field(default_factory=list)
    levels: dict[str, str] = field(default_factory=dict)   # final level of each criterion
    # How the final design was chosen among the equally balanced ones:
    #   method  "uniform" (all listed, one drawn with equal probability), "random walk" or
    #           "random objective"; uniform  True only for "uniform"; designs  size of the listed set
    randomization: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)          # extra sentences for the methods text
    # Outcome of each "can this criterion be perfect?" check: "met", "impossible" (proven by the
    # solver) or "not settled" (the check ran out of time).
    checks: dict = field(default_factory=dict)
    # Criteria optimized one at a time, in priority order: name -> {"value": remaining deviation,
    # "proven": whether the solver proved that value the best possible given the earlier criteria}.
    criteria: dict = field(default_factory=dict)
    reproducible: bool | None = None     # reproducible mode: True unless the safety cap was hit
    work_seconds: float | None = None    # reproducible mode: search effort used, in nominal seconds


# --------------------------------------------------------------------------- model
class _Model:
    """Sparse MILP builder solved with HiGHS."""

    def __init__(self):
        self.n = 0
        self._lb, self._ub, self._int, self._cost = [], [], [], []
        self._ri, self._rj, self._rv, self.lo, self.hi = [], [], [], [], []
        self._pins = []                 # (idx, values): variables that can never change
        self.tier_vars = {}             # (criterion, unit kind) -> penalty variables (see TIERS)

    def pin(self, idx, values):
        """Fix variables for good (applied after any fix/bounds passed to solve)."""
        self._pins.append((np.asarray(idx, int), np.asarray(values, float)))

    def add_vars(self, k, lb=0.0, ub=INF, integer=False, cost=0.0):
        idx = np.arange(self.n, self.n + k)
        self.n += k
        self._lb.append(np.broadcast_to(np.asarray(lb, float), (k,)))
        self._ub.append(np.broadcast_to(np.asarray(ub, float), (k,)))
        self._int.append(np.full(k, bool(integer)))
        self._cost.append(np.broadcast_to(np.asarray(cost, float), (k,)))
        return idx

    def add_row(self, idx, coef, lo, hi):
        idx = np.asarray(idx, int)
        self._ri.append(np.full(len(idx), len(self.lo)))
        self._rj.append(idx)
        self._rv.append(np.broadcast_to(np.asarray(coef, float), (len(idx),)))
        self.lo.append(-INF if lo == -np.inf else lo)
        self.hi.append(INF if hi == np.inf else hi)

    @property
    def cost(self):
        return np.concatenate(self._cost) if self._cost else np.zeros(0)

    def copy(self):
        m = _Model()
        m.n = self.n
        for name in ("_lb", "_ub", "_int", "_cost", "_ri", "_rj", "_rv", "lo", "hi", "_pins"):
            setattr(m, name, list(getattr(self, name)))
        m.tier_vars = {k: list(v) for k, v in self.tier_vars.items()}
        return m

    def tier_cost(self, key):
        """Cost vector that sums the penalty variables of one tier."""
        c = np.zeros(self.n)
        for idx in self.tier_vars.get(key, []):
            c[idx] += 1.0
        return c

    def solve(self, cost, time_limit, gap, seed, start=None, fix=None, bounds=None):
        """Return (x or None, status text, proven_optimal).

        fix=(idx, values) pins variables; bounds=(idx, lower, upper) overrides their bounds."""
        lb, ub = np.concatenate(self._lb).copy(), np.concatenate(self._ub).copy()
        if fix is not None:
            lb[fix[0]] = ub[fix[0]] = fix[1]
        if bounds is not None:
            lb[bounds[0]], ub[bounds[0]] = bounds[1], bounds[2]
        for idx, vals in self._pins:
            lb[idx] = ub[idx] = vals
        key = (self.n, len(self.lo))
        if getattr(self, "_A_key", None) != key:
            self._A = _csc(np.concatenate(self._ri), np.concatenate(self._rj), np.concatenate(self._rv),
                           len(self.lo), self.n)
            self._A_key = key
        indptr, indices, data = self._A
        if BACKEND == "gurobi":
            return self._solve_gurobi(cost, lb, ub, time_limit, gap, seed, start)
        lp = highspy.HighsLp()
        lp.num_col_, lp.num_row_ = self.n, len(self.lo)
        lp.col_cost_, lp.col_lower_, lp.col_upper_ = np.asarray(cost, float), lb, ub
        lp.row_lower_, lp.row_upper_ = np.array(self.lo, float), np.array(self.hi, float)
        lp.a_matrix_.format_ = highspy.MatrixFormat.kColwise
        lp.a_matrix_.start_, lp.a_matrix_.index_, lp.a_matrix_.value_ = indptr, indices, data
        integ = np.concatenate(self._int)
        lp.integrality_ = [highspy.HighsVarType.kInteger if v else highspy.HighsVarType.kContinuous
                           for v in integ]
        h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        if THREADS:
            h.setOptionValue("threads", THREADS)
        clk, nnz = _CLOCK, len(data)
        if clk.det:
            h.setOptionValue("time_limit", float(clk.wall_left()))
            h.setOptionValue("mip_max_nodes", clk.node_limit(max(0.0, time_limit), nnz))
        else:
            h.setOptionValue("time_limit", float(max(0.5, time_limit)))
        h.setOptionValue("mip_rel_gap", float(gap))
        h.setOptionValue("random_seed", int(seed) % 2_147_483_647)
        h.passModel(lp)
        if start is not None:
            sol = highspy.HighsSolution()
            sol.col_value = np.asarray(start, float).tolist()
            sol.value_valid = True
            h.setSolution(sol)
        h.run()
        status = h.getModelStatus()
        text = h.modelStatusToString(status)
        if clk.det:
            info = h.getInfo()
            clk.charge(info.simplex_iteration_count, nnz, info.mip_node_count, self.n)
            if status == highspy.HighsModelStatus.kTimeLimit:
                clk.cap_hit = True
            elif status == highspy.HighsModelStatus.kSolutionLimit:
                text = "Work limit reached"
        if h.getInfo().primal_solution_status != 2:      # 2 = feasible
            return None, text, False
        x = np.array(h.getSolution().col_value)
        return x, text, status == highspy.HighsModelStatus.kOptimal

    def _solve_gurobi(self, cost, lb, ub, time_limit, gap, seed, start):
        """Same contract as solve(), with Gurobi. Status texts mimic HiGHS ("Infeasible", ...)."""
        import gurobipy as gp
        import scipy.sparse as sp
        from gurobipy import GRB
        indptr, indices, data = self._A
        A = sp.csc_matrix((data, indices, indptr), shape=(len(self.lo), self.n)).tocsr()
        lo, hi = np.array(self.lo, float), np.array(self.hi, float)
        integ = np.concatenate(self._int)
        with gp.Env(empty=True) as env:
            env.setParam("OutputFlag", 0)
            env.start()
            with gp.Model(env=env) as m:
                x = m.addMVar(self.n, lb=np.where(np.isinf(lb), -GRB.INFINITY, lb),
                              ub=np.where(np.isinf(ub), GRB.INFINITY, ub),
                              vtype=np.where(integ, GRB.INTEGER, GRB.CONTINUOUS),
                              obj=np.asarray(cost, float))
                eq = np.isfinite(lo) & np.isfinite(hi) & (lo == hi)
                up = np.isfinite(hi) & ~eq
                dn = np.isfinite(lo) & ~eq
                for mask, sense, rhs in ((eq, "=", lo), (up, "<", hi), (dn, ">", lo)):
                    if mask.any():
                        m.addMConstr(A[mask], x, sense, rhs[mask])
                clk = _CLOCK
                if clk.det:     # same idea as for HiGHS: node limit, fixed threads, work charged
                    m.Params.TimeLimit = float(clk.wall_left())
                    m.Params.NodeLimit = float(clk.node_limit(max(0.0, time_limit), len(data)))
                    m.Params.Threads = THREADS or 1
                else:
                    m.Params.TimeLimit = float(max(0.5, time_limit))
                    m.Params.Threads = THREADS
                m.Params.MIPGap = float(gap)
                m.Params.Seed = int(seed) % 2_000_000_000
                if start is not None:
                    x.Start = np.asarray(start, float)
                m.optimize()
                text = {GRB.OPTIMAL: "Optimal", GRB.INFEASIBLE: "Infeasible",
                        GRB.INF_OR_UNBD: "Infeasible", GRB.TIME_LIMIT: "Time limit reached",
                        GRB.NODE_LIMIT: "Work limit reached"}.get(m.Status, f"Gurobi status {m.Status}")
                if clk.det:
                    clk.charge(int(m.IterCount), len(data), int(m.NodeCount) if m.IsMIP else 0, self.n)
                    clk.cap_hit |= m.Status == GRB.TIME_LIMIT
                if m.SolCount == 0:
                    return None, text, False
                return np.array(x.X), text, m.Status == GRB.OPTIMAL


def _csc(rows, cols, vals, n_rows, n_cols):
    """Compressed sparse column arrays (duplicates summed), built with numpy only."""
    key = cols.astype(np.int64) * n_rows + rows
    order = np.argsort(key, kind="stable")
    key, vals = key[order], vals[order]
    uniq, first = np.unique(key, return_index=True)
    data = np.add.reduceat(vals, first) if len(vals) else vals
    c, r = uniq // n_rows, uniq % n_rows
    indptr = np.searchsorted(c, np.arange(n_cols + 1))
    return indptr.astype(np.int32), r.astype(np.int32), data.astype(float)


def _empty():
    return np.zeros(0, int), np.zeros(0)


def _concat(exprs):
    exprs = list(exprs)
    if not exprs:
        return _empty()
    return np.concatenate([e[0] for e in exprs]), np.concatenate([e[1] for e in exprs])


# ------------------------------------------------------------------ formulations
class _SequenceForm:
    name = "sequence counts"

    def __init__(self, model, ctx, members):
        self.seqs, self.adj = ctx.seqs, ctx.adj
        self.seq_index = {tuple(s): i for i, s in enumerate(ctx.seqs)}
        S = len(self.seqs)
        self.m = []
        for mem in members:
            v = model.add_vars(S, ub=len(mem), integer=True)
            model.add_row(v, 1.0, len(mem), len(mem))
            self.m.append(v)
        self.decision = np.concatenate(self.m)
        self.mass = sum(len(mem) for mem in members)    # sum of decision values
        self._has = np.zeros((S, ctx.t), bool)
        for k in range(self.seqs.shape[1]):
            self._has[np.arange(S), self.seqs[:, k]] = True
        self._cache = {}

    def _pick(self, c, key, mask_fn):
        if key not in self._cache:
            self._cache[key] = np.flatnonzero(mask_fn())
        ix = self._cache[key]
        return self.m[c][ix], np.ones(len(ix))

    def period(self, c, k, a):
        return self._pick(c, ("p", k, a), lambda: self.seqs[:, k] == a)

    def transition(self, c, j, a, b):
        k1, k2 = self.adj[j]
        return self._pick(c, ("t", j, a, b), lambda: (self.seqs[:, k1] == a) & (self.seqs[:, k2] == b))

    def cooc(self, c, a, b):
        return self._pick(c, ("c", a, b), lambda: self._has[:, a] & self._has[:, b])

    def encode(self, c, rows):
        counts = np.zeros(len(self.seqs))
        for r in rows:
            counts[self.seq_index[tuple(r)]] += 1
        return self.m[c], counts

    def extract(self, x, c):
        counts = np.round(x[self.m[c]]).astype(int)
        return np.repeat(self.seqs, counts, axis=0)

    def release(self, x, c, n_free, rng):
        """Bounds letting `n_free` random subjects of cell c change their sequence."""
        rows = self.extract(x, c)
        keep = rows[rng.permutation(len(rows))[n_free:]]
        lb = self.encode(c, keep)[1]
        return self.m[c], lb, lb + n_free


class _SubjectForm:
    name = "per-subject"

    def __init__(self, model, ctx, members):
        spec, t, p, adj = ctx.spec, ctx.t, ctx.p, ctx.adj
        self.adj = adj
        self.offsets = np.cumsum([0] + [len(m) for m in members])
        N = int(self.offsets[-1])
        ub = np.ones((N, p, t))
        for k, a in ctx.forbidden_pos:
            ub[:, k, a] = 0
        X = model.add_vars(N * p * t, ub=ub.ravel(), integer=True).reshape(N, p, t)
        self.X, self.decision, self.mass = X, X.ravel(), N * p
        # Symmetry breaking: subjects of a cell are interchangeable, so require them to be sorted by
        # their first two treatments (any design can be reordered this way within each cell).
        self._key_len = min(p, 2)
        kw = np.array([t ** (self._key_len - 1 - k) for k in range(self._key_len)], float)
        key_coef = (kw[:, None] * np.arange(t)[None, :]).ravel()
        for c in range(len(members)):
            for i in range(self.offsets[c], self.offsets[c + 1] - 1):
                model.add_row(np.r_[X[i, :self._key_len].ravel(), X[i + 1, :self._key_len].ravel()],
                              np.r_[key_coef, -key_coef], -INF, 0.0)
        for i in range(N):
            for k in range(p):
                model.add_row(X[i, k], 1.0, 1, 1)
            for a in range(t):
                model.add_row(X[i, :, a], 1.0, spec.min_per_subject, spec.max_per_subject)
            for a, b in ctx.order_idx:            # a never after b
                for k in range(p):
                    model.add_row(np.r_[X[i, k, b], X[i, k + 1:, a]], 1.0, -INF, 1)
        pairs = ctx.allowed_pairs
        self.pair_index = {pq: q for q, pq in enumerate(pairs)}
        self.Y = None
        if adj:
            Q = len(pairs)
            Y = model.add_vars(N * len(adj) * Q, ub=1.0).reshape(N, len(adj), Q)
            out_of = [[q for q, (a, _) in enumerate(pairs) if a == s] for s in range(t)]
            into = [[q for q, (_, b) in enumerate(pairs) if b == s] for s in range(t)]
            for i in range(N):
                for j, (k1, k2) in enumerate(adj):
                    for s in range(t):
                        model.add_row(np.r_[Y[i, j, out_of[s]], X[i, k1, s]],
                                      np.r_[np.ones(len(out_of[s])), -1.0], 0, 0)
                        model.add_row(np.r_[Y[i, j, into[s]], X[i, k2, s]],
                                      np.r_[np.ones(len(into[s])), -1.0], 0, 0)
            self.Y = Y
        self.Z = None
        if ctx.need_cooc:
            co_pairs = [(a, b) for a in range(t) for b in range(a + 1, t)]
            Z = model.add_vars(N * len(co_pairs), ub=1.0).reshape(N, len(co_pairs))
            for i in range(N):
                for q, (a, b) in enumerate(co_pairs):
                    ua, ub_ = X[i, :, a], X[i, :, b]
                    model.add_row(np.r_[Z[i, q], ua], np.r_[1.0, -np.ones(p)], -INF, 0)
                    model.add_row(np.r_[Z[i, q], ub_], np.r_[1.0, -np.ones(p)], -INF, 0)
                    model.add_row(np.r_[Z[i, q], ua, ub_], np.r_[1.0, -np.ones(2 * p)], -1, INF)
            self.Z, self.co_index = Z, {pq: q for q, pq in enumerate(co_pairs)}

    def _rows(self, c):
        return np.arange(self.offsets[c], self.offsets[c + 1])

    def period(self, c, k, a):
        idx = self.X[self._rows(c), k, a]
        return idx, np.ones(len(idx))

    def transition(self, c, j, a, b):
        q = self.pair_index.get((a, b))
        if q is None or self.Y is None:
            return _empty()
        idx = self.Y[self._rows(c), j, q]
        return idx, np.ones(len(idx))

    def cooc(self, c, a, b):
        idx = self.Z[self._rows(c), self.co_index[(a, b)]]
        return idx, np.ones(len(idx))

    def encode(self, c, rows):
        Xc = self.X[self._rows(c)]
        vals = np.zeros(Xc.shape)
        rows = np.asarray(rows)
        if len(rows):           # sorted by the first treatments, as the symmetry breaking requires
            rows = rows[np.lexsort(rows[:, :self._key_len].T[::-1])]
        for i, r in enumerate(rows):
            vals[i, np.arange(len(r)), r] = 1
        return Xc.ravel(), vals.ravel()

    def extract(self, x, c):
        return x[self.X[self._rows(c)]].argmax(axis=2)

    def release(self, x, c, n_free, rng):
        """Bounds pinning all but `n_free` random subjects of cell c."""
        rows = self._rows(c)
        keep = rows[rng.permutation(len(rows))[n_free:]]
        idx = self.X[keep].ravel()
        vals = np.round(x[idx])
        return idx, vals, vals


# ---------------------------------------------------------------- preparation
@dataclass
class _Ctx:
    spec: DesignSpec
    T: list[str]
    t: int
    p: int
    adj: list[tuple[int, int]]
    allowed_pairs: list[tuple[int, int]]
    forbidden_pos: list[tuple[int, int]]
    order_idx: list[tuple[int, int]]
    w: np.ndarray
    need_cooc: bool
    members: list[np.ndarray]
    units: list[Unit]
    block: pd.Series
    cell_stratum: list[str]
    seqs: np.ndarray | None = None
    locked_rows: dict = field(default_factory=dict)   # cell -> fixed rows (kept subjects)


def _enumerate_sequences(spec, t, p, adj, allowed_pair_set, forbidden_pos, order_idx, limit):
    """All treatment orders allowed by the per-subject rules, or None if more than `limit`."""
    adjacent_prev = {k2 for _, k2 in adj}
    must_not_after = {}
    for a, b in order_idx:
        must_not_after.setdefault(b, set()).add(a)
    forb = set(forbidden_pos)
    out, seq, counts, banned = [], [], [0] * t, [0] * t

    def rec(k):
        if len(out) > limit:
            return
        if k == p:
            if all(c >= spec.min_per_subject for c in counts):
                out.append(tuple(seq))
            return
        if sum(max(0, spec.min_per_subject - c) for c in counts) > p - k:
            return
        for a in range(t):
            if counts[a] >= spec.max_per_subject or banned[a] or (k, a) in forb:
                continue
            if k in adjacent_prev and (seq[-1], a) not in allowed_pair_set:
                continue
            seq.append(a); counts[a] += 1
            for x in must_not_after.get(a, ()):
                banned[x] += 1
            rec(k + 1)
            for x in must_not_after.get(a, ()):
                banned[x] -= 1
            seq.pop(); counts[a] -= 1

    rec(0)
    if len(out) > limit:
        return None
    return np.array(out, dtype=int).reshape(-1, p)


def _cells_and_units(spec: DesignSpec, rng):
    df = spec.subjects.reset_index(drop=True)
    n = len(df)
    if spec.strata:
        stratum = df[spec.strata].astype(str).apply(
            lambda r: ", ".join(f"{c}={v}" for c, v in r.items()), axis=1)
    else:
        stratum = pd.Series(["All"] * n)
    block = pd.Series([""] * n, dtype=object)
    ids = df[spec.id_column].astype(str).to_numpy()
    locked = np.array([i in spec.locked for i in ids], bool)
    if spec.block_sizes:
        for s in dict.fromkeys(stratum):
            idx = np.flatnonzero((stratum.to_numpy() == s) & ~locked)
            # kept subjects keep their old blocks; new blocks are numbered after them
            old = {spec.locked_blocks.get(i, "") for i in ids[(stratum.to_numpy() == s) & locked]} - {""}
            pos, b = 0, 1 + len(old)
            while pos < len(idx):
                size = int(rng.choice(spec.block_sizes))
                block.iloc[idx[pos:pos + size]] = f"{s}, block {b}" if spec.strata else f"Block {b}"
                pos, b = pos + size, b + 1
    key = (stratum + "|" + block).tolist()
    for i in np.flatnonzero(locked):          # one cell per (group, kept sequence)
        key[i] = f"{stratum.iloc[i]}|kept:" + "\x1f".join(spec.locked[ids[i]])
        block.iloc[i] = spec.locked_blocks.get(ids[i], "")
    cell_keys = list(dict.fromkeys(key))
    lookup = {k: i for i, k in enumerate(cell_keys)}
    cell_of = np.array([lookup[k] for k in key])
    members = [np.flatnonzero(cell_of == c) for c in range(len(cell_keys))]
    cell_stratum = [k.split("|")[0] for k in cell_keys]

    units = [Unit(f"All {spec.noun()}", "overall", list(range(len(members))), n)]
    for f in spec.strata:
        col = df[f].astype(str).to_numpy()
        levels = list(dict.fromkeys(col))
        if len(levels) < 2:
            continue
        for lvl in levels:
            rows = np.flatnonzero(col == lvl)
            units.append(Unit(f"{f} = {lvl}", "group", sorted(set(cell_of[rows].tolist())), len(rows)))
    if spec.block_sizes:
        for bl in dict.fromkeys(block[~locked]):   # blocks of kept subjects are already complete
            rows = np.flatnonzero((block.to_numpy() == bl) & ~locked)
            units.append(Unit(bl, "block", sorted(set(cell_of[rows].tolist())), len(rows)))
    return members, units, block, cell_stratum


def _prepare(spec: DesignSpec, rng) -> _Ctx:
    T = list(spec.treatments)
    t = len(T)
    tix = {name: i for i, name in enumerate(T)}
    rp = spec.randomized_periods
    p = len(rp)
    pos_of_period = {k + 1: j for j, k in enumerate(rp)}
    forbidden_pos = sorted({(pos_of_period[k], tix[a]) for a, k in spec.forbidden_periods if k in pos_of_period})
    order_idx = sorted({(tix[a], tix[b]) for a, b in spec.order_rules})
    banned = {(tix[a], tix[b]) for a, b in spec.forbidden_transitions} | {(b, a) for a, b in order_idx}
    repeat_ok = spec.allow_back_to_back and spec.max_per_subject > 1
    allowed_pairs = [(a, b) for a in range(t) for b in range(t)
                     if (a != b or repeat_ok) and (a, b) not in banned]
    members, units, block, cell_stratum = _cells_and_units(spec, rng)
    ctx = _Ctx(spec=spec, T=T, t=t, p=p, adj=list(spec.adjacent_pairs), allowed_pairs=allowed_pairs,
               forbidden_pos=forbidden_pos, order_idx=order_idx,
               w=np.array([spec.weight(n) for n in T]),
               need_cooc=spec.max_per_subject == 1 and 2 <= p < t and spec.cooccurrence_balance != "off",
               members=members, units=units, block=block, cell_stratum=cell_stratum)
    if spec.locked:
        ids = spec.subjects[spec.id_column].astype(str).to_numpy()
        for c, mem in enumerate(members):
            seq = spec.locked.get(ids[mem[0]])
            if seq is not None:
                row = np.array([tix[x] for x in seq], int)
                ctx.locked_rows[c] = np.tile(row, (len(mem), 1))
    limit = SEQUENCE_VAR_LIMIT // max(1, len(members))
    if spec.max_per_subject > 1 or math.perm(t, p) <= 20 * limit:
        ctx.seqs = _enumerate_sequences(spec, t, p, ctx.adj, set(allowed_pairs), forbidden_pos, order_idx, limit)
        if ctx.seqs is not None and len(ctx.seqs) == 0:
            raise DesignError("No treatment order satisfies the per-subject rules "
                              "(forbidden transitions / periods / order rules). Relax them.")
    return ctx


def _band(target):
    return math.floor(target + 1e-9), math.ceil(target - 1e-9)


def _build(ctx: _Ctx, members, units, levels, pin=True):
    """Build the balance model for the given cells. `levels` maps each criterion
    (period, carryover, cooccurrence, spread) to required / preferred / off.
    With `pin`, kept subjects (members must be ctx.members) can never change.
    Returns (model, form, penalty variable groups)."""
    spec, t, p, w = ctx.spec, ctx.t, ctx.p, ctx.w
    model = _Model()
    form = _SequenceForm(model, ctx, members) if ctx.seqs is not None else _SubjectForm(model, ctx, members)
    if pin:
        for c, rows in ctx.locked_rows.items():
            model.pin(*form.encode(c, rows))
    penalties: dict[str, list[np.ndarray]] = {}

    def balance(expr, target, level, kind, tag):
        if level == "off":
            return
        lo, hi = _band(target)
        idx, coef = expr
        if level == "required":
            model.add_row(idx, coef, lo, hi)
            return
        ou = model.add_vars(2, cost=PENALTY[(tag, kind)])
        model.add_row(np.r_[idx, ou[0]], np.r_[coef, -1.0], -INF, hi)
        model.add_row(np.r_[idx, ou[1]], np.r_[coef, 1.0], lo, INF)
        penalties.setdefault(tag, []).append((ou, idx, coef, lo, hi))
        model.tier_vars.setdefault((tag, kind), []).append(ou)

    def evenness(expr, target, kind):
        """Squared distance of a count from its target, exact at integer counts near the target.
        It separates even from uneven splits when the bands cannot all be met (e.g. under
        forbidden transitions), where the distance from the bands is the same for both."""
        idx, coef = expr
        if not len(idx):
            return
        s = model.add_vars(1, cost=PENALTY[("carryover_even", kind)])
        f = lambda v: (v - target) ** 2                                   # noqa: E731
        k0 = max(0, math.floor(target) - EVEN_WINDOW)
        for k in range(k0, math.ceil(target) + EVEN_WINDOW):
            slope = f(k + 1) - f(k)                    # s >= f(k) + slope * (count - k)
            model.add_row(np.r_[s, idx], np.r_[1.0, -slope * coef], f(k) - slope * k, INF)
        model.tier_vars.setdefault(("carryover_even", kind), []).append(s)

    forb = set(ctx.forbidden_pos)
    for u in units:
        for k in range(p):
            allowed = [a for a in range(t) if (k, a) not in forb]
            wsum = w[allowed].sum()
            for a in allowed:
                balance(_concat(form.period(c, k, a) for c in u.cells),
                        u.size * w[a] / wsum, levels["period"], u.kind, "period")

    seq_units = [u for u in units if u.kind == "overall" or (u.kind == "group" and spec.balance_scope == "groups")]
    adj, pairs = ctx.adj, ctx.allowed_pairs
    if adj and pairs:
        pw = np.array([w[a] * w[b] for a, b in pairs])
        pw = pw / pw.sum()
        for u in seq_units:
            for q, (a, b) in enumerate(pairs):
                per_adj = [_concat(form.transition(c, j, a, b) for c in u.cells) for j in range(len(adj))]
                balance(_concat(per_adj), u.size * len(adj) * pw[q], levels["carryover"], u.kind, "carryover")
                if levels["carryover"] == "preferred" and len(pairs) > 1:
                    evenness(_concat(per_adj), u.size * len(adj) * pw[q], u.kind)
                for j in range(len(adj)):
                    balance(per_adj[j], u.size * pw[q], levels["spread"], u.kind, "spread")
    if levels.get("fulllist", "off") != "off" and isinstance(form, _SequenceForm) and form.seqs.shape[1] >= 4:
        _add_fulllist(model, form, [u for u in seq_units if u.kind != "block"])
    if ctx.need_cooc:
        lam = p * (p - 1) / (t * (t - 1))
        for u in seq_units:
            for a in range(t):
                for b in range(a + 1, t):
                    balance(_concat(form.cooc(c, a, b) for c in u.cells),
                            u.size * lam, levels["cooccurrence"], u.kind, "cooccurrence")
    return model, form, penalties


FULLLIST_STEP = 2                # the observer has seen this many sessions of the participant


def _add_fulllist(model, form, units):
    """Full-list observer: someone who holds the complete list and knows a participant's group
    sees the first FULLLIST_STEP sessions and guesses the most common continuation among the
    group's matching rows. Within a unit, that observer is right for max_c m(q, c) participants
    with beginning q, where m(q, c) counts those continuing with c. One variable per beginning,
    at least every continuation count, makes the number of correct guesses linear."""
    seqs, k = form.seqs, FULLLIST_STEP
    groups: dict[tuple, dict[int, list[int]]] = {}
    for i, s in enumerate(seqs):
        groups.setdefault(tuple(s[:k]), {}).setdefault(int(s[k]), []).append(i)
    for u in units:
        for conts in groups.values():
            M = model.add_vars(1, cost=PENALTY[("fulllist", u.kind)])
            for ids in conts.values():
                idx = np.concatenate([form.m[c][ids] for c in u.cells])
                model.add_row(np.r_[M, idx], np.r_[1.0, -np.ones(len(idx))], 0.0, INF)
            model.tier_vars.setdefault(("fulllist", u.kind), []).append(M)


def deviation_counts(x, penalties):
    """Total distance of each penalized count from its ideal [floor, ceil] range, evaluated on the
    actual design (penalty variables themselves may overstate it once the objective is capped)."""
    out = {}
    for tag, items in penalties.items():
        total = 0.0
        for _, idx, coef, lo, hi in items:
            v = float(coef @ np.round(x[idx])) if len(idx) else 0.0
            total += max(0.0, v - hi) + max(0.0, lo - v)
        out[tag] = round(total, 6)
    return out


def _encode_all(form, members, rows_per_cell):
    parts = [form.encode(c, rows_per_cell[c]) for c in range(len(members))]
    return np.concatenate([q[0] for q in parts]), np.concatenate([q[1] for q in parts])


def _with_kept(ctx, rows_per_cell):
    """A start assignment with the kept subjects' sequences put back."""
    if rows_per_cell is None or not ctx.locked_rows:
        return rows_per_cell
    return [ctx.locked_rows.get(c, r) for c, r in enumerate(rows_per_cell)]


def _complete_solution(model, form, members, rows_per_cell, seed):
    """Full variable vector for a given assignment (fix decisions, solve for the rest)."""
    fix = _encode_all(form, members, rows_per_cell)
    x, _, _ = model.solve(model.cost, 30, 1.0, seed, fix=fix)
    return x


# ------------------------------------------------------------------ warm start
def williams_square(t: int) -> np.ndarray:
    """Williams design: rows are subjects, columns periods. Each treatment is directly
    followed by every other treatment equally often (t rows for even t, 2t for odd t)."""
    first, lo, hi = [0], 1, t - 1
    while len(first) < t:
        first.append(lo); lo += 1
        if len(first) < t:
            first.append(hi); hi -= 1
    sq = (np.array(first)[None, :] + np.arange(t)[:, None]) % t
    return sq if t % 2 == 0 else np.vstack([sq, sq[:, ::-1]])


def _williams_start(ctx: _Ctx, rng, candidates=300):
    """Fill cells with relabelled Williams squares (complete designs without rules).

    Each new square's relabelling and direction (forward / time-reversed, both
    carry-over balanced) is chosen among random candidates to minimize repeated
    transitions within each period change. For odd t a Williams design is two Latin
    squares; the second (mirror) square continues into the next cell.
    """
    spec, t = ctx.spec, ctx.t
    if not (spec.is_complete and spec.max_per_subject == 1) or t < 2:
        return None
    if spec.forbidden_transitions or spec.forbidden_periods or spec.order_rules:
        return None
    base = williams_square(t)
    adj = ctx.adj
    k1 = np.array([a for a, _ in adj], int)
    k2 = np.array([b for _, b in adj], int)
    counts = np.zeros((len(adj), t, t))          # transitions placed so far, overall

    def increments(rows):
        inc = np.zeros_like(counts)
        for j in range(len(adj)):
            np.add.at(inc[j], (rows[:, k1[j]], rows[:, k2[j]]), 1)
        return inc

    def next_block():
        best, best_score = None, np.inf
        for _ in range(candidates):
            perm = rng.permutation(t)
            rows = perm[base[:, ::-1] if rng.random() < 0.5 else base]
            score = ((counts + increments(rows)) ** 2).sum()
            if score < best_score:
                best, best_score = rows, score
        return [best[i:i + t] for i in range(0, len(best), t)]    # Latin squares

    # Whole Latin squares fill each cell; the leftover rows (< t) of every cell come from ONE shared
    # square, taken in rotation. Each cell's leftovers are distinct rows of that square (period-
    # balanced within the cell) and, summed over cells, every row is used equally often (+-1), so
    # the start is also period-balanced within groups and overall.
    shared, cursor = None, 0
    queue, out = [], []
    for c, mem in enumerate(ctx.members):
        if c and ctx.cell_stratum[c] != ctx.cell_stratum[c - 1]:
            queue = []              # mirror squares only continue within the same group
        n, rows = len(mem), []
        while n - len(rows) >= t:
            if not queue:
                queue = next_block()
            square = queue.pop(0)[rng.permutation(t)]
            counts += increments(square)
            rows.extend(square)
        r = n - len(rows)
        if r:
            if shared is None:
                shared = next_block()[0]
            take = shared[(cursor + np.arange(r)) % t]
            cursor = (cursor + r) % t
            counts += increments(take)
            rows.extend(take)
        out.append(np.array(rows)[rng.permutation(n)])
    return out


CYCLIC_MAX_REPS = 50_000         # (t-1)! initial orders; covers t <= 9


def _cyclic_ok(ctx: _Ctx) -> bool:
    """The cyclic search applies to complete designs without rules whose cells are whole blocks."""
    spec, t = ctx.spec, ctx.t
    return (spec.is_complete and spec.max_per_subject == 1 and t >= 3 and bool(ctx.adj)
            and not ctx.locked_rows
            and not (spec.forbidden_transitions or spec.forbidden_periods or spec.order_rules)
            and len(set(ctx.w.tolist())) == 1 and math.factorial(t - 1) <= CYCLIC_MAX_REPS
            and all(len(m) % t == 0 and len(m) > 0 for m in ctx.members))


def _cyclic_start(ctx: _Ctx, rng, levels, seed, time_limit):
    """Search the cyclic subspace for a design meeting `levels` (or as close as possible).

    A cyclic block develops one initial order r (r_1 = 0) mod t: rows r + i, i = 0..t-1. Each block
    is a Latin square, so session balance holds in every cell. In a design built from blocks, the
    number of times the ordered pair (a, a + d) occurs at transition j equals the number of initial
    orders with difference d at j, whatever a is. Carry-over and spread therefore depend only on
    these differences, and the search is a small integer program over initial orders, much smaller
    than the full model. Williams squares and the three-square designs of Newcombe and Prescott are
    cyclic. Returns rows per cell, or None if the subspace has no design meeting the required
    criteria within the time limit."""
    t, adj = ctx.t, ctx.adj
    reps = np.array([(0,) + q for q in __import__("itertools").permutations(range(1, t))], dtype=int)
    k1 = np.array([a for a, _ in adj], int)
    k2 = np.array([b for _, b in adj], int)
    D = (reps[:, k2] - reps[:, k1]) % t                       # (R, J) differences per transition
    R, J = D.shape
    m = t * (t - 1)
    model = _Model()
    y = []
    for mem in ctx.members:
        v = model.add_vars(R, ub=len(mem) // t, integer=True)
        model.add_row(v, 1.0, len(mem) // t, len(mem) // t)
        y.append(v)

    def balance(idx, coef, target, level, kind, tag):
        if level == "off":
            return
        lo, hi = _band(target)
        if level == "required":
            model.add_row(idx, coef, lo, hi)
            return
        ou = model.add_vars(2, cost=PENALTY[(tag, kind)])
        model.add_row(np.r_[idx, ou[0]], np.r_[coef, -1.0], -INF, hi)
        model.add_row(np.r_[idx, ou[1]], np.r_[coef, 1.0], lo, INF)

    spec = ctx.spec
    units = [u for u in ctx.units if u.kind == "overall" or (u.kind == "group" and spec.balance_scope == "groups")]
    carry_coef = [(D == d).sum(1).astype(float) for d in range(t)]
    for u in units:
        idx = np.concatenate([y[c] for c in u.cells])
        for d in range(1, t):
            balance(idx, np.tile(carry_coef[d], len(u.cells)), u.size * J / m, levels.get("carryover", "off"),
                    u.kind, "carryover")
            for j in range(J):
                balance(idx, np.tile((D[:, j] == d).astype(float), len(u.cells)), u.size / m,
                        levels.get("spread", "off"), u.kind, "spread")
    cost = model.cost.copy()
    dec = np.concatenate(y)
    has_pen = bool(np.any(cost > 0))
    cost[dec] += rng.random(len(dec)) * (0.5 / max(1, len(dec)) if has_pen else 1.0)   # random tie-breaking
    x, _, _ = model.solve(cost, time_limit, 1e-6 if has_pen else 1.0, seed)
    if x is None:
        return None
    rows_per_cell = []
    for c, mem in enumerate(ctx.members):
        counts = np.round(x[y[c]]).astype(int)
        blocks = [(reps[r][None, :] + np.arange(t)[:, None]) % t for r in np.flatnonzero(counts)
                  for _ in range(counts[r])]
        rows = np.vstack(blocks)
        rows_per_cell.append(rows[rng.permutation(len(rows))])
    return rows_per_cell


def _greedy_start(ctx: _Ctx, rng, budget, seed, say, levels):
    """Place subjects chunk by chunk, each chunk solved as a small ILP given the ones placed.
    Small cells are one chunk; large cells are split into chunks of about two Latin squares."""
    chunk = 2 * max(ctx.t, 2)
    chunks, chunk_cell = [], []
    for c, mem in enumerate(ctx.members):
        mem = mem[rng.permutation(len(mem))]
        n_parts = 1 if len(mem) <= 1.5 * chunk else len(mem) // chunk
        for part in np.array_split(mem, n_parts):
            chunks.append(part)
            chunk_cell.append(c)
    if len(chunks) < 2:
        return None
    order = rng.permutation(len(chunks))
    placed: dict[int, np.ndarray] = {}
    kept = [a for a in range(len(chunks)) if chunk_cell[a] in ctx.locked_rows]
    for a in kept:                      # kept subjects are placed first and never move
        placed[a] = ctx.locked_rows[chunk_cell[a]][:len(chunks[a])]
    order = np.array(kept + [int(a) for a in order if a not in set(kept)], int)
    if len(kept) == len(chunks):
        return None
    per_step = max(1.0, budget / len(chunks))
    for step in range(len(kept), len(chunks)):
        active = [int(a) for a in order[:step + 1]]
        say(f"Warm start: placing subject chunk {step + 1} of {len(chunks)}…")
        members = [chunks[a] for a in active]
        units = []
        for u in ctx.units:
            cs = [i for i, a in enumerate(active) if chunk_cell[a] in u.cells]
            if cs:
                units.append(Unit(u.name, u.kind, cs, int(sum(len(members[i]) for i in cs))))
        model, form, _ = _build(ctx, members, units, levels, pin=False)
        fixed = [i for i, a in enumerate(active) if a in placed]
        fix = None
        if fixed:
            parts = [form.encode(i, placed[active[i]]) for i in fixed]
            fix = (np.concatenate([q[0] for q in parts]), np.concatenate([q[1] for q in parts]))
        cost = model.cost.copy()
        cost[form.decision] += rng.random(len(form.decision)) * 0.5 / max(1, form.mass)
        x, _, _ = model.solve(cost, per_step, 0.01, seed, fix=fix)
        if x is None:
            return None
        placed[active[-1]] = form.extract(x, len(active) - 1)
    rows_per_cell = []
    for c, mem in enumerate(ctx.members):
        rows = np.zeros((len(mem), ctx.p), dtype=int)
        pos = {s: i for i, s in enumerate(mem)}
        for ch, cc in enumerate(chunk_cell):
            if cc == c:
                for s, r in zip(chunks[ch], placed[ch]):
                    rows[pos[s]] = r
        rows_per_cell.append(rows)
    return rows_per_cell


# ------------------------------------------------------------------ improvement
def _lns(model, form, members, x, cost, rng, seed, deadline, say):
    """Large-neighbourhood search: free a random subset of subjects, re-solve the ILP
    with everyone else fixed, keep the result if it is no worse. Repeat until time is up."""
    sizes = np.array([len(m) for m in members])
    N = int(sizes.sum())
    best = float(cost @ x)
    k = int(min(N, max(4, N // 3)))
    it = 0
    while _CLOCK.now() < deadline - 0.3 and best > 1e-9 and N > 1:
        it += 1
        if rng.random() < 0.3:          # focus on one cell (e.g. one group or block)
            c = int(rng.integers(len(members)))
            free = np.zeros(len(members), int)
            free[c] = min(sizes[c], k)
            rest = k - free[c]
            if rest > 0:
                extra = rng.choice(N, size=min(rest, N), replace=False)
                free += np.minimum(np.bincount(np.searchsorted(np.cumsum(sizes), extra, side="right"),
                                               minlength=len(members)), sizes - free)
        else:
            pick = rng.choice(N, size=k, replace=False)
            free = np.bincount(np.searchsorted(np.cumsum(sizes), pick, side="right"), minlength=len(members))
        parts = [form.release(x, c, int(free[c]), rng) for c in range(len(members))]
        bounds = tuple(np.concatenate([q[i] for q in parts]) for i in range(3))
        limit = min(deadline - _CLOCK.now(), 4.0)
        xn, _, opt = model.solve(cost, limit, 1e-6, seed + it, start=x, bounds=bounds)
        if xn is not None and cost @ xn <= best + 1e-9:
            if cost @ xn < best - 1e-9:
                say(f"Improving balance… (penalty {cost @ xn:.0f})")
            x, best = xn, float(cost @ xn)
        k = int(min(N, k * 1.25 + 1)) if opt else int(max(2, k * 0.7))
    return x


# ------------------------------------------------------------------ final choice
ENUM_MAX_FAMILIES = 300          # stop listing beyond this many designs (relabelling families)
ENUM_MAX_RELABELLINGS = 720       # list relabelling families only up to t = 6 (t! relabellings)
WALK_GAP = 0.05                   # relative gap of each random-walk step
SMALL_SPACE = 10                  # warn when no more equally balanced designs (families) than this exist


def _relabel_index(ctx, form):
    """For every relabelling pi of the conditions, the index of pi(s) for each order s."""
    import itertools
    seqs = form.seqs
    perms = np.array(list(itertools.permutations(range(ctx.t))), dtype=int)
    return np.array([[form.seq_index[tuple(pi[s])] for s in seqs] for pi in perms])


def _enumerate_optimal(model, form, ctx, members, symmetric, seed, deadline, say, x0=None):
    """List every design as balanced as the current cap allows (the model must already contain the
    cap on the penalty). With `symmetric`, designs are listed by relabelling family: each found design
    excludes its whole family, and the family's size is recorded so that a uniform draw over families
    weighted by size, followed by the solver's uniform relabelling, is uniform over designs.

    Returns (list of count vectors per cell, family sizes, complete)."""
    m = model.copy()
    cells = form.m
    sizes_c = [len(mem) for mem in members]
    perm_idx = _relabel_index(ctx, form) if symmetric else None
    ident = None
    if symmetric:
        # Symmetry breaking: every family has a member in which some subject of cell 0 receives the
        # identity order (relabel any of its rows), so the search can be restricted to such members.
        ident = form.seq_index.get(tuple(range(ctx.p)))
        if ident is not None:
            m.add_row([cells[0][ident]], [1.0], 1.0, INF)
    sols, fam, total, it = [], [], 0, 0
    while _CLOCK.now() < deadline - 0.2:
        it += 1
        if it == 1 and x0 is not None:
            x = x0                             # the design in hand is the first member
        else:
            x, text, _ = m.solve(np.zeros(m.n), deadline - _CLOCK.now(), 1.0, seed + it)
            if x is None:
                return sols, fam, "nfeasible" in text
        v = [np.round(x[cells[c]]).astype(int) for c in range(len(cells))]
        members_of_family = [v]
        if symmetric:
            seen = {}
            for row in perm_idx:
                u = [np.zeros_like(vc) for vc in v]
                for c, vc in enumerate(v):
                    u[c][row] = vc
                seen.setdefault(b"".join(uc.tobytes() for uc in u), u)
            members_of_family = list(seen.values())
        sols.append(v)
        fam.append(len(members_of_family))
        total += len(members_of_family)
        if len(sols) > ENUM_MAX_FAMILIES:
            return sols, fam, False
        if ident is not None:                  # only members inside the restricted space need a cut
            members_of_family = [u for u in members_of_family if u[0][ident] >= 1]
        for u in members_of_family:            # no-good cut: some used order must be used less often
            zs, idx, coef = [], [], []
            for c, uc in enumerate(u):
                for s in np.flatnonzero(uc):
                    z = m.add_vars(1, ub=1.0, integer=True)[0]
                    m.add_row([cells[c][s], z], [1.0, sizes_c[c] - uc[s] + 1.0], -INF, sizes_c[c])
                    zs.append(z)
            m.add_row(zs, 1.0, 1.0, INF)
        if it % 10 == 0:
            say(f"Listing equally balanced designs… ({total} so far)")
    return sols, fam, False


def _random_walk(model, form, members, x, rng, seed, deadline):
    """Random moves among equally balanced designs: free a random third of the subjects and re-solve
    them with a random objective (the model contains the cap on the penalty). Returns (x, moves)."""
    sizes = np.array([len(mem) for mem in members])
    N = int(sizes.sum())
    k = int(min(N, max(3, N // 3)))
    moves, it = 0, 0
    while _CLOCK.now() < deadline - 0.3 and N > 1:
        it += 1
        before = moves
        pick = rng.choice(N, size=k, replace=False)
        free = np.bincount(np.searchsorted(np.cumsum(sizes), pick, side="right"), minlength=len(members))
        parts = [form.release(x, c, int(free[c]), rng) for c in range(len(members))]
        bounds = tuple(np.concatenate([q[j] for q in parts]) for j in range(3))
        rand_cost = np.zeros(model.n)
        rand_cost[form.decision] = rng.random(len(form.decision))
        # near-optimal for the random objective is enough to move; proving optimality is costly
        xn, _, _ = model.solve(rand_cost, min(2.0, deadline - _CLOCK.now()), WALK_GAP, seed + 1000 + it,
                               start=x, bounds=bounds)
        if xn is not None:
            if not np.array_equal(np.round(xn[form.decision]), np.round(x[form.decision])):
                moves += 1
            x = xn
        if moves == before:                   # stuck: free more subjects next time
            k = int(min(N, k + max(1, N // 6)))
    return x, moves


def _choose(model, form, ctx, members, x, rng, spec, deadline, symmetric, say):
    """Final random choice among designs as balanced as x (the model contains the cap)."""
    if spec.randomization == "speed":
        say("Picking a random design among the best ones…")
        rand_cost = np.zeros(model.n)
        rand_cost[form.decision] = rng.random(len(form.decision))
        t2 = max(2.0, min(deadline - _CLOCK.now(), max(3.0, 0.1 * spec.time_limit)))
        x2, _, _ = model.solve(rand_cost, t2, 0.25, spec.seed, start=x)
        return (x2 if x2 is not None else x), {"method": "random objective", "uniform": False, "designs": None}

    # why the walk is used: too many designs to list, listing ran out of time, or listing not possible
    # (per-subject formulation, or too many relabellings of the treatments)
    info = {"method": "random walk", "uniform": False, "designs": None, "reason": "not listable"}
    if isinstance(form, _SequenceForm) and (not symmetric or math.factorial(ctx.t) <= ENUM_MAX_RELABELLINGS):
        say("Listing all equally balanced designs…")
        sols, fam, complete = _enumerate_optimal(model, form, ctx, members, symmetric, spec.seed,
                                                 _CLOCK.now() + 0.85 * max(0.0, deadline - _CLOCK.now()), say,
                                                 x0=x)
        info["reason"] = "too many" if len(sols) > ENUM_MAX_FAMILIES else "time"
        if sols:
            # Target: every acceptable allocation of orders to subjects equally likely. A design whose
            # cell c uses order s n_cs times can be dealt to the cell's subjects in N_c! / prod_s n_cs!
            # distinct ways (the same for every member of a relabelling family), and step 2 deals it
            # uniformly, so each design is drawn with probability proportional to that number times
            # its family size.
            log_alloc = np.array([sum(math.lgamma(len(members[c]) + 1)
                                      - sum(math.lgamma(int(k) + 1) for k in v[c] if k > 1)
                                      for c in range(len(members))) for v in sols])
            w = np.array(fam, float) * np.exp(log_alloc - log_alloc.max())
            pick = int(rng.choice(len(sols), p=w / w.sum())) if complete else int(rng.integers(len(sols)))
            rows = [np.repeat(form.seqs, sols[pick][c], axis=0) for c in range(len(members))]
            xs = _complete_solution(model, form, members, rows, spec.seed)
            if xs is not None:
                x = xs
                if complete:
                    n_alloc = float(np.log10(np.sum(np.array(fam, float) * np.exp(log_alloc - log_alloc.max())))
                                    + log_alloc.max() / math.log(10))
                    return x, {"method": "uniform", "uniform": True, "designs": int(sum(fam)),
                               "families": len(fam), "log10_allocations": round(n_alloc, 2)}
    say("Moving randomly among equally balanced designs…")
    x, moves = _random_walk(model, form, members, x, rng, spec.seed, deadline)
    info["moves"] = moves
    return x, info


# ------------------------------------------------------------------ main entry
def solve(spec: DesignSpec, progress=None) -> Result:
    errors, warnings = validate(spec)
    if errors:
        raise DesignError("\n".join(errors))
    say = progress or (lambda msg: None)
    global BACKEND
    BACKEND = spec.solver
    if spec.solver == "gurobi" and not gurobi_available():
        raise DesignError("Gurobi was selected, but gurobipy or its license was not found. "
                          "Choose the built-in HiGHS solver instead.")
    global _CLOCK
    _CLOCK = _Clock(spec.deterministic, spec.time_limit)
    try:
        return _solve(spec, say, warnings)
    finally:
        _CLOCK = _Clock()


def _solve(spec: DesignSpec, say, warnings) -> Result:
    rng = np.random.default_rng(spec.seed)
    wall0 = time.time()
    t0 = _CLOCK.now()
    deadline = t0 + spec.time_limit

    def at(frac):           # search-clock time at a fraction of the time budget
        return t0 + frac * spec.time_limit

    # Phase ends (optimization of the criteria, neighbourhood search). Variety mode keeps 45% of the
    # time for the final choice among equally balanced designs; speed mode spends it on balance.
    p_glob, p_lns = (0.6, 0.85) if spec.randomization == "speed" else (0.4, 0.55)

    ctx = _prepare(spec, rng)
    members, units = ctx.members, ctx.units

    # ---------------- lexicographic hardening
    # In priority order, try to meet each "preferred" criterion perfectly as a hard
    # constraint (a fast feasibility problem). Criteria met this way are locked in. The first one
    # that cannot be met, and all after it, are then optimized one at a time (below).
    levels = {"period": spec.period_balance, "carryover": spec.carryover_balance,
              "cooccurrence": spec.cooccurrence_balance if ctx.need_cooc else "off",
              "spread": spec.spread_balance,
              "fulllist": "off" if spec.fulllist_balance == "off" else "preferred"}
    if not ctx.adj:
        levels["carryover"] = levels["spread"] = "off"
    if levels["fulllist"] != "off" and (ctx.seqs is None or ctx.p < FULLLIST_STEP + 2):
        levels["fulllist"] = "off"
        warnings.append("The full-list criterion was not applied: it needs at least "
                        f"{FULLLIST_STEP + 2} randomized {spec.period(plural=True)} and a design small "
                        "enough for the order-count model.")
    order = ["period", "carryover", "cooccurrence", "spread"]
    start_rows = _with_kept(ctx, _williams_start(ctx, rng)) if ctx.p > 1 else None
    cyclic = ctx.p > 1 and _cyclic_ok(ctx)
    locked, checks = [], {}
    for i, tag in enumerate(order):
        if levels[tag] != "preferred":
            continue
        if tag == "spread" and levels["fulllist"] != "off":
            break               # the full-list criterion comes before spread; optimize both below
        trial = {k: ("required" if k == tag else levels[k] if j < i else "off") for j, k in enumerate(order)}
        say(f"Checking whether perfect {LABELS[tag]} is possible…")
        m_t, f_t, _ = _build(ctx, members, units, trial)
        x0 = _complete_solution(m_t, f_t, members, start_rows, spec.seed) if start_rows is not None else None
        if x0 is None and cyclic and tag in ("carryover", "spread"):
            rows = _cyclic_start(ctx, rng, trial, spec.seed,
                                 max(2.0, min(0.1 * spec.time_limit, at(p_glob) - _CLOCK.now())))
            if rows is not None:
                x0 = _complete_solution(m_t, f_t, members, rows, spec.seed)
        text = ""
        if x0 is None:
            cap = max(5.0, min(0.25 * spec.time_limit, at(p_glob) - _CLOCK.now()))
            x0, text, _ = m_t.solve(np.zeros(m_t.n), cap, 1.0, spec.seed)
        if x0 is None:
            # "impossible" only when the solver proved it; otherwise the check ran out of time
            checks[tag] = "impossible" if "nfeasible" in text else "not settled"
            break
        checks[tag] = "met"
        levels[tag] = "required"
        locked.append(tag)
        start_rows = [f_t.extract(x0, c) for c in range(len(members))]

    say("Building the full ILP…")
    model, form, penalties = _build(ctx, members, units, levels)
    base_cost = model.cost
    start = _complete_solution(model, form, members, start_rows, spec.seed) if start_rows is not None else None
    if cyclic and penalties and (start is None or base_cost @ start > 1e-9):
        # the best cyclic design for the remaining (penalized) criteria is often a much better start
        rows = _cyclic_start(ctx, rng, levels, spec.seed,
                             max(2.0, min(0.1 * spec.time_limit, at(p_glob) - _CLOCK.now())))
        if rows is not None:
            xc = _complete_solution(model, form, members, rows, spec.seed)
            if xc is not None and (start is None or base_cost @ xc < base_cost @ start - 1e-9):
                start = xc
    tiers = [(tag, kinds) for tag, kinds in TIERS if any(model.tier_vars.get((tag, k)) for k in kinds)]
    if start is None and ctx.p > 1 and tiers:
        rows = _greedy_start(ctx, rng, 0.3 * spec.time_limit, spec.seed, say, levels)
        if rows is not None:
            start = _complete_solution(model, form, members, rows, spec.seed)

    # ---------------- criteria one at a time (preemptive goal programming)
    proven, x, criteria = True, start, {}
    for i, (tag, kinds) in enumerate(tiers):
        name = tag if len(kinds) > 1 else f"{tag}:{kinds[0]}"
        if tag == "carryover_even" and all(criteria.get(f"carryover:{k}", {}).get("value", 0) <= 1e-9
                                           for k in ("group", "overall")):
            continue            # every carry-over count is in its band: evenness cannot change
        say(f"Optimizing {LABELS[tag]}" + (f" within groups…" if kinds == ("group",) else "…"))
        c = sum(model.tier_cost((tag, k)) for k in kinds)
        tier_start = _CLOCK.now()
        share = max(1.0, (at(p_lns) - tier_start) / (len(tiers) - i))
        x1, text, opt = model.solve(c, 0.7 * share, 1e-6, spec.seed + i, start=x)
        if x1 is not None and (x is None or c @ x1 <= c @ x + 1e-9):
            x = x1
        if x is None:
            raise DesignError(_infeasible_message(text, spec))
        if c @ x > 1e-9 and not opt:
            x = _lns(model, form, members, x, c, rng, spec.seed + 100 * i, tier_start + share, say)
        z = float(c @ x)
        ok = bool(opt or z <= 1e-9)
        proven &= ok
        criteria[name] = {"value": round(z, 6), "proven": ok}
        nz = np.flatnonzero(c)
        model.add_row(nz, c[nz], -INF, z + 1e-6 * max(1.0, abs(z)) + 1e-6)     # cap: never worse

    symmetric = (not spec.forbidden_transitions and not spec.forbidden_periods and not spec.order_rules
                 and len(set(ctx.w.tolist())) == 1 and not spec.locked)
    if x is None:
        # all criteria required and no start available: find any feasible design first
        x, text0, _ = model.solve(np.zeros(model.n), max(2.0, deadline - _CLOCK.now()), 1.0, spec.seed)
        if x is None:
            raise DesignError(_infeasible_message(text0, spec))
    x, rand_info = _choose(model, form, ctx, members, x, rng, spec, deadline, symmetric, say)
    status = "optimal" if proven else "best found within the time limit"
    if rand_info.get("uniform") and rand_info.get("families", 99) <= SMALL_SPACE:
        k = rand_info["families"]
        warnings.append(f"Only {k} equally balanced design{'s' if k > 1 else ''} exist"
                        + (" up to relabelling the treatments" if symmetric else "")
                        + f", so the randomness comes mainly from which {spec.noun(plural=False)} gets which order"
                        + (" and from relabelling the treatments." if symmetric else "."))
    unsettled = [LABELS[k] for k, v in checks.items() if v == "not settled"]
    if unsettled and not proven:
        warnings.append(f"The check whether perfect {unsettled[0]} is possible did not finish in time. "
                        "A longer time limit may give a better balanced schedule.")
    reproducible = None
    if _CLOCK.det:
        reproducible = not _CLOCK.cap_hit
        if _CLOCK.cap_hit:
            warnings.append("A solve hit the safety time cap, so this schedule may not be reproduced exactly "
                            "on another computer. Keep the saved schedule as the record.")

    # ---------------- assemble
    t = ctx.t
    assign = np.zeros((len(spec.subjects), ctx.p), dtype=int)
    for c, mem in enumerate(members):
        rows = form.extract(x, c)
        assign[mem] = rows[rng.permutation(len(rows))]
    if symmetric:
        assign = rng.permutation(t)[assign]

    labels = np.empty((len(spec.subjects), spec.n_periods), dtype=object)
    for k, lab in spec.fixed.items():
        labels[:, k - 1] = lab
    labels[:, spec.randomized_periods] = np.array(ctx.T, dtype=object)[assign]
    period_cols = [f"{spec.period_name} {k + 1}" for k in range(spec.n_periods)]
    schedule = spec.subjects.reset_index(drop=True).copy()
    if spec.block_sizes:
        schedule["Block"] = ctx.block.to_numpy()
    for k, col in enumerate(period_cols):
        schedule[col] = labels[:, k]

    codes = None
    if spec.blind:
        pool = [chr(ord("A") + i) for i in range(26)] if t <= 26 else [f"T{i + 1:02d}" for i in range(t)]
        chosen = rng.permutation(len(pool))[:t]
        codes = {name: pool[i] for name, i in zip(ctx.T, chosen)}

    violations = {tag: 0.0 for tag in locked}
    violations.update(deviation_counts(x, penalties))
    subject_units = [np.concatenate([members[c] for c in u.cells]) for u in units]
    return Result(spec=spec, schedule=schedule, period_columns=period_cols, assign=assign, units=units,
                  subject_unit_ids=subject_units, codes=codes, status=status, proven_optimal=proven,
                  formulation=form.name, violations=violations, solve_seconds=time.time() - wall0,
                  warnings=warnings, levels=levels, randomization=rand_info, checks=checks,
                  criteria=criteria, reproducible=reproducible,
                  work_seconds=round(_CLOCK.used, 2) if _CLOCK.det else None)


def _infeasible_message(status_text, spec):
    if "nfeasible" in status_text:
        hard = [name for name, lvl in [("period balance", spec.period_balance),
                                        ("carry-over balance", spec.carryover_balance),
                                        ("spread within period changes", spec.spread_balance),
                                        ("co-occurrence balance", spec.cooccurrence_balance)]
                if lvl == "required"]
        msg = "No design satisfies all hard rules."
        if hard:
            msg += f" Try setting {', '.join(hard)} to 'preferred' instead of 'required'."
        if spec.forbidden_transitions or spec.forbidden_periods or spec.order_rules:
            msg += " Forbidden transitions/periods and order rules may also be too strict."
        return msg
    return (f"The solver found no design within {spec.time_limit:.0f} s ({status_text}). "
            "Increase the time limit or relax 'required' rules.")
