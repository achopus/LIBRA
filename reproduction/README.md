# Reproducing the analyses of the article

These scripts produce every result, table and figure of the article "LIBRA: Linear Integer
Programming for Balanced Randomization" and its Supplementary Material. Every LIBRA design was made
with LIBRA 1.0.0 at its default settings (reproducible mode, budget 60, Variety final choice), by
calling the application's own `solve()`.

## Setup

Python 3.11 or later. From this folder:

```shell
pip install -r requirements.txt
```

The scripts import LIBRA from `../app/` (in the archived materials) or from `../` (in the source
repository). To use another copy of LIBRA, set the environment variable `ANALYSIS_SOLVER` to the
folder that contains its `randomizer` package.

## Running

```shell
python run_all.py                 # run every stage; the designs already in pools/ are reused
python run_all.py --fresh         # delete the generated designs and regenerate everything
python run_all.py --from r15      # resume at a stage
python run_all.py --only a02 r16  # selected stages only
```

Each stage runs in its own process and writes its log to `results/logs/<stage>.log`;
`results/run_all_status.md` shows progress. Settings, set by `run_all.py`:

| Variable | Value | Meaning |
| --- | --- | --- |
| `BENCH_SECONDS` | 60 | Budget of every LIBRA and annealing design (LIBRA's default) |
| `BENCH_WORKERS` | 20 | Parallel processes; lower it on a smaller computer |
| `LIBRA_THREADS` | 1 | Solver threads per process |
| `LIBRA_SAFETY_FACTOR` | 40 | Wall-clock safety cap of each solve, as a multiple of its budget (LIBRA's default is 10). Many parallel solves slow each other down; the larger cap keeps every design within the work budget, so that it is reproducible from its seed. |

**Run time.** On the computer described in the Supplementary Material (20 parallel processes), a
complete run with `--fresh` takes about a working day. The longest stages are the pools (`a02`,
`r02`, `r12`), the scalability grid (`a07`), the uniformity study (`r20`), the design limits
(`r21`, up to one hour per configuration for counting designs) and the certificates (`a01`, `r08`,
`r22`). Without `--fresh`, `a02` reuses the LIBRA designs in `pools/ilp_runs/` and the stages that
only analyze the pools take minutes.

**Reproducibility.** Every random step is seeded. LIBRA's designs depend only on the seed and the
settings, not on the computer or its load (reproducible mode), as long as no solve reaches the
safety cap; LIBRA records this for every design (`pools/ilp_runs.csv`, column `reproducible`). The
simulated-annealing comparators and the research copy of the solver (`ext_solver.py`, used only for
the exact models behind proofs and certificates) use wall-clock limits, so their designs can differ
on another computer. All generated designs are therefore included in `pools/`, with SHA-256
checksums in `pools/SHA256SUMS.txt`, and every later stage reads them from there.

## Where each result comes from

Tables are written by `r18_latex_tables.py` to `results/latex/<NAME>.tex` from the result files
below; figures are written to `figures/`.

| Article | Script (output in `results/` unless noted) |
| --- | --- |
| Balance table, Figure "Balance" | `a02` (pools), `r02`, `r12` (classical design, annealers), `r16_table_stats.py` (`r16_*.csv`), `r17_figures.py` (`figures/fig_balance.png`) |
| Predictability table, Figure "Predictability" | `r16_table_stats.py`, `r21_design_limits.py` (attainable floor, `r21_floors.csv`), `r17_figures.py` (`figures/fig_predictability.png`) |
| Efficiency table | `a04_efficiency_dropout.py` (`efficiency_*.csv`), `r10_eval_comparators.py`, `r05_aopt.py` (best design without balance constraints) |
| Type I error, power, bias | `a05_simulation.py`, `r14_exact_power.py`, `r06_sim_strata.py` |
| Randomization validity, uniformity | `a06_randomization_validity.py`, `a06b`, `a06c`, `r01`, `r01b`, `r01c`, `r03`, `r03b`, `r11_williams_check.py`, `r20_variety_uniformity.py` |
| Certificates (proofs) | `a01_verification.py`, `x02_feasibility.py`, `x02_independent_check.py`, `x03_g3_bound.py`, `r13_stratum_g3_bound.py`, `x04_enumerate_e.py`, `r08_certificates.py` (model files in `certificates/`), `r22_cpsat_certificates.py` (re-solved with CP-SAT) |
| Run time and scalability, Figure S "Scalability" | `a07_scalability.py` (`scalability.csv`, `figures/fig_scalability.png`), `r21_design_limits.py` (smallest possible carry-over range) |
| Rules and an incomplete design | `r04_rules.py` |
| Clinical example | `r15_human_example.py` (24 runs, schedule of seed 1), `r19_worked_example.py` (both final-choice modes), `r21_design_limits.py` (without the evenness tier, `r21_noeven.csv`) |
| Rodent example | `a08_case_study.py` (`case_study_*.csv`) |
| Full-list criterion, Figure S "Full list" | `x03_predict.py` (`figures/fig_x03_predict.png`) |
| Partial unblinding, early stopping | `r07_partial_observer.py`, `x05_early_stopping.py` |
| Reference values | `r09_reference_values.py` |
| Screenshots of the tutorial | `screenshots.py` (dark mode; opens the built-in example "Two-center crossover trial", seed 1) |

The clinical example was run with the labels of a psychology experiment (CONTROL, EASY, MEDIUM, HARD,
DUAL at two sites); the article uses clinical labels (PLACEBO, LOW, MEDIUM, HIGH, ACTIVE at two
centers). Renaming the treatments gives the identical schedule (see `../examples/`).

## Contents

| Path | Contents |
| --- | --- |
| `common.py` | Configurations A–E, the comparison methods, and every metric, written independently of LIBRA so they cross-check its own balance report |
| `plotstyle.py` | Figure style |
| `ext_solver.py` | Research copy of the solver with extra model options, for the exact models behind proofs and certificates |
| `pools/` | Every generated design (`<config>_<method>.npz`), LIBRA's per-seed runs (`ilp_runs/`, `ilp_runs.csv`) and checksums |
| `certificates/` | Model files (MPS) of every certificate, with their own README |
| `results/` | Per-design and summary results of every stage, the table bodies (`latex/`) and the logs (`logs/`) |
| `figures/` | Figures of the article and the supplement |

### Configurations

| ID | Treatments | Subjects | Strata | Purpose |
| --- | --- | --- | --- | --- |
| A | 5 | 15 | 1 | Odd t, N = 3t: needs a three-square design |
| B | 5 | 30 | 2 × 15 | Two strata of 3t |
| C | 4 | 16 | 2 × 8 | Williams squares fit exactly |
| D | 6 | 20 | 2 × 10 | Stratum size not a multiple of t |
| E | 3 | 9 | 1 | Perfect carry-over balance impossible |

A and B are generated with an extra fixed final period, which the model leaves out of the
randomization; the analyses use the five randomized periods.
