"""Background solving: the solver runs in its own process; this thread relays its progress."""
from __future__ import annotations

import traceback

from PySide6.QtCore import QThread, Signal

from randomizer.runner import Cancelled, solve_isolated
from randomizer.solver import DesignError


class SolveWorker(QThread):
    progress = Signal(str)
    done = Signal(object)          # Result
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, spec, parent=None):
        super().__init__(parent)
        self.spec = spec
        self._stop = False

    def cancel(self):
        self._stop = True

    def run(self):
        try:
            res = solve_isolated(self.spec, progress=self.progress.emit, cancel=lambda: self._stop)
            self.done.emit(res)
        except Cancelled:
            self.cancelled.emit()
        except DesignError as e:
            self.failed.emit(str(e))
        except Exception:  # noqa: BLE001 - show anything unexpected to the user
            self.failed.emit("Unexpected error:\n" + traceback.format_exc(limit=3))
