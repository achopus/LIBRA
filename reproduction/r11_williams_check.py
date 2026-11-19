"""Williams pools: per-copy relabelling of stacked Williams squares.

1. Regenerate every Williams pool with the generator and seeds of a02 (common.gen_williams, which
   draws a new relabelling for every stacked square, or for every Williams pair when t is odd) and
   check that the pools are regenerated exactly from their seeds.
2. For contrast, a variant with ONE relabelling per stratum shared by all stacked copies, evaluated
   on the predictability and efficiency metrics (G2 after one period, G3 after two, M2 efficiency,
   skeletons), to show that the choice does change these numbers where a stratum holds more than
   one copy (C).

Output: results/r11_williams_check.txt
"""
import hashlib

import numpy as np
import pandas as pd

from a06_randomization_validity import canonical
from common import CONFIGS, RESULTS, _fill_strata, a_efficiency, gen_williams, guess_accuracy, load_pool, williams_square


def gen_williams_shared(cfg, rng):
    base = williams_square(cfg.t)
    out = np.zeros((cfg.N, cfg.t), dtype=int)
    for s, size in enumerate(cfg.strata_sizes):
        lab = rng.permutation(cfg.t)
        sub = type(cfg)(cfg.name, cfg.t, (size,), cfg.fixed_last)
        out[cfg.strata == s] = _fill_strata(sub, rng, lambda: lab[base])
    return out


def summary(pool, cfg):
    rows = []
    for D in pool:
        g = guess_accuracy(D, cfg.t)
        rows.append({"G2": g["G2"][0], "G3": g["G3"][1] if cfg.t > 3 else np.nan,
                     "M2": a_efficiency(D, cfg.t, True)[0],
                     "sk": hashlib.md5(repr(canonical(D, cfg)).encode()).hexdigest()})
    df = pd.DataFrame(rows)
    return df.G2.mean(), df.G3.mean(), df.M2.mean(), df.sk[:60].nunique()


def main():
    lines = []
    for c, cfg in CONFIGS.items():
        rng = np.random.default_rng(1000 + ord(c))
        regen = np.stack([gen_williams(cfg, rng) for _ in range(200)])
        same = np.array_equal(regen, load_pool(c, "williams"))
        lines.append(f"{c}: regenerated Williams pool identical to saved pool: {same}")
    lines.append("")
    lines.append("config  variant              G2(1)   G3(2)   M2      skeletons(first 60)")
    for c in ("A", "B", "C", "D"):
        cfg = CONFIGS[c]
        rng = np.random.default_rng(77)
        shared = np.stack([gen_williams_shared(cfg, rng) for _ in range(200)])
        for name, pool in (("per-copy (paper)", load_pool(c, "williams")), ("shared per stratum", shared)):
            g2, g3, m2, sk = summary(pool, cfg)
            lines.append(f"{c:7} {name:20} {g2:.3f}   {g3:.3f}   {m2:.3f}   {sk}")
    text = "\n".join(lines)
    print(text)
    (RESULTS / "r11_williams_check.txt").write_text(text + "\n")


if __name__ == "__main__":
    main()
