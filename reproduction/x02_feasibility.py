"""Step 2 side question: does config A (t=5, N=15) admit a design with perfect period balance,
perfect carry-over balance AND perfect nested (prefix) carry-over balance?
Pure feasibility ILP, zero objective, long time limit."""
import sys
import time

import numpy as np

from common import CONFIGS, ilp_spec
from ext_solver import _build
from randomizer import solver as S

c = sys.argv[1] if len(sys.argv) > 1 else "A"
limit = float(sys.argv[2]) if len(sys.argv) > 2 else 600
spec = ilp_spec(CONFIGS[c], 1, limit)
rng = np.random.default_rng(1)
ctx = S._prepare(spec, rng)
levels = {"period": "required", "carryover": "required", "nested": "required",
          "cooccurrence": "off", "spread": "off"}
model, form, _ = _build(ctx, ctx.members, ctx.units, levels)
t0 = time.time()
x, text, proven = model.solve(np.zeros(model.n), limit, 1.0, 1)
print(f"{c}: status={text} feasible={x is not None} seconds={time.time() - t0:.1f}")
if x is not None:
    for cell in range(len(ctx.members)):
        print(form.extract(x, cell))
