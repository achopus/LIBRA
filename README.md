# LIBRA: materials accompanying the article

Brejtr, V., Šíchová, K., Páleníček, T., & Lhotská, L. (2026). LIBRA: Linear Integer Programming for Balanced
Randomization. *Behavior Research Methods* (submitted).

| Folder | Contents |
| --- | --- |
| [`app/`](app/) | LIBRA 1.0.0: source code of the application and its solver, tests, and the scripts that build the installers for Windows and macOS |
| [`reproduction/`](reproduction/) | Every analysis of the article and the Supplementary Material, with all generated designs, per-design results, certificate model files and figures |
| [`examples/`](examples/) | The two worked examples of the article as LIBRA project files, with the schedules reported in the article |

## Quick start

Installers for Windows and macOS are on the [Releases page](https://github.com/achopus/LIBRA/releases). To run LIBRA from source (Python 3.11 or
later):

```shell
cd app
pip install -r requirements.txt
python -m randomizer_gui              # the desktop application
python -m randomizer --help           # the command line
python -m pytest tests                # the tests (about 4 minutes)
```

Open `examples/clinical_two_centers.libra` in LIBRA (File > Open) to see the clinical example with
its schedule, or start from the built-in example "Two-center crossover trial" on the start screen.

To reproduce the analyses, see [`reproduction/README.md`](reproduction/README.md).

## License

The code (`app/` and the scripts in `reproduction/`) is released under the MIT license (`LICENSE`).
The data in `reproduction/` (generated designs, results, certificate model files and figures) and
the example projects are released under the Creative Commons Attribution 4.0 International license
(CC BY 4.0). LIBRA uses HiGHS (MIT), NumPy, pandas, Matplotlib and openpyxl (permissive licenses),
and Qt for Python (PySide6, LGPL-3.0); see `app/THIRD_PARTY_LICENSES.md`.

## Citation

See `app/CITATION.cff`.
