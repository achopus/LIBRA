"""Start the desktop app:  python -m randomizer_gui [project.libra]"""
from __future__ import annotations

import multiprocessing
import sys


def main(argv=None):
    multiprocessing.freeze_support()          # the solver runs in a child process, also when frozen
    argv = list(sys.argv if argv is None else argv)
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from randomizer import __version__
    from . import theme
    from .controller import Controller, settings_store
    from .mainwindow import MainWindow, app_icon

    from PySide6.QtCore import QLocale
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedKingdom))   # the app is in English
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("LIBRA")
    app.setOrganizationName("LIBRA")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(app_icon())
    theme.apply(app, settings_store().value("theme", "system"))
    windows = []

    def make(ctl=None):
        w = MainWindow(ctl)
        w.rebuild_requested.connect(lambda: rebuild(w))
        windows.append(w)
        return w

    def rebuild(old):
        """Theme change: build a fresh window (icons and colors) around the same project."""
        ctl = Controller()
        ctl.project, ctl.dirty = old.ctl.project, old.ctl.dirty
        old.ctl._timer.stop()
        step = old.current_step() if old.ctl.project else None
        geo, maxed = old.saveGeometry(), old.isMaximized()
        old.ctl.project = None
        old._rebuilding = True
        w = make(ctl)
        w.restoreGeometry(geo)
        w.showMaximized() if maxed else w.show()
        if step:
            w.go(step)
        old.close()
        old.deleteLater()
        windows.remove(old)

    if "--self-test" in argv:
        i = argv.index("--self-test")
        return self_test(argv[i + 1] if len(argv) > i + 1 else "selftest.txt", make)

    # macOS sends double-clicked files as events, not as arguments
    from PySide6.QtCore import QEvent, QObject

    class FileOpener(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.FileOpen and windows:
                windows[-1].open_file(event.file())
                return True
            return False

    opener = FileOpener(app)
    app.installEventFilter(opener)

    win = make()
    win.show()
    files = [a for a in argv[1:] if a.lower().endswith(".libra")]
    if files:
        QTimer.singleShot(0, lambda: win.open_file(files[0]))
    else:
        QTimer.singleShot(300, win.maybe_first_start)
    return app.exec()


def self_test(report: str, make) -> int:
    """Used by the installer build: exercise the packaged app without showing it."""
    import tempfile
    import time
    import traceback
    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    lines = []
    try:
        from randomizer import plots
        from randomizer.examples import EXAMPLES
        from randomizer.runner import solve_isolated
        from . import printing
        w = make()
        w.open_example("human-crossover")
        w.ctl.dirty = False
        for step in ("subjects", "treatments", "rules", "balance", "generate"):
            w.go(step)
        w._run_checks()
        QApplication.processEvents()
        lines.append(f"window: {len(w._findings)} findings")
        spec, _ = EXAMPLES["human-crossover"]().build_spec()
        spec.time_limit = 8
        t0 = time.time()
        res = solve_isolated(spec)                      # child process through this executable
        lines.append(f"solve: {res.status} in {time.time() - t0:.1f} s")
        png = plots.figure_png(plots.schedule_figure(res))
        lines.append(f"figure: {len(png)} bytes")
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "labels.pdf"
            printing.labels_pdf(printing.label_texts(res, None, True, False), str(pdf), printing.LAYOUTS[0])
            lines.append(f"pdf: {pdf.stat().st_size} bytes")
        w.close()
        Path(report).write_text("OK\n" + "\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except Exception:  # noqa: BLE001
        Path(report).write_text("FAILED\n" + "\n".join(lines) + "\n" + traceback.format_exc(), encoding="utf-8")
        return 1


if __name__ == "__main__":
    sys.exit(main())
