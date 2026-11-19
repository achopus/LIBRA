from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QSpinBox, QVBoxLayout, QWidget

from randomizer.project import randomized_count, treatment_names

from ..widgets import discard, Banner, Card, button, hbox, label
from .base import Page


class RuleList(QWidget):
    """Rows of [treatment] word [treatment or period] [x] plus an Add button."""

    def __init__(self, page, key: str, word: str, second: str, add_text: str):
        super().__init__()
        self.page, self.key, self.word, self.second = page, key, word, second
        self.rows = QVBoxLayout()
        self.rows.setSpacing(6)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.empty = label("No rules.", "Muted")
        self.add_btn = button(add_text, "plus")
        self.add_btn.clicked.connect(self._add)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.empty)
        lay.addLayout(self.rows)
        lay.addLayout(hbox(self.add_btn, None))
        self._shown = None

    def _names(self):
        return treatment_names(self.page.s)

    def _add(self):
        names = self._names()
        if len(names) < (1 if self.second == "period" else 2):
            return
        new = [names[0], 1] if self.second == "period" else [names[0], names[1]]
        self.page.ctl.set(self.key, self.page.s[self.key] + [new], "Add rule")

    def _changed(self):
        out = []
        for i in range(self.rows.count()):
            w = self.rows.itemAt(i).widget()
            a = w.a.currentText()
            b = w.b.value() if self.second == "period" else w.b.currentText()
            out.append([a, b])
        self.page.ctl.set(self.key, out, "Edit rule")

    def _remove(self, i):
        rows = list(self.page.s[self.key])
        rows.pop(i)
        self.page.ctl.set(self.key, rows, "Remove rule")

    def refresh(self):
        rules = self.page.s[self.key]
        names = self._names()
        t = self.page.terms()
        state = (tuple(map(tuple, rules)), tuple(names), t["period"])
        if state == self._shown:
            return
        self._shown = state
        while self.rows.count():
            discard(self.rows.takeAt(0).widget())
        for i, (a, b) in enumerate(rules):
            row = QWidget()
            row.a = QComboBox()
            row.a.addItems(names if a in names else names + [a])
            row.a.setCurrentText(a)
            if self.second == "period":
                row.b = QSpinBox()
                row.b.setRange(1, 99)
                row.b.setPrefix(f"{t['period_cap']} ")
                row.b.setValue(int(b))
                row.b.valueChanged.connect(lambda _: self._changed())
            else:
                row.b = QComboBox()
                row.b.addItems(names if b in names else names + [b])
                row.b.setCurrentText(b)
                row.b.currentIndexChanged.connect(lambda _: self._changed())
            row.a.currentIndexChanged.connect(lambda _: self._changed())
            for c in (row.a, row.b):
                c.setMinimumWidth(150)
            rm = button("", "close", flat=True, tip="Remove this rule")
            rm.clicked.connect(lambda _=False, k=i: self._remove(k))
            row.setLayout(hbox(row.a, label(self.word), row.b, rm, None))
            self.rows.addWidget(row)
        self.empty.setVisible(not rules)
        self.add_btn.setEnabled(len(names) >= (1 if self.second == "period" else 2))


class RulesPage(Page):
    step = "rules"
    title_text = "Rules"
    lead_text = ("Optional. Rules are always obeyed. Use them for safety or logic, such as dose escalation "
                 "or drugs that must not follow each other.")

    def __init__(self, ctl, parent=None):
        super().__init__(ctl, parent)
        tf = self.terms
        self.banner = Banner("info", "")
        self.content.addWidget(self.banner)
        self.banner.hide()                   # shown once the checks have run
        self.c1 = Card("Never directly followed by", help_key="forbidden_transitions", terms_fn=tf)
        self.l1 = RuleList(self, "forbidden_transitions", "never directly followed by", "treatment", "Add rule")
        self.c1.add(self.l1)
        self.c3 = Card("Must come before", help_key="order_rules", terms_fn=tf,
                       hint="For example dose escalation: the lower dose is always given first.")
        self.l3 = RuleList(self, "order_rules", "always before", "treatment", "Add rule")
        self.c3.add(self.l3)
        self.c2 = Card("Not allowed in a {period}", help_key="forbidden_periods", terms_fn=tf)
        self.l2 = RuleList(self, "forbidden_periods", "never in", "period", "Add rule")
        self.c2.add(self.l2)
        for c in (self.c1, self.c3, self.c2):
            self.content.addWidget(c)
        self.finish()

    def set_findings(self, findings):
        rel = [f for f in findings if f.step == "rules"]
        if rel:
            worst = "error" if any(f.level == "error" for f in rel) else rel[0].level
            self.banner.set(worst, " ".join(f.text for f in rel))
            self.banner.show()
        else:
            self.banner.hide()

    def refresh(self):
        super().refresh()
        t = self.terms()
        self.c2.title_label.setText(f"Not allowed in a {t['period']}")
        multi = randomized_count(self.s) > 1
        self.c1.setEnabled(multi)
        self.c3.setEnabled(multi)
        for lst in (self.l1, self.l2, self.l3):
            lst.refresh()
