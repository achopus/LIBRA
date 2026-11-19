"""A guided tour: the window is dimmed except for one highlighted part, and a small card explains
what to do there. Starts on the first launch; replay it from Help → Show the tutorial."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTextDocument
from PySide6.QtWidgets import QApplication, QFrame, QWidget

from . import theme
from .widgets import HelpPopup, button, fmt, hbox, label, terms, vbox

CARD_WIDTH = 380
MARGIN = 8            # space between the highlight and the widget


@dataclass
class Step:
    title: str
    text: str
    target: Callable[[], object] | None = None     # widget, list of widgets, or None (centered card)
    prepare: Callable[[], None] | None = None      # e.g. go to a page first


def steps_for(mw) -> list[Step]:
    """The tour. Texts use the project's own words ({many}, {period}, ...)."""
    p = mw.page

    def go(step):
        return lambda: mw.go(step)

    return [
        Step("Welcome to LIBRA",
             "LIBRA makes balanced, hard-to-predict treatment schedules for crossover and parallel-group "
             "studies. This short tour shows where to click and what to type. Use <b>Next</b> or the arrow "
             "keys; <b>Esc</b> ends the tour at any time.",
             prepare=lambda: mw.stack.setCurrentWidget(mw.start)),
        Step("Start or open a study",
             "<b>New project</b> starts an empty study and saves it as a <b>.libra</b> file. "
             "<b>Open project…</b> continues one you saved earlier.",
             target=lambda: [mw.start.new_btn, mw.start.open_btn],
             prepare=lambda: mw.stack.setCurrentWidget(mw.start)),
        Step("Or begin from an example",
             "Each example is a complete, typical study. Open one, change what differs in yours, and generate. "
             "For this tour we open the rat crossover.",
             target=lambda: mw.start.examples,
             prepare=lambda: mw.stack.setCurrentWidget(mw.start)),
        Step("The steps of a study",
             "Work through the steps from top to bottom. A <b>✓</b> means the step is fine; a warning or error "
             "sign means something needs attention (hover over it to see what).",
             target=lambda: list(mw.step_buttons.values()),
             prepare=lambda: (mw.tour_open_project(), mw.go("subjects"))),
        Step("Your words",
             "Type what you randomize and what one step of the schedule is called, for example "
             "<i>rat / rats</i> and <i>Week / Weeks</i>. These words are used everywhere, including the "
             "exported files. The list on the right fills in common choices.",
             target=lambda: p["subjects"].terms_card, prepare=go("subjects")),
        Step("Enter the {many}",
             "One row per {one}, in the order they join the study. <b>Generate IDs…</b> creates a list "
             "(optionally in groups such as sex), <b>Import file…</b> reads Excel or CSV, and you can paste "
             "rows copied from Excel with <b>Ctrl+V</b>. Double-click a cell to type in it.",
             target=lambda: p["subjects"].table_card, prepare=go("subjects")),
        Step("Groups and cages",
             "Tick a column (sex, genotype…) to balance the schedule within each of its groups. If whole cages "
             "must get the same treatment, choose the cage column at the bottom.",
             target=lambda: p["subjects"].roles, prepare=go("subjects")),
        Step("Choose the design",
             "Click the design that fits: everyone gets every treatment (crossover), only some (incomplete), "
             "treatments repeated (replicated), or one treatment each (parallel groups).",
             target=lambda: p["treatments"].design_card, prepare=go("treatments")),
        Step("List the treatments",
             "<b>Add treatment</b> adds a row; double-click a name to change it. The arrows change the order.",
             target=lambda: p["treatments"].trt_card, prepare=go("treatments")),
        Step("{Periods} and fixed {periods}",
             "Add {periods} that are the same for everyone, such as a baseline or a final maximal dose. The "
             "timeline below shows the whole schedule.",
             target=lambda: p["treatments"].per_card, prepare=go("treatments")),
        Step("Rules (optional)",
             "Add rules that must always hold: two treatments that must never follow each other, a dose "
             "escalation (one treatment always before another), or a treatment not allowed in a {period}.",
             target=lambda: p["rules"].c1, prepare=go("rules")),
        Step("What to balance",
             "The defaults suit most studies. <b>Required</b> must hold exactly; <b>Preferred</b> is met as "
             "closely as possible. Enrollment blocks are below.",
             target=lambda: p["balance"].crit_card, prepare=go("balance")),
        Step("Check before you generate",
             "A plain-language summary of the study. Anything that cannot work is listed here, with a link to "
             "the page where you fix it.",
             target=lambda: p["generate"].summary_card, prepare=go("generate")),
        Step("Seed, time and blinding",
             "The <b>seed</b> makes the schedule reproducible. Larger studies may need a longer <b>time limit</b>. "
             "Tick <b>blinding</b> to give treatments neutral codes for the experimenters.",
             target=lambda: p["generate"].rand_card, prepare=go("generate")),
        Step("Generate",
             "Click here to make the schedule. Progress is shown below, and you can cancel at any time.",
             target=lambda: p["generate"].go, prepare=go("generate")),
        Step("Results",
             "Every schedule you generate is kept here. Check the balance, look at the pictures, set dates, "
             "<b>Export</b> to Excel/CSV/PNG, and <b>Mark as final</b> the one you will use; it is then locked.",
             target=lambda: mw.step_buttons["results"], prepare=go("generate")),
        Step("Help is one click away",
             "Click any <b>?</b> for a short explanation with an example.",
             target=lambda: p["subjects"].terms_card.findChild(QWidget, "HelpButton"), prepare=go("subjects")),
        Step("Undo and save",
             "Undo (<b>Ctrl+Z</b>) and redo (<b>Ctrl+Y</b>) any change. Saved projects are saved automatically "
             "as you work.",
             target=lambda: [mw.undo_btn, mw.redo_btn, mw.save_btn], prepare=go("subjects")),
        Step("You are ready",
             "Start with <b>New project</b> or an example. You can replay this tour any time from "
             "<b>Help → Show the tutorial</b>.",
             prepare=go("subjects")),
    ]


class _Card(QFrame):
    """The explanation card with Back / Next / Skip."""

    def __init__(self, tour):
        super().__init__(tour)
        self.setObjectName("Card")
        self.tour = tour
        self.count = label("", "Muted")
        self.title = label("", "CardTitle")
        self.text = label("", wrap=True)
        self.text.setTextFormat(Qt.RichText)
        self.back = button("Back", flat=True)
        self.next = button("Next", "arrow-right", primary=True)
        self.skip = button("Skip tour", flat=True)
        self.back.clicked.connect(tour.back)
        self.next.clicked.connect(tour.next)
        self.skip.clicked.connect(tour.finish)
        self.setLayout(vbox(self.count, self.title, self.text, 6, hbox(self.skip, None, self.back, self.next),
                            spacing=6, margins=(18, 14, 18, 14)))
        self.setFixedWidth(CARD_WIDTH)

    def show_step(self, i, n, title, text):
        self.count.setText(f"Step {i + 1} of {n}")
        self.title.setText(title)
        self.text.setText(text)
        HelpPopup._fit(self.title, CARD_WIDTH - 36)
        # measure the formatted text the way Qt lays it out (tags such as <b> take no space)
        doc = QTextDocument()
        doc.setDefaultFont(self.text.font())
        doc.setDocumentMargin(0)
        doc.setHtml(text)
        doc.setTextWidth(CARD_WIDTH - 36)
        self.text.setFixedSize(CARD_WIDTH - 36, int(doc.size().height()) + 6)
        self.back.setEnabled(i > 0)
        last = i == n - 1
        self.next.setText("Finish" if last else "Next")
        self.skip.setVisible(not last)
        self.adjustSize()


class Tour(QWidget):
    """Covers the main window; blocks clicks so the user follows the cards."""

    def __init__(self, mw, on_done=None):
        super().__init__(mw)
        self.mw, self.on_done = mw, on_done
        self.steps = steps_for(mw)
        self.i = 0
        self.hole: QRectF | None = None
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.StrongFocus)
        self.card = _Card(self)
        mw.installEventFilter(self)
        self.setGeometry(mw.rect())

    # ---------------------------------------------------------------- flow
    def start(self):
        self.show()
        self.raise_()
        self.setFocus()
        self._show()

    def next(self):
        if self.i >= len(self.steps) - 1:
            self.finish()
        else:
            self.i += 1
            self._show()

    def back(self):
        if self.i > 0:
            self.i -= 1
            self._show()

    def finish(self):
        self.mw.removeEventFilter(self)
        self.hide()
        if self.on_done:
            self.on_done()
        self.deleteLater()

    # ---------------------------------------------------------------- layout
    def _targets(self, step):
        if step.target is None:
            return []
        try:
            t = step.target()
        except (AttributeError, KeyError):
            return []
        ws = t if isinstance(t, (list, tuple)) else [t]
        return [w for w in ws if isinstance(w, QWidget) and w.isVisible()]

    def _show(self):
        step = self.steps[self.i]
        if step.prepare:
            step.prepare()
        QApplication.processEvents()
        ws = self._targets(step)
        if ws:
            page = self.mw.pages.currentWidget() if self.mw.stack.currentWidget() is self.mw.workspace else None
            scroll = getattr(page, "scroll", None)
            if scroll is not None and page.isAncestorOf(ws[0]):
                scroll.ensureWidgetVisible(ws[0], 40, 60)
                QApplication.processEvents()
        t = terms(self.mw.ctl.project.settings) if self.mw.ctl.project else \
            {"one": "subject", "many": "subjects", "period": "period", "periods": "periods",
             "Periods": "Periods", "One": "Subject", "Many": "Subjects", "period_cap": "Period"}
        self.card.show_step(self.i, len(self.steps), fmt(step.title, t), fmt(step.text, t))
        self._place(ws)
        self.setFocus()

    def _place(self, ws):
        self.setGeometry(self.mw.rect())
        if ws:
            r = QRect()
            for w in ws:
                r = r.united(QRect(w.mapTo(self.mw, QPoint(0, 0)), w.size()))
            r = r.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN).intersected(self.rect().adjusted(4, 4, -4, -4))
            self.hole = QRectF(r)
        else:
            self.hole = None
        c = self.card
        c.adjustSize()
        W, H = self.width(), self.height()
        cw, ch = c.width(), c.height()
        if self.hole is None:
            x, y = (W - cw) // 2, (H - ch) // 2
        else:
            h = self.hole.toRect()
            if h.bottom() + 14 + ch < H:                         # below
                x, y = h.left(), h.bottom() + 14
            elif h.top() - 14 - ch > 0:                          # above
                x, y = h.left(), h.top() - 14 - ch
            elif h.right() + 14 + cw < W:                        # right
                x, y = h.right() + 14, h.top()
            elif h.left() - 14 - cw > 0:                         # left
                x, y = h.left() - 14 - cw, h.top()
            else:                                                # inside, bottom right
                x, y = h.right() - cw - 16, h.bottom() - ch - 16
            x = max(12, min(x, W - cw - 12))
            y = max(12, min(y, H - ch - 12))
        c.move(x, y)
        c.raise_()
        self.update()

    # ---------------------------------------------------------------- events
    def eventFilter(self, obj, e):
        if obj is self.mw and e.type() == QEvent.Resize:
            self._place(self._targets(self.steps[self.i]))
        return False

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.finish()
        elif e.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self.next()
        elif e.key() == Qt.Key_Left:
            self.back()

    def mousePressEvent(self, e):
        e.accept()                                   # the rest of the window is paused during the tour

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        shade = QPainterPath()
        shade.addRect(QRectF(self.rect()))
        if self.hole is not None:
            hole = QPainterPath()
            hole.addRoundedRect(self.hole, 10, 10)
            shade = shade.subtracted(hole)
        p.fillPath(shade, QColor(0, 0, 0, 150 if theme.is_dark() else 120))
        if self.hole is not None:
            pen = QPen(QColor(theme.tokens()["grad_a"]), 2.5)
            p.setPen(pen)
            p.drawRoundedRect(self.hole.adjusted(1, 1, -1, -1), 10, 10)
        p.end()
