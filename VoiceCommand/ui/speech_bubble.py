"""
Speech bubble widget (based on the original implementation)
"""
import os
import logging
import re
import threading
from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Qt, QRect, QPoint
from PySide6.QtGui import QPainter, QColor, QFont, QFontMetrics, QFontDatabase, QPolygon

from ui import theme as theme_module

_MARKDOWN_MARKS = re.compile(r"\*\*|__|`+|^\s{0,3}#{1,6}\s+", re.MULTILINE)


def _plain_bubble_text(text: str) -> str:
    """The speech bubble strips markdown emphasis, headings, and code markers."""
    return _MARKDOWN_MARKS.sub("", text or "")


_font_family = None  # Global font family name cache
_font_family_lock = threading.Lock()


def register_fonts():
    """Register the font when the application starts (preferably called on the main thread)"""
    global _font_family
    if _font_family is not None:
        return _font_family

    with _font_family_lock:
        if _font_family is not None:
            return _font_family

        try:
            from core.resource_manager import ResourceManager
            font_path = ResourceManager.get_bundle_path("DNFBitBitv2.ttf")
        except Exception:
            font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "DNFBitBitv2.ttf")

        if os.path.exists(font_path):
            font_id = QFontDatabase.addApplicationFont(font_path)
            if font_id != -1:
                families = QFontDatabase.applicationFontFamilies(font_id)
                if families:
                    _font_family = families[0]
                    logging.info(f"Speech bubble font loaded: {_font_family}")
        else:
            logging.warning(f"Speech bubble font file not found: {font_path}")

        if _font_family is None:
            _font_family = "Malgun Gothic"
            logging.warning("Falling back to the default speech bubble font (Malgun Gothic).")

    return _font_family


class SpeechBubble(QWidget):
    """Speech bubble widget"""

    MAX_LINES = 8

    def __init__(self, text, parent):
        super().__init__(parent)
        self.text = text
        self.parent_widget = parent

        # Window settings
        self.setWindowFlags(Qt.ToolTip | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        # Font settings (uses the already registered font)
        font_family = register_fonts()
        self.font = QFont(font_family, theme_module.FONT_SIZE_LARGE + 1)
        self.fm = QFontMetrics(self.font)
        self.padding = 12

        try:
            # Size calculation
            self.calculate_size()
            # Position calculation
            self.update_position()
        except Exception as e:
            logging.error(f"Error while initializing SpeechBubble: {e}")

    def _text_height(self, text: str, width: int) -> int:
        # Measure the height with the same width and flags used for painting
        return self.fm.boundingRect(
            QRect(0, 0, width, 100000),
            Qt.TextWordWrap | Qt.AlignCenter,
            text,
        ).height()

    def _fit_tail(self, text: str, width: int, max_height: int) -> str:
        """For long overflowing responses, trim the beginning and keep the newest content."""
        if self._text_height(text, width) <= max_height:
            return text
        low, high = 1, len(text)
        while low < high:
            middle = (low + high) // 2
            if self._text_height("…" + text[middle:].lstrip(), width) <= max_height:
                high = middle
            else:
                low = middle + 1
        return "…" + text[low:].lstrip()

    def calculate_size(self):
        """Speech bubble size calculation"""
        max_width = 250
        plain_text = _plain_bubble_text(self.text)
        # Even with line breaks, the width is based on the longest line
        text_width = max(
            (self.fm.horizontalAdvance(line) for line in plain_text.split("\n")),
            default=0,
        )
        self.bubble_width = min(text_width + self.padding * 2, max_width)
        inner_width = self.bubble_width - self.padding * 2
        self.display_text = self._fit_tail(
            plain_text, inner_width, self.fm.lineSpacing() * self.MAX_LINES
        )
        text_height = self._text_height(self.display_text, inner_width)
        self.bubble_height = max(text_height, self.fm.height()) + self.padding * 2

        # Add tail space
        self.bubble_height += 15

        self.setFixedSize(self.bubble_width, self.bubble_height)

    def update_text(self, text: str) -> None:
        """Update the speech bubble text and recalculate the size."""
        self.text = text
        self.calculate_size()
        self.update_position()
        self.update()

    def update_position(self):
        """Speech bubble position update"""
        if not self.parent_widget:
            return

        # Character screen coordinates
        parent_rect = self.parent_widget.rect()
        parent_pos = self.parent_widget.mapToGlobal(parent_rect.topLeft())

        # Horizontally centered
        x = parent_pos.x() + (parent_rect.width() - self.bubble_width) // 2

        head_top_offset = getattr(self.parent_widget, "head_top_offset", None)
        head_top_offset = int(head_top_offset() or 0) if callable(head_top_offset) else 0
        y = parent_pos.y() + head_top_offset - self.bubble_height - 5

        # Restrict to the work area of the screen the character is on (the above-head placement is kept)
        screen = self.parent_widget.screen()
        if screen is not None:
            area = screen.availableGeometry()
            x = max(area.left(), min(x, area.right() - self.bubble_width + 1))
            y = max(area.top() + 10, y)
        else:
            y = max(10, y)

        self.move(x, y)

    def paintEvent(self, event):
        """Speech bubble painting"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Speech bubble area (excluding the tail)
        bubble_rect = QRect(0, 0, self.bubble_width, self.bubble_height - 15)

        # Theme-based colors
        bg_color = QColor(theme_module.COLOR_BG_WHITE)
        bg_color.setAlpha(245)
        border_color = QColor(210, 210, 210)

        # Background painting
        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawRoundedRect(bubble_rect, 10, 10)

        # Tail painting
        tail_x = self.bubble_width // 2
        tail_y = bubble_rect.bottom()
        tail_points = [
            (tail_x - 8, tail_y),
            (tail_x, tail_y + 15),
            (tail_x + 8, tail_y)
        ]
        polygon = QPolygon([QPoint(x, y) for x, y in tail_points])
        painter.setBrush(bg_color)
        painter.setPen(border_color)
        painter.drawPolygon(polygon)

        # Text painting
        painter.setPen(QColor(theme_module.COLOR_TEXT_PRIMARY))
        painter.setFont(self.font)
        text_rect = bubble_rect.adjusted(self.padding, self.padding, -self.padding, -self.padding)
        painter.drawText(
            text_rect, Qt.TextWordWrap | Qt.AlignCenter, getattr(self, "display_text", self.text)
        )
