from __future__ import annotations

from contextlib import contextmanager

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import QFrame, QScrollArea, QVBoxLayout, QWidget

from ..widgets import Banner, fmt, hbox, label, terms


@contextmanager
def quiet(*widgets):
    """Change widgets from code without triggering their change handlers."""
    blockers = [QSignalBlocker(w) for w in widgets]
    try:
        yield
    finally:
        del blockers


class Page(QWidget):
    """A scrollable page with a title, a lead sentence and a centered column of cards."""
    step = ""
    title_text = ""
    lead_text = ""
    max_width = 1060

    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        self.setObjectName("Page")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        body = QWidget()
        body.setObjectName("PageBody")
        self.column = QWidget()
        self.column.setMaximumWidth(self.max_width)
        self.content = QVBoxLayout(self.column)
        self.content.setContentsMargins(32, 26, 32, 40)
        self.content.setSpacing(16)
        outer = hbox(None, self.column, None, spacing=0)
        outer.setStretch(1, 100)
        body.setLayout(outer)
        scroll.setWidget(body)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        self.scroll = scroll
        self.title = label("", "PageTitle")
        self.lead = label("", "PageLead", wrap=True)
        self.content.addWidget(self.title)
        self.content.addWidget(self.lead)
        self.lock_banner = Banner("info", "")
        self.lock_banner.hide()
        self.content.addWidget(self.lock_banner)

    # helpers
    @property
    def project(self):
        return self.ctl.project

    @property
    def s(self) -> dict:
        return self.ctl.project.settings

    def terms(self) -> dict:
        return terms(self.s)

    def t(self, text: str) -> str:
        return fmt(text, self.terms())

    def refresh(self):
        """Show the project's current state (called after every change, undo and redo)."""
        self.title.setText(self.t(self.title_text))
        self.lead.setText(self.t(self.lead_text))
        fr = self.project.final_run if self.project else None
        if fr and self.step not in ("results",):
            self.lock_banner.set("info", f"{fr.id} is the final schedule and stays locked. Changes here only "
                                         f"affect new runs.")
            self.lock_banner.show()
        else:
            self.lock_banner.hide()

    def finish(self):
        self.content.addStretch(1)


def set_text(widget, text):
    if widget.text() != text:
        with quiet(widget):
            widget.setText(text)
