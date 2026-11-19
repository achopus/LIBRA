"""Screenshots of the app for the tutorial figures (Figures 1 and 2 of the article), in dark mode.

Opens the built-in example "Two-center crossover trial", generates the schedule with seed 1 and
default settings, and saves the pictures used in the article.

    python screenshots.py [output folder]       (default: figures/)

Output: fig_libra_participants.png, fig_libra_rules.png, fig_libra_balance.png,
fig_libra_checks.png, fig_libra_schedule.png
"""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import common  # noqa: E402,F401  (puts LIBRA on sys.path)

from PySide6.QtCore import QPoint, QRect
from PySide6.QtWidgets import QApplication, QFrame

WIDTH, HEIGHT = 1650, 880        # window size in logical pixels; pictures are saved at 1.5x


def settle(app, n=20):
    for _ in range(n):
        app.processEvents()


def grab(w, widgets, out, pad=8, height=None):
    """Save the part of the window that holds the given widgets."""
    rect = QRect()
    for x in widgets:
        r = QRect(x.mapTo(w, QPoint(0, 0)), x.size())
        rect = r if rect.isNull() else rect.united(r)
    rect.adjust(-pad, -pad, pad, pad)
    if height:
        rect.setHeight(height)
    w.grab(rect.intersected(w.rect())).save(str(out))
    print("saved", out.name)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "figures"
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("QT_SCALE_FACTOR", "1.5")
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    from PySide6.QtCore import QLocale
    QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedKingdom))
    app = QApplication(sys.argv)
    from randomizer.runner import solve_isolated
    from randomizer_gui import theme
    from randomizer_gui.mainwindow import MainWindow
    theme.apply(app, "dark")

    w = MainWindow()
    w.resize(WIDTH, HEIGHT)
    w.show()
    w.open_example("two-centers")
    w.ctl.set("seed", 1, "Seed")
    settle(app)

    # (a) subjects page: whole window
    w.go("subjects")
    settle(app)
    w.grab().save(str(out / "fig_libra_participants.png"))
    print("saved fig_libra_participants.png")

    # (b) rules page: the summary banner and the forbidden transitions
    w.go("rules")
    settle(app)
    w._run_checks()
    settle(app)
    page = w.page["rules"]
    grab(w, [page.banner, page.c1], out / "fig_libra_rules.png")

    # (c) balance page: the criteria card
    w.go("balance")
    settle(app)
    grab(w, [w.page["balance"].crit_card], out / "fig_libra_balance.png")

    # generate (seed 1, default settings) and show the result
    spec, cluster = w.ctl.project.build_spec()
    res = solve_isolated(spec, progress=lambda s: None)
    run = w.ctl.project.add_run(res, cluster=cluster, settings=w.ctl.project.settings)
    w.ctl.runs_edited(autosave=False)
    w._generated(run.id)
    settle(app, 50)

    # Figure 2 (a): the right-hand panel down to the end of the overview cards
    page = w.page["results"]
    right = page.tabs.parentWidget()
    cards = [c for c in page.overview.findChildren(QFrame) if c.objectName() == "Card" and c.isVisible()]
    top = right.mapTo(w, QPoint(0, 0))
    bottom = max(c.mapTo(w, QPoint(0, c.height())).y() for c in cards)
    w.grab(QRect(top.x() - 8, top.y() - 8, right.width() + 16, bottom - top.y() + 16)).save(
        str(out / "fig_libra_checks.png"))
    print("saved fig_libra_checks.png; fingerprint", run.fingerprint)

    # (b) the first rows of the schedule tab
    w.resize(WIDTH, 1300)
    page.tabs.setCurrentIndex(1)
    settle(app, 50)
    view = page.sched_view
    hh, vh = view.horizontalHeader(), view.verticalHeader()
    last = view.model().columnCount() - 1
    width = vh.width() + hh.sectionPosition(last) + hh.sectionSize(last) + 2 * view.frameWidth()
    height = hh.height() + sum(vh.sectionSize(r) for r in range(17)) + vh.sectionSize(17) // 2
    pos = view.mapTo(w, QPoint(0, 0))
    w.grab(QRect(pos.x(), pos.y(), width, height)).save(str(out / "fig_libra_schedule.png"))
    print("saved fig_libra_schedule.png")
    w.ctl.dirty = False
    w.ctl.discard_recovery()
    w.close()


if __name__ == "__main__":
    main()
