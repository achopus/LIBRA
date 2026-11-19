"""Desktop app smoke tests (offscreen; skipped when PySide6 is missing)."""
import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
PySide6 = pytest.importorskip("PySide6")

from PySide6.QtCore import QSettings  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from randomizer import solve  # noqa: E402
from randomizer.examples import EXAMPLES  # noqa: E402


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    import randomizer_gui.controller as C
    import randomizer_gui.mainwindow as MW
    d = tmp_path_factory.mktemp("gui")
    C.settings_store = lambda: QSettings(str(d / "settings.ini"), QSettings.IniFormat)
    MW.settings_store = C.settings_store
    C.recovery_dir = lambda: d
    a = QApplication.instance() or QApplication([])
    from randomizer_gui import theme
    theme.apply(a, "light")
    yield a


@pytest.fixture
def win(app):
    from randomizer_gui.mainwindow import MainWindow
    w = MainWindow()
    w.show()
    yield w
    w.ctl.dirty = False
    w.close()


def test_every_page_of_every_example_renders(win):
    for key in EXAMPLES:
        win.open_example(key)
        win.ctl.dirty = False
        for step in ("subjects", "treatments", "rules", "balance", "generate"):
            win.go(step)
            win._run_checks()
            QApplication.processEvents()
        assert not [f for f in win._findings if f.level == "error"], key


def test_undo_redo_and_save(win, tmp_path):
    win.open_example("rat-crossover")
    c = win.ctl
    c.set("seed", 4242, "seed")
    c.set("period_name", "Day")
    c.set("treatments", c.project.settings["treatments"][:3], "remove")
    assert c.project.settings["period_name"] == "Day"
    c.undo.undo()
    assert len(c.project.settings["treatments"]) == 4
    c.undo.undo()
    assert c.project.settings["period_name"] == "Week"
    c.undo.redo()
    assert c.project.settings["period_name"] == "Day"
    f = tmp_path / "p.libra"
    c.save(str(f))
    assert not c.dirty and f.exists()
    win.open_file(str(f))
    assert c.project.settings["seed"] == 4242 and c.project.settings["period_name"] == "Day"


def test_generate_through_the_window(win):
    win.open_example("human-crossover")
    win.ctl.project.settings["time_limit"] = 5
    win.go("generate")
    win._run_checks()
    g = win.page["generate"]
    assert g.go.isEnabled()
    g.start()
    t0 = time.time()
    while (g.progress.running() or not win.ctl.project.runs) and time.time() - t0 < 90:
        QApplication.processEvents()
        time.sleep(0.05)
    QApplication.processEvents()
    assert win.ctl.project.runs and win.current_step() == "results"
    r = win.page["results"]
    for i in range(r.tabs.count()):
        r.tabs.setCurrentIndex(i)
        QApplication.processEvents()
    r.show_codes.setChecked(True)
    QApplication.processEvents()
    assert set(r.sched_model.df["Session 1"]) <= set(r.run.view().codes.values())


def test_printing(app, tmp_path):
    from randomizer_gui import printing
    p = EXAMPLES["human-crossover"]()
    p.settings["time_limit"] = 5
    spec, _ = p.build_spec()
    res = solve(spec)
    cal = {"start_date": "2026-11-02", "days_between": 7, "skip_weekends": True, "holidays": [],
           "start_column": ""}
    f1 = tmp_path / "daily.pdf"
    printing.daily_sheets_pdf(res, cal, str(f1), True, "Study")
    texts = printing.label_texts(res, cal, True, per_period=True)
    assert len(texts) == 18 * 3 and texts[0][-1] in res.codes.values()
    f2 = tmp_path / "labels.pdf"
    printing.labels_pdf(texts, str(f2), printing.LAYOUTS[0])
    html = printing.daily_sheets_html(res, cal, True, "Study")
    assert "Placebo" not in html and html.count("page-break-before") == 2
    for f in (f1, f2):
        assert f.stat().st_size > 2000 and f.read_bytes()[:4] == b"%PDF"


def test_wording_fields_keep_plurals_in_step(win):
    from randomizer_gui.pages.subjects import set_word
    win.open_example("rat-crossover")
    c = win.ctl
    set_word(c, "period_name", "Batch")
    assert c.project.settings["period_plural"] == "Batches"
    set_word(c, "period_plural", "Runs of the batch")            # a custom plural is kept...
    set_word(c, "period_name", "Run")
    assert c.project.settings["period_plural"] == "Runs of the batch"
    set_word(c, "subject_noun", "NHP")                            # an automatic plural follows the singular
    assert c.project.settings["subject_plural"] == "NHPs"
    assert c.project.settings["terms"] == "Custom words"


def test_tutorial_runs_once_and_can_be_replayed(win):
    import randomizer_gui.controller as C
    from PySide6.QtCore import QEvent, Qt
    from PySide6.QtGui import QKeyEvent
    C.settings_store().remove("tutorial_done")
    win.ctl.close()
    win.maybe_first_start()                         # first start: the tour opens by itself
    tour = win._tour
    assert tour is not None and tour.isVisible()
    for _ in range(5):
        tour.next()
        QApplication.processEvents()
    assert win.ctl.project is not None              # it opened an example to show the pages
    tour.back()
    assert tour.i == 4
    while win._tour is not None:
        tour.next()
        QApplication.processEvents()
    assert win.ctl.project is None                  # ...and closed it again at the end
    assert C.settings_store().value("tutorial_done", type=bool)
    win.maybe_first_start()
    assert win._tour is None                        # not again on the next start
    # replay with the user's own project: it stays open and unchanged
    win.open_example("human-crossover")
    win.ctl.dirty = False
    before = (dict(win.ctl.project.settings), win.ctl.project.subjects.copy())
    win.start_tutorial()
    for _ in range(3):
        win._tour.next()
    QApplication.sendEvent(win._tour, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    QApplication.processEvents()
    assert win._tour is None and win.ctl.project is not None and not win.ctl.dirty
    assert win.ctl.project.settings == before[0] and win.ctl.project.subjects.equals(before[1])
