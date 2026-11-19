"""Reusable widgets: cards, help popovers, segmented controls, banners, pandas tables."""
from __future__ import annotations

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (QAbstractButton, QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QLayout, QPushButton, QSizePolicy, QTableView, QToolButton, QVBoxLayout, QWidget)

from . import icons, theme
from .help_texts import HELP


def terms(settings: dict) -> dict:
    """The project's own words, ready for sentences ({one}, {Many}, {periods}, ...)."""
    from randomizer.spec import cap_first, plural_of, soft_lower
    one = settings["subject_noun"].strip() or "subject"
    many = settings["subject_plural"].strip() or plural_of(one)
    per = settings["period_name"].strip() or "Period"
    pers = str(settings.get("period_plural", "")).strip() or plural_of(per)
    return {"one": soft_lower(one), "many": soft_lower(many), "One": cap_first(one), "Many": cap_first(many),
            "period": soft_lower(per), "period_cap": cap_first(per),
            "periods": soft_lower(pers), "Periods": cap_first(pers)}


def fmt(text: str, t: dict) -> str:
    try:
        return text.format(**t)
    except (KeyError, IndexError, ValueError):
        return text


def discard(w):
    """Remove a widget at once (deleteLater alone leaves it visible until the event loop runs)."""
    if w is not None:
        w.hide()
        w.setParent(None)
        w.deleteLater()


def clear_layout(layout):
    """Remove every widget and nested layout from a layout."""
    while layout.count():
        it = layout.takeAt(0)
        if it.widget():
            discard(it.widget())
        elif it.layout():
            clear_layout(it.layout())


def logo(size: int) -> QLabel:
    """The LIBRA logo, rendered for the screen's real pixel density (sharp at 125 % / 150 %)."""
    from pathlib import Path
    from PySide6.QtGui import QGuiApplication, QPixmap
    lab = QLabel()
    path = Path(__file__).resolve().parent / "assets" / "logo.png"
    if path.exists():
        ratio = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
        px = round(size * ratio)
        pm = QPixmap(str(path)).scaled(px, px, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(ratio)
        lab.setPixmap(pm)
    lab.setFixedSize(size, size)
    return lab


def repolish(w: QWidget):
    w.style().unpolish(w)
    w.style().polish(w)
    w.update()


def label(text="", name=None, wrap=False, selectable=False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    if selectable:
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lab


def button(text="", icon_name=None, primary=False, flat=False, tip=None, big=False, danger=False) -> QPushButton:
    b = QPushButton(text)
    if icon_name:
        b.setIcon(icons.icon(icon_name, theme.tokens()["accent_text"] if primary else None))
        b._icon_name = icon_name
    if primary:
        b.setProperty("primary", True)
    if flat:
        b.setProperty("flat", True)
    if big:
        b.setProperty("big", True)
    if danger:
        b.setProperty("danger", True)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.PointingHandCursor)
    return b


def hbox(*items, spacing=8, margins=(0, 0, 0, 0), stretch_end=False) -> QHBoxLayout:
    lay = QHBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, int):
            lay.addSpacing(it)
        elif isinstance(it, QLayout):
            lay.addLayout(it)
        else:
            lay.addWidget(it)
    if stretch_end:
        lay.addStretch(1)
    return lay


def vbox(*items, spacing=8, margins=(0, 0, 0, 0)) -> QVBoxLayout:
    lay = QVBoxLayout()
    lay.setSpacing(spacing)
    lay.setContentsMargins(*margins)
    for it in items:
        if it is None:
            lay.addStretch(1)
        elif isinstance(it, int):
            lay.addSpacing(it)
        elif isinstance(it, QLayout):
            lay.addLayout(it)
        else:
            lay.addWidget(it)
    return lay


# ----------------------------------------------------------------------------- help popover
class HelpPopup(QFrame):
    def __init__(self, title, text, example, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_DeleteOnClose)
        width = 360
        lay = vbox(spacing=8, margins=(16, 14, 16, 14))
        lay.setSizeConstraint(QLayout.SetFixedSize)
        self.setLayout(lay)
        lay.addWidget(self._fit(label(title, "CardTitle", wrap=True), width))
        lay.addWidget(self._fit(label(text, wrap=True), width))
        if example:
            box = QFrame()
            box.setObjectName("Card")
            box.setProperty("flat", True)
            box.setLayout(vbox(self._fit(label("Example", "Muted"), width - 24),
                               self._fit(label(example, "Hint", wrap=True), width - 24),
                               spacing=3, margins=(12, 9, 12, 10)))
            lay.addWidget(box)

    @staticmethod
    def _fit(lab: QLabel, width: int) -> QLabel:
        """Give a wrapped label exactly the height its text needs (Qt underestimates it in popups,
        so the last line used to slide under the next box)."""
        lab.ensurePolished()
        r = lab.fontMetrics().boundingRect(QRect(0, 0, width, 100_000), Qt.TextWordWrap, lab.text())
        lab.setFixedSize(width, r.height() + 4)
        lab.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        return lab


class HelpButton(QToolButton):
    """A small (?) that shows a short explanation with an example."""

    def __init__(self, key: str, terms_fn=None, parent=None):
        super().__init__(parent)
        self.key, self.terms_fn = key, terms_fn
        self.setObjectName("HelpButton")
        self.setIcon(icons.icon("help", theme.tokens()["muted"], 16))
        self.setIconSize(QSize(16, 16))
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("What is this?")
        self.clicked.connect(self.show_help)

    def show_help(self):
        title, text, example = HELP[self.key]
        t = self.terms_fn() if self.terms_fn else {}
        pop = HelpPopup(fmt(title, t), fmt(text, t), fmt(example, t), self.window())
        pop.adjustSize()
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry()
        x = min(pos.x(), geo.right() - pop.width() - 8)
        y = pos.y() if pos.y() + pop.height() < geo.bottom() else self.mapToGlobal(QPoint(0, 0)).y() - pop.height() - 4
        pop.move(x, y)
        pop.show()


# ----------------------------------------------------------------------------- cards and banners
class Card(QFrame):
    def __init__(self, title=None, hint=None, help_key=None, terms_fn=None, flat=False, spacing=10):
        super().__init__()
        self.setObjectName("Card")
        if flat:
            self.setProperty("flat", True)
        self.outer = vbox(spacing=spacing, margins=(18, 16, 18, 18))
        self.setLayout(self.outer)
        self.title_label = self.hint_label = None
        if title:
            self.title_label = label(title, "CardTitle")
            row = hbox(self.title_label, spacing=6)
            if help_key:
                row.addWidget(HelpButton(help_key, terms_fn))
            row.addStretch(1)
            self.header = row
            self.outer.addLayout(row)
            if hint:
                self.hint_label = label(hint, "CardHint", wrap=True)
                self.outer.addWidget(self.hint_label)
        self.body = self.outer

    def add(self, w):
        if isinstance(w, QLayout):
            self.outer.addLayout(w)
        else:
            self.outer.addWidget(w)
        return w


class Banner(QFrame):
    ICONS = {"error": ("x-circle", "err"), "warning": ("alert", "warn"), "info": ("info", "info"),
             "ok": ("check-circle", "ok")}

    def __init__(self, kind="info", text="", parent=None):
        super().__init__(parent)
        self.setObjectName("Banner")
        self.icon = QLabel()
        self.text = label(text, wrap=True)
        self.text.setTextInteractionFlags(Qt.TextSelectableByMouse | Qt.LinksAccessibleByMouse)
        self.text.setOpenExternalLinks(False)
        self.extra = QHBoxLayout()
        self.extra.setSpacing(6)
        lay = hbox(self.icon, spacing=10, margins=(12, 9, 12, 9))
        lay.setAlignment(self.icon, Qt.AlignTop)
        lay.addWidget(self.text, 1)
        lay.addLayout(self.extra)
        self.setLayout(lay)
        self.set(kind, text)

    def set(self, kind, text):
        name, color = self.ICONS.get(kind, self.ICONS["info"])
        self.icon.setPixmap(icons.pixmap(name, 18, theme.tokens()[color]))
        self.text.setText(text)
        self.setProperty("kind", kind)
        repolish(self)


class Pill(QLabel):
    def __init__(self, text, kind="info"):
        super().__init__(text)
        self.setObjectName("Pill")
        self.setProperty("kind", kind)


class Chip(QLabel):
    def __init__(self, text, kind=""):
        super().__init__(text)
        self.setObjectName("Chip")
        if kind:
            self.setProperty("kind", kind)


# ----------------------------------------------------------------------------- segmented control
class Segmented(QWidget):
    changed = Signal(str)

    """Painted by hand: style-sheet borders on the widget's edge were cut off at 125 % / 150 % display
    scaling. The outline is drawn half a pixel inside the edge, which stays sharp at any scale."""
    PAD_X, RADIUS = 14, 7

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(parent)
        self.options = list(options)
        self._index = -1
        self._hover = -1
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    # ---------------------------------------------------------------- value
    def value(self):
        return self.options[self._index][0] if self._index >= 0 else None

    def set_value(self, value):
        i = next((k for k, (v, _) in enumerate(self.options) if v == value), -1)
        if i != self._index:
            self._index = i
            self.update()

    def _choose(self, i):
        if 0 <= i < len(self.options) and self.isEnabled():
            changed = i != self._index
            self._index = i
            self.update()
            if changed:
                self.changed.emit(self.options[i][0])

    # ---------------------------------------------------------------- geometry
    def _widths(self):
        fm = self.fontMetrics()
        return [fm.horizontalAdvance(t) + 2 * self.PAD_X for _, t in self.options]

    def sizeHint(self):
        return QSize(sum(self._widths()) + 1, max(30, self.fontMetrics().height() + 14))

    def minimumSizeHint(self):
        return self.sizeHint()

    def _edges(self):
        w = self._widths()
        scale = (self.width() - 1) / max(1, sum(w))
        xs = [0.0]
        for v in w:
            xs.append(xs[-1] + v * scale)
        return xs

    def _at(self, x):
        xs = self._edges()
        return next((i for i in range(len(self.options)) if xs[i] <= x < xs[i + 1]), -1)

    # ---------------------------------------------------------------- events
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.setFocus(Qt.MouseFocusReason)
            self._choose(self._at(e.position().x()))

    def mouseMoveEvent(self, e):
        h = self._at(e.position().x())
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Left, Qt.Key_Up):
            self._choose(max(0, self._index - 1))
        elif e.key() in (Qt.Key_Right, Qt.Key_Down):
            self._choose(min(len(self.options) - 1, self._index + 1))
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e):
        super().changeEvent(e)
        self.update()

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
        t = theme.tokens()
        on = self.isEnabled()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(outer, self.RADIUS, self.RADIUS)
        p.fillPath(path, QColor(t["surface"] if on else t["surface2"]))
        xs = self._edges()
        p.save()
        p.setClipPath(path)
        for i in range(len(self.options)):
            seg = QRectF(xs[i] + 0.5, outer.top(), xs[i + 1] - xs[i], outer.height())
            if i == self._index:
                if on:
                    from PySide6.QtGui import QLinearGradient
                    g = QLinearGradient(seg.bottomLeft(), seg.topRight())
                    g.setColorAt(0, QColor(t["grad_a"]))
                    g.setColorAt(1, QColor(t["grad_b"]))
                    p.fillRect(seg, g)
                else:
                    p.fillRect(seg, QColor(t["border"]))
            elif i == self._hover and on:
                p.fillRect(seg, QColor(t["sunken"]))
        p.restore()
        p.setPen(QPen(QColor(t["border_strong"] if on else t["border"]), 1))
        for i in range(1, len(self.options)):
            if self._index not in (i - 1, i):              # no line next to the filled segment
                x = round(xs[i]) + 0.5
                p.drawLine(x, outer.top(), x, outer.bottom())
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if self.hasFocus():
            p.setPen(QPen(QColor(t["accent"]), 1))
            p.drawPath(path)
        for i, (_, text) in enumerate(self.options):
            seg = QRectF(xs[i], 0, xs[i + 1] - xs[i], self.height())
            if i == self._index:
                color = t["accent_text"] if on else t["muted"]
            else:
                color = t["text"] if on else t["muted"]
            p.setPen(QColor(color))
            p.drawText(seg, Qt.AlignCenter, text)
        p.end()


class ChoiceCard(QPushButton):
    """A large checkable button with a title and a description."""

    def __init__(self, title, desc):
        super().__init__()
        self.setObjectName("ChoiceCard")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.t = label(title, "CardTitle")
        self.d = label(desc, "Hint", wrap=True)
        for w in (self.t, self.d):
            w.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setLayout(vbox(self.t, self.d, spacing=3, margins=(14, 10, 14, 10)))
        self.setMinimumHeight(68)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def sizeHint(self):
        return QSize(180, max(68, self.layout().sizeHint().height() + 4))


# ----------------------------------------------------------------------------- flow layout
class FlowLayout(QLayout):
    def __init__(self, parent=None, spacing=6):
        super().__init__(parent)
        self.items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self.items.append(item)

    def count(self):
        return len(self.items)

    def itemAt(self, i):
        return self.items[i] if 0 <= i < len(self.items) else None

    def takeAt(self, i):
        return self.items.pop(i) if 0 <= i < len(self.items) else None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._do(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self.items:
            s = s.expandedTo(it.minimumSize())
        return s

    def clear(self):
        while self.items:
            it = self.items.pop()
            if it.widget():
                discard(it.widget())

    def _do(self, rect, test):
        x, y, line = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self.items:
            hint = it.sizeHint()
            nx = x + hint.width() + sp
            if nx - sp > rect.right() and line > 0:
                x, y = rect.x(), y + line + sp
                nx, line = x + hint.width() + sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x, line = nx, max(line, hint.height())
        return y + line - rect.y()


# ----------------------------------------------------------------------------- pandas table
class DataFrameModel(QAbstractTableModel):
    """Table model on a DataFrame. Editable models emit `edited(df)` with a changed copy instead of
    changing the frame in place (so every edit can go through undo/redo)."""
    edited = Signal(object)

    def __init__(self, df: pd.DataFrame | None = None, editable=False, colors=None, columns_colored=None):
        super().__init__()
        self.df = df if df is not None else pd.DataFrame()
        self.editable = editable
        self.colors = colors or {}                 # value -> (fill, ink)
        self.columns_colored = set(columns_colored or [])
        self.formats = {}                          # column -> python format, e.g. "{:.0%}"

    def set_frame(self, df: pd.DataFrame, colors=None, columns_colored=None):
        self.beginResetModel()
        self.df = df
        if colors is not None:
            self.colors = colors
        if columns_colored is not None:
            self.columns_colored = set(columns_colored)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.df)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.df.columns)

    def _text(self, v, col):
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return ""
        f = self.formats.get(col)
        if f:
            try:
                return f.format(v)
            except (ValueError, TypeError):
                pass
        if isinstance(v, (float, np.floating)) and float(v).is_integer():
            return str(int(v))
        return str(v)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        col = self.df.columns[index.column()]
        v = self.df.iat[index.row(), index.column()]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return self._text(v, col)
        if col in self.columns_colored:
            pair = self.colors.get(str(v))
            if pair and role == Qt.BackgroundRole:
                return QColor(pair[0])
            if pair and role == Qt.ForegroundRole:
                return QColor(pair[1])
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self.df.columns[section]) if section < len(self.df.columns) else None
        return str(section + 1)

    def flags(self, index):
        f = Qt.ItemIsSelectable | Qt.ItemIsEnabled
        if self.editable:
            f |= Qt.ItemIsEditable
        return f

    def setData(self, index, value, role=Qt.EditRole):
        if role != Qt.EditRole or not self.editable:
            return False
        self.write_block(index.row(), index.column(), [[value]])
        return True

    def write_block(self, r0, c0, rows):
        """Write a block of text values at (r0, c0), adding rows as needed; emits edited(df)."""
        df = self.df.copy()
        need = r0 + len(rows) - len(df)
        if need > 0:
            df = pd.concat([df, pd.DataFrame([[""] * len(df.columns)] * need, columns=df.columns)],
                           ignore_index=True)
        df = df.astype(object)
        for i, row in enumerate(rows):
            for j, v in enumerate(row):
                if c0 + j < len(df.columns):
                    df.iat[r0 + i, c0 + j] = str(v).strip()
        self.edited.emit(df)


class DataTable(QTableView):
    """Table view with Excel-style copy, paste and delete."""
    paste_with_header = Signal(list)       # rows of text when pasting into an empty table

    def __init__(self, model: DataFrameModel, parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.m = model
        self.setAlternatingRowColors(True)
        self.verticalHeader().setDefaultSectionSize(28)
        self.verticalHeader().setMinimumWidth(36)
        self.horizontalHeader().setStretchLastSection(False)
        self.horizontalHeader().setDefaultSectionSize(120)
        self.setSelectionMode(QTableView.ExtendedSelection)
        self.setEditTriggers(QTableView.DoubleClicked | QTableView.EditKeyPressed | QTableView.AnyKeyPressed)
        self.setHorizontalScrollMode(QTableView.ScrollPerPixel)
        self.setVerticalScrollMode(QTableView.ScrollPerPixel)

    def keyPressEvent(self, e):
        if e.matches(QKeySequence.Copy):
            self.copy_selection()
        elif e.matches(QKeySequence.Paste) and self.m.editable:
            self.paste()
        elif e.key() in (Qt.Key_Delete, Qt.Key_Backspace) and self.m.editable and \
                self.state() != QTableView.EditingState:
            self.clear_selection_cells()
        else:
            super().keyPressEvent(e)

    def copy_selection(self):
        idx = self.selectedIndexes()
        if not idx:
            return
        rows = sorted({i.row() for i in idx})
        cols = sorted({i.column() for i in idx})
        lines = []
        if len(rows) == self.m.rowCount() or len(idx) > 1:
            lines.append("\t".join(str(self.m.df.columns[c]) for c in cols))
        for r in rows:
            lines.append("\t".join(self.m.data(self.m.index(r, c)) or "" for c in cols))
        QApplication.clipboard().setText("\n".join(lines))

    def paste(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        rows = [line.split("\t") for line in text.rstrip("\r\n").replace("\r\n", "\n").split("\n")]
        empty = self.m.rowCount() == 0 or self.m.df.replace("", np.nan).dropna(how="all").empty
        if empty:
            self.paste_with_header.emit(rows)
            return
        cur = self.currentIndex()
        r0, c0 = (cur.row(), cur.column()) if cur.isValid() else (self.m.rowCount(), 0)
        self.m.write_block(r0, c0, rows)

    def clear_selection_cells(self):
        idx = self.selectedIndexes()
        if not idx:
            return
        df = self.m.df.copy().astype(object)
        for i in idx:
            df.iat[i.row(), i.column()] = ""
        self.m.edited.emit(df)


def frame_line() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"color: {theme.tokens()['border']};")
    return f
