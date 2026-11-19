from __future__ import annotations

import copy

import pandas as pd
from PySide6.QtCore import QDate, QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit, QFileDialog, QFrame, QGridLayout,
                               QHeaderView, QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QMessageBox, QScrollArea, QSpinBox, QTabWidget, QTextEdit, QToolButton,
                               QVBoxLayout, QWidget)

from randomizer import diagnostics as dg
from randomizer import export, plots
from randomizer.dates import check as cal_check, dated_schedule, parse_date

from .. import icons, theme
from ..dialogs import (CITATION, CompareDialog, ExportDialog, ExtendDialog, LabelsDialog, ReplaceDialog,
                       safe_name, show_files)
from ..progress import ProgressDialog
from ..widgets import (clear_layout, discard, Banner, Card, DataFrameModel, DataTable, HelpButton, Pill, button, hbox, label, vbox)
from .base import quiet


def table_for(df: pd.DataFrame, formats=None, max_rows=14, index=False) -> DataTable:
    if index:
        df = df.reset_index().rename(columns={"index": ""})
    m = DataFrameModel(df)
    m.formats = formats or {}
    v = DataTable(m)
    v.verticalHeader().hide()
    hdr = v.horizontalHeader()
    hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
    short = max((len(str(c)) for c in df.columns), default=0) <= 14
    if len(df.columns) <= 8 and short:          # small numeric tables: spread the columns evenly
        for i in range(1, len(df.columns)):
            hdr.setSectionResizeMode(i, QHeaderView.Stretch)
    else:
        hdr.setStretchLastSection(True)
    v.setFixedHeight(min(max_rows, len(df)) * 28 + 36 + (16 if len(df.columns) > 8 else 0))
    return v


def scroll_of(widget) -> QScrollArea:
    sc = QScrollArea()
    sc.setWidgetResizable(True)
    sc.setFrameShape(QFrame.NoFrame)
    sc.setWidget(widget)
    return sc


class RunItem(QWidget):
    def __init__(self, run, many):
        super().__init__()
        res_status = "optimal" if run.result.get("proven_optimal") else "time limit"
        top = hbox(label(run.id, "CardTitle"), spacing=6)
        if run.final:
            top.addWidget(Pill("FINAL", "final"))
        if run.kind == "extension":
            top.addWidget(Pill(f"+{many}", "info"))
        if run.kind == "replacement":
            top.addWidget(Pill("replacement", "info"))
        top.addStretch(1)
        lay = vbox(top, label(run.created.replace("T", " ")[:16] + f" · {res_status}", "Hint"),
                   spacing=2, margins=(6, 6, 6, 6))
        if run.note:
            n = label(run.note, "Muted", wrap=True)
            lay.addWidget(n)
        self.setLayout(lay)


class ResultsPage(QWidget):
    step = "results"
    retry = Signal()

    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setObjectName("Page")
        self.run = None
        self._pictures_for = None

        # ---------------- left: runs
        left = QFrame()
        left.setObjectName("Card")
        left.setFixedWidth(250)
        self.runs = QListWidget()
        self.runs.setFrameShape(QFrame.NoFrame)
        self.runs.setStyleSheet("QListWidget { border: none; background: transparent; }")
        self.runs.currentRowChanged.connect(self._select)
        cmp_btn = button("Compare runs", "compare")
        cmp_btn.clicked.connect(lambda: CompareDialog(self.ctl.project, self).exec())
        self.cmp_btn = cmp_btn
        left.setLayout(vbox(label("Runs", "CardTitle"), self.runs, cmp_btn, spacing=8, margins=(12, 14, 12, 12)))

        # ---------------- right: header and actions
        self.title = label("", "PageTitle")
        self.final_pill = Pill("FINAL", "final")
        self.fp = label("", "Mono")
        self.fp.setTextInteractionFlags(Qt.TextSelectableByMouse)
        fp_copy = button("", "copy", flat=True, tip="Copy fingerprint")
        fp_copy.clicked.connect(lambda: QApplication.clipboard().setText(self.run.fingerprint if self.run else ""))
        self.final_btn = button("Mark as final", "lock")
        self.final_btn.clicked.connect(self._toggle_final)
        export_btn = button("Export…", "download", primary=True)
        export_btn.clicked.connect(self.export)
        more = QToolButton()
        more.setText("More")
        more.setPopupMode(QToolButton.InstantPopup)
        more.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        more.setIcon(icons.icon("list"))
        self.more_menu = QMenu(more)
        self.act_verify = self.more_menu.addAction(icons.icon("check-circle"), "Verify (re-create from seed)", self._verify)
        self.act_extend = self.more_menu.addAction(icons.icon("user-plus"), "Add subjects…", self._extend)
        self.act_replace = self.more_menu.addAction(icons.icon("swap"), "Replace a dropout…", self._replace)
        self.more_menu.addSeparator()
        self.more_menu.addAction(icons.icon("refresh"), "Use the settings of this run", self._use_settings)
        self.act_delete = self.more_menu.addAction(icons.icon("trash"), "Delete this run", self._delete)
        more.setMenu(self.more_menu)
        header = hbox(self.title, self.final_pill, 12, icons_label("fingerprint"), self.fp, fp_copy,
                      HelpButton("fingerprint", self.terms), None, self.final_btn,
                      HelpButton("final", self.terms), more, export_btn, spacing=6)
        self.status = Banner("ok", "")
        self.status_retry = button("Retry with more time", "refresh")
        self.status_retry.clicked.connect(self.retry.emit)
        self.status.extra.addWidget(self.status_retry)
        self.note_label = label("", "Hint", wrap=True)

        # ---------------- tabs
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.currentChanged.connect(self._tab_changed)
        self.overview = QWidget()
        self.overview_lay = vbox(spacing=8, margins=(2, 12, 2, 12))
        self.overview.setLayout(self.overview_lay)
        self.tabs.addTab(scroll_of(self.overview), "Overview")

        sched = QWidget()
        self.show_codes = QCheckBox("Show blinding codes instead of treatment names")
        self.show_codes.toggled.connect(lambda _: self._fill_schedule())
        self.sched_model = DataFrameModel()
        self.sched_view = DataTable(self.sched_model)
        sched.setLayout(vbox(self.show_codes, self.sched_view, spacing=8, margins=(2, 12, 2, 2)))
        self.tabs.addTab(sched, "Schedule")

        self.balance = QWidget()
        self.balance_lay = vbox(spacing=10, margins=(2, 12, 2, 12))
        self.balance.setLayout(self.balance_lay)
        self.tabs.addTab(scroll_of(self.balance), "Balance")

        pics = QWidget()
        self.pic_unit = QComboBox()
        self.pic_unit.activated.connect(lambda _: self._fill_pictures(force=True))
        self.pic_lay = vbox(spacing=12, margins=(0, 0, 0, 0))
        self.pic_holder = QWidget()
        self.pic_holder.setLayout(self.pic_lay)
        self.pic_dpi = QSpinBox()
        self.pic_dpi.setRange(72, 1200)
        self.pic_dpi.setSingleStep(50)
        self.pic_dpi.setSuffix(" dpi")
        self.pic_dpi.setToolTip("Resolution of the pictures, here and in exports.")
        self.pic_dpi.editingFinished.connect(self._dpi_changed)
        pics.setLayout(vbox(hbox(label("Show"), self.pic_unit, 16, label("Resolution"), self.pic_dpi, None),
                            scroll_of(self.pic_holder),
                            spacing=8, margins=(2, 12, 2, 2)))
        self.tabs.addTab(pics, "Pictures")

        self.calendar = self._build_calendar()
        self.tabs.addTab(scroll_of(self.calendar), "Calendar")

        methods = QWidget()
        self.methods = QTextEdit()
        self.methods.setReadOnly(True)
        copy_m = button("Copy methods text", "copy", primary=True)
        copy_m.clicked.connect(lambda: QApplication.clipboard().setText(self.methods.toPlainText()))
        copy_c = button("Copy citation", "copy")
        copy_c.clicked.connect(lambda: QApplication.clipboard().setText(CITATION))
        methods.setLayout(vbox(label("A ready-to-paste paragraph for the methods section of a paper or protocol.",
                                     "Hint"), self.methods, hbox(copy_m, copy_c, None), spacing=8,
                               margins=(2, 12, 2, 2)))
        self.tabs.addTab(methods, "Methods text")

        hist = QWidget()
        self.log_model = DataFrameModel()
        self.log_view = DataTable(self.log_model)
        hist.setLayout(vbox(label("Everything that happened in this project, oldest first. Included in "
                                  "Excel exports.", "Hint"), self.log_view, spacing=8, margins=(2, 12, 2, 2)))
        self.tabs.addTab(hist, "History")

        right = QWidget()
        right.setLayout(vbox(header, self.status, self.note_label, self.tabs, spacing=10, margins=(0, 0, 0, 0)))
        self.empty = vbox(label("No schedules yet", "PageTitle"),
                          label("Generate a schedule on the Generate page. Every run is kept here.", "PageLead"),
                          None, margins=(0, 0, 0, 0))
        self.empty_w = QWidget()
        self.empty_w.setLayout(self.empty)
        lay = hbox(left, right, self.empty_w, spacing=18, margins=(24, 22, 28, 22))
        lay.setStretch(1, 1)
        lay.setStretch(2, 1)
        self.setLayout(lay)
        self.right, self.left = right, left

    # ------------------------------------------------------------------ helpers
    def terms(self):
        from ..widgets import terms
        return terms(self.ctl.project.settings)

    @property
    def project(self):
        return self.ctl.project

    def refresh(self):
        """Settings changed (wording, calendar...)."""
        if self.run is not None:
            self._fill_calendar_form()
            self._fill_log()

    def refresh_runs(self, select: str | None = None):
        p = self.project
        cur = select or (self.run.id if self.run and p.run(self.run.id) else None)
        with quiet(self.runs):
            self.runs.clear()
            for r in reversed(p.runs):
                it = QListWidgetItem()
                w = RunItem(r, self.terms()["many"])
                w.adjustSize()
                it.setSizeHint(QSize(200, w.sizeHint().height() + 8))
                it.setData(Qt.UserRole, r.id)
                self.runs.addItem(it)
                self.runs.setItemWidget(it, w)
        has = bool(p.runs)
        self.left.setVisible(has)
        self.right.setVisible(has)
        self.empty_w.setVisible(not has)
        self.cmp_btn.setEnabled(len(p.runs) > 1)
        if not has:
            self.run = None
            return
        ids = [self.runs.item(i).data(Qt.UserRole) for i in range(self.runs.count())]
        row = ids.index(cur) if cur in ids else 0
        self.runs.setCurrentRow(row)
        self._select(row)

    def _select(self, row):
        if row < 0:
            return
        rid = self.runs.item(row).data(Qt.UserRole)
        self.run = self.project.run(rid)
        self.run.invalidate()
        self._pictures_for = None
        self._fill()

    # ------------------------------------------------------------------ fill
    def _fill(self):
        run, t = self.run, self.terms()
        res = run.view()
        self.title.setText(run.id)
        self.final_pill.setVisible(run.final)
        self.fp.setText(run.fingerprint)
        self.final_btn.setText("Remove final mark" if run.final else "Mark as final")
        self.final_btn.setIcon(icons.icon("unlock" if run.final else "lock"))
        self.act_delete.setEnabled(not run.final)
        self.act_extend.setText(f"Add {t['many']}…")
        self.act_extend.setEnabled(not run.cluster)
        self.act_replace.setText(f"Replace a {t['one']} who dropped out…")
        if res.proven_optimal:
            self.status.set("ok", "Proven best: each balance criterion is as close to its ideal as your rules "
                                  "allow, taken one at a time in order of priority.")
            self.status_retry.hide()
        else:
            self.status.set("warning", f"Stopped at the time limit ({res.spec.time_limit:.0f} s). This is the best "
                                       f"schedule found; more time may improve balance.")
            self.status_retry.show()
        bits = [f"Seed {res.spec.seed}", f"solved in {res.solve_seconds:.0f} s", run.created.replace("T", " ")]
        if run.parent:
            bits.append(f"based on {run.parent}")
        if run.note:
            bits.append(f"note: {run.note}")
        self.note_label.setText(" · ".join(bits))
        self.show_codes.setVisible(bool(res.codes))
        self._fill_overview(res)
        self._fill_schedule()
        self._fill_balance(res)
        self._fill_calendar_form()
        self.methods.setPlainText(export.methods_text(res))
        self._fill_log()
        units = [(u.name, i) for i, u in enumerate(res.units) if u.kind != "block"]
        with quiet(self.pic_unit):
            self.pic_unit.clear()
            for name, i in units:
                self.pic_unit.addItem(name, i)
        if self.tabs.currentIndex() == 3:
            self._fill_pictures()

    def _fill_overview(self, res):
        lay = self.overview_lay
        clear_layout(lay)
        tk = theme.tokens()
        for w in res.warnings or []:
            lay.addWidget(Banner("warning", w))
        card = Card("Checks")
        for c in dg.checks(res):
            spread = c.name.startswith("Spread")
            name, color = ("check-circle", tk["ok"]) if c.ok else (("info", tk["muted"]) if spread else ("alert", tk["warn"]))
            ic = QLabel()
            ic.setPixmap(icons.pixmap(name, 18, color))
            txt = label(f"<b>{c.name}.</b> {c.detail}", wrap=True)
            row = hbox(ic, txt, spacing=10)
            row.setAlignment(ic, Qt.AlignTop)
            row.setStretch(1, 1)
            card.add(row)
        info = res.randomization or {}
        outcomes = export.check_outcomes_text(res)
        if outcomes:
            ic = QLabel()
            ic.setPixmap(icons.pixmap("info", 18, tk["info"]))
            row = hbox(ic, label(f"<b>Before optimizing.</b> {outcomes}.", wrap=True), spacing=10)
            row.setAlignment(ic, Qt.AlignTop)
            row.setStretch(1, 1)
            card.add(row)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("dice", 18, tk["info"]))
        row = hbox(ic, label(f"<b>Final choice.</b> {export.choice_text(res)}.", wrap=True), spacing=10)
        row.setStretch(1, 1)
        card.add(row)
        lay.addWidget(card)
        if res.spec.adjacent_pairs:
            pr = dg.predictability(res)
            overall = pr.iloc[-1]["Best-guess accuracy"]
            floor = dg.guess_floor(res)
            c2 = Card("How predictable is the next treatment?")
            low = ("This is the lowest possible for these numbers and rules." if overall <= floor + 1e-9
                   else f"No schedule with these numbers and rules can go below about {floor:.0%}.")
            c2.add(label(f"Someone who knows this schedule and always guesses the most common next treatment "
                         f"would be right <b>{overall:.0%}</b> of the time. {low}", wrap=True))
            ex = dg.full_list_exposure(res)
            if ex is not None and ex["group_aware"] >= 0.999:
                grp = " and knows which group a {one} is in" if any(u.kind == "group" for u in res.units) else ""
                c2.add(Banner("warning", ("Anyone who sees the full list{grp} can tell each {one}'s remaining "
                                          "treatments after the first two {periods}. Keep the list away from the "
                                          "people who test or score {many}, or set the full-list criterion "
                                          "to Preferred.").replace("{grp}", grp).format(**self.terms())))
            elif ex is not None and ex["group_aware"] >= 0.8:
                c2.add(label(f"Someone who holds the full list would guess the third treatment correctly "
                             f"{ex['group_aware']:.0%} of the time after seeing the first two; keep the list "
                             f"away from the people who test.", "Hint", wrap=True))
            lay.addWidget(c2)
        if res.notes:
            c3 = Card("Notes")
            for n in res.notes:
                c3.add(label(n, wrap=True))
            lay.addWidget(c3)
        lay.addStretch(1)
        del info

    def _fill_schedule(self):
        if not self.run:
            return
        res = self.run.view()
        colors = plots.treatment_colors(res.spec)
        if self.show_codes.isChecked() and res.codes:
            df = export.blinded_schedule(res)
            colors = {**colors, **{code: colors.get(name, ("#ffffff", "#000000")) for name, code in res.codes.items()}}
        else:
            df = res.schedule
        self.sched_model.set_frame(df, colors, res.period_columns)
        hdr = self.sched_view.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeToContents)
        self.sched_view.resizeColumnsToContents()

    def _fill_balance(self, res):
        lay = self.balance_lay
        clear_layout(lay)
        t = self.terms()
        pct = {"Best-guess accuracy": "{:.0%}", "Mutual information (bits)": "{:.3f}"}
        c = Card("Balance in each group", hint="'Unit' is a set of " + t["many"] + " over which balance is counted.")
        c.add(table_for(dg.unit_summary(res), pct))
        lay.addWidget(c)
        unit = QComboBox()
        for i, u in enumerate(res.units):
            unit.addItem(u.name, i)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 0, 0)

        def show(_=None):
            clear_layout(hl)
            ui = unit.currentData() or 0
            per = res.spec.period()
            c1 = Card(f"Treatments in each {per}")
            c1.add(table_for(dg.period_table(res, ui), index=True))
            hl.addWidget(c1)
            if res.spec.adjacent_pairs and res.units[ui].kind != "block":
                c2 = Card("Carry-over: row treatment directly followed by column treatment")
                c2.add(table_for(dg.transition_table(res, ui), index=True))
                hl.addWidget(c2)
        unit.currentIndexChanged.connect(show)
        lay.addLayout(hbox(label("Details for"), unit, None))
        lay.addWidget(holder)
        show()
        if res.spec.adjacent_pairs:
            c3 = Card(f"Predictability of the next treatment, per {res.spec.period()} change")
            c3.add(table_for(dg.predictability(res), pct))
            lay.addWidget(c3)
        c4 = Card("Sequences used")
        c4.add(table_for(dg.sequence_table(res), max_rows=12))
        lay.addWidget(c4)
        lay.addStretch(1)

    def _tab_changed(self, i):
        if i == 3:
            self._fill_pictures()

    def _fill_pictures(self, force=False):
        if not self.run:
            return
        dpi = int(self.project.settings.get("picture_dpi", 300))
        with quiet(self.pic_dpi):
            self.pic_dpi.setValue(dpi)
        key = (self.run.id, self.pic_unit.currentData(), dpi)
        if key == self._pictures_for and not force:
            return
        self._pictures_for = key
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            clear_layout(self.pic_lay)
            res = self.run.view()
            ui = self.pic_unit.currentData() or 0
            figs = [plots.schedule_figure(res), plots.period_balance_figure(res, ui)]
            if res.spec.adjacent_pairs:
                figs += [plots.carryover_figure(res, ui), plots.changes_figure(res, ui)]
            for fig in figs:
                pm = QPixmap()
                d = plots.screen_dpi(fig, dpi)
                pm.loadFromData(plots.figure_png(fig, dpi=d))
                pm.setDevicePixelRatio(d / 100)          # always shown at 100 px per inch, sharper with more dpi
                lab = QLabel()
                lab.setPixmap(pm)
                lab.setAlignment(Qt.AlignLeft)
                box = QFrame()
                box.setStyleSheet(f"background: {plots.SURFACE}; border-radius: 10px;")
                box.setLayout(vbox(lab, margins=(14, 14, 14, 14)))
                self.pic_lay.addWidget(box)
            self.pic_lay.addStretch(1)
        finally:
            QApplication.restoreOverrideCursor()

    def _dpi_changed(self):
        v = self.pic_dpi.value()
        if v != int(self.project.settings.get("picture_dpi", 300)):
            self.ctl.set("picture_dpi", v, "Change picture resolution")
            self._fill_pictures(force=True)

    def _fill_log(self):
        log = pd.DataFrame(self.project.log or [], columns=["time", "event", "detail"])
        log.columns = ["Time", "Event", "Details"]
        log["Time"] = log["Time"].astype(str).str.replace("T", " ")
        self.log_model.set_frame(log)
        self.log_view.resizeColumnsToContents()
        self.log_view.horizontalHeader().setStretchLastSection(True)

    # ------------------------------------------------------------------ calendar tab
    def _build_calendar(self) -> QWidget:
        w = QWidget()
        card = Card("Dates", help_key="calendar", terms_fn=self.terms)
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.cal_start = QDateEdit()
        self.cal_start.setCalendarPopup(True)
        self.cal_start.setDisplayFormat("ddd d MMM yyyy")
        self.cal_start.setDate(QDate.currentDate())
        self.cal_use = QCheckBox("Everyone starts on")
        self.cal_col = QComboBox()
        self.cal_days = QSpinBox()
        self.cal_days.setRange(1, 365)
        self.cal_days.setSuffix(" days")
        self.cal_skip = QCheckBox("Move dates that fall on a weekend or holiday to the next working day")
        self.cal_hol = QLineEdit()
        self.cal_hol.setPlaceholderText("Holidays, e.g. 2026-12-24, 2026-12-25, 2027-01-01")
        g.addWidget(self.cal_use, 0, 0)
        g.addWidget(self.cal_start, 0, 1)
        self.cal_col_label = label("")
        g.addWidget(self.cal_col_label, 1, 0)
        g.addWidget(self.cal_col, 1, 1)
        self.cal_between_label = label("")
        g.addWidget(self.cal_between_label, 2, 0)
        g.addWidget(self.cal_days, 2, 1)
        g.addWidget(self.cal_skip, 3, 0, 1, 3)
        g.addWidget(label("Holidays"), 4, 0)
        g.addWidget(self.cal_hol, 4, 1, 1, 2)
        g.setColumnStretch(2, 1)
        card.add(g)
        self.cal_msg = Banner("info", "")
        card.add(self.cal_msg)
        set_cal = self.ctl.set
        self.cal_use.toggled.connect(lambda on: set_cal(
            "calendar.start_date", self.cal_start.date().toString("yyyy-MM-dd") if on else "", "Change start date"))
        self.cal_start.dateChanged.connect(lambda d: self.cal_use.isChecked() and set_cal(
            "calendar.start_date", d.toString("yyyy-MM-dd"), "Change start date", merge=True))
        self.cal_col.activated.connect(lambda _: set_cal("calendar.start_column", self.cal_col.currentData() or "",
                                                         "Change start date column"))
        self.cal_days.valueChanged.connect(lambda v: set_cal("calendar.days_between", v, "Change interval", merge=True))
        self.cal_skip.toggled.connect(lambda on: set_cal("calendar.skip_weekends", on, "Toggle weekends"))
        self.cal_hol.editingFinished.connect(self._holidays)

        out = Card("Daily sheets and labels")
        self.day_pick = QComboBox()
        self.day_pick.setMinimumWidth(220)
        self.day_pick.currentIndexChanged.connect(self._show_day)
        self.day_blind = QCheckBox("Codes only (for blinded experimenters)")
        self.day_blind.toggled.connect(lambda _: self._fill_days())
        pdf = button("Daily sheets PDF…", "printer", primary=True)
        pdf.clicked.connect(self._daily_pdf)
        prn = button("Print…", "printer")
        prn.clicked.connect(self._daily_print)
        lab = button("Labels PDF…", "tag")
        lab.clicked.connect(self._labels)
        out.add(hbox(label("Day"), self.day_pick, self.day_blind, None))
        self.day_model = DataFrameModel()
        self.day_view = DataTable(self.day_model)
        self.day_view.setMinimumHeight(240)
        out.add(self.day_view)
        out.add(hbox(pdf, prn, lab, None))
        self.cal_out = out
        w.setLayout(vbox(card, out, None, spacing=14, margins=(2, 12, 2, 12)))
        return w

    def _holidays(self):
        parts = [p.strip() for p in self.cal_hol.text().replace(";", ",").split(",") if p.strip()]
        dates = [parse_date(p) for p in parts]
        if any(d is None for d in dates):
            self.cal_msg.set("error", "Some holiday dates could not be read. Use the form 2026-12-24.")
            self.cal_msg.show()
            return
        self.ctl.set("calendar.holidays", [d.isoformat() for d in dates], "Change holidays")

    def _fill_calendar_form(self):
        if not self.run:
            return
        cal, t = self.project.settings["calendar"], self.terms()
        res = self.run.view()
        d = parse_date(cal.get("start_date"))
        with quiet(self.cal_use, self.cal_start, self.cal_col, self.cal_days, self.cal_skip):
            self.cal_use.setChecked(d is not None)
            if d:
                self.cal_start.setDate(QDate(d.year, d.month, d.day))
            self.cal_col.clear()
            self.cal_col.addItem("— (not used)", "")
            for c in res.schedule.columns:
                if c not in res.period_columns and c not in ("Block", "Status", res.spec.id_column):
                    self.cal_col.addItem(str(c), str(c))
            self.cal_col.setCurrentIndex(max(0, self.cal_col.findData(cal.get("start_column", ""))))
            self.cal_days.setValue(int(cal.get("days_between", 7)))
            self.cal_skip.setChecked(bool(cal.get("skip_weekends", True)))
        self.cal_start.setEnabled(d is not None)
        self.cal_col_label.setText(f"Or each {t['one']}'s own start date, from column")
        self.cal_between_label.setText(f"Days between {t['periods']}")
        if not self.cal_hol.hasFocus():
            self.cal_hol.setText(", ".join(cal.get("holidays", [])))
        self.day_blind.setVisible(bool(res.codes))
        problems = cal_check(cal, res)
        if problems:
            self.cal_msg.set("info", " ".join(problems))
            self.cal_msg.show()
        else:
            self.cal_msg.hide()
        self.cal_out.setEnabled(not problems)
        self._fill_days()

    def _fill_days(self):
        cal = self.project.settings["calendar"]
        res = self.run.view()
        if cal_check(cal, res):
            self._dated = None
            with quiet(self.day_pick):
                self.day_pick.clear()
            self.day_model.set_frame(pd.DataFrame())
            return
        self._dated = dated_schedule(res, cal, blinded=self.day_blind.isChecked() and bool(res.codes))
        days = sorted(d for d in self._dated["Date"].dropna().unique())
        cur = self.day_pick.currentData()
        with quiet(self.day_pick):
            self.day_pick.clear()
            self.day_pick.addItem(f"All days ({len(days)})", None)
            for d in days:
                n = int((self._dated["Date"] == d).sum())
                self.day_pick.addItem(f"{d:%a %d %b %Y} · {n}", d)
            i = self.day_pick.findData(cur)
            self.day_pick.setCurrentIndex(max(0, i))
        self._show_day()

    def _show_day(self, _=None):
        if self._dated is None:
            return
        d = self.day_pick.currentData()
        df = self._dated if d is None else self._dated[self._dated["Date"] == d]
        res = self.run.view()
        colors = plots.treatment_colors(res.spec)
        if res.codes:
            colors.update({code: colors.get(n, ("#fff", "#000")) for n, code in res.codes.items()})
        self.day_model.set_frame(df.reset_index(drop=True), colors, [c for c in ("Treatment", "Code") if c in df])
        self.day_view.resizeColumnsToContents()

    def _pdf_path(self, what):
        base = (self.project.path and str(__import__("pathlib").Path(self.project.path).parent)) or ""
        name = f"{safe_name(self.project.name)}_{self.run.id}_{what}.pdf"
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", str(__import__("pathlib").Path(base) / name),
                                              "PDF (*.pdf)")
        return path

    def _daily_pdf(self):
        from .. import printing
        path = self._pdf_path("daily_sheets" + ("_BLINDED" if self.day_blind.isChecked() else ""))
        if not path:
            return
        printing.daily_sheets_pdf(self.run.view(), self.project.settings["calendar"], path,
                                  self.day_blind.isChecked() and bool(self.run.view().codes), self.project.name)
        self.project.event("Daily sheets saved", f"{self.run.id}: {path}")
        self.ctl.runs_edited(autosave=True)
        show_files(self, [path], "Daily sheets saved")

    def _daily_print(self):
        from PySide6.QtPrintSupport import QPrintDialog, QPrinter
        from .. import printing
        printer = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(printer, self).exec():
            printing.print_html(printer, printing.daily_sheets_html(
                self.run.view(), self.project.settings["calendar"],
                self.day_blind.isChecked() and bool(self.run.view().codes), self.project.name))

    def _labels(self):
        from .. import printing
        res = self.run.view()
        cal = self.project.settings["calendar"]
        has_dates = not cal_check(cal, res)
        dlg = LabelsDialog(bool(res.codes), has_dates, self)
        if not dlg.exec():
            return
        path = self._pdf_path("labels")
        if not path:
            return
        texts = printing.label_texts(res, cal if has_dates else None, dlg.blinded.isChecked(),
                                     dlg.per_period.isChecked())
        printing.labels_pdf(texts, path, dlg.layouts[dlg.layout_box.currentIndex()], dlg.outline.isChecked(),
                            f"{self.project.name} labels")
        self.project.event("Labels saved", f"{self.run.id}: {len(texts)} labels")
        self.ctl.runs_edited(autosave=True)
        show_files(self, [path], "Labels saved")

    # ------------------------------------------------------------------ actions
    def export(self):
        if not self.run:
            return
        dlg = ExportDialog(self.project, self.run, self)
        if not dlg.exec():
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            paths = dlg.export()
        except OSError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Export failed", f"The files could not be written:\n{e}\n\nIf one is open "
                                                       f"in Excel, close it and try again.")
            return
        QApplication.restoreOverrideCursor()
        self.project.event("Exported", f"{self.run.id}: {', '.join(p.name for p in paths)}")
        self.ctl.runs_edited()
        show_files(self, paths)

    def _toggle_final(self):
        run = self.run
        if run.final:
            reason, ok = QInputDialog.getText(self, "Remove final mark",
                                              "Why is this schedule no longer final? (kept in the history)")
            if not ok or not reason.strip():
                return
            self.project.unmark_final(reason.strip())
        else:
            old = self.project.final_run
            msg = (f"Mark {run.id} as the final schedule?\n\nIt will be locked: it cannot be deleted, and its "
                   f"fingerprint {run.fingerprint} identifies it.")
            if old:
                msg += f"\n\n{old.id} is final now and will lose the mark."
            if QMessageBox.question(self, "Mark as final", msg) != QMessageBox.Yes:
                return
            self.project.mark_final(run.id)
        self.ctl.runs_edited()
        self.refresh_runs(run.id)

    def _verify(self):
        from randomizer.project import df_from_json, fingerprint, result_to_dict
        run = self.run
        spec = run.solver_spec()
        dlg = ProgressDialog(spec, f"Verifying {run.id}", self)
        dlg.exec()
        if dlg.kind != "done":
            if dlg.kind == "failed":
                QMessageBox.warning(self, "Verify", dlg.payload)
            return
        fp = fingerprint(df_from_json(result_to_dict(dlg.payload)["schedule"]))
        same = fp == run.raw_fingerprint
        run.verifications.append({"fingerprint": fp, "same": same})
        self.project.event("Verified" if same else "Verification differed", f"{run.id}: {fp} vs {run.raw_fingerprint}")
        self.ctl.runs_edited()
        if same:
            QMessageBox.information(self, "Verified", f"The same settings and seed re-create {run.id} exactly.")
        else:
            QMessageBox.warning(self, "Different result",
                                f"Re-running gave a different schedule. This happens when the solver stops at "
                                f"the time limit, because it then depends on computer speed. The saved "
                                f"schedule ({run.fingerprint}) remains the record.")

    def _extend(self):
        from ..widgets import terms as T
        run = self.run
        dlg = ExtendDialog(self.project, run, self)
        if not dlg.exec():
            return
        new = dlg.new_subjects()
        t = T(self.project.settings)
        if new.empty:
            return
        try:
            spec = self.project.extension_spec(run.id, new, seed=dlg.seed.value())
            spec.time_limit = float(dlg.limit.value())
            from randomizer.spec import validate
            errors, _ = validate(spec)
            if errors:
                raise ValueError("\n".join(errors))
        except ValueError as e:
            QMessageBox.warning(self, f"Add {t['many']}", str(e))
            return
        pd_ = ProgressDialog(spec, f"Adding {len(new)} {t['many']}", self)
        pd_.exec()
        if pd_.kind == "failed":
            QMessageBox.warning(self, f"Add {t['many']}", pd_.payload)
            return
        if pd_.kind != "done":
            return
        new_run = self.project.add_run(pd_.payload, kind="extension", parent=run.id,
                                       note=f"{len(new)} {t['many']} added", replacements=run.replacements,
                                       settings=run.settings)
        self.ctl.runs_edited()
        self.refresh_runs(new_run.id)

    def _replace(self):
        dlg = ReplaceDialog(self.project, self.run, self)
        if not dlg.exec():
            return
        try:
            new = self.project.replacement_run(self.run.id, dlg.old.currentText(), dlg.new.text().strip(),
                                               dlg.note.text().strip())
        except ValueError as e:
            QMessageBox.warning(self, "Replace", str(e))
            return
        self.ctl.runs_edited()
        self.refresh_runs(new.id)

    def _use_settings(self):
        run = self.run
        if QMessageBox.question(self, "Use these settings", f"Copy all settings of {run.id} (including the seed) "
                                                            f"to the project? You can undo this.") != QMessageBox.Yes:
            return
        st = copy.deepcopy(run.settings)
        self.ctl.edit(f"Use settings of {run.id}", lambda p: p.settings.update(st))

    def _delete(self):
        run = self.run
        if QMessageBox.question(self, "Delete run", f"Delete {run.id}? This cannot be undone.") != QMessageBox.Yes:
            return
        try:
            self.project.delete_run(run.id)
        except ValueError as e:
            QMessageBox.warning(self, "Delete run", str(e))
            return
        self.run = None
        self.ctl.runs_edited()
        self.refresh_runs()


def icons_label(name):
    lab = QLabel()
    lab.setPixmap(icons.pixmap(name, 16, theme.tokens()["muted"]))
    lab.setToolTip("Fingerprint of this schedule")
    return lab
