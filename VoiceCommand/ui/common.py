"""
UI common utilities (UI Common Utilities)
Collects the repeated widget-creation and layout-manipulation patterns in one place.

Main exports:
  - clear_layout()       remove every widget in a layout at once
  - apply_shadow()       apply a QGraphicsDropShadowEffect
  - create_input_field() QLineEdit with unified styling
  - create_icon_button() icon button factory
  - show_temp_status()   timer-based temporary status message
  - FloatingPanel        frameless floating window base class
"""
from typing import Callable, Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
    QLabel, QLayout, QLineEdit, QMainWindow, QPushButton, QVBoxLayout,
    QWidget,
)

from ui import theme as theme_module


# ── Layout utilities ─────────────────────────────────────────────────────────────

def clear_layout(layout: QLayout) -> None:
    """Safely remove every widget in a layout and release its memory."""
    while layout.count():
        item = layout.takeAt(0)
        if item and item.widget():
            # Hide first so the previous widget is not painted on top before it is deleted.
            item.widget().hide()
            item.widget().deleteLater()


# ── Visual effect utilities ────────────────────────────────────────────────────────────

def apply_shadow(
    widget: QWidget,
    blur_radius: int = theme_module.SHADOW_BLUR,
    offset_y: int = theme_module.SHADOW_OFFSET,
) -> None:
    """Apply a drop shadow effect to a widget."""
    shadow = QGraphicsDropShadowEffect(widget)
    shadow.setBlurRadius(blur_radius)
    shadow.setColor(Qt.black)
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)


# ── Widget factory ───────────────────────────────────────────────────────────────

def create_input_field(
    placeholder: str = "",
    font_size: int = theme_module.FONT_SIZE_NORMAL,
    height: int = 32,
) -> QLineEdit:
    """Create a QLineEdit with the theme style applied."""
    w = QLineEdit()
    w.setPlaceholderText(placeholder)
    w.setFont(QFont(theme_module.FONT_KO, font_size))
    w.setFixedHeight(height)
    w.setStyleSheet(theme_module.INPUT_STYLE)
    return w


def create_icon_button(
    icon: str,
    tooltip: str,
    size: int,
    color: str,
    callback: Optional[Callable] = None,
) -> QPushButton:
    """Create an icon button. If a callback is given, connect it to clicked."""
    btn = QPushButton(icon)
    btn.setFixedSize(size, size)
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setStyleSheet(theme_module.icon_btn_style(color, size))
    if callback:
        btn.clicked.connect(callback)
    return btn


def create_section_label(text: str, color: str = "") -> QLabel:
    """Create a section header label."""
    lbl = QLabel(text)
    lbl.setFont(QFont(theme_module.FONT_KO, theme_module.FONT_SIZE_NORMAL, QFont.Bold))
    lbl.setStyleSheet(f"color: {color or theme_module.COLOR_PRIMARY};")
    return lbl


def create_muted_label(text: str) -> QLabel:
    """Create a muted secondary text label."""
    lbl = QLabel(text)
    lbl.setFont(QFont(theme_module.FONT_KO, theme_module.FONT_SIZE_NORMAL))
    lbl.setStyleSheet(f"color: {theme_module.COLOR_MUTED};")
    return lbl


# ── Status message ───────────────────────────────────────────────────────────────

def show_temp_status(
    label: QLabel,
    msg: str,
    duration_ms: int = theme_module.TEMP_STATUS_DURATION,
) -> None:
    """Show a message on the label and clear it automatically after duration_ms."""
    label.setText(msg)
    QTimer.singleShot(duration_ms, label, lambda: label.setText(""))


# ── Common title bar ────────────────────────────────────────────────────────────

class PanelTitleBar(QFrame):
    """Common title bar with drag-to-move and a Close button.

    Used automatically by classes based on FloatingPanel.
    Call add_button() from a subclass if you need extra buttons.
    """

    def __init__(self, title: str, parent: QMainWindow):
        super().__init__(parent)
        self._win = parent
        self._drag_pos = None
        self.setFixedHeight(theme_module.TITLEBAR_HEIGHT)
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(14, 0, 10, 0)

        self._title_lbl = QLabel(title)
        self._title_lbl.setFont(QFont(theme_module.FONT_KO, theme_module.FONT_SIZE_TITLE, QFont.Bold))
        self._lay.addWidget(self._title_lbl)
        self._lay.addStretch()

        # The Close button is always rightmost
        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(30, 30)
        self._close_btn.setCursor(Qt.PointingHandCursor)
        self._close_btn.clicked.connect(parent.hide)
        self._lay.addWidget(self._close_btn)
        self.refresh_theme()

    def add_button(
        self,
        icon: str,
        tooltip: str,
        callback: Callable,
        size: int = theme_module.BUTTON_LG,
    ) -> QPushButton:
        """Add an icon button before the Close button."""
        btn = QPushButton(icon)
        btn.setFixedSize(size, size)
        btn.setToolTip(tooltip)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton { background: rgba(255,255,255,15); color: white;
                           border: none; border-radius: 16px; font-size: 14px; }
            QPushButton:hover { background: rgba(255,255,255,35); }
        """)
        btn.clicked.connect(callback)
        # Insert right before the Close button (index=-1)
        count = self._lay.count()
        self._lay.insertWidget(count - 1, btn)
        return btn

    def refresh_theme(self) -> None:
        self.setFixedHeight(theme_module.TITLEBAR_HEIGHT)
        self.setStyleSheet(f"""
            QFrame {{ background-color: {theme_module.COLOR_TITLEBAR};
                      border-top-left-radius: {theme_module.RADIUS_LG};
                      border-top-right-radius: {theme_module.RADIUS_LG}; }}
        """)
        self._title_lbl.setFont(QFont(theme_module.FONT_KO, theme_module.FONT_SIZE_TITLE, QFont.Bold))
        self._title_lbl.setStyleSheet("color: white;")
        self._close_btn.setStyleSheet(theme_module.close_btn_style())

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self._win.pos()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self._win.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None


# ── Frameless floating panel base class ───────────────────────────────────────

class FloatingPanel(QMainWindow):
    """Frameless floating panel base class with a translucent background.

    When subclassing:
      1. super().__init__(title, width, height, parent)
      2. add content to self.content_layout
      3. use self.title_bar.add_button(...) if you need title bar buttons

    Example:
        class MyPanel(FloatingPanel):
            def __init__(self):
                super().__init__("🔧 My Panel", 400, 500)
                lbl = QLabel("Content")
                self.content_layout.addWidget(lbl)
    """

    def __init__(
        self,
        title: str,
        width: int,
        height: int,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.resize(width, height)
        self._title_text = title
        self._build_shell(title)

    def _build_shell(self, title: str) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(theme_module.MARGIN_PANEL, theme_module.MARGIN_PANEL, theme_module.MARGIN_PANEL, theme_module.MARGIN_PANEL)

        self._bg_frame = QFrame()
        self._bg_frame.setObjectName("FloatingPanelBg")
        apply_shadow(self._bg_frame, theme_module.SHADOW_BLUR_LG, theme_module.SHADOW_OFFSET_SM)
        outer.addWidget(self._bg_frame)

        self._bg_layout = QVBoxLayout(self._bg_frame)
        self._bg_layout.setContentsMargins(0, 0, 0, 0)
        self._bg_layout.setSpacing(0)

        self.title_bar = PanelTitleBar(title, self)
        self._bg_layout.addWidget(self.title_bar)

        # Layout that subclasses add widgets to
        content_widget = QWidget()
        content_widget.setObjectName("FloatingPanelContent")
        content_widget.setStyleSheet(f"#FloatingPanelContent {{ background: {theme_module.COLOR_BG_PANEL}; }}")
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(0)
        self._bg_layout.addWidget(content_widget)
        self.refresh_shell_theme()

    def show_near(self, x: int, y: int) -> None:
        """Show near the given coordinates without leaving the screen bounds."""
        screen = QApplication.primaryScreen().geometry()
        fx = min(x + 10, screen.width() - self.width() - 10)
        fy = max(20, min(y, screen.height() - self.height() - 40))
        self.move(fx, fy)
        self.show()
        self.activateWindow()

    def refresh_shell_theme(self) -> None:
        central = self.centralWidget()
        if central and central.layout():
            central.layout().setContentsMargins(
                theme_module.MARGIN_PANEL,
                theme_module.MARGIN_PANEL,
                theme_module.MARGIN_PANEL,
                theme_module.MARGIN_PANEL,
            )
        self._bg_frame.setStyleSheet(f"""
            #FloatingPanelBg {{ background-color: {theme_module.COLOR_BG_PANEL};
                                border-radius: {theme_module.RADIUS_LG};
                                border: 1px solid {theme_module.COLOR_BORDER_LIGHT}; }}
        """)
        for idx in range(self._bg_layout.count()):
            item = self._bg_layout.itemAt(idx)
            widget = item.widget() if item else None
            if widget and widget.objectName() == "FloatingPanelContent":
                widget.setStyleSheet(f"#FloatingPanelContent {{ background: {theme_module.COLOR_BG_PANEL}; }}")
        apply_shadow(self._bg_frame, theme_module.SHADOW_BLUR_LG, theme_module.SHADOW_OFFSET_SM)
        self.title_bar.refresh_theme()
