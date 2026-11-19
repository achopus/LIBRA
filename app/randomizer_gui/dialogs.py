"""Dialogs: new project, export, labels, add subjects, replace a dropout, compare runs, about."""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
from PySide6.QtCore import QStandardPaths, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHeaderView, QLineEdit, QListWidget, QMessageBox, QRadioButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout)

from randomizer import APP_EXPANSION, __version__
from randomizer.dates import check as cal_check
from randomizer.diagnostics import best_guess_rate, checks, transition_matrix
from randomizer.project import DESIGNS, TERMS, Project, default_settings, new_seed

from . import theme
from .widgets import logo, Banner, DataFrameModel, DataTable, HelpButton, button, hbox, label, terms, vbox

from randomizer import CITATION  # noqa: E402  (re-exported for the results page)


def _buttons(dlg, ok_text="OK", cancel=True):
    bb = QDialogButtonBox((QDialogButtonBox.Ok | QDialogButtonBox.Cancel) if cancel else QDialogButtonBox.Ok)
    ok = bb.button(QDialogButtonBox.Ok)
    ok.setText(ok_text)
    ok.setProperty("primary", True)
    bb.accepted.connect(dlg.accept)
    bb.rejected.connect(dlg.reject)
    return bb


def safe_name(text: str) -> str:
    return re.sub(r'\s*[\\/:*?"<>|]+\s*', " - ", text).strip(" .-") or "study"


def documents_folder() -> Path:
    return Path(QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or Path.home()) / \
        "LIBRA"


# ----------------------------------------------------------------------------- new project
class NewProjectDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New project")
        self.setMinimumWidth(520)
        self.name = QLineEdit("New study")
        self.name.selectAll()
        self.terms = QComboBox()
        self.terms.addItems(list(TERMS))
        self.design = QComboBox()
        for k, (n, d) in DESIGNS.items():
            self.design.addItem(n, k)
        self.folder = QLineEdit(str(documents_folder()))
        browse = button("Choose…", "folder")
        browse.clicked.connect(self._browse)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        form.addRow("Study name", self.name)
        form.addRow("What you randomize", self.terms)
        form.addRow("Design", self.design)
        form.addRow("Save in folder", hbox(self.folder, browse))
        lay = vbox(form, label("The project is saved there and then saved automatically as you work. "
                               "You can change everything later.", "Hint", wrap=True),
                   _buttons(self, "Create project"), spacing=12, margins=(20, 18, 20, 18))
        self.setLayout(lay)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Save projects in", self.folder.text())
        if d:
            self.folder.setText(d)

    def project(self) -> tuple[Project, Path]:
        s = default_settings()
        preset = self.terms.currentText()
        s["terms"] = preset
        s["subject_noun"], s["subject_plural"], s["period_name"], s["period_plural"] = TERMS[preset]
        s["design"] = self.design.currentData()
        if s["design"] == "parallel":
            s["treatments"] = [{"name": "Vehicle", "ratio": 1.0}, {"name": "Drug", "ratio": 1.0}]
        name = self.name.text().strip() or "New study"
        p = Project(name=name, settings=s)
        folder = Path(self.folder.text().strip() or documents_folder())
        path = folder / f"{safe_name(name)}.libra"
        i = 2
        while path.exists():
            path = folder / f"{safe_name(name)} ({i}).libra"
            i += 1
        return p, path


# ----------------------------------------------------------------------------- export
class ExportDialog(QDialog):
    def __init__(self, project: Project, run, parent=None):
        super().__init__(parent)
        self.project, self.run = project, run
        res = run.view()
        self.res = res
        self.setWindowTitle(f"Export {run.id}")
        self.setMinimumWidth(560)
        self.xlsx = QRadioButton("Excel workbook (.xlsx): schedule, checks, methods text and settings in one file")
        self.csv = QRadioButton("CSV files: the schedule as plain tables, plus the methods text")
        self.xlsx.setChecked(True)
        grp = QButtonGroup(self)
        grp.addButton(self.xlsx)
        grp.addButton(self.csv)
        t = terms(project.settings)
        self.long = QCheckBox(f"Also a long table (one row per {t['one']} and {t['period']}), for R, SPSS or JASP")
        self.long.setChecked(True)
        self.png = QCheckBox("Picture of the schedule (.png)")
        self.png.setChecked(True)
        self.bal_png = QCheckBox("Pictures of the balance (.png)")
        self.dpi = QSpinBox()
        self.dpi.setRange(72, 1200)
        self.dpi.setSingleStep(50)
        self.dpi.setSuffix(" dpi")
        self.dpi.setValue(int(project.settings.get("picture_dpi", 300)))
        self.dpi.setToolTip("300 dpi suits print and journals; 600 for very large posters.")
        for box in (self.png, self.bal_png):
            box.toggled.connect(lambda _: self.dpi.setEnabled(self.png.isChecked() or self.bal_png.isChecked()))
        self.experiment = QCheckBox("Files for experiment software (PsychoPy, OpenSesame, jsPsych, lab.js)")
        self.experiment.setToolTip(f"A folder with the condition of every {t['one']} in every {t['period']} "
                                   "(CSV and JSON) and copy-paste code that reads it. With blinding, codes only.")
        self.experiment.setChecked(bool(project.settings.get("export_experiment", False)))
        cal = project.settings["calendar"]
        self.cal_ok = not cal_check(cal, res)
        self.dates = QCheckBox("Add dates from the calendar")
        self.dates.setChecked(self.cal_ok)
        self.dates.setEnabled(self.cal_ok)
        if not self.cal_ok:
            self.dates.setToolTip("Set a start date on the Calendar tab first.")
        stem = f"{safe_name(project.name)}_{run.id}" + ("_FINAL" if run.final else "")
        self.stem = QLineEdit(stem)
        default_dir = Path(project.path).parent if project.path else documents_folder()
        self.folder = QLineEdit(str(default_dir))
        browse = button("Choose…", "folder")
        browse.clicked.connect(self._browse)
        form = QFormLayout()
        form.addRow("File name", self.stem)
        form.addRow("Folder", hbox(self.folder, browse))
        lay = vbox(label("Format", "CardTitle"), self.xlsx, self.csv, self.long, 6,
                   label("Extras", "CardTitle"), self.png, self.bal_png,
                   hbox(label("Picture resolution"), self.dpi, None), self.experiment, self.dates, 6, form,
                   spacing=8, margins=(20, 18, 20, 18))
        if res.codes:
            lay.addWidget(Banner("info", "Blinding is on. You get three kinds of file: the full record "
                                         "(keep it yourself), a blinded schedule with codes only (for the "
                                         "experimenters), and the code key (keep it separate)."))
        lay.addWidget(_buttons(self, "Export"))
        self.setLayout(lay)
        self.csv.toggled.connect(lambda on: self.long.setEnabled(on))
        self.long.setEnabled(False)

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "Export to", self.folder.text())
        if d:
            self.folder.setText(d)

    def export(self) -> list[Path]:
        from randomizer.export import write_outputs
        fmt = "xlsx" if self.xlsx.isChecked() else "csv"
        self.project.settings["picture_dpi"] = self.dpi.value()            # remembered for next time
        self.project.settings["export_experiment"] = self.experiment.isChecked()
        extra = {"Audit log": pd.DataFrame(self.project.log)} if fmt == "xlsx" else None
        if fmt == "xlsx":
            info = pd.DataFrame({"Item": ["Project", "Run", "Created", "Fingerprint", "Final", "Note"],
                                 "Value": [self.project.name, self.run.id, self.run.created,
                                           self.run.fingerprint, "yes" if self.run.final else "no",
                                           self.run.note]})
            extra = {"Run": info, **extra}
        return write_outputs(self.res, self.folder.text().strip(), safe_name(self.stem.text().strip()),
                             fmt=fmt, long=self.long.isChecked(), png=self.png.isChecked(),
                             balance_png=self.bal_png.isChecked(),
                             calendar=self.project.settings["calendar"] if self.dates.isChecked() else None,
                             dpi=self.dpi.value(), experiment=self.experiment.isChecked(),
                             run_id=self.run.id, extra=extra)


def show_files(parent, paths, title="Export finished"):
    paths = [Path(p) for p in paths]
    dlg = QDialog(parent)
    dlg.setWindowTitle(title)
    dlg.setMinimumWidth(520)
    lst = QListWidget()
    lst.addItems([p.name for p in paths])
    lst.setMaximumHeight(min(260, 30 * len(paths) + 10))
    open_btn = button("Open folder", "folder", primary=True)
    open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[0].parent))))
    close = button("Close")
    close.clicked.connect(dlg.accept)
    dlg.setLayout(vbox(label(f"{len(paths)} file{'s' if len(paths) != 1 else ''} saved in", "Hint"),
                       label(str(paths[0].parent), selectable=True, wrap=True), lst, hbox(None, close, open_btn),
                       spacing=10, margins=(20, 18, 20, 18)))
    dlg.exec()


# ----------------------------------------------------------------------------- labels
class LabelsDialog(QDialog):
    def __init__(self, has_codes: bool, has_dates: bool, parent=None):
        super().__init__(parent)
        from .printing import LAYOUTS
        self.setWindowTitle("Print labels")
        self.setMinimumWidth(520)
        self.layouts = LAYOUTS
        self.layout_box = QComboBox()
        self.layout_box.addItems([lay.name for lay in LAYOUTS])
        self.per_period = QRadioButton("One label per subject and period" + (" (with date)" if has_dates else ""))
        self.per_subject = QRadioButton("One label per subject, with the whole sequence")
        self.per_period.setChecked(True)
        self.blinded = QCheckBox("Show codes instead of treatment names")
        self.blinded.setChecked(has_codes)
        self.blinded.setEnabled(has_codes)
        self.outline = QCheckBox("Draw label outlines (for checking alignment on plain paper)")
        self.outline.setChecked(True)
        self.setLayout(vbox(label("Sheet", "CardTitle"), self.layout_box, 6, label("Content", "CardTitle"),
                            self.per_period, self.per_subject, self.blinded, self.outline,
                            label("Tip: print one page on plain paper first and hold it against a label sheet.",
                                  "Hint", wrap=True),
                            _buttons(self, "Save PDF…"), spacing=8, margins=(20, 18, 20, 18)))


# ----------------------------------------------------------------------------- add subjects
class ExtendDialog(QDialog):
    def __init__(self, project: Project, run, parent=None):
        super().__init__(parent)
        self.project, self.run = project, run
        spec = run.solver_spec()
        t = terms(project.settings)
        self.setWindowTitle(f"Add {t['many']} to {run.id}")
        self.setMinimumSize(560, 520)
        self.cols = [spec.id_column] + [c for c in spec.strata]
        start = len(spec.subjects) + 1
        df = pd.DataFrame({c: [""] * 4 for c in self.cols})
        ids = spec.subjects[spec.id_column].astype(str)
        m = re.match(r"^(.*?)(\d+)$", ids.iloc[-1]) if len(ids) else None
        if m:
            w = len(m.group(2))
            nums = [int(re.match(r"^.*?(\d+)$", x).group(1)) for x in ids if re.match(r"^.*?(\d+)$", x)]
            start = max(nums) + 1 if nums else start
            df[spec.id_column] = [f"{m.group(1)}{i:0{w}d}" for i in range(start, start + 4)]
        self.model = DataFrameModel(df, editable=True)
        self.model.edited.connect(lambda d: self.model.set_frame(d))
        self.view = DataTable(self.model)
        self.view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.view.paste_with_header.connect(lambda rows: self.model.write_block(0, 0, rows))
        add = button("Add row", "plus", flat=True)
        add.clicked.connect(lambda: self.model.write_block(self.model.rowCount(), 0, [[""]]))
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_646)
        self.seed.setValue(new_seed())
        self.limit = QSpinBox()
        self.limit.setRange(5, 3600)
        self.limit.setSuffix(" s")
        self.limit.setValue(int(spec.time_limit))
        need = f" and their {', '.join(spec.strata)}" if spec.strata else ""
        self.setLayout(vbox(
            label(f"Everyone already in {run.id} keeps their sequence. Enter the new {t['many']} (IDs{need}); "
                  f"you can paste from Excel.", wrap=True),
            self.view, hbox(add, None),
            hbox(label("Seed"), self.seed, 16, label("Time limit"), self.limit, None),
            _buttons(self, f"Add {t['many']}"), spacing=10, margins=(20, 18, 20, 18)))

    def new_subjects(self) -> pd.DataFrame:
        df = self.model.df.copy().astype(str)
        df = df[df[self.cols[0]].str.strip() != ""]
        return df.reset_index(drop=True)


# ----------------------------------------------------------------------------- replace a dropout
class ReplaceDialog(QDialog):
    def __init__(self, project: Project, run, parent=None):
        super().__init__(parent)
        res = run.view()
        t = terms(project.settings)
        idc = res.spec.id_column
        status = res.schedule["Status"] if "Status" in res.schedule.columns else pd.Series([""] * len(res.schedule))
        ids = [str(i) for i, st in zip(res.schedule[idc], status.fillna("")) if not str(st).startswith("Dropped")]
        self.setWindowTitle(f"Replace a {t['one']} who dropped out")
        self.setMinimumWidth(460)
        self.old = QComboBox()
        self.old.addItems(ids)
        self.new = QLineEdit()
        self.new.setPlaceholderText("ID of the replacement")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional, e.g. 'dropped out after week 2 (illness)'")
        form = QFormLayout()
        form.addRow(f"{t['One']} who dropped out", self.old)
        form.addRow("Replacement ID", self.new)
        form.addRow("Note", self.note)
        self.setLayout(vbox(label(f"The replacement gets the full sequence of the {t['one']} who dropped out, "
                                  f"so the balance of the design stays the same. Both rows are kept, with a "
                                  f"status note. This creates a new run.", wrap=True),
                            form, _buttons(self, "Replace"), spacing=12, margins=(20, 18, 20, 18)))


# ----------------------------------------------------------------------------- compare runs
def compare_table(project: Project, runs) -> pd.DataFrame:
    rows = {}
    ref = project.final_run or runs[0]
    for r in runs:
        res = r.view()
        col = {"Created": r.created.replace("T", " "), "Kind": r.kind, "Note": r.note,
               "Seed": res.spec.seed, "Final": "yes" if r.final else "",
               "Solver result": "optimal" if res.proven_optimal else "time limit",
               "Solve time (s)": f"{res.solve_seconds:.0f}",
               "Final choice": (res.randomization or {}).get("method", ""),
               "Fingerprint": r.fingerprint}
        for c in checks(res):
            col[c.name] = ("✓ " if c.ok else "– ") + c.detail
        if res.spec.adjacent_pairs:
            M = transition_matrix(res.assign, len(res.spec.treatments), res.spec.adjacent_pairs)
            col["Next treatment guessed right"] = f"{best_guess_rate(M):.0%}"
        if r is not ref:
            a, b = ref.view().schedule, res.schedule
            idc = res.spec.id_column
            if idc in a.columns and idc in b.columns:
                pa = a.set_index(a[idc].astype(str))[ref.view().period_columns].astype(str)
                pb = b.set_index(b[idc].astype(str))[res.period_columns].astype(str)
                common = pa.index.intersection(pb.index)
                if len(pa.columns) == len(pb.columns):
                    diff = int((pa.loc[common].to_numpy() != pb.loc[common].to_numpy()).any(axis=1).sum())
                    col[f"Different sequence than {ref.id}"] = f"{diff} of {len(common)}"
        rows[r.id] = col
    return pd.DataFrame(rows)


class CompareDialog(QDialog):
    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Compare runs")
        self.resize(1000, 600)
        df = compare_table(project, project.runs)
        table = QTableWidget(len(df.index), len(df.columns))
        table.setHorizontalHeaderLabels(list(df.columns))
        table.setVerticalHeaderLabels(list(df.index))
        for i in range(len(df.index)):
            for j in range(len(df.columns)):
                v = df.iat[i, j]
                it = QTableWidgetItem("" if v is None or (isinstance(v, float) and np.isnan(v)) else str(v))
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                table.setItem(i, j, it)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        table.horizontalHeader().setDefaultSectionSize(220)
        table.setWordWrap(True)
        table.resizeRowsToContents()
        table.verticalHeader().setMinimumWidth(190)
        close = button("Close")
        close.clicked.connect(self.accept)
        self.setLayout(vbox(table, hbox(None, close), spacing=10, margins=(16, 16, 16, 16)))


# ----------------------------------------------------------------------------- about
class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from PySide6 import __version__ as qt_version
        import highspy  # noqa: F401
        self.setWindowTitle("About LIBRA")
        self.setMinimumWidth(520)
        cite = label(CITATION, wrap=True, selectable=True)
        copy_btn = button("Copy citation", "copy")
        copy_btn.clicked.connect(lambda: __import__("PySide6.QtWidgets", fromlist=["QApplication"])
                                 .QApplication.clipboard().setText(CITATION))
        close = button("Close", primary=True)
        close.clicked.connect(self.accept)
        self.setLayout(vbox(
            hbox(logo(56), vbox(label("LIBRA", "PageTitle"),
                                label(f"Crossover Randomizer · version {__version__}", "Hint"),
                                label(f"{APP_EXPANSION}", "Muted"), spacing=1), None, spacing=14),
            label("Balanced, hard-to-predict treatment schedules for crossover and parallel studies, chosen by "
                  "integer linear programming (HiGHS solver).", wrap=True),
            Banner("ok", "Runs entirely on this computer. Nothing you enter is sent online."),
            label("How to cite", "CardTitle"), cite, hbox(copy_btn, None),
            label(f"Free software under the MIT license. Built with Python, Qt for Python {qt_version} (LGPL), "
                  "HiGHS, NumPy, pandas, matplotlib and openpyxl.", "Hint", wrap=True),
            hbox(None, close), spacing=10, margins=(22, 20, 22, 20)))
