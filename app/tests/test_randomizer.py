import io
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from randomizer import DesignError, DesignSpec, solve, validate  # noqa: E402
from randomizer.diagnostics import checks, transition_matrix, unit_summary  # noqa: E402
from randomizer.export import long_format, methods_text, to_excel  # noqa: E402
from randomizer.runner import solve_isolated  # noqa: E402
from randomizer.solver import williams_square  # noqa: E402

T5 = ["VEHICLE", "LOW", "HIGH", "NOMINAL", "OTHER"]


def subjects(n, **groups):
    df = pd.DataFrame({"subject": [f"s{i + 1}" for i in range(n)]})
    for col, levels in groups.items():
        df[col] = levels
    return df


def check(res, name):
    return next(c for c in checks(res) if name in (c.name, c.key))


@pytest.mark.parametrize("t", [2, 3, 4, 5, 6, 7, 8])
def test_williams_square_is_carryover_balanced(t):
    sq = williams_square(t)
    assert all(sorted(r) == list(range(t)) for r in sq)
    for k in range(t):                                   # every period balanced
        counts = np.bincount(sq[:, k], minlength=t)
        assert counts.min() == counts.max()
    M = transition_matrix(sq, t, [(k, k + 1) for k in range(t - 1)])
    off = M[~np.eye(t, dtype=bool)]
    assert off.min() == off.max()


def test_rodent_study_case():
    """15 animals, 5 treatments, MAX fixed in week 6 (the notebook setup)."""
    spec = DesignSpec(subjects=subjects(15), treatments=T5, n_periods=6, fixed={6: "MAX"},
                      period_name="Week", seed=2026, time_limit=20)
    res = solve(spec)
    assert (res.schedule["Week 6"] == "MAX").all()
    assert check(res, "Per-subject rule").ok
    assert check(res, "Period balance").ok
    assert check(res, "Carry-over balance").ok
    M = transition_matrix(res.assign, 5, spec.adjacent_pairs)
    assert set(M[~np.eye(5, dtype=bool)]) == {3}
    # within a single week change at most one pair of animals may share a transition
    extra = sum(np.clip(transition_matrix(res.assign, 5, spec.adjacent_pairs, which={j}) - 1, 0, None).sum()
                for j in range(4))
    assert extra <= 2


def test_two_sexes_balanced_within_each_sex():
    spec = DesignSpec(subjects=subjects(30, sex=["m"] * 15 + ["f"] * 15), strata=["sex"], treatments=T5,
                      n_periods=6, fixed={6: "MAX"}, time_limit=20)
    res = solve_isolated(spec)          # fresh process, as in the app
    assert check(res, "Period balance").ok
    for u, rows in zip(res.units, res.subject_unit_ids):
        M = transition_matrix(res.assign, 5, spec.adjacent_pairs, rows)
        off = M[~np.eye(5, dtype=bool)]
        assert off.max() - off.min() <= 1, u.name


def test_enrollment_blocks_balance_each_block():
    spec = DesignSpec(subjects=subjects(20), treatments=["A", "B", "C", "D"], n_periods=4,
                      block_sizes=[4, 8], time_limit=10)
    res = solve(spec)
    assert "Block" in res.schedule
    assert check(res, "Period balance").ok
    for block, grp in res.schedule.groupby("Block"):
        for col in res.period_columns:
            counts = grp[col].value_counts()
            assert counts.max() - counts.min() <= 1 or len(counts) < 4, block


def test_parallel_design_with_ratio_and_strata():
    spec = DesignSpec(subjects=subjects(36, site=["x"] * 18 + ["y"] * 18), strata=["site"],
                      treatments=["Drug", "Placebo"], weights={"Drug": 2, "Placebo": 1}, n_periods=1,
                      min_per_subject=0, block_sizes=[6], time_limit=10)
    res = solve(spec)
    for site, grp in res.schedule.groupby("site"):
        assert (grp["Period 1"] == "Drug").sum() == 12
    for block, grp in res.schedule.groupby("Block"):
        assert (grp["Period 1"] == "Drug").sum() == 4


def test_incomplete_design_cooccurrence():
    spec = DesignSpec(subjects=subjects(12), treatments=list("ABCD"), n_periods=3, min_per_subject=0,
                      time_limit=10)
    res = solve(spec)
    assert all(len(set(r)) == 3 for r in res.assign)
    assert check(res, "Co-occurrence balance").ok


def test_replicated_design():
    spec = DesignSpec(subjects=subjects(8), treatments=["T", "R"], n_periods=4, min_per_subject=2,
                      max_per_subject=2, time_limit=10)
    res = solve(spec)
    assert all(np.bincount(r, minlength=2).tolist() == [2, 2] for r in res.assign)
    assert all((r[:-1] != r[1:]).all() for r in res.assign)          # no back-to-back repeats


def test_rules_are_obeyed():
    spec = DesignSpec(subjects=subjects(20), treatments=T5, n_periods=5,
                      forbidden_transitions=[("HIGH", "OTHER")], order_rules=[("LOW", "HIGH")],
                      forbidden_periods=[("OTHER", 1)], period_balance="preferred", time_limit=10)
    res = solve(spec)
    assert check(res, "Forbidden patterns").ok
    s = res.schedule
    assert not (s["Period 1"] == "OTHER").any()
    for _, row in s.iterrows():
        seq = [row[c] for c in res.period_columns]
        assert seq.index("LOW") < seq.index("HIGH")
        assert all(not (a == "HIGH" and b == "OTHER") for a, b in zip(seq, seq[1:]))


def test_large_design_uses_subject_formulation():
    spec = DesignSpec(subjects=subjects(16), treatments=list("ABCDEFGH"), n_periods=8, time_limit=15)
    res = solve(spec)
    assert res.formulation == "per-subject"
    assert check(res, "Carry-over balance").ok


def test_same_seed_same_design_for_fast_problems():
    kw = dict(subjects=subjects(12), treatments=list("ABCD"), n_periods=4, seed=7, time_limit=10)
    a, b = solve(DesignSpec(**kw)), solve(DesignSpec(**kw))
    assert a.schedule.equals(b.schedule)


def test_validation_errors():
    spec = DesignSpec(subjects=subjects(5), treatments=["A", "A"], n_periods=3)
    errors, _ = validate(spec)
    assert any("unique" in e for e in errors)
    with pytest.raises(DesignError):
        solve(spec)


def test_impossible_hard_rules_raise():
    spec = DesignSpec(subjects=subjects(10), treatments=list("ABCDE"), n_periods=5,
                      order_rules=[("A", "B")], time_limit=10)          # period balance 'required'
    with pytest.raises(DesignError):
        solve(spec)


def test_export_and_methods():
    spec = DesignSpec(subjects=subjects(10, sex=["m"] * 5 + ["f"] * 5), strata=["sex"],
                      treatments=list("ABCDE"), n_periods=5, blind=True, time_limit=10)
    res = solve(spec)
    xls = pd.ExcelFile(io.BytesIO(to_excel(res)))
    assert {"Schedule", "Blinded schedule", "Code key (keep separate)", "Settings"} <= set(xls.sheet_names)
    assert len(long_format(res)) == 10 * 5
    assert "stratified by sex" in methods_text(res)
    assert len(unit_summary(res)) == 3


def test_variety_mode_lists_small_optimal_sets():
    # t = 4, N = 12, spread off: exactly 58 designs have session and carry-over balance
    spec = DesignSpec(subjects=subjects(12), treatments=list("ABCD"), n_periods=4, spread_balance="off",
                      seed=3, time_limit=10, randomization="variety")
    res = solve(spec)
    assert res.randomization["method"] == "uniform" and res.randomization["designs"] == 58
    assert check(res, "Carry-over balance").ok
    assert "equally likely" in methods_text(res)
    assert res.randomization["log10_allocations"] > 0


def test_speed_mode_says_not_uniform():
    spec = DesignSpec(subjects=subjects(12), treatments=list("ABCD"), n_periods=4, seed=3, time_limit=10,
                      randomization="speed")
    res = solve(spec)
    assert res.randomization["method"] == "random objective"
    assert "not uniform" in methods_text(res)


def test_cyclic_search_finds_balanced_design_for_seven_treatments():
    # a carry-over-balanced design for t = 7, N = 21 exists (three-square design) but is hard to find
    spec = DesignSpec(subjects=subjects(21), treatments=list("ABCDEFG"), n_periods=7, seed=1, time_limit=30,
                      randomization="speed")
    res = solve(spec)
    assert res.levels["carryover"] == "required"
    assert check(res, "Carry-over balance").ok


def test_invalid_randomization_mode():
    spec = DesignSpec(subjects=subjects(6), treatments=list("ABC"), n_periods=3, randomization="fast")
    errors, _ = validate(spec)
    assert any("Randomization" in e for e in errors)


def test_reproducible_mode_gives_the_same_schedule():
    spec = DesignSpec(subjects=subjects(15), treatments=T5, n_periods=5, seed=11, time_limit=8)
    a, b = solve(spec), solve(spec)
    assert a.reproducible and b.reproducible
    assert np.array_equal(a.assign, b.assign)
    assert "reproduce the schedule exactly" in methods_text(a)


def test_impossible_carryover_is_reported_as_impossible():
    # t = 3, N = 9: no carry-over-balanced design exists (an odd number of Williams squares)
    spec = DesignSpec(subjects=subjects(9), treatments=list("ABC"), n_periods=3, seed=1, time_limit=10)
    res = solve(spec)
    assert res.checks["carryover"] == "impossible"
    assert all(v["proven"] for v in res.criteria.values())


def test_forbidden_transitions_give_an_even_split():
    # HARD and DUAL may not follow each other: pairs with them are forced to 4, so the six pairs among
    # the other three share 12 transitions; the even split (2 each) must be chosen, not 1/3.
    T = ["CONTROL", "EASY", "MEDIUM", "HARD", "DUAL"]
    spec = DesignSpec(subjects=subjects(15), treatments=T, n_periods=5, seed=1, time_limit=30,
                      forbidden_transitions=[("HARD", "DUAL"), ("DUAL", "HARD")])
    res = solve(spec)
    M = transition_matrix(res.assign, 5, spec.adjacent_pairs)
    light = [M[a, b] for a in range(3) for b in range(3) if a != b]
    assert light == [2] * 6
    assert "as even as the rules allow" in check(res, "Carry-over balance").detail


def test_prediction_floor_and_full_list_exposure():
    from randomizer.diagnostics import best_guess_rate, full_list_exposure, guess_floor
    spec = DesignSpec(subjects=subjects(15), treatments=T5, n_periods=5, seed=2, time_limit=10)
    res = solve(spec)
    M = transition_matrix(res.assign, 5, spec.adjacent_pairs, which={0})
    floor = guess_floor(res, which={0})
    assert abs(floor - 1 / 3) < 1e-9                  # 3 subjects per treatment, 4 possible successors
    assert best_guess_rate(M) >= floor - 1e-9
    ex = full_list_exposure(res)
    assert 0 < ex["pooled"] <= 1


def test_full_list_criterion_lowers_exposure():
    from randomizer.diagnostics import full_list_exposure
    base = dict(subjects=subjects(15), treatments=T5, n_periods=5, seed=4, time_limit=20)
    off = solve(DesignSpec(**base))
    on = solve(DesignSpec(**base, fulllist_balance="preferred"))
    assert full_list_exposure(on)["pooled"] < full_list_exposure(off)["pooled"]
    assert on.levels["fulllist"] == "preferred"


def test_subject_formulation_with_symmetry_breaking(monkeypatch):
    from randomizer import solver as S
    monkeypatch.setattr(S, "SEQUENCE_VAR_LIMIT", 10)      # force the per-subject model
    spec = DesignSpec(subjects=subjects(8, sex=["m"] * 4 + ["f"] * 4), strata=["sex"], treatments=list("ABCD"),
                      n_periods=4, seed=5, time_limit=15)
    res = solve(spec)
    assert res.formulation == "per-subject"
    assert check(res, "Period balance").ok and check(res, "Carry-over balance").ok
