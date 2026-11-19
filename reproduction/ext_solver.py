"""A research copy of the solver with extra model options, used for the exact models behind proofs
and certificates.

It reuses the app's internals (formulations, model builder, warm starts, LNS) and copies its
pipeline: lexicographic hardening -> global ILP -> LNS -> random pick among the best -> shuffle
and relabel. Extensions are switched on through `Options`:

  tolerance  (step 1) balance vs randomness: in the final random pick, allow each listed
             criterion to be up to k deviation counts worse than the best design found, so the
             random choice ranges over a larger set of near-optimal designs.
             e.g. Options(tolerance={"spread": 5}).
  nested     (step 2) nested carry-over balance: carry-over is also balanced within every prefix of
             the schedule (periods 1-2, 1-3, ..., 1-(p-1)), so the design stays balanced when the
             study is cut short or subjects drop out early. "off" / "preferred" / "required".
             Priority: after full carry-over, before co-occurrence and spread.
  predict_weight  (step 3) sequence predictability: penalize the accuracy of an observer who holds
             the complete allocation list (without subject identities), sees a subject's first k
             treatments and guesses the most common continuation among matching rows (metric G3).
             For each prefix q of length k, that observer is right for exactly max_c m(q, c)
             subjects, where m(q, c) counts subjects whose sequence starts with q and continues
             with c. So  N * G3_k = sum_q max_c m(q, c), which is linear with one auxiliary
             variable M_q >= m(q, c) per prefix. The penalty is weight * sum_k sum_q M_q over
             k = 1 .. p-2 (k = p-1 is always fully predictable in a complete design).
             Pooled over all subjects; sequence-count formulation only. Not hardened: it is a
             pure minimization term, placed by its weight relative to the app's penalties
             (spread 10 overall / 3 per stratum, carry-over 100 / 30).
  rerank     (step 4) precision re-ranking: in the final random pick, collect this many designs
             from the set of equally balanced designs (by the random walk below) and keep the one
             with the highest A-efficiency under the model with first-order carry-over (exact,
             nonlinear; ties broken at random).
  walk_pick  replace the app's final random pick (re-solve the whole capped model with a random
             objective, which in larger problems usually returns its start unchanged) by a random
             walk: repeatedly free a random third of the subjects and re-solve them with a random
             objective, staying as balanced as the best design.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from randomizer import solver as S
from randomizer.spec import validate

INF = S.INF


@dataclass
class Options:
    tolerance: dict = field(default_factory=dict)      # criterion -> extra deviation counts allowed
    nested: str = "off"                                 # nested (prefix) carry-over balance
    predict_weight: float = 0.0                         # weight of the G3 predictability term
    predict_steps: tuple | None = None                  # prefix lengths k to include (None = 1..p-2)
    rerank: int = 0                                     # step 4: candidates re-ranked by M2 efficiency
    walk_pick: bool = False                             # random pick by a random walk (see below)


ORDER = ["period", "carryover", "nested", "cooccurrence", "spread"]
NESTED_PENALTY = {"overall": 30.0, "group": 10.0}       # between carry-over and spread


def _build(ctx, members, units, levels):
    """The app's model, plus the research criteria switched on in `levels`."""
    model, form, penalties = S._build(ctx, members, units, levels)
    if levels.get("nested", "off") != "off":
        _add_nested(model, form, penalties, ctx, units, levels["nested"])
    if levels.get("predict_w", 0.0) > 0:
        _add_predict(model, form, ctx, levels["predict_w"], levels.get("predict_k"))
    return model, form, penalties


def _add_predict(model, form, ctx, weight, steps=None):
    """Linear model of the full-list observer's hit count (see module docstring)."""
    if ctx.seqs is None:
        raise S.DesignError("The predictability term needs the sequence-count formulation.")
    seqs, p = form.seqs, form.seqs.shape[1]
    for k in (steps or range(1, p - 1)):                       # prefix length k (default 1 .. p-2)
        if not 1 <= k <= p - 2:
            continue
        groups: dict[tuple, dict[int, list[int]]] = {}
        for i, s in enumerate(seqs):
            groups.setdefault(tuple(s[:k]), {}).setdefault(int(s[k]), []).append(i)
        for conts in groups.values():
            M = model.add_vars(1, cost=weight)
            for ids in conts.values():
                idx = np.concatenate([form.m[c][ids] for c in range(len(form.m))])
                model.add_row(np.r_[M, idx], np.r_[1.0, -np.ones(len(idx))], 0.0, INF)


def _add_nested(model, form, penalties, ctx, units, level):
    spec, w, adj, pairs = ctx.spec, ctx.w, ctx.adj, ctx.allowed_pairs
    if not adj or not pairs:
        return
    seq_units = [u for u in units if u.kind == "overall" or (u.kind == "group" and spec.balance_scope == "groups")]
    pw = np.array([w[a] * w[b] for a, b in pairs])
    pw = pw / pw.sum()
    adj_order = sorted(range(len(adj)), key=lambda j: adj[j][0])
    for u in seq_units:
        for q, (a, b) in enumerate(pairs):
            per_adj = {j: S._concat(form.transition(c, j, a, b) for c in u.cells) for j in adj_order}
            for m in range(1, len(adj)):                   # first m changes = first m+1 periods
                idx, coef = S._concat(per_adj[j] for j in adj_order[:m])
                lo, hi = S._band(u.size * m * pw[q])
                if level == "required":
                    model.add_row(idx, coef, lo, hi)
                    continue
                ou = model.add_vars(2, cost=NESTED_PENALTY[u.kind])
                model.add_row(np.r_[idx, ou[0]], np.r_[coef, -1.0], -INF, hi)
                model.add_row(np.r_[idx, ou[1]], np.r_[coef, 1.0], lo, INF)
                penalties.setdefault("nested", []).append((ou, idx, coef, lo, hi))


@dataclass
class ExtResult:
    assign: np.ndarray
    levels: dict
    violations: dict
    proven: bool
    seconds: float
    best_violations: dict          # deviations of the best design before the random pick
    rerank_effs: list = field(default_factory=list)   # step 4: efficiencies of the candidates
    walk_moves: int = 0                                # random-walk steps that changed the design


def _penalty_sum_row(model, items):
    idx = np.concatenate([ou for ou, *_ in items])
    return idx, np.ones(len(idx))


def solve_ext(spec, opts: Options | None = None) -> ExtResult:
    opts = opts or Options()
    errors, _ = validate(spec)
    if errors:
        raise S.DesignError("\n".join(errors))
    rng = np.random.default_rng(spec.seed)
    t0 = time.time()
    deadline = t0 + spec.time_limit

    def at(frac):
        return t0 + frac * spec.time_limit

    ctx = S._prepare(spec, rng)
    members, units = ctx.members, ctx.units

    levels = {"period": spec.period_balance, "carryover": spec.carryover_balance,
              "cooccurrence": spec.cooccurrence_balance if ctx.need_cooc else "off",
              "spread": spec.spread_balance, "nested": opts.nested,
              "predict_w": opts.predict_weight, "predict_k": opts.predict_steps}
    if not ctx.adj:
        levels["carryover"] = levels["spread"] = levels["nested"] = "off"
    order = ORDER
    start_rows = S._williams_start(ctx, rng) if ctx.p > 1 else None
    locked = []
    for i, tag in enumerate(order):
        if levels[tag] != "preferred":
            continue
        trial = {k: ("required" if k == tag else levels[k] if j < i else "off") for j, k in enumerate(order)}
        m_t, f_t, _ = _build(ctx, members, units, trial)
        x0 = S._complete_solution(m_t, f_t, members, start_rows, spec.seed) if start_rows is not None else None
        if x0 is None:
            cap = max(5.0, min(0.25 * spec.time_limit, at(0.6) - time.time()))
            x0, _, _ = m_t.solve(np.zeros(m_t.n), cap, 1.0, spec.seed)
        if x0 is None:
            break
        levels[tag] = "required"
        locked.append(tag)
        start_rows = [f_t.extract(x0, c) for c in range(len(members))]

    model, form, penalties = _build(ctx, members, units, levels)
    base_cost = model.cost
    start = S._complete_solution(model, form, members, start_rows, spec.seed) if start_rows is not None else None
    if start is None and ctx.p > 1 and penalties:
        rows = S._greedy_start(ctx, rng, 0.3 * spec.time_limit, spec.seed, lambda m: None, levels)
        if rows is not None:
            start = S._complete_solution(model, form, members, rows, spec.seed)

    proven, x = not penalties, start
    best_dev = {}
    if penalties:
        x1, text, proven = model.solve(base_cost, at(0.6) - time.time(), 1e-6, spec.seed, start=x)
        if x1 is not None and (x is None or base_cost @ x1 <= base_cost @ x + 1e-9):
            x = x1
        if x is None:
            raise S.DesignError(S._infeasible_message(text, spec))
        if base_cost @ x > 1e-9 and not proven:
            x = S._lns(model, form, members, x, base_cost, rng, spec.seed, at(0.85), lambda m: None)
        proven = proven or base_cost @ x <= 1e-9
        best_dev = S.deviation_counts(x, penalties)
        if opts.tolerance:
            # step 1: cap each criterion separately at (best + tolerance) instead of capping the
            # weighted total at the best value
            for tag, items in penalties.items():
                idx, coef = _penalty_sum_row(model, items)
                model.add_row(idx, coef, -INF, best_dev[tag] + opts.tolerance.get(tag, 0) + 1e-6)
        else:
            best = float(base_cost @ x)
            nz = np.flatnonzero(base_cost)
            model.add_row(nz, base_cost[nz], -INF, best + 1e-6 * max(1.0, abs(best)) + 1e-6)

    rerank_effs = []
    walk_moves = 0
    if (opts.rerank > 0 or opts.walk_pick) and x is not None:
        # Random walk over the equally balanced designs (the cap row above keeps every step as
        # balanced as the best design): free a random third of the subjects, re-solve them with a
        # random objective, move there. Small neighbourhoods make a different solution easy to
        # find, unlike re-solving the whole capped model (which usually returns its start).
        steps = opts.rerank if opts.rerank > 0 else 12
        walk = _random_walk(model, form, members, x, rng, spec.seed, steps,
                            max(2.0, deadline - time.time()))
        walk_moves = sum(1 for a, b in zip([x] + walk, walk) if not np.allclose(a, b))
        if opts.rerank > 0 and walk:
            # step 4: keep the most precise design under the model with carry-over (ties at random)
            from common import a_efficiency
            rerank_effs = [a_efficiency(np.vstack([form.extract(xi, c) for c in range(len(members))]),
                                        ctx.t, True)[0] for xi in walk]
            top = max(rerank_effs)
            best_ids = [i for i, e in enumerate(rerank_effs) if e >= top - 1e-9]
            x = walk[int(rng.choice(best_ids))]
        elif walk:
            x = walk[-1]
    else:
        rand_cost = np.zeros(model.n)
        rand_cost[form.decision] = rng.random(len(form.decision))
        t2 = max(2.0, deadline - time.time())
        x2, text2, _ = model.solve(rand_cost, t2, 0.25, spec.seed, start=x)
        if x2 is not None:
            if x is not None:      # record whether the app-style pick changed the design
                walk_moves = int(not np.allclose(np.round(x2[form.decision]), np.round(x[form.decision])))
            x = x2
        if x is None:
            raise S.DesignError(S._infeasible_message(text2, spec))

    assign = np.zeros((len(spec.subjects), ctx.p), dtype=int)
    for c, mem in enumerate(members):
        rows = form.extract(x, c)
        assign[mem] = rows[rng.permutation(len(rows))]
    symmetric = (not spec.forbidden_transitions and not spec.forbidden_periods and not spec.order_rules
                 and len(set(ctx.w.tolist())) == 1)
    if symmetric:
        assign = rng.permutation(ctx.t)[assign]
    violations = {tag: 0.0 for tag in locked}
    violations.update(S.deviation_counts(x, penalties))
    return ExtResult(assign=assign, levels=levels, violations=violations, proven=bool(proven),
                     seconds=time.time() - t0, best_violations=best_dev, rerank_effs=rerank_effs,
                     walk_moves=walk_moves)


def _random_walk(model, form, members, x, rng, seed, steps, budget):
    """`steps` random moves within the current model's feasible set (see solve_ext)."""
    sizes = np.array([len(m) for m in members])
    N = int(sizes.sum())
    k = int(min(N, max(3, N // 3)))
    per = max(0.3, budget / steps)
    out, cur = [], x
    for i in range(steps):
        pick = rng.choice(N, size=k, replace=False)
        free = np.bincount(np.searchsorted(np.cumsum(sizes), pick, side="right"), minlength=len(members))
        parts = [form.release(cur, c, int(free[c]), rng) for c in range(len(members))]
        bounds = tuple(np.concatenate([q[j] for q in parts]) for j in range(3))
        rand_cost = np.zeros(model.n)
        rand_cost[form.decision] = rng.random(len(form.decision))
        xn, _, _ = model.solve(rand_cost, per, 0.0, seed + 1000 + i, start=cur, bounds=bounds)
        if xn is not None:
            cur = xn
        out.append(cur)
    return out
