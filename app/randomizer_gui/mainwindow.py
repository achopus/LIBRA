from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame, QLineEdit, QMainWindow,
                               QMessageBox, QPushButton, QStackedWidget, QToolButton, QVBoxLayout, QWidget)

from randomizer import APP_TITLE, __version__
from randomizer.examples import EXAMPLES
from randomizer.prechecks import precheck
from randomizer.project import EXT, Project

from . import icons, theme
from .controller import (Controller, recent_files, recovery_candidates, remove_recent, settings_store)
from .dialogs import AboutDialog, NewProjectDialog
from .pages.balance import BalancePage
from .pages.generate import GeneratePage
from .pages.results import ResultsPage
from .pages.rules import RulesPage
from .pages.start import StartPage
from .pages.subjects import SubjectsPage
from .pages.treatments import TreatmentsPage
from .widgets import hbox, label, logo, terms, vbox

FILTER = f"LIBRA projects (*{EXT})"
STEPS = [("subjects", "{Many}", "users"), ("treatments", "Treatments", "flask"), ("rules", "Rules", "shield"),
         ("balance", "Balance", "sliders"), ("generate", "Generate", "play"), ("results", "Results", "table")]


def app_icon() -> QIcon:
    base = Path(__file__).resolve().parent / "assets"
    ic = QIcon()
    for f in ("icon.png", "icon.ico"):
        if (base / f).exists():
            ic.addFile(str(base / f))
    return ic


class MainWindow(QMainWindow):
    rebuild_requested = Signal()

    def __init__(self, ctl: Controller | None = None):
        super().__init__()
        self.ctl = ctl or Controller()
        self.ctl.setParent(None)
        self.setWindowIcon(app_icon())
        self.resize(1320, 860)
        self.setMinimumSize(980, 640)
        self._findings = []
        self._stale = set()

        self.stack = QStackedWidget()
        self.start = StartPage()
        self.stack.addWidget(self.start)
        self.workspace = self._build_workspace()
        self.stack.addWidget(self.workspace)
        self.setCentralWidget(self.stack)
        self._build_menus()

        self.start.new_requested.connect(self.new_project)
        self.start.open_requested.connect(self.open_dialog)
        self.start.open_path.connect(self.open_file)
        self.start.open_example.connect(self.open_example)
        self.start.tour_requested.connect(self.start_tutorial)
        self._tour = None
        self._tour_example = False
        c = self.ctl
        c.changed.connect(self._on_changed)
        c.runs_changed.connect(self._on_runs)
        c.project_changed.connect(self._on_project)
        # bound methods (not lambdas): Qt disconnects them when this window is deleted
        c.dirty_changed.connect(self._update_title)
        c.saved.connect(self._update_title)
        c.undo.canUndoChanged.connect(self._can_undo)
        c.undo.canRedoChanged.connect(self._can_redo)
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.setInterval(250)
        self._check_timer.timeout.connect(self._run_checks)
        self._on_project()

    # ------------------------------------------------------------------ layout
    def _build_workspace(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(230)
        title = label("LIBRA", "AppTitle")
        sub = label("Crossover Randomizer", "AppSubtitle")
        self.step_group = QButtonGroup(self)
        self.step_buttons = {}
        steps = QVBoxLayout()
        steps.setSpacing(2)
        for i, (key, text, icon_name) in enumerate(STEPS):
            b = QPushButton()
            b.setObjectName("StepButton")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setIconSize(QSize(18, 18))
            b._icon_name = icon_name
            b.clicked.connect(lambda _=False, k=key: self.go(k))
            self.step_group.addButton(b)
            self.step_buttons[key] = b
            steps.addWidget(b)
        theme_btn = QToolButton()
        theme_btn.setProperty("flat", True)
        theme_btn.setIcon(icons.icon("moon" if not theme.is_dark() else "sun"))
        theme_btn.setToolTip("Switch between light and dark")
        theme_btn.clicked.connect(lambda: self.set_theme("light" if theme.is_dark() else "dark"))
        about_btn = QToolButton()
        about_btn.setProperty("flat", True)
        about_btn.setIcon(icons.icon("info"))
        about_btn.setToolTip("About and how to cite")
        about_btn.clicked.connect(lambda: AboutDialog(self).exec())
        home_btn = QToolButton()
        home_btn.setProperty("flat", True)
        home_btn.setIcon(icons.icon("arrow-left"))
        home_btn.setToolTip("Close the project and go to the start screen")
        home_btn.clicked.connect(self.close_project)
        foot = label("Offline · nothing is sent online", "SidebarFoot")
        side.setLayout(vbox(hbox(logo(34), vbox(title, sub, spacing=0), None, spacing=10), 14, steps, None, foot,
                            hbox(home_btn, None, theme_btn, about_btn, spacing=2),
                            spacing=8, margins=(14, 18, 14, 12)))

        top = QFrame()
        top.setObjectName("TopBar")
        self.name_edit = QLineEdit()
        self.name_edit.setObjectName("ProjectName")
        self.name_edit.setMinimumWidth(280)
        self.name_edit.setToolTip("Project name (click to rename)")
        self.name_edit.editingFinished.connect(lambda: self.ctl.project and self.name_edit.text().strip() != self.ctl.project.name
                                               and self.ctl.rename(self.name_edit.text()))
        self.save_state = label("", "SaveState")
        self.undo_btn = self._tool("undo", "Undo (Ctrl+Z)", lambda: self.ctl.undo.undo())
        self.redo_btn = self._tool("redo", "Redo (Ctrl+Y)", lambda: self.ctl.undo.redo())
        save_btn = self.save_btn = self._tool("save", "Save (Ctrl+S)", self.save)
        self.top_generate = QPushButton("Generate")
        self.top_generate.setProperty("primary", True)
        self.top_generate.setIcon(icons.icon("play", theme.tokens()["accent_text"]))
        self.top_generate.setCursor(Qt.PointingHandCursor)
        self.top_generate.clicked.connect(lambda: self.go("generate"))
        top.setLayout(hbox(self.name_edit, self.save_state, None, self.undo_btn, self.redo_btn, save_btn, 8,
                           self.top_generate, spacing=4, margins=(18, 8, 18, 8)))

        self.pages = QStackedWidget()
        self.page = {
            "subjects": SubjectsPage(self.ctl), "treatments": TreatmentsPage(self.ctl),
            "rules": RulesPage(self.ctl), "balance": BalancePage(self.ctl),
            "generate": GeneratePage(self.ctl), "results": ResultsPage(self.ctl),
        }
        for p in self.page.values():
            self.pages.addWidget(p)
        self.page["generate"].goto.connect(self.go)
        self.page["generate"].generated.connect(self._generated)
        self.page["results"].retry.connect(self._retry)

        right = QWidget()
        right.setLayout(vbox(top, self.pages, spacing=0))
        w = QWidget()
        w.setLayout(hbox(side, right, spacing=0))
        return w

    def _tool(self, icon_name, tip, fn):
        b = QToolButton()
        b.setProperty("flat", True)
        b.setIcon(icons.icon(icon_name))
        b.setIconSize(QSize(18, 18))
        b.setToolTip(tip)
        b.clicked.connect(fn)
        return b

    def _build_menus(self):
        mb = self.menuBar()
        f = mb.addMenu("&File")
        f.addAction("New project…", self.new_project, QKeySequence.New)
        f.addAction("Open…", self.open_dialog, QKeySequence.Open)
        self.recent_menu = f.addMenu("Open recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent)
        f.addSeparator()
        self.act_save = f.addAction("Save", self.save, QKeySequence.Save)
        self.act_save_as = f.addAction("Save as…", self.save_as, QKeySequence("Ctrl+Shift+S"))
        self.act_export = f.addAction("Export…", self.export, QKeySequence("Ctrl+E"))
        f.addSeparator()
        auto = f.addAction("Save automatically")
        auto.setCheckable(True)
        auto.setChecked(settings_store().value("autosave", True, type=bool))
        auto.toggled.connect(lambda on: settings_store().setValue("autosave", on))
        f.addSeparator()
        self.act_close = f.addAction("Close project", self.close_project)
        f.addAction("Quit", self.close, QKeySequence.Quit)
        e = mb.addMenu("&Edit")
        self.act_undo = e.addAction("Undo", lambda: self.ctl.undo.undo(), QKeySequence.Undo)
        self.act_redo = e.addAction("Redo", lambda: self.ctl.undo.redo(), QKeySequence.Redo)
        e.addSeparator()
        self.act_generate = e.addAction("Generate schedule", self.generate_now, QKeySequence("Ctrl+G"))
        v = mb.addMenu("&View")
        tm = v.addMenu("Theme")
        grp = QActionGroup(self)
        cur = settings_store().value("theme", "system")
        for mode, text in (("system", "Same as the system"), ("light", "Light"), ("dark", "Dark")):
            a = QAction(text, self, checkable=True)
            a.setChecked(mode == cur)
            a.triggered.connect(lambda _=False, m=mode: self.set_theme(m))
            grp.addAction(a)
            tm.addAction(a)
        h = mb.addMenu("&Help")
        h.addAction("Show the tutorial", self.start_tutorial)
        h.addSeparator()
        about = h.addAction("About and how to cite", lambda: AboutDialog(self).exec())
        about.setMenuRole(QAction.AboutRole)                 # macOS: goes to the app menu

    def _fill_recent(self):
        self.recent_menu.clear()
        for p in recent_files():
            self.recent_menu.addAction(Path(p).name, lambda q=p: self.open_file(q)).setToolTip(p)
        if not self.recent_menu.actions():
            self.recent_menu.addAction("(none)").setEnabled(False)

    # ------------------------------------------------------------------ navigation
    def go(self, step: str):
        if self.ctl.project is None:
            return
        if self.stack.currentWidget() is not self.workspace:
            self.stack.setCurrentWidget(self.workspace)
        b = self.step_buttons[step]
        if not b.isEnabled():
            return
        b.setChecked(True)
        page = self.page[step]
        self.pages.setCurrentWidget(page)
        if step in self._stale or step == "results":
            self._stale.discard(step)
            page.refresh()

    def current_step(self) -> str:
        w = self.pages.currentWidget()
        return next(k for k, p in self.page.items() if p is w)

    def _generated(self, run_id):
        self.page["results"].refresh_runs(run_id)
        self.go("results")

    def _retry(self):
        self.go("generate")
        self.page["generate"].retry_more_time()

    def generate_now(self):
        if self.ctl.project is None:
            return
        self.go("generate")
        g = self.page["generate"]
        if g.go.isEnabled():
            g.start()

    # ------------------------------------------------------------------ reactions
    def _on_project(self):
        p = self.ctl.project
        has = p is not None
        for a in (self.act_save, self.act_save_as, self.act_export, self.act_close, self.act_generate):
            a.setEnabled(has)
        self.act_undo.setEnabled(False)
        self.act_redo.setEnabled(False)
        self.undo_btn.setEnabled(False)
        self.redo_btn.setEnabled(False)
        if not has:
            self.start.build()
            self.stack.setCurrentWidget(self.start)
            self._update_title()
            return
        self.stack.setCurrentWidget(self.workspace)
        self._stale = set(self.page)
        # fill everything now (a window rebuilt for a new theme gets no "changed" signal of its own)
        self.page["results"].refresh_runs()
        self._run_checks()
        self.go("results" if p.runs else "subjects")
        self._on_changed()
        self._update_title()

    def _on_changed(self):
        p = self.ctl.project
        if p is None:
            return
        if self.name_edit.text() != p.name and not self.name_edit.hasFocus():
            self.name_edit.setText(p.name)
        cur = self.current_step()
        self._stale = set(self.page) - {cur}
        self.page[cur].refresh()
        self._update_steps_text()
        self._check_timer.start()

    def _on_runs(self):
        if self.ctl.project is None:
            return
        self.page["results"].refresh_runs()
        self._update_steps()
        for k in self.page:
            if k != self.current_step():
                self._stale.add(k)
        if self.current_step() != "results":
            self.page[self.current_step()].refresh()

    def _run_checks(self):
        p = self.ctl.project
        if p is None:
            return
        try:
            self._findings = precheck(p.settings, p.subjects)
        except Exception as e:  # noqa: BLE001 - never break the UI on a check
            from randomizer.prechecks import Finding
            self._findings = [Finding("error", "subjects", f"Could not check the settings: {e}")]
        for key in ("rules", "balance", "generate"):
            self.page[key].set_findings(self._findings)
        self._update_steps()

    def _update_steps_text(self):
        t = terms(self.ctl.project.settings)
        for i, (key, text, _) in enumerate(STEPS):
            b = self.step_buttons[key]
            label_text = text.format(**t)
            if key == "results" and self.ctl.project.runs:
                label_text += f"  ({len(self.ctl.project.runs)})"
            b.setText(f"  {label_text}")

    def _update_steps(self):
        tk = theme.tokens()
        for key, b in self.step_buttons.items():
            rel = [f for f in self._findings if f.step == key]
            if any(f.level == "error" for f in rel):
                b.setIcon(icons.icon("x-circle", tk["err"]))
                b.setToolTip(" ".join(f.text for f in rel if f.level == "error"))
            elif any(f.level == "warning" for f in rel):
                b.setIcon(icons.icon("alert", tk["warn"]))
                b.setToolTip(" ".join(f.text for f in rel if f.level == "warning"))
            elif key in ("generate", "results"):
                b.setIcon(icons.icon(b._icon_name))
                b.setToolTip("")
            else:
                b.setIcon(icons.icon("check-circle", tk["ok"]))
                b.setToolTip("No problems")
        has_runs = bool(self.ctl.project and self.ctl.project.runs)
        self.step_buttons["results"].setEnabled(has_runs)
        self._update_steps_text()

    def _can_undo(self, ok):
        self.undo_btn.setEnabled(ok)
        self.act_undo.setEnabled(ok)

    def _can_redo(self, ok):
        self.redo_btn.setEnabled(ok)
        self.act_redo.setEnabled(ok)

    def _update_title(self, *_):
        p = self.ctl.project
        if p is None:
            self.setWindowTitle(APP_TITLE)
            return
        star = " •" if self.ctl.dirty else ""
        self.setWindowTitle(f"{p.name}{star} — LIBRA")
        if not self.name_edit.hasFocus():
            self.name_edit.setText(p.name)
        if p.path is None:
            self.save_state.setText("Not saved yet")
        elif self.ctl.dirty:
            self.save_state.setText("Unsaved changes")
        else:
            self.save_state.setText(f"Saved · {Path(p.path).name}")
        self.save_state.setToolTip(p.path or "")

    # ------------------------------------------------------------------ files
    def maybe_save(self) -> bool:
        """True when it is fine to discard the current project."""
        p = self.ctl.project
        if p is None or not self.ctl.dirty:
            return True
        if p.path and self.ctl.autosave_enabled():
            try:
                self.ctl.save()
                return True
            except OSError:
                pass
        r = QMessageBox.question(self, "Unsaved changes", f"Save the changes to “{p.name}”?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Save)
        if r == QMessageBox.Cancel:
            return False
        if r == QMessageBox.Save:
            return self.save()
        return True

    def new_project(self):
        if not self.maybe_save():
            return
        dlg = NewProjectDialog(self)
        if not dlg.exec():
            return
        proj, path = dlg.project()
        proj.event("Project created", proj.name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            proj.save(path)
        except OSError as e:
            QMessageBox.warning(self, "Could not save", f"{e}\n\nThe project is open but not saved yet.")
        self.ctl.load(proj)

    def open_dialog(self):
        if not self.maybe_save():
            return
        start = str(Path(self.ctl.project.path).parent) if self.ctl.project and self.ctl.project.path else ""
        path, _ = QFileDialog.getOpenFileName(self, "Open project", start, FILTER + ";;All files (*)")
        if path:
            self.open_file(path, asked=True)

    def open_file(self, path: str, asked=False):
        if not asked and not self.maybe_save():
            return
        try:
            self.ctl.open(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Could not open the project", str(e))
            if not Path(path).exists():
                remove_recent(path)
                self.start.build()

    def open_example(self, key: str):
        if not self.maybe_save():
            return
        proj = EXAMPLES[key]()
        proj.event("Created from example", proj.name)
        self.ctl.load(proj, dirty=True)

    def save(self) -> bool:
        p = self.ctl.project
        if p is None:
            return False
        if not p.path:
            return self.save_as()
        try:
            self.ctl.save()
            return True
        except OSError as e:
            QMessageBox.warning(self, "Could not save", str(e))
            return False

    def save_as(self) -> bool:
        p = self.ctl.project
        if p is None:
            return False
        from .dialogs import documents_folder, safe_name
        base = Path(p.path).parent if p.path else documents_folder()
        base.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self, "Save project", str(base / f"{safe_name(p.name)}{EXT}"), FILTER)
        if not path:
            return False
        if not path.endswith(EXT):
            path += EXT
        try:
            self.ctl.save(path)
            return True
        except OSError as e:
            QMessageBox.warning(self, "Could not save", str(e))
            return False

    def export(self):
        p = self.ctl.project
        if p is None:
            return
        if not p.runs:
            QMessageBox.information(self, "Export", "Generate a schedule first.")
            return
        self.go("results")
        self.page["results"].export()

    def close_project(self):
        if self.maybe_save():
            self.ctl.close()

    def set_theme(self, mode):
        settings_store().setValue("theme", mode)
        theme.apply(QApplication.instance(), mode)
        self.rebuild_requested.emit()

    # ------------------------------------------------------------------ tutorial
    def start_tutorial(self):
        """Guided tour of the app (first start, Help menu, start screen)."""
        from .tutorial import Tour
        if self._tour is not None:
            return
        self._tour = Tour(self, on_done=self._tutorial_done)
        self._tour.start()

    def tour_open_project(self):
        """The tour needs a study to show: open the rat example if nothing is open."""
        if self.ctl.project is None:
            self.open_example("rat-crossover")
            self.ctl.dirty = False
            self._tour_example = True

    def _tutorial_done(self):
        self._tour = None
        settings_store().setValue("tutorial_done", True)
        if self._tour_example:                     # close the example the tour opened, without asking
            self._tour_example = False
            self.ctl.dirty = False
            self.ctl.close()
        elif self.ctl.project is None:
            self.stack.setCurrentWidget(self.start)

    def maybe_first_start(self):
        """Recovery first; then, on the very first start, the tutorial."""
        self.check_recovery()
        if not settings_store().value("tutorial_done", False, type=bool):
            self.start_tutorial()

    def check_recovery(self):
        for f, d in recovery_candidates():
            rec = d.get("_recovery", {})
            when = rec.get("time", "").replace("T", " ")
            r = QMessageBox.question(
                self, "Recover unsaved work",
                f"The app closed unexpectedly while “{d.get('name', 'a project')}” had unsaved changes "
                f"(last copy {when}).\n\nRecover these changes?",
                QMessageBox.Yes | QMessageBox.Discard, QMessageBox.Yes)
            if r == QMessageBox.Yes:
                try:
                    proj = Project.from_dict(d)
                    proj.path = rec.get("path")
                    proj.event("Recovered after a crash", when)
                    self.ctl.load(proj, dirty=True)
                except ValueError as e:
                    QMessageBox.warning(self, "Could not recover", str(e))
                try:
                    f.unlink()
                except OSError:
                    pass
                return
            try:
                f.unlink()
            except OSError:
                pass

    def closeEvent(self, e):
        if getattr(self, "_rebuilding", False):
            e.accept()
            return
        g = self.page["generate"].progress
        if g.running():
            if QMessageBox.question(self, "Still generating", "A schedule is being generated. Stop it and quit?") \
                    != QMessageBox.Yes:
                e.ignore()
                return
            g.cancel()
        if self.maybe_save():
            self.ctl.discard_recovery()
            e.accept()
        else:
            e.ignore()
