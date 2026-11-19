from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget

from randomizer import APP_EXPANSION, __version__
from randomizer.examples import EXAMPLES

from .. import icons, theme
from ..controller import recent_files
from ..widgets import clear_layout, discard, logo, button, hbox, label, vbox

EXAMPLE_TEXT = {
    "rat-crossover": ("Rat crossover", "4 doses, 24 rats, balanced within each sex."),
    "human-crossover": ("Human crossover, blinded", "3 sessions, 18 participants, codes for experimenters."),
    "two-centers": ("Two-center crossover trial", "5 treatments, 30 patients; HIGH and ACTIVE never back to back."),
    "two-sites": ("Two testing sites", "5 conditions, 30 participants; HARD and DUAL never back to back."),
    "parallel-blocks": ("Parallel groups in blocks", "2 groups, 40 mice, blocks of 4 or 6 by arrival."),
    "dose-escalation": ("Dose escalation", "Doses always rise; the placebo session is randomized."),
    "fixed-last-week": ("Fixed last week", "5 randomized weeks, then MAX for every animal."),
    "cages": ("Cages as units", "Drug in drinking water: whole cages are randomized."),
}


class StartPage(QWidget):
    new_requested = Signal()
    open_requested = Signal()
    open_path = Signal(str)
    open_example = Signal(str)
    tour_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StartPage")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("PageBody")
        col = QWidget()
        col.setMaximumWidth(880)
        self.col = QVBoxLayout(col)
        self.col.setContentsMargins(36, 48, 36, 36)
        self.col.setSpacing(18)
        body.setLayout(hbox(None, col, None))
        body.layout().setStretch(1, 100)
        scroll.setWidget(body)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        self.build()

    def build(self):
        clear_layout(self.col)
        tk = theme.tokens()
        mark = logo(72)
        title = label("LIBRA", "PageTitle")
        title.setStyleSheet("font-size: 30px; letter-spacing: 1px;")
        what = label("Crossover Randomizer", "CardTitle")
        what.setStyleSheet("font-size: 16px;")
        acro = label(APP_EXPANSION, "Muted")
        sub = label("Balanced, hard-to-predict treatment schedules for crossover and parallel-group studies.",
                    "PageLead", wrap=True)
        self.col.addLayout(hbox(mark, vbox(hbox(title, what, None, spacing=12), acro, sub, spacing=2),
                                None, spacing=16))
        new = button("New project", "file-plus", primary=True, big=True)
        new.clicked.connect(self.new_requested.emit)
        op = button("Open project…", "folder", big=True)
        op.clicked.connect(self.open_requested.emit)
        tour = button("Take the tour", "help", flat=True, big=True)
        tour.clicked.connect(self.tour_requested.emit)
        self.new_btn, self.open_btn = new, op            # the tutorial points at these
        self.col.addLayout(hbox(new, op, 6, tour, None, spacing=10))

        recent = recent_files()
        if recent:
            self.col.addWidget(label("Recent projects", "CardTitle"))
            box = QFrame()
            box.setObjectName("Card")
            bl = vbox(spacing=0, margins=(6, 6, 6, 6))
            box.setLayout(bl)
            for p in recent[:6]:
                b = QPushButton()
                b.setObjectName("RecentItem")
                b.setCursor(Qt.PointingHandCursor)
                when = datetime.fromtimestamp(Path(p).stat().st_mtime).strftime("%d %b %Y, %H:%M")
                name = label(Path(p).stem, "CardTitle")
                path = label(f"{Path(p).parent}  ·  {when}", "Hint")
                for w in (name, path):
                    w.setAttribute(Qt.WA_TransparentForMouseEvents)
                b.setLayout(vbox(name, path, spacing=0, margins=(10, 6, 10, 6)))
                b.clicked.connect(lambda _=False, q=p: self.open_path.emit(q))
                bl.addWidget(b)
            self.col.addWidget(box)

        self.col.addWidget(label("Start from an example", "CardTitle"))
        grid = QGridLayout()
        grid.setSpacing(10)
        for i, key in enumerate(EXAMPLES):
            t, d = EXAMPLE_TEXT.get(key, (key, ""))
            b = QPushButton()
            b.setObjectName("ExampleCard")
            b.setCursor(Qt.PointingHandCursor)
            ic = QLabel()
            ic.setPixmap(icons.pixmap("flask", 18, tk["accent"]))
            tl = label(t, "CardTitle")
            dl = label(d, "Hint", wrap=True)
            for w in (ic, tl, dl):
                w.setAttribute(Qt.WA_TransparentForMouseEvents)
            b.setLayout(vbox(hbox(ic, tl, None, spacing=8), dl, None, spacing=4, margins=(14, 12, 14, 12)))
            b.setMinimumHeight(92)
            b.clicked.connect(lambda _=False, k=key: self.open_example.emit(k))
            grid.addWidget(b, i // 3, i % 3)
        self.examples = QWidget()
        self.examples.setLayout(grid)
        grid.setContentsMargins(0, 0, 0, 0)
        self.col.addWidget(self.examples)
        self.col.addStretch(1)
        ic = QLabel()
        ic.setPixmap(icons.pixmap("shield", 16, tk["ok"]))
        self.col.addLayout(hbox(ic, label("Runs entirely on this computer. Nothing you enter is sent online.",
                                          "Hint"), None, label(f"Version {__version__}", "Muted"), spacing=8))


def _clear(layout):
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            discard(it.widget())
        elif it.layout():
            _clear(it.layout())
