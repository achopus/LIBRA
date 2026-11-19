from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                               QGridLayout, QHeaderView, QInputDialog, QLineEdit, QMenu, QMessageBox, QRadioButton,
                               QSpinBox, QTableWidget, QTableWidgetItem, QToolButton, QWidget)

from randomizer.project import TERMS

from .. import icons
from ..widgets import (Card, DataFrameModel, DataTable, FlowLayout, HelpButton, button, hbox, label, vbox)
from .base import Page, quiet

ID_NAMES = ("id", "subject", "animal", "participant", "patient", "rat", "mouse", "code", "name")


def guess_id_column(df: pd.DataFrame) -> str:
    for c in df.columns:
        if str(c).strip().lower() in ID_NAMES or str(c).strip().lower().endswith(" id"):
            return c
    for c in df.columns:
        col = df[c].astype(str).str.strip()
        if col.ne("").all() and col.is_unique:
            return c
    return df.columns[0]


def rows_to_frame(rows: list[list[str]], current_cols: list[str]) -> pd.DataFrame:
    """Pasted rows -> table. The first row is a header when it looks like one."""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    first = [c.strip() for c in rows[0]]
    looks_header = (len(rows) > 1 and all(first) and len(set(first)) == len(first)
                    and not any(re.fullmatch(r"[-+]?\d+([.,]\d+)?", c) for c in first))
    if looks_header:
        return pd.DataFrame(rows[1:], columns=first)
    cols = list(current_cols[:width]) + [f"Column {i + 1}" for i in range(len(current_cols), width)]
    return pd.DataFrame(rows, columns=cols)


class GenerateIdsDialog(QDialog):
    def __init__(self, terms: dict, has_rows: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Generate {terms['many']}")
        self.setMinimumWidth(460)
        self.prefix = QLineEdit(terms["One"][:1].upper())
        self.count = QSpinBox()
        self.count.setRange(1, 5000)
        self.count.setValue(24)
        self.grouped = QCheckBox(f"The {terms['many']} come in groups (e.g. sex)")
        self.group_name = QLineEdit("Sex")
        self.levels = QTableWidget(2, 2)
        self.levels.setHorizontalHeaderLabels(["Group", terms["Many"]])
        for r, (lvl, n) in enumerate([("male", 12), ("female", 12)]):
            self.levels.setItem(r, 0, QTableWidgetItem(lvl))
            self.levels.setItem(r, 1, QTableWidgetItem(str(n)))
        self.levels.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.levels.verticalHeader().hide()
        self.levels.setMaximumHeight(150)
        add = button("Add group", "plus", flat=True)
        add.clicked.connect(lambda: self.levels.insertRow(self.levels.rowCount()))
        rem = button("Remove", "trash", flat=True)
        rem.clicked.connect(lambda: self.levels.removeRow(max(0, self.levels.currentRow())))
        self.replace = QRadioButton("Replace the current table")
        self.append = QRadioButton("Add below the current rows")
        self.replace.setChecked(True)
        form = QFormLayout()
        form.addRow("ID prefix", self.prefix)
        form.addRow(f"Number of {terms['many']}", self.count)
        self.group_box = QWidget()
        self.group_box.setLayout(vbox(hbox(label("Group column"), self.group_name),
                                      self.levels, hbox(add, rem, None)))
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Generate")
        bb.button(QDialogButtonBox.Ok).setProperty("primary", True)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay = vbox(form, self.grouped, self.group_box, spacing=10, margins=(18, 16, 18, 16))
        if has_rows:
            lay.addWidget(self.replace)
            lay.addWidget(self.append)
        lay.addWidget(label("IDs are numbered in table order, which is taken as the enrollment order.", "Hint", wrap=True))
        lay.addWidget(bb)
        self.setLayout(lay)
        self.grouped.toggled.connect(self._toggle)
        self._toggle(False)

    def _toggle(self, on):
        self.group_box.setVisible(on)
        self.count.setEnabled(not on)
        self.adjustSize()

    def frame(self, id_col: str) -> pd.DataFrame:
        prefix = self.prefix.text().strip()
        if not self.grouped.isChecked():
            n = self.count.value()
            w = max(2, len(str(n)))
            return pd.DataFrame({id_col: [f"{prefix}{i:0{w}d}" for i in range(1, n + 1)]})
        gname = self.group_name.text().strip() or "Group"
        rows = []
        for r in range(self.levels.rowCount()):
            lvl = (self.levels.item(r, 0).text() if self.levels.item(r, 0) else "").strip()
            try:
                n = int((self.levels.item(r, 1).text() if self.levels.item(r, 1) else "0").strip())
            except ValueError:
                n = 0
            if lvl and n > 0:
                rows += [lvl] * n
        w = max(2, len(str(len(rows))))
        return pd.DataFrame({id_col: [f"{prefix}{i:0{w}d}" for i in range(1, len(rows) + 1)], gname: rows})


class SubjectsPage(Page):
    step = "subjects"
    title_text = "{Many}"
    lead_text = ("List the {many} in the order they enter the study. Paste from Excel, import a file, "
                 "or generate IDs.")

    def __init__(self, ctl, parent=None):
        super().__init__(ctl, parent)
        tf = self.terms
        # wording
        self.terms_card = Card("Wording", help_key="terms", terms_fn=tf,
                               hint="Use any words you like. They appear everywhere in the app and in the "
                                    "exported files.")
        self.preset = QComboBox()
        self.preset.addItem("Fill in from a common choice…")
        self.preset.addItems(list(TERMS))
        self.preset.setMinimumWidth(240)
        self.terms_card.header.addWidget(self.preset)
        self.words = {}
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        rows = [("What you randomize", "subject_noun", "e.g. rat, participant, cage", "subject_plural", "e.g. rats"),
                ("One step of the schedule", "period_name", "e.g. Week, Session, MRI scan", "period_plural",
                 "e.g. Weeks")]
        for r, (title, k1, ph1, k2, ph2) in enumerate(rows):
            grid.addWidget(label(title), r, 0)
            for c, (key, ph, lab) in enumerate(((k1, ph1, "one"), (k2, ph2, "several"))):
                e = QLineEdit()
                e.setPlaceholderText(ph)
                e.setMinimumWidth(170)
                e.editingFinished.connect(lambda k=key, w=e: self._word(k, w.text()))
                self.words[key] = e
                grid.addWidget(label(lab, "Hint"), r, 1 + 2 * c)
                grid.addWidget(e, r, 2 + 2 * c)
        grid.setColumnStretch(5, 1)
        self.terms_card.add(grid)
        self.content.addWidget(self.terms_card)
        self.preset.activated.connect(self._preset)

        # table
        self.table_card = Card("{Many}", help_key="subjects", terms_fn=tf)
        b_gen = button("Generate IDs…", "users")
        b_imp = button("Import file…", "upload")
        b_paste = button("Paste", "clipboard", tip="Paste rows copied from Excel (Ctrl+V)")
        b_add = button("Add row", "plus", flat=True)
        b_del = button("Delete rows", "trash", flat=True)
        b_cols = QToolButton()
        b_cols.setText("Columns")
        b_cols.setIcon(icons.icon("columns"))
        b_cols.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        b_cols.setPopupMode(QToolButton.InstantPopup)
        b_cols.setProperty("flat", True)
        menu = QMenu(b_cols)
        menu.addAction("Add column…", self._add_column)
        menu.addAction("Rename column…", self._rename_column)
        menu.addAction("Delete column…", self._delete_column)
        menu.addSeparator()
        menu.addAction("Clear the whole table", self._clear)
        b_cols.setMenu(menu)
        self.table_card.add(hbox(b_gen, b_imp, b_paste, 12, b_add, b_del, b_cols, None))
        self.model = DataFrameModel(editable=True)
        self.view = DataTable(self.model)
        self.view.setMinimumHeight(300)
        self.table_card.add(self.view)
        self.count_label = label("", "Hint")
        self.table_card.add(self.count_label)
        self.content.addWidget(self.table_card)
        self.model.edited.connect(lambda df: self.ctl.set_subjects(df, "Edit table"))
        self.view.paste_with_header.connect(self._paste_new)
        b_gen.clicked.connect(self._generate)
        b_imp.clicked.connect(self._import)
        b_paste.clicked.connect(self.view.paste)
        b_add.clicked.connect(self._add_row)
        b_del.clicked.connect(self._delete_rows)

        # columns' roles
        self.roles = Card("Groups", hint="Tell the app what the columns mean.")
        self.id_combo = QComboBox()
        self.id_combo.setMinimumWidth(200)
        self.id_combo.activated.connect(lambda _: self.ctl.set("id_column", self.id_combo.currentText(),
                                                                 "Choose ID column"))
        self.roles.add(hbox(label("ID column"), self.id_combo, None))
        self.strata_row = FlowLayout(spacing=14)
        self.roles.add(hbox(label("Balance separately within"), HelpButton("strata", tf), None, spacing=4))
        self.strata_holder = QWidget()
        self.strata_holder.setLayout(self.strata_row)
        self.roles.add(self.strata_holder)
        self.no_groups = label("", "Hint", wrap=True)
        self.roles.add(self.no_groups)
        self.cluster = QComboBox()
        self.cluster.setMinimumWidth(200)
        self.cluster.activated.connect(self._cluster)
        self.cluster_label = label("")
        self.roles.add(hbox(self.cluster_label, self.cluster, HelpButton("cluster", tf), None, spacing=6))
        self.content.addWidget(self.roles)
        self.finish()

    # ------------------------------------------------------------------ wording
    def _preset(self, i):
        name = self.preset.itemText(i)
        with quiet(self.preset):
            self.preset.setCurrentIndex(0)
        if name in TERMS:
            one, many, per, pers = TERMS[name]
            self.ctl.edit("Change wording", lambda p: p.settings.update(
                {"terms": name, "subject_noun": one, "subject_plural": many, "period_name": per,
                 "period_plural": pers}))

    def _word(self, key: str, text: str):
        """Any word is fine. Changing the singular also updates a plural that was made from it."""
        set_word(self.ctl, key, text)
        self.refresh()

    # ------------------------------------------------------------------ table actions
    def _set_table(self, df: pd.DataFrame, text: str, id_col: str | None = None):
        df = df.copy()
        df.columns = [str(c).strip() or f"Column {i + 1}" for i, c in enumerate(df.columns)]
        df = df.loc[:, ~pd.Index(df.columns).duplicated()]
        idc = id_col or (self.s["id_column"] if self.s["id_column"] in df.columns else guess_id_column(df))

        def fn(p):
            p.subjects = df.reset_index(drop=True)
            p.settings["id_column"] = idc
            p.settings["strata"] = [c for c in p.settings["strata"] if c in df.columns and c != idc]
            if p.settings.get("cluster_column") not in df.columns:
                p.settings["cluster_column"] = ""
        self.ctl.edit(text, fn)

    def _paste_new(self, rows):
        self._set_table(rows_to_frame(rows, list(self.project.subjects.columns)), "Paste table")

    def _generate(self):
        has_rows = not self.project.subjects.dropna(how="all").empty
        dlg = GenerateIdsDialog(self.terms(), has_rows, self)
        if dlg.exec() != QDialog.Accepted:
            return
        idc = self.s["id_column"] or "ID"
        new = dlg.frame(idc)
        if has_rows and dlg.append.isChecked():
            df = pd.concat([self.project.subjects, new], ignore_index=True).fillna("")
        else:
            df = new
        self._set_table(df, f"Generate {self.terms()['many']}", idc)
        group_cols = [c for c in new.columns if c != idc]
        if group_cols:
            self.ctl.set("strata", sorted(set(self.s["strata"]) | set(group_cols)), "Balance within groups")

    def _import(self):
        path, _ = QFileDialog.getOpenFileName(self, f"Import {self.terms()['many']}", "",
                                              "Tables (*.csv *.xlsx *.xls *.tsv *.txt)")
        if not path:
            return
        try:
            df = read_table(path, self)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "Could not read the file", str(e))
            return
        if df is None:
            return
        if df.empty:
            QMessageBox.warning(self, "Empty file", "The file has no rows.")
            return
        self._set_table(df.fillna(""), f"Import {Path(path).name}")

    def _add_row(self):
        df = self.project.subjects
        new = pd.DataFrame([[""] * len(df.columns)], columns=df.columns)
        self.ctl.set_subjects(pd.concat([df, new], ignore_index=True), "Add row")
        self.view.scrollToBottom()

    def _delete_rows(self):
        rows = sorted({i.row() for i in self.view.selectedIndexes()})
        if not rows:
            QMessageBox.information(self, "Delete rows", "Select the rows to delete first.")
            return
        df = self.project.subjects.drop(index=self.project.subjects.index[rows])
        self.ctl.set_subjects(df, f"Delete {len(rows)} row{'s' if len(rows) > 1 else ''}")

    def _add_column(self):
        name, ok = QInputDialog.getText(self, "Add column", "Name of the new column (e.g. Sex, Cage, Cohort):")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.project.subjects.columns:
            QMessageBox.information(self, "Add column", f"There is already a column called {name}.")
            return
        df = self.project.subjects.copy()
        df[name] = ""
        self.ctl.set_subjects(df, f"Add column {name}")

    def _pick_column(self, title):
        cols = [str(c) for c in self.project.subjects.columns]
        if not cols:
            return None
        cur = self.view.currentIndex()
        default = cur.column() if cur.isValid() else 0
        name, ok = QInputDialog.getItem(self, title, "Column:", cols, default, False)
        return name if ok else None

    def _rename_column(self):
        old = self._pick_column("Rename column")
        if old is None:
            return
        new, ok = QInputDialog.getText(self, "Rename column", f"New name for '{old}':", text=old)
        new = new.strip()
        if not ok or not new or new == old:
            return
        if new in self.project.subjects.columns:
            QMessageBox.information(self, "Rename column", f"There is already a column called {new}.")
            return

        def fn(p):
            p.subjects = p.subjects.rename(columns={old: new})
            s = p.settings
            s["strata"] = [new if c == old else c for c in s["strata"]]
            if s["id_column"] == old:
                s["id_column"] = new
            if s.get("cluster_column") == old:
                s["cluster_column"] = new
            if s["calendar"].get("start_column") == old:
                s["calendar"]["start_column"] = new
        self.ctl.edit(f"Rename column {old}", fn)

    def _delete_column(self):
        col = self._pick_column("Delete column")
        if col is None:
            return

        def fn(p):
            p.subjects = p.subjects.drop(columns=[col])
            s = p.settings
            s["strata"] = [c for c in s["strata"] if c != col]
            if s.get("cluster_column") == col:
                s["cluster_column"] = ""
            if s["id_column"] == col and len(p.subjects.columns):
                s["id_column"] = guess_id_column(p.subjects)
        self.ctl.edit(f"Delete column {col}", fn)

    def _clear(self):
        if QMessageBox.question(self, "Clear table", f"Remove all {self.terms()['many']} and columns?") \
                != QMessageBox.Yes:
            return
        idc = self.s["id_column"] or "ID"
        self._set_table(pd.DataFrame({idc: pd.Series(dtype=str)}), "Clear table", idc)

    def _toggle_stratum(self, col, on):
        cur = list(self.s["strata"])
        if on and col not in cur:
            cur.append(col)
        if not on:
            cur = [c for c in cur if c != col]
        self.ctl.set("strata", cur, f"{'Balance' if on else 'Stop balancing'} within {col}")

    def _cluster(self, _):
        v = self.cluster.currentData() or ""
        self.ctl.edit("Choose randomization unit", lambda p: p.settings.update(
            {"cluster_column": v, "strata": [c for c in p.settings["strata"] if c != v]}))

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        super().refresh()
        s, t = self.s, self.terms()
        for key, w in self.words.items():
            v = str(s.get(key, ""))
            if w.text() != v and not w.hasFocus():
                with quiet(w):
                    w.setText(v)
        self.table_card.title_label.setText(t["Many"])
        df = self.project.subjects
        if not df.equals(self.model.df):
            self.model.set_frame(df.copy())
            hdr = self.view.horizontalHeader()
            for i in range(len(df.columns)):
                hdr.setSectionResizeMode(i, QHeaderView.Interactive)
            if len(df.columns) <= 4:
                for i in range(len(df.columns)):
                    hdr.setSectionResizeMode(i, QHeaderView.Stretch)
        n = len(df.dropna(how="all"))
        self.count_label.setText(f"{n} {t['many'] if n != 1 else t['one']}. Table order is the enrollment "
                                 f"order (used for enrollment blocks). Double-click a cell to edit.")
        cols = [str(c) for c in df.columns]
        with quiet(self.id_combo):
            self.id_combo.clear()
            self.id_combo.addItems(cols)
            if s["id_column"] in cols:
                self.id_combo.setCurrentText(s["id_column"])
        others = [c for c in cols if c != s["id_column"] and c != s.get("cluster_column")]
        self.strata_row.clear()
        for c in others:
            cb = QCheckBox(c)
            cb.setChecked(c in s["strata"])
            nun = df[c].astype(str).str.strip().replace("", pd.NA).dropna().nunique()
            cb.setToolTip(f"{nun} different value{'s' if nun != 1 else ''}")
            cb.toggled.connect(lambda on, col=c: self._toggle_stratum(col, on))
            self.strata_row.addWidget(cb)
        self.strata_holder.setVisible(bool(others))
        self.no_groups.setText("Add a column (for example Sex or Genotype) to balance within groups."
                               if not others else "")
        self.no_groups.setVisible(not others)
        self.cluster_label.setText(f"Same sequence for every {t['one']} in the same")
        with quiet(self.cluster):
            self.cluster.clear()
            self.cluster.addItem(f"— (each {t['one']} separately)", "")
            for c in cols:
                if c != s["id_column"]:
                    self.cluster.addItem(c, c)
            i = self.cluster.findData(s.get("cluster_column", ""))
            self.cluster.setCurrentIndex(max(0, i))


PLURAL_OF = {"subject_noun": "subject_plural", "period_name": "period_plural"}


def set_word(ctl, key: str, text: str):
    """Set one of the four wording fields (shared with the treatments page)."""
    from randomizer.spec import plural_of
    text = text.strip()
    s = ctl.project.settings
    if not text or text == str(s.get(key, "")):
        return
    upd = {key: text}
    pk = PLURAL_OF.get(key)
    if pk:
        old_plural = str(s.get(pk, "")).strip()
        if not old_plural or old_plural == plural_of(str(s.get(key, ""))):
            upd[pk] = plural_of(text)               # the plural was automatic: keep it in step
    new = {**s, **upd}
    words = (new["subject_noun"], new["subject_plural"], new["period_name"], new.get("period_plural", ""))
    upd["terms"] = next((n for n, w in TERMS.items() if tuple(w) == words), "Custom words")
    ctl.edit("Change wording", lambda p: p.settings.update(upd))


def read_table(path: str, parent=None) -> pd.DataFrame | None:
    """CSV/TSV/Excel to a table of text (IDs such as 007 keep their zeros)."""
    p = Path(path)
    if p.suffix.lower() in (".xlsx", ".xls"):
        sheets = pd.ExcelFile(p).sheet_names
        sheet = sheets[0]
        if len(sheets) > 1 and parent is not None:
            sheet, ok = QInputDialog.getItem(parent, "Choose a sheet", "The workbook has several sheets:",
                                             sheets, 0, False)
            if not ok:
                return None
        return pd.read_excel(p, sheet_name=sheet, dtype=str)
    sep = "\t" if p.suffix.lower() in (".tsv", ".txt") else None
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return pd.read_csv(p, sep=sep, engine="python", dtype=str, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("Unknown text encoding.")
