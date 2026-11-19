"""The open project: every edit goes through here (undo/redo), plus saving, autosave and
crash recovery."""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSettings, QStandardPaths, QTimer, Signal
from PySide6.QtGui import QUndoCommand, QUndoStack

from randomizer.project import Project, now

AUTOSAVE_SECONDS = 30
MAX_RECENT = 8


def settings_store() -> QSettings:
    return QSettings("LIBRA", "LIBRA")


def recovery_dir() -> Path:
    base = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation) or Path.home() / ".libra")
    d = base / "recovery"
    d.mkdir(parents=True, exist_ok=True)
    return d


class _Snapshot(QUndoCommand):
    def __init__(self, ctl, before, after, text, merge_key):
        super().__init__(text)
        self.ctl, self.before, self.after, self.merge_key = ctl, before, after, merge_key
        self.stamp = time.monotonic()
        self._first = True

    def id(self):
        return 7 if self.merge_key else -1

    def mergeWith(self, other):
        if other.merge_key != self.merge_key or other.stamp - self.stamp > 2.5:
            return False
        self.after, self.stamp = other.after, other.stamp
        return True

    def redo(self):
        if self._first:            # the change was already applied when the command was pushed
            self._first = False
            return
        self.ctl._restore(self.after)

    def undo(self):
        self.ctl._restore(self.before)


class Controller(QObject):
    changed = Signal()             # settings or subjects changed: pages refresh
    runs_changed = Signal()
    project_changed = Signal()     # another project opened or closed
    dirty_changed = Signal(bool)
    saved = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project: Project | None = None
        self.undo = QUndoStack(self)
        self.dirty = False
        self._timer = QTimer(self)
        self._timer.setInterval(AUTOSAVE_SECONDS * 1000)
        self._timer.timeout.connect(self._autosave)
        self._timer.start()

    # ------------------------------------------------------------------ state and undo
    def _state(self):
        p = self.project
        return {"settings": copy.deepcopy(p.settings), "subjects": p.subjects.copy(), "name": p.name}

    @staticmethod
    def _same(a, b):
        return a["name"] == b["name"] and a["settings"] == b["settings"] and \
            a["subjects"].shape == b["subjects"].shape and a["subjects"].astype(str).equals(b["subjects"].astype(str)) \
            and list(a["subjects"].columns) == list(b["subjects"].columns)

    def _restore(self, st):
        p = self.project
        p.settings = copy.deepcopy(st["settings"])
        p.subjects = st["subjects"].copy()
        p.name = st["name"]
        self._set_dirty(True)
        self.changed.emit()

    def edit(self, text: str, fn, merge_key: str | None = None):
        """Apply fn(project) as one undoable step."""
        if self.project is None:
            return
        before = self._state()
        fn(self.project)
        after = self._state()
        if self._same(before, after):
            return
        self.undo.push(_Snapshot(self, before, after, text, merge_key))
        self._set_dirty(True)
        self.changed.emit()

    def set(self, key: str, value, text: str | None = None, merge: bool = False):
        """Set a setting; dotted keys reach into nested dicts (calendar.start_date)."""
        def fn(p):
            d = p.settings
            parts = key.split(".")
            for k in parts[:-1]:
                d = d[k]
            d[parts[-1]] = copy.deepcopy(value)
        self.edit(text or f"Change {key.split('.')[-1].replace('_', ' ')}", fn, key if merge else None)

    def get(self, key: str, default=None):
        d = self.project.settings
        for k in key.split("."):
            if not isinstance(d, dict) or k not in d:
                return default
            d = d[k]
        return d

    def set_subjects(self, df, text="Edit table"):
        self.edit(text, lambda p: setattr(p, "subjects", df.reset_index(drop=True)))

    def rename(self, name: str):
        name = name.strip() or "Untitled study"
        self.edit("Rename project", lambda p: setattr(p, "name", name))

    # ------------------------------------------------------------------ runs (not undoable: history)
    def runs_edited(self, autosave=True):
        self._set_dirty(True)
        self.runs_changed.emit()
        if autosave and self.project.path and self.autosave_enabled():
            self.save()

    # ------------------------------------------------------------------ files
    def _set_dirty(self, d: bool):
        if d != self.dirty:
            self.dirty = d
            self.dirty_changed.emit(d)

    def load(self, project: Project, dirty=False):
        self.discard_recovery()
        self.project = project
        self.undo.clear()
        self.dirty = dirty
        self.project_changed.emit()
        self.changed.emit()
        self.runs_changed.emit()
        self.dirty_changed.emit(dirty)
        if project.path:
            add_recent(project.path)

    def open(self, path: str):
        p = Project.load(path)
        p.event("Opened", Path(path).name)
        self.load(p)

    def save(self, path: str | None = None):
        p = self.project
        target = path or p.path
        if not target:
            raise ValueError("No file chosen")
        if path and path != p.path:
            p.event("Saved as", Path(path).name)
        p.save(target)
        self.undo.setClean()
        self._set_dirty(False)
        self.discard_recovery()
        add_recent(p.path)
        self.saved.emit(p.path)

    def close(self):
        self.discard_recovery()
        self.project = None
        self.undo.clear()
        self.dirty = False
        self.project_changed.emit()

    # ------------------------------------------------------------------ autosave and recovery
    @staticmethod
    def autosave_enabled() -> bool:
        return settings_store().value("autosave", True, type=bool)

    def _recovery_file(self) -> Path | None:
        return recovery_dir() / f"{self.project.id}.libra" if self.project else None

    def _autosave(self):
        if not self.project or not self.dirty:
            return
        if self.project.path and self.autosave_enabled():
            try:
                self.save()
                return
            except OSError:
                pass                       # e.g. the file is on a disconnected drive: keep a recovery copy
        try:
            d = self.project.to_dict()
            d["_recovery"] = {"path": self.project.path, "time": now()}
            self._recovery_file().write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def discard_recovery(self):
        f = self._recovery_file()
        if f and f.exists():
            try:
                f.unlink()
            except OSError:
                pass


def recovery_candidates() -> list[tuple[Path, dict]]:
    out = []
    for f in sorted(recovery_dir().glob("*.libra"), key=lambda q: q.stat().st_mtime, reverse=True):
        try:
            out.append((f, json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            continue
    return out


def recent_files() -> list[str]:
    v = settings_store().value("recent", [])
    if isinstance(v, str):
        v = [v]
    return [p for p in (v or []) if Path(p).exists()]


def add_recent(path: str):
    path = str(Path(path).resolve())
    items = [p for p in recent_files() if str(Path(p).resolve()) != path]
    settings_store().setValue("recent", [path] + items[:MAX_RECENT - 1])


def remove_recent(path: str):
    settings_store().setValue("recent", [p for p in recent_files() if p != path])
