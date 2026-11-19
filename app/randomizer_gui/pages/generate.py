from __future__ import annotations

import copy

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QGridLayout, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from randomizer.project import DESIGNS, new_seed
from randomizer.prechecks import summary_line

from ..widgets import discard, Banner, Card, HelpButton, Segmented, button, hbox, label
from ..progress import ProgressPanel
from .base import Page, quiet

STEP_NAMES = {"subjects": "{Many}", "treatments": "Treatments", "rules": "Rules", "balance": "Balance",
              "generate": "Generate"}

_GUROBI = None


def gurobi_ok() -> bool:
    global _GUROBI
    if _GUROBI is None:
        from randomizer.solver import gurobi_available
        _GUROBI = gurobi_available()
    return _GUROBI


class GeneratePage(Page):
    step = "generate"
    title_text = "Generate"
    lead_text = "Check the summary, then generate the schedule. Every run is kept in the project."
    goto = Signal(str)
    generated = Signal(str)            # run id

    def __init__(self, ctl, parent=None):
        super().__init__(ctl, parent)
        tf = self.terms
        self.summary_card = Card()
        self.summary = label("", "Big")
        self.design_label = label("", "Hint")
        self.summary_card.add(self.summary)
        self.summary_card.add(self.design_label)
        self.findings_box = QVBoxLayout()
        self.findings_box.setSpacing(6)
        self.summary_card.add(self.findings_box)
        self.content.addWidget(self.summary_card)

        self.rand_card = Card("Randomization")
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.seed = QSpinBox()
        self.seed.setRange(0, 2_147_483_646)
        self.seed.setMinimumWidth(130)
        self.seed.valueChanged.connect(lambda v: self.ctl.set("seed", v, "Change seed", merge=True))
        dice = button("New seed", "dice", flat=True)
        dice.clicked.connect(lambda: self.ctl.set("seed", new_seed(), "New seed"))
        self.limit = QSpinBox()
        self.limit.setRange(5, 3600)
        self.limit.setSingleStep(15)
        self.limit.setSuffix(" s")
        self.limit.valueChanged.connect(lambda v: self.ctl.set("time_limit", v, "Change time limit", merge=True))
        self.mode = Segmented([("variety", "Variety"), ("speed", "Speed")])
        self.mode.changed.connect(lambda v: self.ctl.set("randomization", v, "Change final choice"))
        self.solver = QComboBox()
        self.solver.addItem("HiGHS (built in)", "highs")
        self.solver.activated.connect(lambda _: self.ctl.set("solver", self.solver.currentData(), "Change solver"))
        self.repro = QCheckBox("Same schedule on every computer (the time limit becomes a fixed amount of "
                               "search; the actual time varies)")
        self.repro.toggled.connect(lambda on: self.ctl.set("deterministic", on, "Toggle reproducible mode"))
        self.blind = QCheckBox("Give treatments neutral codes (A, B, C…) for blinded experimenters")
        self.blind.toggled.connect(lambda on: self.ctl.set("blind", on, "Toggle blinding"))
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional, e.g. 'pilot' or 'final for ethics submission'")
        rows = [("Seed", hbox(self.seed, dice, None), "seed"),
                ("Time limit", hbox(self.limit, None), "time_limit"),
                ("Reproducible", hbox(self.repro, None), "deterministic"),
                ("Choice among equally balanced schedules", hbox(self.mode, None), "mode"),
                ("Solver", hbox(self.solver, None), "solver"),
                ("Blinding", hbox(self.blind, None), "blind"),
                ("Note for this run", self.note, "note")]
        for r, (name, w, key) in enumerate(rows):
            g.addLayout(hbox(label(name), HelpButton(key, tf) if key else None, None, spacing=4), r, 0)
            if isinstance(w, QWidget):
                g.addWidget(w, r, 1)
            else:
                g.addLayout(w, r, 1)
        g.setColumnStretch(1, 1)
        self.rand_card.add(g)
        self.content.addWidget(self.rand_card)

        self.go = button("Generate schedule", "play", primary=True, big=True)
        self.go.clicked.connect(self.start)
        self.go_hint = label("", "Hint")
        self.content.addLayout(hbox(self.go, self.go_hint, None, spacing=14))
        self.error = Banner("error", "")
        self.retry = button("Retry with more time", "refresh")
        self.retry.clicked.connect(self.retry_more_time)
        self.error.extra.addWidget(self.retry)
        self.error.hide()
        self.content.addWidget(self.error)
        self.progress = ProgressPanel()
        self.progress.hide()
        self.progress.finished.connect(self._finished)
        self.content.addWidget(self.progress)
        self.finish()
        self._findings = []

    # ------------------------------------------------------------------ findings
    def set_findings(self, findings):
        self._findings = findings
        while self.findings_box.count():
            discard(self.findings_box.takeAt(0).widget())
        order = {"error": 0, "warning": 1, "info": 2}
        t = self.terms()
        for f in sorted(findings, key=lambda f: order[f.level]):
            b = Banner(f.level, f.text)
            if f.step != "generate":
                link = button(f"Go to {STEP_NAMES[f.step].format(**t)}", "arrow-right", flat=True)
                link.clicked.connect(lambda _=False, st=f.step: self.goto.emit(st))
                b.extra.addWidget(link)
            self.findings_box.addWidget(b)
        if not findings:
            self.findings_box.addWidget(Banner("ok", "Everything is set. No problems found."))
        errors = sum(f.level == "error" for f in findings)
        self.go.setEnabled(errors == 0 and not self.progress.running())
        self.go_hint.setText(f"Fix {errors} problem{'s' if errors > 1 else ''} above first." if errors else
                             f"Takes up to {int(self.s['time_limit'])} s.")

    # ------------------------------------------------------------------ solving
    def start(self):
        if self.progress.running():
            return
        try:
            spec, self._cluster = self.project.build_spec()
        except ValueError as e:
            self._show_error(str(e), retry=False)
            return
        self._settings = copy.deepcopy(self.s)
        self._note = self.note.text().strip()
        self.error.hide()
        self.go.setEnabled(False)
        self.progress.show()
        self.progress.start(spec)
        self.scroll.ensureWidgetVisible(self.progress)

    def retry_more_time(self):
        self.ctl.set("time_limit", int(min(3600, max(60, 2 * self.s["time_limit"]))), "More time")
        self.start()

    def _show_error(self, text, retry=True):
        self.error.set("error", text)
        self.retry.setVisible(retry)
        self.error.show()

    def _finished(self, kind, payload):
        self.progress.hide()
        self.set_findings(self._findings)
        if kind == "cancelled":
            return
        if kind == "failed":
            self._show_error(payload, retry="time" in payload.lower() or "no design" in payload.lower())
            return
        run = self.project.add_run(payload, note=self._note, cluster=self._cluster, settings=self._settings)
        self.note.clear()
        self.ctl.runs_edited()
        self.generated.emit(run.id)

    # ------------------------------------------------------------------ refresh
    def refresh(self):
        super().refresh()
        s, t = self.s, self.terms()
        self.summary.setText(summary_line(s, self.project.subjects))
        name, desc = DESIGNS[s["design"]]
        self.design_label.setText(f"{name}: {desc.format(one=t['one'], period=t['period'])}")
        with quiet(self.seed, self.limit, self.blind, self.solver, self.mode, self.repro):
            self.seed.setValue(int(s["seed"]))
            self.repro.setChecked(bool(s.get("deterministic", True)))
            self.limit.setValue(int(s["time_limit"]))
            self.mode.set_value(s.get("randomization", "variety"))
            self.blind.setChecked(bool(s.get("blind")))
            if gurobi_ok() and self.solver.count() == 1:
                self.solver.addItem("Gurobi (installed on this computer)", "gurobi")
            i = self.solver.findData(s.get("solver", "highs"))
            self.solver.setCurrentIndex(max(0, i))
        self.solver.setEnabled(self.solver.count() > 1)
        self.solver.setToolTip("" if self.solver.count() > 1 else "Gurobi is not installed on this computer.")
