from functools import lru_cache
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

_GRID = 24.0
_SIZE = 64


def _lines(painter: QPainter, *segments) -> None:
    for x1, y1, x2, y2 in segments:
        painter.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _poly(painter: QPainter, *points) -> None:
    painter.drawPolyline(QPolygonF([QPointF(x, y) for x, y in points]))


def _draw(painter: QPainter, name: str, color: QColor) -> None:
    painter.setBrush(Qt.NoBrush)
    if name == "mic":
        painter.drawRoundedRect(QRectF(9, 3, 6, 11), 3, 3)
        path = QPainterPath(QPointF(5, 11))
        path.arcTo(QRectF(5, 6, 14, 10), 180, 180)
        painter.drawPath(path)
        _lines(painter, (12, 16, 12, 21), (8, 21, 16, 21))
    elif name == "pause":
        _lines(painter, (8, 5, 8, 19), (16, 5, 16, 19))
    elif name == "play":
        painter.setBrush(color)
        painter.drawPolygon(QPolygonF([QPointF(7, 4), QPointF(19, 12), QPointF(7, 20)]))
    elif name == "stop":
        painter.setBrush(color)
        painter.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)
    elif name == "bookmark":
        painter.drawPolygon(QPolygonF([QPointF(6, 3), QPointF(18, 3), QPointF(18, 21), QPointF(12, 16), QPointF(6, 21)]))
    elif name == "book":
        painter.drawRoundedRect(QRectF(5, 3, 14, 18), 2, 2)
        _lines(painter, (9, 3, 9, 21), (12, 8, 16, 8))
    elif name == "calendar":
        painter.drawRoundedRect(QRectF(3, 5, 18, 16), 2, 2)
        _lines(painter, (3, 10, 21, 10), (8, 3, 8, 7), (16, 3, 16, 7))
    elif name == "drive":
        _poly(painter, (3, 13), (6, 5), (18, 5), (21, 13))
        painter.drawRoundedRect(QRectF(3, 13, 18, 7), 2, 2)
        _lines(painter, (7, 16.5, 7.1, 16.5))
    elif name == "settings":
        painter.drawEllipse(QPointF(12, 12), 3, 3)
        painter.drawEllipse(QPointF(12, 12), 7, 7)
        import math
        for i in range(8):
            a = math.radians(i * 45)
            painter.drawLine(
                QPointF(12 + 7 * math.cos(a), 12 + 7 * math.sin(a)),
                QPointF(12 + 9.5 * math.cos(a), 12 + 9.5 * math.sin(a)),
            )
    elif name == "user":
        painter.drawEllipse(QPointF(12, 8), 4, 4)
        path = QPainterPath(QPointF(4, 21))
        path.arcTo(QRectF(4, 13, 16, 16), 180, -180)
        painter.drawPath(path)
    elif name in ("upload", "download"):
        if name == "upload":
            _lines(painter, (12, 16, 12, 4))
            _poly(painter, (7, 9), (12, 4), (17, 9))
        else:
            _lines(painter, (12, 4, 12, 16))
            _poly(painter, (7, 11), (12, 16), (17, 11))
        _poly(painter, (4, 16), (4, 20), (20, 20), (20, 16))
    elif name == "back":
        _lines(painter, (20, 12, 5, 12))
        _poly(painter, (11, 6), (5, 12), (11, 18))
    elif name == "printer":
        painter.drawRect(QRectF(6, 3, 12, 6))
        painter.drawRoundedRect(QRectF(3, 9, 18, 8), 2, 2)
        painter.drawRect(QRectF(6, 14, 12, 7))
    elif name == "trash":
        _lines(painter, (4, 7, 20, 7), (10, 11, 10, 16), (14, 11, 14, 16))
        _poly(painter, (9, 7), (9, 4), (15, 4), (15, 7))
        _poly(painter, (6, 7), (7, 20), (17, 20), (18, 7))
    elif name == "plus":
        _lines(painter, (12, 5, 12, 19), (5, 12, 19, 12))
    else:
        painter.drawEllipse(QPointF(12, 12), 8, 8)


@lru_cache(maxsize=256)
def _render(name: str, color_name: str) -> QIcon:
    color = QColor(color_name)
    pix = QPixmap(_SIZE, _SIZE)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.scale(_SIZE / _GRID, _SIZE / _GRID)
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    _draw(painter, name, color)
    painter.end()
    return QIcon(pix)


def make_icon(name: str, color: str = "#e5e5e5") -> QIcon:
    return _render(name, QColor(color).name())
