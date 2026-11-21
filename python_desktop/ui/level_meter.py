from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPalette
from PySide6.QtWidgets import QSizePolicy, QWidget

FLOOR_DB = -60.0
SEGMENTS = 40
GAP = 2.0
FALL_PER_TICK = 0.10
PEAK_HOLD_TICKS = 8
PEAK_FALL_PER_TICK = 0.03

_GREEN = QColor("#22c55e")
_AMBER = QColor("#fbbf24")
_RED = QColor("#ef4444")


class LevelMeter(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._level = 0.0
        self._peak = 0.0
        self._hold = 0
        self.setFixedHeight(18)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def reset(self) -> None:
        self._level = 0.0
        self._peak = 0.0
        self._hold = 0
        self.update()

    def push(self, db: float) -> None:
        ratio = 0.0 if db <= -79 else max(0.0, min(1.0, (float(db) - FLOOR_DB) / -FLOOR_DB))
        self._level = ratio if ratio >= self._level else max(ratio, self._level - FALL_PER_TICK)
        if ratio >= self._peak:
            self._peak = ratio
            self._hold = PEAK_HOLD_TICKS
        elif self._hold > 0:
            self._hold -= 1
        else:
            self._peak = max(ratio, self._peak - PEAK_FALL_PER_TICK)
        self.update()

    @staticmethod
    def _zone_color(frac: float) -> QColor:
        if frac < 0.65:
            return _GREEN
        if frac < 0.85:
            return _AMBER
        return _RED

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        w, h = float(self.width()), float(self.height())
        seg_w = (w - GAP * (SEGMENTS - 1)) / SEGMENTS
        off = QColor(self.palette().color(QPalette.Mid))
        off.setAlpha(90)
        peak_idx = min(SEGMENTS - 1, int(self._peak * SEGMENTS)) if self._peak > 0 else -1
        for i in range(SEGMENTS):
            frac = (i + 0.5) / SEGMENTS
            if frac <= self._level or (i == peak_idx and self._peak > self._level):
                color = self._zone_color(frac)
            else:
                color = off
            painter.setBrush(color)
            x = i * (seg_w + GAP)
            painter.drawRoundedRect(QRectF(x, 0, seg_w, h), 2, 2)
        painter.end()
