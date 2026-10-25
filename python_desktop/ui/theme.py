"""Тёмная и светлая темы: палитра Qt (стиль Fusion) и таблица стилей."""
from string import Template
from typing import Dict

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

THEMES: Dict[str, Dict[str, str]] = {
    "dark": {
        "window": "#0a0a0a", "panel": "#171717", "base": "#121214", "text": "#e5e5e5",
        "heading": "#ffffff", "muted": "#a1a1aa", "faint": "#71717a", "border": "#262626",
        "field_border": "#27272a", "btn": "#1f1f23", "btn_hover": "#2a2a30", "btn_border": "#2e2e34",
        "btn_hover_border": "#3f3f46", "accent": "#4f46e5", "accent_hover": "#4338ca",
        "accent_text": "#a5b4fc", "accent_strong": "#6366f1", "list_bg": "#141417",
        "item_hover": "#1f1f24", "item_selected": "#27272a", "progress_bg": "#14141d",
        "progress_border": "#4338ca", "expand_bg": "#1e1b4b", "expand_hover": "#312e81",
        "expand_text": "#a5b4fc", "revert_bg": "#2e1f0f", "revert_hover": "#452c14",
        "revert_border": "#b45309", "revert_text": "#fcd34d", "amber": "#fbbf24",
        "nav_idle": "#18191d", "bar_bg": "#18191d", "highlight_text": "#ffffff",
    },
    "light": {
        "window": "#f4f4f5", "panel": "#ffffff", "base": "#ffffff", "text": "#18181b",
        "heading": "#09090b", "muted": "#52525b", "faint": "#a1a1aa", "border": "#d4d4d8",
        "field_border": "#d4d4d8", "btn": "#f4f4f5", "btn_hover": "#e4e4e7", "btn_border": "#d4d4d8",
        "btn_hover_border": "#a1a1aa", "accent": "#4f46e5", "accent_hover": "#4338ca",
        "accent_text": "#4338ca", "accent_strong": "#4f46e5", "list_bg": "#ffffff",
        "item_hover": "#f4f4f5", "item_selected": "#e0e7ff", "progress_bg": "#eef2ff",
        "progress_border": "#6366f1", "expand_bg": "#eef2ff", "expand_hover": "#e0e7ff",
        "expand_text": "#4338ca", "revert_bg": "#fffbeb", "revert_hover": "#fef3c7",
        "revert_border": "#d97706", "revert_text": "#92400e", "amber": "#b45309",
        "nav_idle": "#ffffff", "bar_bg": "#e4e4e7", "highlight_text": "#ffffff",
    },
}

THEME_CHOICES = (("dark", "Тёмная"), ("light", "Светлая"), ("system", "Как в системе"))

_STYLESHEET = Template("""
QMainWindow, QDialog, QMessageBox { background-color: $window; }
QWidget { color: $text; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
QToolTip { background-color: $panel; color: $text; border: 1px solid $border; }
QFrame#headerBar { background-color: $panel; border-bottom: 1px solid $border; }
QFrame#sidebar { background-color: $panel; border-right: 1px solid $border; }
QFrame#card { background-color: $panel; border: 1px solid $border; border-radius: 12px; }
QFrame#progressCard { background-color: $progress_bg; border: 1px solid $progress_border; border-radius: 12px; }
QLabel { background: transparent; }
QLabel#brand { color: $heading; }
QLabel#muted { color: $muted; font-size: 12px; }
QLabel#hint { color: $muted; font-size: 11px; }
QLabel#accentText { color: $accent_text; font-size: 12px; font-weight: 500; }
QLabel#stageText { color: $accent_text; font-size: 12px; font-weight: 600; }
QLabel#timerLabel { color: $accent_strong; padding: 14px; }
QLabel#emptyState { color: $faint; padding: 24px; }
QLabel#deadlineText { color: $amber; font-size: 11px; }
QLabel#taskTitle { color: $heading; font-size: 13px; font-weight: 600; }
QLabel#taskTitleDone { color: $faint; font-size: 13px; text-decoration: line-through; }
QLabel#storageInfo { font-size: 13px; }
QLabel#cardTitle { font-size: 14px; font-weight: 600; }
QPushButton { background-color: $btn; border: 1px solid $btn_border; border-radius: 8px; padding: 7px 13px; font-size: 12px; font-weight: 500; color: $text; }
QPushButton:hover { background-color: $btn_hover; border-color: $btn_hover_border; }
QPushButton:disabled { color: $faint; }
QPushButton#primaryBtn { background-color: $accent; border: none; color: #ffffff; font-weight: 600; }
QPushButton#primaryBtn:hover { background-color: $accent_hover; }
QPushButton#expandAiBtn { background-color: $expand_bg; border: 1px solid $progress_border; color: $expand_text; font-weight: 600; }
QPushButton#expandAiBtn:hover { background-color: $expand_hover; }
QPushButton#revertBtn { background-color: $revert_bg; border: 1px solid $revert_border; color: $revert_text; font-weight: 600; }
QPushButton#revertBtn:hover { background-color: $revert_hover; }
QPushButton#recordBtn { background-color: #e11d48; border: none; color: #ffffff; font-weight: 600; padding: 12px 24px; font-size: 13px; border-radius: 10px; }
QPushButton#recordBtn:hover { background-color: #be123c; }
QPushButton#recordBtn:disabled { background-color: $btn; color: $faint; }
QPushButton#navBtn { text-align: left; padding: 10px 12px; background-color: $nav_idle; color: $text; }
QPushButton#navBtn[active="true"] { background-color: $accent; color: #ffffff; font-weight: 600; }
QLineEdit, QComboBox, QTextEdit { background-color: $base; border: 1px solid $field_border; border-radius: 8px; padding: 8px 12px; font-size: 13px; color: $text; selection-background-color: $accent; selection-color: #ffffff; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid $accent_strong; }
QComboBox QAbstractItemView { background-color: $base; color: $text; selection-background-color: $accent; selection-color: #ffffff; border: 1px solid $field_border; }
QListWidget { background-color: $list_bg; border: 1px solid $border; border-radius: 10px; padding: 6px; }
QListWidget::item { padding: 12px; border-radius: 8px; margin: 3px 0px; }
QListWidget::item:hover { background-color: $item_hover; }
QListWidget::item:selected { background-color: $item_selected; color: $text; border-left: 3px solid $accent_strong; }
QProgressBar { border: 1px solid $field_border; border-radius: 6px; text-align: center; height: 16px; background-color: $bar_bg; color: $text; font-size: 11px; font-weight: 600; }
QProgressBar::chunk { background-color: $accent; border-radius: 5px; }
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical { background: transparent; width: 10px; }
QScrollBar::handle:vertical { background: $btn_hover_border; border-radius: 5px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { spacing: 8px; }
""")


def resolve_theme(name: str) -> str:
    """Превращает «system» в «dark» или «light» по настройке ОС."""
    if name in ("dark", "light"):
        return name
    try:
        from PySide6.QtCore import Qt
        scheme = QApplication.styleHints().colorScheme()
        return "light" if scheme == Qt.ColorScheme.Light else "dark"
    except Exception:
        return "dark"


def _build_palette(t: Dict[str, str]) -> QPalette:
    pal = QPalette()
    roles = {
        QPalette.Window: t["window"], QPalette.WindowText: t["text"], QPalette.Base: t["base"],
        QPalette.AlternateBase: t["panel"], QPalette.Text: t["text"], QPalette.Button: t["btn"],
        QPalette.ButtonText: t["text"], QPalette.ToolTipBase: t["panel"], QPalette.ToolTipText: t["text"],
        QPalette.Highlight: t["accent"], QPalette.HighlightedText: t["highlight_text"],
        QPalette.PlaceholderText: t["faint"], QPalette.Link: t["accent_text"],
    }
    for role, color in roles.items():
        pal.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["faint"]))
    return pal


def apply_theme(app: QApplication, name: str) -> bool:
    """Применяет тему ко всему приложению. Возвращает True, если тема тёмная."""
    resolved = resolve_theme(name)
    tokens = THEMES[resolved]
    app.setStyle("Fusion")
    app.setPalette(_build_palette(tokens))
    app.setStyleSheet(_STYLESHEET.substitute(tokens))
    return resolved == "dark"
