"""Application theme and shared UI helpers."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QAbstractButton, QApplication, QComboBox, QLabel

DARK = {
    "bg": "#12141a",
    "panel": "#171a22",
    "card": "#1e222c",
    "cardHover": "#242936",
    "border": "#2a3040",
    "text": "#e7eaf2",
    "muted": "#8b93a7",
    "accent": "#5b8cff",
    "accentHover": "#7ba3ff",
    "accentDim": "#33477a",
    "danger": "#ff5c72",
    "success": "#3ddc84",
    "warning": "#f4b860",
}

LIGHT = {
    "bg": "#f3f5fa",
    "panel": "#ffffff",
    "card": "#ffffff",
    "cardHover": "#eef2fb",
    "border": "#d8ddea",
    "text": "#1a1f2b",
    "muted": "#667085",
    "accent": "#3b6cf6",
    "accentHover": "#2f5de0",
    "accentDim": "#dbe5ff",
    "danger": "#d92d4b",
    "success": "#12a150",
    "warning": "#b7791f",
}

DARK_QSS = """
* { outline: 0; }
QWidget { background: transparent; color: @text; font-size: 13px; }
QMainWindow, QDialog { background: @bg; }
QToolTip {
    background: @card; color: @text; border: 1px solid @border;
    padding: 5px 8px; border-radius: 6px;
}
QFrame#Card {
    background: @card; border: 1px solid @border; border-radius: 10px;
}
QFrame#Panel { background: @panel; border-right: 1px solid @border; }
QLabel#H1 { font-size: 22px; font-weight: 700; }
QLabel#H2 { font-size: 16px; font-weight: 600; }
QLabel#Muted { color: @muted; }
QLabel#StatusPill {
    background: @card; border: 1px solid @border; border-radius: 10px;
    padding: 3px 9px; color: @muted; font-size: 12px;
}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPlainTextEdit {
    background: @card; border: 1px solid @border; border-radius: 8px;
    padding: 7px 10px; selection-background-color: @accent;
    min-height: 20px;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: @accent; }
QLineEdit:disabled, QComboBox:disabled { color: @muted; }
QLineEdit#UrlInput { font-size: 14px; padding: 9px 12px; }
QComboBox::drop-down { border: 0; width: 22px; }
QComboBox QAbstractItemView {
    background: @card; border: 1px solid @border; selection-background-color: @accentDim;
    padding: 4px;
}
QPushButton {
    background: @card; border: 1px solid @border; border-radius: 8px;
    padding: 7px 14px; color: @text;
}
QPushButton:hover { background: @cardHover; border-color: @accentDim; }
QPushButton:pressed { background: @accentDim; }
QPushButton:disabled { color: @muted; background: @panel; }
QPushButton#Primary {
    background: @accent; border: 1px solid @accent; color: #ffffff; font-weight: 600;
}
QPushButton#Primary:hover { background: @accentHover; }
QPushButton#Primary:disabled { background: @accentDim; border-color: @accentDim; color: @muted; }
QPushButton#Flat { background: transparent; border: 0; color: @muted; padding: 5px 9px; }
QPushButton#Flat:hover { color: @text; background: @card; }
QPushButton#Danger { background: transparent; border: 1px solid @border; color: @danger; }
QPushButton#Danger:hover { background: rgba(255, 92, 114, 0.12); border-color: @danger; }
QPushButton#Icon { background: transparent; border: 0; border-radius: 6px; padding: 4px 7px; }
QPushButton#Icon:hover { background: @cardHover; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar { background: transparent; }
QTabBar::tab {
    background: transparent; color: @muted; padding: 9px 18px;
    border: 0; border-bottom: 2px solid transparent; font-weight: 600;
}
QTabBar::tab:hover { color: @text; }
QTabBar::tab:selected { color: @text; border-bottom: 2px solid @accent; }
QProgressBar {
    background: @bg; border: 1px solid @border; border-radius: 6px;
    min-height: 12px; max-height: 12px; text-align: center; color: transparent;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 @accent, stop:1 #8ab0ff);
    border-radius: 5px;
}
QScrollArea { border: 0; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: @border; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: @muted; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border; border-radius: 5px; min-width: 30px; }
QTableWidget, QTableWidget QTableCornerButton::section {
    background: @card; border: 1px solid @border; border-radius: 8px;
    gridline-color: @border; alternate-background-color: @panel;
}
QTableWidget::item { padding: 6px; border: 0; }
QTableWidget::item:selected { background: @accentDim; color: @text; }
QHeaderView::section {
    background: @panel; color: @muted; border: 0; border-bottom: 1px solid @border;
    padding: 7px 8px; font-weight: 600;
}
QListWidget {
    background: @card; border: 1px solid @border; border-radius: 8px; padding: 4px;
}
QListWidget::item { padding: 6px; border-radius: 6px; }
QListWidget::item:selected { background: @accentDim; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border: 1px solid @border; border-radius: 4px;
    background: @card;
}
QCheckBox::indicator:checked { background: @accent; border-color: @accent; }
QGroupBox {
    border: 1px solid @border; border-radius: 10px; margin-top: 12px;
    padding: 14px 12px 10px 12px; background: @panel; font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 12px; padding: 0 5px; color: @muted;
}
QMenu {
    background: @card; border: 1px solid @border; border-radius: 8px; padding: 5px;
}
QMenu::item { padding: 6px 22px; border-radius: 5px; }
QMenu::item:selected { background: @accentDim; }
QStatusBar { background: @panel; border-top: 1px solid @border; color: @muted; }
QStatusBar::item { border: 0; }
QStatusBar QLabel { padding: 0 9px; }
QSplitter::handle { background: @border; }
"""


def _render(qss: str, colors: dict[str, str]) -> str:
    out = qss
    for key, value in colors.items():
        out = out.replace(f"@{key}", value)
    return out


class _PointerCursorFilter(QObject):
    """Give clickable controls a hand cursor (QSS has no ``cursor`` property).

    Also watches enabled state so disabled buttons fall back to the arrow.
    """

    _WIDGETS = (QAbstractButton, QComboBox)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if isinstance(watched, self._WIDGETS) and event.type() in (
            QEvent.Type.Polish,
            QEvent.Type.EnabledChange,
        ):
            self._apply(watched)
        return False

    @staticmethod
    def _apply(widget) -> None:
        if widget.isEnabled():
            if widget.cursor().shape() != Qt.CursorShape.PointingHandCursor:
                widget.setCursor(Qt.CursorShape.PointingHandCursor)
        elif widget.cursor().shape() != Qt.CursorShape.ArrowCursor:
            widget.unsetCursor()


def _install_pointer_cursors(app: QApplication) -> None:
    if getattr(app, "_pointer_cursor_filter", None) is not None:
        return
    pointer_filter = _PointerCursorFilter(app)
    app._pointer_cursor_filter = pointer_filter  # type: ignore[attr-defined]
    app.installEventFilter(pointer_filter)
    for widget in app.allWidgets():
        if isinstance(widget, _PointerCursorFilter._WIDGETS):
            _PointerCursorFilter._apply(widget)


def apply_theme(app: QApplication, theme: str = "dark") -> None:
    app.setStyle("Fusion")
    colors = LIGHT if theme == "light" else DARK
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["card"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["panel"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["card"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["card"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["muted"]))
    app.setPalette(palette)
    qss = _render(DARK_QSS, colors)
    # Table editor polish that depends on theme.
    qss += f"""
    QHeaderView::section {{ background: {colors['panel']}; }}
    """
    app.setStyleSheet(qss)
    _install_pointer_cursors(app)


def muted(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("Muted")
    return label
