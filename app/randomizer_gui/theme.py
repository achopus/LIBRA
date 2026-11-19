"""Light and dark themes: color tokens, a Qt palette and one style sheet built from the tokens."""
from __future__ import annotations

import sys

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette
from PySide6.QtCore import Qt

LIGHT = {
    "bg": "#f4f5f7", "surface": "#ffffff", "surface2": "#f7f8fa", "sunken": "#eef0f3",
    "border": "#dfe2e7", "border_strong": "#c7ccd4",
    "text": "#1a1d23", "text2": "#555d69", "muted": "#8a919c",
    "accent": "#d9411a", "accent_hover": "#bb3012", "accent_text": "#ffffff", "accent_soft": "#fcebe4",
    "grad_a": "#f47216", "grad_b": "#d3062a", "grad_a_hover": "#e0600c", "grad_b_hover": "#b5001f",
    "ok": "#a07800", "ok_soft": "#faf3dc", "warn": "#b4520a", "warn_soft": "#fdebdc",     # gold; burnt orange
    "err": "#c42b2b", "err_soft": "#fdecec", "info": "#4b5563", "info_soft": "#eef0f3",
    "sidebar": "#fbfbfc", "selection": "#f9d9cc",
}
DARK = {
    "bg": "#15171b", "surface": "#1d2025", "surface2": "#22262c", "sunken": "#191c20",
    "border": "#30353d", "border_strong": "#424852",
    "text": "#e7e9ec", "text2": "#a9b0ba", "muted": "#7c838e",
    "accent": "#ff8a47", "accent_hover": "#ffa06a", "accent_text": "#ffffff", "accent_soft": "#3a2119",
    "grad_a": "#f47216", "grad_b": "#d3062a", "grad_a_hover": "#ff8a2e", "grad_b_hover": "#e8103a",
    "ok": "#e3b341", "ok_soft": "#2a2412", "warn": "#f08a45", "warn_soft": "#33200f",
    "err": "#f06a6a", "err_soft": "#371b1d", "info": "#a9b0ba", "info_soft": "#23272d",
    "sidebar": "#181a1e", "selection": "#5a2c1e",
}

_current = dict(LIGHT)


def tokens() -> dict:
    return _current


def is_dark() -> bool:
    return _current is DARK or _current == DARK


def system_prefers_dark() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


def base_font() -> QFont:
    f = QFont()
    if sys.platform == "win32":
        f.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
        f.setPointSizeF(10)
    else:
        f.setPointSizeF(13 if sys.platform == "darwin" else 10)
    return f


QSS = """
* { outline: none; }
QWidget { color: %(text)s; }
QMainWindow, #Page, #StartPage, QScrollArea > QWidget > QWidget#PageBody { background: %(bg)s; }
QScrollArea { background: transparent; border: none; }
QToolTip { background: %(surface)s; color: %(text)s; border: 1px solid %(border_strong)s; padding: 6px 8px;
           border-radius: 6px; }

/* ---------- sidebar */
#Sidebar { background: %(sidebar)s; border-right: 1px solid %(border)s; }
#AppTitle { font-size: 15px; font-weight: 600; }
#AppSubtitle, #SidebarFoot { color: %(muted)s; font-size: 12px; }
#StepButton { text-align: left; border: none; border-radius: 8px; padding: 9px 10px; background: transparent;
              color: %(text2)s; font-size: 13px; }
#StepButton:hover { background: %(sunken)s; color: %(text)s; }
#StepButton:checked { background: %(accent_soft)s; color: %(text)s; font-weight: 600; }
#StepButton:disabled { color: %(muted)s; }

/* ---------- top bar */
#TopBar { background: %(surface)s; border-bottom: 1px solid %(border)s; }
#ProjectName { font-size: 15px; font-weight: 600; border: 1px solid transparent; border-radius: 6px;
               padding: 3px 6px; background: transparent; }
#ProjectName:hover { border-color: %(border)s; }
#ProjectName:focus { border-color: %(accent)s; background: %(surface)s; }
#SaveState { color: %(muted)s; font-size: 12px; }

/* ---------- headings and text */
#PageTitle { font-size: 22px; font-weight: 600; }
#PageLead { color: %(text2)s; font-size: 13px; }
#CardTitle { font-size: 14px; font-weight: 600; }
#CardHint, #Hint { color: %(text2)s; font-size: 12px; }
#Muted { color: %(muted)s; }
#Big { font-size: 26px; font-weight: 600; }
#Mono { font-family: "Cascadia Mono", "Consolas", "SF Mono", "Menlo", monospace; }

/* ---------- cards */
#Card { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; }
#Card[flat="true"] { background: %(surface2)s; }
#ExampleCard { background: %(surface)s; border: 1px solid %(border)s; border-radius: 10px; text-align: left;
               padding: 0; min-height: 88px; }
#RecentItem { background: transparent; border: 1px solid transparent; border-radius: 8px; text-align: left;
              padding: 0; min-height: 50px; }
#RecentItem:hover { background: %(sunken)s; }
#ExampleCard:hover { border-color: %(accent)s; background: %(surface2)s; }

/* ---------- buttons */
QPushButton, QToolButton { background: %(surface)s; border: 1px solid %(border_strong)s; border-radius: 7px;
              padding: 6px 12px; min-height: 18px; }
QPushButton:hover, QToolButton:hover { background: %(surface2)s; border-color: %(muted)s; }
QPushButton:pressed, QToolButton:pressed { background: %(sunken)s; }
QPushButton:disabled, QToolButton:disabled { color: %(muted)s; border-color: %(border)s; background: %(surface2)s; }
QPushButton[primary="true"] { background: qlineargradient(x1:0, y1:1, x2:1, y2:0, stop:0 %(grad_a)s,
              stop:1 %(grad_b)s); color: %(accent_text)s; border: 1px solid transparent;
              font-weight: 600; }
QPushButton[primary="true"]:hover { background: qlineargradient(x1:0, y1:1, x2:1, y2:0,
              stop:0 %(grad_a_hover)s, stop:1 %(grad_b_hover)s); border-color: transparent; }
QPushButton[primary="true"]:disabled { background: %(border)s; border-color: %(border)s; color: %(muted)s; }
QPushButton[big="true"] { padding: 10px 22px; font-size: 14px; }
QPushButton[danger="true"] { color: %(err)s; }
QPushButton[flat="true"], QToolButton[flat="true"] { background: transparent; border: 1px solid transparent; }
QPushButton[flat="true"]:hover, QToolButton[flat="true"]:hover { background: %(sunken)s; }
QToolButton::menu-indicator { image: none; width: 0; }
#HelpButton { border: none; background: transparent; padding: 0; min-height: 0; }

/* segmented control */
#Segment QPushButton { border-radius: 0; border-right-width: 0; padding: 5px 14px; background: %(surface)s; }
#Segment QPushButton[pos="first"] { border-top-left-radius: 7px; border-bottom-left-radius: 7px; }
#Segment QPushButton[pos="last"] { border-top-right-radius: 7px; border-bottom-right-radius: 7px;
                                   border-right-width: 1px; }
#Segment QPushButton:checked { background: %(accent)s; color: %(accent_text)s; border-color: %(accent)s;
                               font-weight: 600; }
#Segment QPushButton:disabled:checked { background: %(border)s; color: %(muted)s; border-color: %(border)s; }

/* choice cards (design type) */
#ChoiceCard { background: %(surface)s; border: 1px solid %(border)s; border-radius: 9px; text-align: left;
              padding: 0; margin: 1px; }
#ChoiceCard:hover { border-color: %(border_strong)s; }
#ChoiceCard:checked { border: 2px solid %(accent)s; background: %(accent_soft)s; margin: 0; }

/* ---------- inputs */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QPlainTextEdit, QTextEdit {
    background: %(surface)s; border: 1px solid %(border_strong)s; border-radius: 6px; padding: 5px 8px;
    selection-background-color: %(selection)s; selection-color: %(text)s; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateEdit:focus,
QPlainTextEdit:focus, QTextEdit:focus { border: 1px solid %(accent)s; }
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled { color: %(muted)s; background: %(surface2)s; }
QLineEdit[invalid="true"] { border: 1px solid %(err)s; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 24px; }
QComboBox::down-arrow, QDateEdit::down-arrow { image: url(%(arrow_down)s); width: 12px; height: 12px; }
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: url(%(arrow_up)s); width: 10px; height: 10px; }
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: url(%(arrow_down)s); width: 10px; height: 10px; }
QSpinBox::up-arrow:disabled, QSpinBox::down-arrow:disabled, QComboBox::down-arrow:disabled { image: none; }
QComboBox QAbstractItemView { background: %(surface)s; border: 1px solid %(border_strong)s;
    selection-background-color: %(selection)s; selection-color: %(text)s; padding: 4px; }
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QDateEdit::up-button, QDateEdit::down-button { width: 16px; border: none; }
QCheckBox, QRadioButton { spacing: 8px; }
QCheckBox::indicator, QRadioButton::indicator { width: 16px; height: 16px; border: 1px solid %(border_strong)s;
    background: %(surface)s; border-radius: 4px; }
QRadioButton::indicator { border-radius: 9px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked { background: qlineargradient(x1:0, y1:1, x2:1, y2:0, stop:0 %(grad_a)s,
    stop:1 %(grad_b)s); border-color: %(grad_b)s; image: url(%(check)s); }
QRadioButton::indicator:checked { background: %(surface)s; border: 5px solid %(accent)s; width: 8px; height: 8px; }
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled { background: %(surface2)s; border-color: %(border)s; }
QCheckBox::indicator:checked:disabled { background: %(border_strong)s; }

/* ---------- tables */
QTableView, QTableWidget, QListWidget, QTreeWidget {
    background: %(surface)s; alternate-background-color: %(surface2)s; border: 1px solid %(border)s;
    border-radius: 8px; gridline-color: %(border)s; selection-background-color: %(selection)s;
    selection-color: %(text)s; }
QHeaderView::section { background: %(surface2)s; color: %(text2)s; border: none;
    border-bottom: 1px solid %(border)s; border-right: 1px solid %(border)s; padding: 6px 8px; font-weight: 600; }
QTableCornerButton::section { background: %(surface2)s; border: none; border-bottom: 1px solid %(border)s; }
QListWidget::item { padding: 6px 8px; border-radius: 6px; }
QListWidget::item:selected { background: %(accent_soft)s; color: %(text)s; }
QListWidget::item:hover:!selected { background: %(sunken)s; }

/* ---------- tabs */
QTabWidget::pane { border: none; top: -1px; }
QTabBar::tab { background: transparent; color: %(text2)s; padding: 8px 14px; border: none;
               border-bottom: 2px solid transparent; margin-right: 2px; }
QTabBar::tab:selected { color: %(text)s; border-bottom: 2px solid %(accent)s; font-weight: 600; }
QTabBar::tab:hover:!selected { color: %(text)s; }

/* ---------- progress, scroll bars, menus */
QProgressBar { background: %(sunken)s; border: none; border-radius: 4px; height: 8px; text-align: center;
               color: transparent; }
QProgressBar::chunk { background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 %(grad_a)s,
    stop:1 %(grad_b)s); border-radius: 4px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 4px; min-height: 30px; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(border_strong)s; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QMenuBar { background: %(surface)s; border-bottom: 1px solid %(border)s; }
QMenuBar::item { padding: 4px 10px; background: transparent; }
QMenuBar::item:selected { background: %(sunken)s; border-radius: 4px; }
QMenu { background: %(surface)s; border: 1px solid %(border_strong)s; padding: 4px; border-radius: 8px; }
QMenu::item { padding: 6px 24px 6px 12px; border-radius: 5px; }
QMenu::item:selected { background: %(accent_soft)s; color: %(text)s; }
QMenu::item:disabled { color: %(muted)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 4px 6px; }
QDialog { background: %(bg)s; }
QSplitter::handle { background: %(border)s; }

/* ---------- banners */
#Banner { border-radius: 8px; border: 1px solid %(border)s; }
#Banner[kind="error"] { background: %(err_soft)s; border-color: %(err)s; }
#Banner[kind="warning"] { background: %(warn_soft)s; border-color: %(warn)s; }
#Banner[kind="info"] { background: %(info_soft)s; border-color: %(info_soft)s; }
#Banner[kind="ok"] { background: %(ok_soft)s; border-color: %(ok_soft)s; }
#Pill { border-radius: 9px; padding: 1px 8px; font-size: 11px; font-weight: 600; }
#Pill[kind="final"] { background: %(ok_soft)s; color: %(ok)s; }
#Pill[kind="info"] { background: %(info_soft)s; color: %(info)s; }
#Pill[kind="warn"] { background: %(warn_soft)s; color: %(warn)s; }
#Chip { background: %(sunken)s; border-radius: 6px; padding: 3px 8px; color: %(text2)s; font-size: 12px; }
#Chip[kind="fixed"] { background: %(warn_soft)s; color: %(warn)s; }
"""


def apply(app, mode: str = "system"):
    """mode: light, dark or system."""
    global _current
    dark = mode == "dark" or (mode == "system" and system_prefers_dark())
    _current = DARK if dark else LIGHT
    t = _current
    app.setStyle("Fusion")
    pal = QPalette()
    for role, key in [(QPalette.Window, "bg"), (QPalette.Base, "surface"), (QPalette.AlternateBase, "surface2"),
                      (QPalette.Text, "text"), (QPalette.WindowText, "text"), (QPalette.Button, "surface"),
                      (QPalette.ButtonText, "text"), (QPalette.Highlight, "selection"),
                      (QPalette.HighlightedText, "text"), (QPalette.ToolTipBase, "surface"),
                      (QPalette.ToolTipText, "text"), (QPalette.PlaceholderText, "muted"),
                      (QPalette.Link, "accent"), (QPalette.Mid, "border"), (QPalette.Dark, "border_strong")]:
        pal.setColor(role, QColor(t[key]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(t["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.WindowText, QColor(t["muted"]))
    app.setPalette(pal)
    app.setFont(base_font())
    app.setStyleSheet(QSS % {**t, **_arrows(t["text2"]), "check": _arrows(t["accent_text"])["check"]})


def _arrows(color: str) -> dict:
    """Small chevron images for combo and spin boxes (style sheets need files)."""
    import tempfile
    from pathlib import Path
    d = Path(tempfile.gettempdir()) / "libra-ui"
    d.mkdir(exist_ok=True)
    out = {}
    for name, path in (("arrow_down", "m6 9 6 6 6-6"), ("arrow_up", "m6 15 6-6 6 6"), ("check", "M5 12.5 10 17 19 7")):
        f = d / f"{name}-{color.strip('#')}.svg"
        if not f.exists():
            f.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
                         f'stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">'
                         f'<path d="{path}"/></svg>', encoding="utf-8")
        out[name] = f.as_posix()
    return out
