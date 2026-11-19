# Third-party software

LIBRA is released under the MIT license (see `LICENSE`). It uses the following software, which keeps
its own license. The installers for Windows and macOS include these packages; their license files are
inside the installation folder, next to each package.

| Package | Used for | License |
| --- | --- | --- |
| [HiGHS](https://highs.dev) (`highspy`) | Integer linear programming solver | MIT |
| [NumPy](https://numpy.org) | Arrays | BSD-3-Clause |
| [pandas](https://pandas.pydata.org) | Tables, import and export | BSD-3-Clause |
| [Matplotlib](https://matplotlib.org) | Pictures | Matplotlib license (BSD-style) |
| [openpyxl](https://openpyxl.readthedocs.io) | Excel files | MIT |
| [Qt for Python](https://doc.qt.io/qtforpython/) (PySide6) and Qt | Desktop interface | LGPL-3.0 |
| [Python](https://www.python.org) | Runtime (bundled in the installers) | PSF License |

**Qt (LGPL-3.0).** The installers contain Qt and PySide6 as separate shared libraries, unchanged, in
the installation folder; you may replace them with other builds of the same version. Their source
code is available from the Qt Project (https://code.qt.io) and Qt for Python
(https://code.qt.io/cgit/pyside/pyside-setup.git). Running LIBRA from source uses the copies you
install with `pip`.

Gurobi, if installed and licensed on your computer, can be used instead of HiGHS; it is not included.
