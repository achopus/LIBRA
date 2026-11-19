"""Progress while the solver works: current step, elapsed and remaining time, Cancel."""
from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import QDialog, QFrame, QProgressBar, QVBoxLayout

from .widgets import button, hbox, label, vbox
from .worker import SolveWorker

PHASES = {
    "Checking whether perfect": "Checking which balance criteria can be met exactly",
    "Building the full": "Setting up the full problem",
    "Warm start": "Building a first schedule",
    "Optimizing": "Improving balance",
    "Improving balance": "Improving balance",
    "Listing": "Listing all equally balanced schedules",
    "Moving randomly": "Choosing at random among the best schedules",
    "Picking a random": "Choosing at random among the best schedules",
}


def friendly(msg: str) -> str:
    for k, v in PHASES.items():
        if msg.startswith(k):
            if k == "Checking whether perfect":
                return "Checking whether " + msg[len("Checking whether "):].rstrip("…").rstrip(".") + "…"
            return v + "…"
    return msg


class ProgressPanel(QFrame):
    """Shows a running SolveWorker. Emits finished(kind, payload): done/failed/cancelled."""
    finished = Signal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.phase = label("Starting…", "CardTitle")
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setFixedHeight(8)
        self.times = label("", "Hint")
        self.cancel_btn = button("Cancel", "close")
        self.cancel_btn.clicked.connect(self.cancel)
        self.setLayout(vbox(self.phase, self.bar, hbox(self.times, None, self.cancel_btn),
                            spacing=10, margins=(18, 16, 18, 16)))
        self.timer = QTimer(self)
        self.timer.setInterval(200)
        self.timer.timeout.connect(self._tick)
        self.worker = None

    def start(self, spec, title="Generating the schedule"):
        self.limit = float(spec.time_limit)
        self.t0 = time.monotonic()
        self.phase.setText(title + "…")
        self.cancel_btn.setEnabled(True)
        self.worker = SolveWorker(spec, self)
        self.worker.progress.connect(lambda m: self.phase.setText(friendly(m)))
        self.worker.done.connect(lambda r: self._end("done", r))
        self.worker.failed.connect(lambda m: self._end("failed", m))
        self.worker.cancelled.connect(lambda: self._end("cancelled", None))
        self.worker.start()
        self.timer.start()
        self._tick()

    def running(self) -> bool:
        return self.worker is not None and self.worker.isRunning()

    def cancel(self):
        if self.worker:
            self.cancel_btn.setEnabled(False)
            self.phase.setText("Stopping…")
            self.worker.cancel()

    def _tick(self):
        el = time.monotonic() - self.t0
        self.bar.setValue(int(1000 * min(1.0, el / max(1.0, self.limit))))
        left = max(0, self.limit - el)
        self.times.setText(f"{el:.0f} s elapsed · at most {left:.0f} s left" if left > 0
                           else f"{el:.0f} s elapsed · finishing…")

    def _end(self, kind, payload):
        self.timer.stop()
        self.bar.setValue(1000)
        w, self.worker = self.worker, None
        if w is not None:
            w.wait(2000)
        self.finished.emit(kind, payload)


class ProgressDialog(QDialog):
    """Modal progress for a solve; after exec(), .kind and .payload hold the outcome."""

    def __init__(self, spec, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(460)
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.panel = ProgressPanel(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.addWidget(self.panel)
        self.kind, self.payload = None, None
        self.panel.finished.connect(self._done)
        self.panel.start(spec, title)

    def _done(self, kind, payload):
        self.kind, self.payload = kind, payload
        self.accept()

    def reject(self):                    # Esc = cancel
        if self.panel.running():
            self.panel.cancel()
        else:
            super().reject()
