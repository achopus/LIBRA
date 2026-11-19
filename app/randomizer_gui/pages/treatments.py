from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QGridLayout, QHeaderView,
                               QSpinBox, QTableWidget, QTableWidgetItem, QWidget)

from randomizer.project import DESIGNS, randomized_count, treatment_names

from ..widgets import Card, Chip, ChoiceCard, FlowLayout, HelpButton, button, fmt, hbox, label
from .base import Page, quiet

PERIOD_WORDS = ["Week", "Day", "Session", "Visit", "Period", "Test day", "Phase"]


class TreatmentsPage(Page):
    step = "treatments"
    title_text = "Treatments and {periods}"
    lead_text = "Choose the design, list the treatments, and add any {periods} that are the same for everyone."

    def __init__(self, ctl, parent=None):
        super().__init__(ctl, parent)
        tf = self.terms
        # design type
        self.design_card = Card("Design", help_key="design", terms_fn=tf)
        grid = QGridLayout()
        grid.setSpacing(10)
        self.design_group = QButtonGroup(self)
        self.design_buttons = {}
        for i, key in enumerate(DESIGNS):
            b = ChoiceCard(DESIGNS[key][0], "")
            self.design_group.addButton(b)
            self.design_buttons[key] = b
            grid.addWidget(b, i // 2, i % 2)
            b.clicked.connect(lambda _=False, k=key: self.ctl.set("design", k, "Change design"))
        self.design_card.add(grid)
        self.design_extra = QWidget()
        self.n_periods = QSpinBox()
        self.n_periods.setRange(1, 50)
        self.n_periods.valueChanged.connect(lambda v: self.ctl.set("periods_per_subject", v, merge=True))
        self.n_periods_label = label("")
        self.repeats = QSpinBox()
        self.repeats.setRange(2, 10)
        self.repeats.valueChanged.connect(lambda v: self.ctl.set("repeats", v, merge=True))
        self.b2b = QCheckBox("Allow the same treatment in two consecutive {periods}")
        self.b2b.toggled.connect(lambda v: self.ctl.set("back_to_back", v))
        self.incomplete_row = QWidget()
        self.incomplete_row.setLayout(hbox(self.n_periods_label, self.n_periods, None))
        self.replicated_row = QWidget()
        self.replicated_row.setLayout(hbox(label("Times each treatment is given"), self.repeats, 16, self.b2b, None))
        self.design_card.add(self.incomplete_row)
        self.design_card.add(self.replicated_row)
        self.content.addWidget(self.design_card)

        # treatments
        self.trt_card = Card("Treatments", help_key="treatments", terms_fn=tf)
        self.trt = QTableWidget(0, 2)
        self.trt.setHorizontalHeaderLabels(["Name", "Ratio"])
        self.trt.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.trt.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.trt.setColumnWidth(1, 90)
        self.trt.verticalHeader().setDefaultSectionSize(30)
        self.trt.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.trt.itemChanged.connect(self._trt_edited)
        add = button("Add treatment", "plus")
        rem = button("Remove", "trash", flat=True)
        up = button("", "up", flat=True, tip="Move up")
        down = button("", "down", flat=True, tip="Move down")
        add.clicked.connect(self._add)
        rem.clicked.connect(self._remove)
        up.clicked.connect(lambda: self._move(-1))
        down.clicked.connect(lambda: self._move(1))
        self.trt_card.add(hbox(add, rem, up, down, None))
        self.trt_card.add(self.trt)
        self.ratio_hint = label("", "Hint", wrap=True)
        self.trt_card.add(self.ratio_hint)
        self.content.addWidget(self.trt_card)

        # periods
        self.per_card = Card("{Periods}", terms_fn=tf)
        self.per_name = QComboBox()
        self.per_name.setEditable(True)
        self.per_name.addItems(PERIOD_WORDS)
        self.per_name.setMinimumWidth(160)
        self.per_name.lineEdit().editingFinished.connect(self._per_name)
        self.per_name.activated.connect(lambda _: self._per_name())
        self.per_card.add(hbox(label("One step of the schedule is called a"), self.per_name,
                               HelpButton("period_name", tf), None, spacing=6))
        self.per_card.add(hbox(label("Fixed {periods}", "CardTitle"), HelpButton("fixed", tf), None, spacing=6))
        self.fixed_title = self.per_card.outer.itemAt(self.per_card.outer.count() - 1).layout().itemAt(0).widget()
        self.fixed = QTableWidget(0, 2)
        self.fixed.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.fixed.verticalHeader().hide()
        self.fixed.setMaximumHeight(140)
        self.fixed.itemChanged.connect(self._fixed_edited)
        addf = button("Add fixed {period}", "plus")
        self.addf = addf
        remf = button("Remove", "trash", flat=True)
        addf.clicked.connect(self._add_fixed)
        remf.clicked.connect(self._remove_fixed)
        self.per_card.add(hbox(addf, remf, None))
        self.per_card.add(self.fixed)
        self.per_card.add(label("Timeline", "CardTitle"))
        self.timeline = FlowLayout(spacing=6)
        holder = QWidget()
        holder.setLayout(self.timeline)
        self.per_card.add(holder)
        self.timeline_hint = label("", "Hint", wrap=True)
        self.per_card.add(self.timeline_hint)
        self.content.addWidget(self.per_card)
        self.finish()

    # ------------------------------------------------------------------ treatments
    def _rows(self):
        out = []
        for r in range(self.trt.rowCount()):
            name = (self.trt.item(r, 0).text() if self.trt.item(r, 0) else "").strip()
            try:
                ratio = float((self.trt.item(r, 1).text() if self.trt.item(r, 1) else "1").replace(",", "."))
            except ValueError:
                ratio = 1.0
            out.append({"name": name, "ratio": ratio if ratio > 0 else 1.0})
        return out

    def _rename_in_rules(self, old: str, new: str):
        def fix(p):
            s = p.settings
            s["treatments"] = self._rows()
            for key in ("forbidden_transitions", "order_rules"):
                s[key] = [[new if x == old else x for x in r] for r in s[key]]
            s["forbidden_periods"] = [[new if a == old else a, k] for a, k in s["forbidden_periods"]]
        return fix

    def _trt_edited(self, item):
        old = [t["name"] for t in self.s["treatments"]]
        rows = self._rows()
        r = item.row()
        if item.column() == 0 and r < len(old) and old[r] and rows[r]["name"] and old[r] != rows[r]["name"]:
            self.ctl.edit(f"Rename {old[r]}", self._rename_in_rules(old[r], rows[r]["name"]))
        else:
            self.ctl.set("treatments", rows, "Edit treatments")

    def _add(self):
        names = treatment_names(self.s)
        i = len(names) + 1
        while f"Treatment {i}" in names:
            i += 1
        self.ctl.set("treatments", self.s["treatments"] + [{"name": f"Treatment {i}", "ratio": 1.0}], "Add treatment")
        r = self.trt.rowCount() - 1
        self.trt.setCurrentCell(r, 0)
        self.trt.editItem(self.trt.item(r, 0))

    def _remove(self):
        r = self.trt.currentRow()
        if r < 0:
            return
        rows = list(self.s["treatments"])
        gone = rows.pop(r)["name"]

        def fn(p):
            s = p.settings
            s["treatments"] = rows
            for key in ("forbidden_transitions", "order_rules"):
                s[key] = [x for x in s[key] if gone not in x]
            s["forbidden_periods"] = [x for x in s["forbidden_periods"] if x[0] != gone]
        self.ctl.edit(f"Remove {gone}", fn)

    def _move(self, d):
        r = self.trt.currentRow()
        rows = list(self.s["treatments"])
        if r < 0 or not 0 <= r + d < len(rows):
            return
        rows[r], rows[r + d] = rows[r + d], rows[r]
        self.ctl.set("treatments", rows, "Reorder treatments")
        self.trt.setCurrentCell(r + d, 0)

    # ------------------------------------------------------------------ periods
    def _per_name(self):
        from .subjects import set_word
        set_word(self.ctl, "period_name", self.per_name.currentText())       # kept as typed

    def _fixed_rows(self):
        out = []
        for r in range(self.fixed.rowCount()):
            try:
                k = int((self.fixed.item(r, 0).text() if self.fixed.item(r, 0) else "").strip())
            except ValueError:
                k = None
            lab = (self.fixed.item(r, 1).text() if self.fixed.item(r, 1) else "").strip()
            out.append({"period": k, "label": lab})
        return out

    def _fixed_edited(self, _):
        self.ctl.set("fixed", self._fixed_rows(), "Edit fixed periods")

    def _add_fixed(self):
        n = randomized_count(self.s) + len(self.s["fixed"]) + 1
        self.ctl.set("fixed", self.s["fixed"] + [{"period": n, "label": "MAX"}], "Add fixed period")

    def _remove_fixed(self):
        r = self.fixed.currentRow()
        if r < 0:
            return
        rows = list(self.s["fixed"])
        rows.pop(r)
        self.ctl.set("fixed", rows, "Remove fixed period")

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        super().refresh()
        s, t = self.s, self.terms()
        self.per_card.title_label.setText(t["Periods"])
        self.fixed_title.setText(f"Fixed {t['periods']}")
        self.addf.setText(f"Add fixed {t['period']}")
        self.b2b.setText(f"Allow the same treatment in two consecutive {t['periods']}")
        for key, b in self.design_buttons.items():
            b.d.setText(fmt(DESIGNS[key][1].replace("{one}", t["one"]).replace("{period}", t["period"]), t))
            with quiet(b):
                b.setChecked(key == s["design"])
        design = s["design"]
        names = treatment_names(s)
        self.incomplete_row.setVisible(design == "incomplete")
        self.replicated_row.setVisible(design == "replicated")
        self.n_periods_label.setText(f"Treatments per {t['one']}")
        with quiet(self.n_periods, self.repeats, self.b2b):
            self.n_periods.setRange(1, max(1, len(names) - 1))
            self.n_periods.setValue(int(s.get("periods_per_subject", 2)))
            self.repeats.setValue(int(s.get("repeats", 2)))
            self.b2b.setChecked(bool(s.get("back_to_back")))
        # treatment table
        rows = s["treatments"]
        if self._rows() != rows or self.trt.rowCount() != len(rows):
            with quiet(self.trt):
                cur = self.trt.currentRow()
                self.trt.setRowCount(len(rows))
                for r, row in enumerate(rows):
                    self.trt.setItem(r, 0, QTableWidgetItem(str(row["name"])))
                    it = QTableWidgetItem(f"{float(row.get('ratio', 1)):g}")
                    it.setTextAlignment(Qt.AlignCenter)
                    self.trt.setItem(r, 1, it)
                if 0 <= cur < len(rows):
                    self.trt.setCurrentCell(cur, 0)
        self.trt.setFixedHeight(min(10, max(3, len(rows))) * 30 + 36)
        ratio = design in ("parallel", "incomplete")
        self.trt.setColumnHidden(1, not ratio)
        self.ratio_hint.setText("Ratio: how often each treatment is used relative to the others (1 = equal)."
                                if ratio else "")
        self.ratio_hint.setVisible(ratio)
        # period name
        with quiet(self.per_name):
            if self.per_name.currentText() != s["period_name"]:
                self.per_name.setCurrentText(s["period_name"])
        # fixed
        self.fixed.setHorizontalHeaderLabels([f"{t['period_cap']} number", "Label (e.g. MAX, Baseline)"])
        fx = s["fixed"]
        if self._fixed_rows() != [{"period": f.get("period"), "label": f.get("label", "")} for f in fx]:
            with quiet(self.fixed):
                self.fixed.setRowCount(len(fx))
                for r, f in enumerate(fx):
                    self.fixed.setItem(r, 0, QTableWidgetItem("" if f.get("period") is None else str(f["period"])))
                    self.fixed.setItem(r, 1, QTableWidgetItem(str(f.get("label", ""))))
        self.fixed.setVisible(bool(fx))
        # timeline
        self.timeline.clear()
        n_rand = randomized_count(s)
        fixed = {}
        for f in fx:
            try:
                if str(f.get("label", "")).strip():
                    fixed[int(f["period"])] = f["label"]
            except (TypeError, ValueError):
                pass
        total = n_rand + len(fixed)
        for k in range(1, total + 1):
            if k in fixed:
                self.timeline.addWidget(Chip(f"{t['period_cap']} {k} · {fixed[k]}", "fixed"))
            else:
                self.timeline.addWidget(Chip(f"{t['period_cap']} {k} · random"))
        bad = [k for k in fixed if not 1 <= k <= total]
        self.timeline_hint.setText(
            (f"{total} {t['periods'] if total != 1 else t['period']} in total: {n_rand} randomized" + (f", {len(fixed)} fixed." if fixed else "."))
            + (f"  Fixed {t['period']} {bad[0]} is outside 1–{total}." if bad else ""))
