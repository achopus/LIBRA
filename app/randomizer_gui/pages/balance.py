from __future__ import annotations

import re

from PySide6.QtWidgets import QCheckBox, QGridLayout, QLineEdit

from randomizer.project import randomized_count, treatment_names

from ..widgets import Banner, Card, HelpButton, Segmented, hbox, label, repolish
from .base import Page, quiet, set_text

CRITERIA = [
    ("period_balance", "Each {period} has each treatment equally often"),
    ("carryover_balance", "Each treatment follows every other equally often (carry-over)"),
    ("cooccurrence_balance", "Every pair of treatments is given to the same {one} equally often"),
    ("fulllist_balance", "The full list reveals little about a {one}'s later treatments"),
    ("spread_balance", "{Many} who shared a treatment split up in the next {period} (spread)"),
]


class BalancePage(Page):
    step = "balance"
    title_text = "Balance"
    lead_text = ("What the schedule should balance, in order of priority. The defaults suit most studies.")

    def __init__(self, ctl, parent=None):
        super().__init__(ctl, parent)
        tf = self.terms
        self.banner = Banner("info", "")
        self.content.addWidget(self.banner)
        self.banner.hide()                   # shown once the checks have run
        self.crit_card = Card("Balance criteria", help_key="levels", terms_fn=tf,
                              hint="Required: must hold exactly. Preferred: exact when possible, otherwise as "
                                   "close as possible. Off: ignored.")
        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.rows = {}
        for i, (key, text) in enumerate(CRITERIA):
            num = label(str(i + 1), "Muted")
            title = label("")
            opts = [("preferred", "Preferred"), ("off", "Off")]
            seg = Segmented(opts if key == "fulllist_balance" else [("required", "Required")] + opts)
            seg.changed.connect(lambda v, k=key: self.ctl.set(k, v, "Change balance"))
            why = label("", "Hint")
            grid.addWidget(num, i, 0)
            grid.addLayout(hbox(title, HelpButton(key, tf), None, spacing=4), i, 1)
            grid.addWidget(seg, i, 2)
            grid.addWidget(why, i, 3)
            self.rows[key] = (title, seg, why, text)
        grid.setColumnStretch(1, 1)
        self.crit_card.add(grid)
        self.scope = QCheckBox("Apply carry-over, pair and spread balance within each group too")
        self.scope.toggled.connect(lambda on: self.ctl.set("balance_scope", "groups" if on else "overall",
                                                           "Change balance scope"))
        self.crit_card.add(hbox(self.scope, HelpButton("scope", tf), None, spacing=4))
        self.content.addWidget(self.crit_card)

        self.block_card = Card("Enrollment blocks", help_key="blocks", terms_fn=tf)
        self.blocks_on = QCheckBox("Randomize in consecutive blocks (in table order)")
        self.blocks_on.toggled.connect(lambda on: self.ctl.set("blocks_enabled", on, "Toggle blocks"))
        self.sizes = QLineEdit()
        self.sizes.setPlaceholderText("e.g. 4, 6")
        self.sizes.setMaximumWidth(160)
        self.sizes.editingFinished.connect(self._sizes)
        self.sizes_hint = label("", "Hint")
        self.block_card.add(self.blocks_on)
        self.block_card.add(hbox(label("Block sizes"), self.sizes, self.sizes_hint, None))
        self.content.addWidget(self.block_card)
        self.finish()

    def _sizes(self):
        txt = self.sizes.text()
        parts = [p for p in re.split(r"[,;\s]+", txt) if p]
        ok = parts and all(p.isdigit() and int(p) > 0 for p in parts)
        self.sizes.setProperty("invalid", not ok)
        repolish(self.sizes)
        if ok:
            self.ctl.set("block_sizes", [int(p) for p in parts], "Change block sizes")

    def set_findings(self, findings):
        rel = [f for f in findings if f.step == "balance"]
        if rel:
            worst = "error" if any(f.level == "error" for f in rel) else ("warning" if any(
                f.level == "warning" for f in rel) else "info")
            self.banner.set(worst, "\n".join(f.text for f in rel))
            self.banner.show()
        else:
            self.banner.hide()

    def refresh(self):
        super().refresh()
        s, t = self.s, self.terms()
        multi = randomized_count(s) > 1
        incomplete = s["design"] == "incomplete"
        why = {"carryover_balance": "" if multi else "only one randomized period",
               "spread_balance": "" if multi else "only one randomized period",
               "cooccurrence_balance": "" if incomplete else "incomplete designs only",
               "fulllist_balance": "" if randomized_count(s) >= 4 else "needs 4 or more randomized periods"}
        for key, (title, seg, note, text) in self.rows.items():
            title.setText(text.format(**t))
            with quiet(seg):
                seg.set_value(s.get(key, "off"))
            off = bool(why.get(key))
            seg.setEnabled(not off)
            title.setEnabled(not off)
            note.setText(why.get(key, ""))
        strata = bool(s["strata"])
        with quiet(self.scope, self.blocks_on):
            self.scope.setChecked(s["balance_scope"] == "groups")
            self.blocks_on.setChecked(bool(s["blocks_enabled"]))
        self.scope.setEnabled(strata and multi)
        self.scope.setToolTip("" if strata else "Tick a group column on the first page to use this.")
        self.sizes.setEnabled(bool(s["blocks_enabled"]))
        if not self.sizes.hasFocus():
            set_text(self.sizes, ", ".join(str(b) for b in s["block_sizes"]))
            self.sizes.setProperty("invalid", False)
            repolish(self.sizes)
        n_t = len(treatment_names(s))
        self.sizes_hint.setText(f"One size is picked at random for each block. Multiples of {n_t} keep "
                                f"every block fully balanced." if n_t else "")
