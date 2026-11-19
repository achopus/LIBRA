# Worked examples

Two LIBRA project files, one for each worked example of the article. Each holds the settings, the
subject list and the schedule reported in the article (run R1). Open them in LIBRA (File > Open) or
use them from the command line, for example:

```shell
python -m randomizer info clinical_two_centers.libra
python -m randomizer verify clinical_two_centers.libra     # re-creates R1 from its seed and compares
python -m randomizer export clinical_two_centers.libra --format csv --out schedule
```

| File | Example | Seed | Time limit |
| --- | --- | --- | --- |
| `clinical_two_centers.libra` | Two-center clinical crossover trial: 30 patients at two centers, PLACEBO, LOW, MEDIUM, HIGH and ACTIVE over five periods, HIGH and ACTIVE never in consecutive periods (Section 6.1; Supplementary Table "Schedule") | 1 | 60 |
| `rodent_study.libra` | Preclinical crossover study: 30 rats (15 per sex), VEHICLE, LOW, HIGH, NOMINAL and OTHER over five randomized weeks, MAX fixed in week 6 (Section 6.2) | 2026 | 120 |

Both were made with LIBRA 1.0.0 in reproducible mode, so `verify` re-creates the same schedule on
any computer. `make_materials.py` in the source repository checks that both schedules are identical
to those produced by the analysis scripts (`reproduction/results/r15_example_schedule.csv`, which
uses the labels of a psychology experiment, and `case_study_schedule.csv`).
