# LIBRA – Crossover Randomizer

**L**inear **I**nteger programming for **B**alanced **RA**ndomization.

A desktop app that builds balanced, hard-to-predict treatment schedules for preclinical and
clinical studies (crossover, incomplete crossover, replicated crossover and parallel-group
designs). Schedules are chosen by integer linear programming (HiGHS solver), so balance is
exact wherever it is mathematically possible. Everything runs on your computer; nothing is sent online.

## Install

**Windows:** run **LIBRA-Setup-1.0.0.exe**.
If Windows shows "Windows protected your PC", click **More info → Run anyway** (the installer is not
code-signed). No administrator rights are needed and nothing else has to be installed. Start the app
from the desktop or Start menu icon, or double-click a `.libra` project file.
To uninstall: **Settings → Apps → LIBRA – Crossover Randomizer → Uninstall**.

**macOS:** open **LIBRA-1.0.0-macOS-arm64.dmg** (Apple silicon) or `-x86_64` (Intel) and
drag the app to Applications. If the app is not signed, macOS refuses the first start: open
**System Settings → Privacy & Security**, click **Open Anyway** next to the message about LIBRA, and
confirm (needed once).

## Using the app

The left sidebar walks through the steps; each shows ✓ when it is fine or ⚠ when something needs attention.

| Step | What you do |
| --- | --- |
| **Start screen** | New project, open a project, recent projects, or start from an example (rat crossover, blinded human crossover, parallel groups in blocks, dose escalation, a fixed last week, cages as units). |
| **1 · Subjects** (or Animals, Participants…) | Choose the wording (Animals · Weeks, Participants · Sessions, …). Enter the subject list: paste from Excel, import CSV/Excel, or generate IDs. Tick group columns to balance within (sex, genotype…). Optionally randomize whole cages (or litters) as units. |
| **2 · Treatments** | Design type, treatments (and ratios), the name of a period, fixed periods such as a baseline or a final MAX dose, and a timeline preview. |
| **3 · Rules** | Optional hard rules: never directly followed by, must come before (dose escalation), not allowed in a period. |
| **4 · Balance** | Each criterion as *Required*, *Preferred* or *Off*; balance within groups; enrollment blocks. |
| **5 · Generate** | A summary with plain-language checks (what cannot work, what can only be balanced to ±1), seed, time limit, *Variety* or *Speed*, solver, blinding. Progress with Cancel; a run that stops at the time limit offers *Retry with more time*. |
| **6 · Results** | Every run is kept. Checks, schedule, balance tables, pictures, calendar, methods text and history. Mark a run as **Final** (locks it), **Verify** it (re-create from its seed), **Export**, **Add subjects** to it without changing anyone already scheduled, **Replace a dropout**, or **Compare runs**. |

Every change can be undone (Ctrl+Z) and redone (Ctrl+Y). Saved projects are saved automatically
(File → Save automatically); unsaved work is kept for recovery if the app closes unexpectedly.
Hover over or click any **?** for a short explanation with an example.
A guided tour runs the first time LIBRA starts; replay it from **Help → Show the tutorial** or
**Take the tour** on the start screen.

### Outputs

* **Excel** (one workbook): schedule, long format, blinded schedule, checks, balance per group,
  carry-over counts, predictability, sequences, methods paragraph, settings, run information and the
  project's audit log; with the calendar, a sheet by date.
* **CSV**: the schedule, a long table (one row per subject and period, for R/SPSS/JASP), the methods text.
* **PNG** (optional): the schedule as a colored grid (labels inside the cells, so it also works in black
  and white) and balance pictures.
* **Experiment software** (optional): a folder `<name>_experiment/` with the condition of every subject
  in every session (`all_conditions.csv`, `conditions.json` and one CSV per subject), and a README with
  copy-paste code for PsychoPy, OpenSesame, jsPsych and lab.js. With blinding it contains codes only.
* **Methods text**: names and cites LIBRA and its version; the citation is set in `randomizer/__init__.py`.
* **Blinding**: the experimenters' files contain codes only; the code key is a separate file.
* **Calendar**: real dates per subject (weekends and holidays move to the next working day; staggered
  starts from a column), daily sheets as PDF or printed (one page per day with Done/Initials columns),
  and printable labels (A4 and Letter label sheets).
* **Fingerprint**: a short checksum of each schedule (e.g. `3F9A-0C21-77BE`) for preregistrations and audits.

## Project files

A project (`.libra`) is one readable JSON file: settings, subject list, every run with its exact
solver input and output, and an audit log (created, generated, marked final, exported, verified…).
Keep it with the study records.

## Command line

The same project files can be used from a terminal (installed as `libra-cli` next to the app, or
`python -m randomizer` from source):

```shell
libra-cli new study.libra --example rat-crossover
libra-cli info study.libra
libra-cli run study.libra --seed 123 --time-limit 60 --note "pilot"
libra-cli final study.libra R1
libra-cli export study.libra --run final --format xlsx --png --dates --out results
libra-cli export study.libra --run final --format csv --experiment     # files for PsychoPy, jsPsych…
libra-cli verify study.libra --run final
```

## Balance criteria (priority order)

1. **Period balance:** every period has each treatment equally often (±1 when not divisible), overall, within each group and within each enrollment block.
2. **Carry-over balance:** each treatment is directly preceded by every other treatment equally often.
3. **Co-occurrence balance** (incomplete designs): every pair of treatments is given to the same subject equally often.
4. **Spread:** within each single change between consecutive periods, subjects that shared a treatment move on to different treatments. This makes the next period's treatment as unpredictable as possible.

*Required* criteria are hard constraints. *Preferred* criteria are first tried as hard constraints
(in the order above). Those that cannot be met perfectly are minimized instead.

## How the solver works

* **Model.** One integer variable per (group, allowed treatment order) counts how many subjects
  get that order. Large designs switch to binary subject × period × treatment variables.
* **Steps.**
  1. Lock in, one by one, every preferred criterion that can be met perfectly.
     For complete designs without rules whose groups are multiples of the number of treatments,
     the check first searches cyclic designs (each block is a starting order plus 0, 1, …, t−1
     mod t, like Williams squares and the classical three-square designs).
  2. Start from a Williams design, the best cyclic design, or a chunk-by-chunk ILP.
  3. Optimize the remaining criteria one at a time, in order of priority (within groups before
     overall): each is minimized with a global ILP plus large-neighbourhood search, and its best
     value is then fixed, so a lower criterion never costs a higher one. When rules make equal
     carry-over counts impossible, the counts are then made as even as possible (squared distance
     from the target).
  4. Choose a random design among the equally good ones using the seed (see below).
* **Final choice: Variety or Speed.**
  * *Variety* (default) lists every design that is as well balanced as the best one found and
    draws one so that every allocation of orders to subjects is equally likely (each design is
    weighted by the number of ways its orders can be dealt to the subjects). When the treatments
    are interchangeable it lists one design per relabelling family and weights each family by its
    size. If there are too many to list in the time available, it moves randomly among them
    instead (random, but not uniform). Uses up to the full time limit.
  * *Speed* takes one quick random-objective solve. Just as balanced, much faster, but some
    designs come up far more often than others.
  * The report, the settings sheet and the methods text say which of these happened.
* **Adding subjects later.** Subjects already scheduled are fixed; only the new ones are placed, so
  that the whole study stays as balanced as possible.
* **Randomization.** Subjects are shuffled within their group. When the rules are symmetric,
  treatment labels are randomly permuted.
* **Solver.** HiGHS is built in. If `gurobipy` and a Gurobi license are available (running from
  source), Gurobi can be chosen on the Generate page.
* Every solve runs in a fresh process. HiGHS slows down after many solves in one process, so this keeps results consistent.

**Reproducible mode** (on by default): the search is limited by solver work (node and
iteration counts) instead of wall-clock time, so the same seed and settings give the same schedule
on any computer with the same LIBRA version (check it with **Verify**). The time limit is then a
fixed amount of search, about that many seconds on a typical laptop. With it off, schedules that
stop at the time limit can differ between computers. The saved project is the record either way.

* **Optional full-list criterion** (Balance step, off by default): makes the complete list reveal
  less about a subject's later treatments once their first two are known, at some cost to spread.

## Developers

```shell
pip install -r requirements.txt
python -m randomizer_gui            # or double-click "Start LIBRA.bat" on Windows
python -m pytest tests -q
```

Code layout: `randomizer/` is the solver, project files, checks, calendar, exports and command line
(no GUI code); `randomizer_gui/` is the PySide6 app; `installer/` builds the installers;
The analyses of the article are in `../reproduction/`.

### Build the installers

```shell
pip install -r requirements.txt "pyinstaller>=6.11"
python installer/build.py
```

The script builds the app with PyInstaller (`installer/libra.spec`), runs a smoke test of
the built programs (a real solve in a child process, an Excel and PNG export, and the app's own
`--self-test`), then packages it:

* **Windows:** needs Inno Setup 6 (`winget install JRSoftware.InnoSetup`); makes
  `installer/output/LIBRA-Setup-<version>.exe`. It installs per user and registers
  `.libra` project files.
* **macOS:** run the same command on a Mac (Xcode command line tools); makes
  `installer/output/LIBRA-<version>-macOS-<arch>.dmg`. Build on Apple silicon for arm64
  and on an Intel Mac (or under Rosetta with an x86_64 Python) for x86_64. Without a Mac, the
  GitHub workflow `.github/workflows/macos-installer.yml` builds both (Actions tab → *macOS
  installer* → *Run workflow*; the `.dmg` files are under *Artifacts*). To sign, set
  `MACOS_SIGN_IDENTITY` before building, then notarize (instructions at the top of `installer/build.py`).

The version number comes from `randomizer/__init__.py`. `installer/build/` holds intermediate files.

## License

MIT (see `LICENSE`). Third-party packages keep their own licenses; Qt for Python is LGPL-3.0
(see `THIRD_PARTY_LICENSES.md`).
