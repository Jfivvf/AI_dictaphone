from collections import deque
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QSizePolicy, QWidget

FLOOR_DB = -60.0
HISTORY = 80


class LevelMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._values = deque([FLOOR_DB] * HISTORY, maxlen=HISTORY)
        self.setMinimumHeight(40)
        self.setMaximumHeight(56)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def reset(self) -> None:
        self._values = deque([FLOOR_DB] * HISTORY, maxlen=HISTORY)
        self.update()

    def push(self, db: float) -> None:
        self._values.append(max(FLOOR_DB, min(0.0, float(db))))
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        w, h = self.width(), self.height()
        slot = w / HISTORY
        bar_w = max(1.5, slot * 0.6)
        base = self.palette().color(QPalette.Highlight)
        for i, db in enumerate(reversed(self._values)):
            ratio = (db - FLOOR_DB) / -FLOOR_DB
            bar_h = max(3.0, ratio * h)
            if db > -6:
                color = QColor("#ef4444")
            elif db > -18:
                color = QColor("#fbbf24")
            else:
                color = QColor(base)
            if ratio <= 0.02:
                color.setAlpha(80)
            painter.setBrush(color)
            painter.setPen(Qt.NoPen)
            x = i * slot + (slot - bar_w) / 2
            painter.drawRoundedRect(QRectF(x, (h - bar_h) / 2, bar_w, bar_h), bar_w / 2, bar_w / 2)
        painter.end()
