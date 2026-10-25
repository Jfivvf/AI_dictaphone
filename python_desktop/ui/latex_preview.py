from typing import Any, Dict, Optional
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QUrl
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QVBoxLayout, QWidget
from export.exporters import bundled_katex_dir, render_lecture_html
from export.pdf_export import PdfExporter


def draw_fixed_app_icon_pixmap(size: int = 64) -> QPixmap:
    pixmap = QPixmap(120, 120)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#B3D7EE"))
    p.drawRoundedRect(0, 0, 120, 120, 26, 26)

    p.setPen(QPen(QColor("#111111"), 3.0))
    p.setBrush(QColor("#E97486"))
    for y in (34, 46, 58):
        p.drawEllipse(12, y, 24, 10)
        p.drawEllipse(84, y, 24, 10)
    p.drawEllipse(78, 72, 26, 18)

    p.setBrush(QColor("#F8BAC2"))
    p.drawRoundedRect(30, 28, 60, 68, 28, 28)

    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FBE5C8"))
    p.drawEllipse(42, 64, 34, 28)

    p.setBrush(QColor("#EE8D9E"))
    p.drawEllipse(38, 53, 8, 8)
    p.drawEllipse(70, 53, 8, 8)

    p.setPen(QPen(QColor("#111111"), 3.2))
    p.setBrush(QColor(251, 208, 214, 110))
    p.drawEllipse(36, 40, 20, 20)
    p.drawEllipse(62, 40, 20, 20)
    p.drawLine(56, 50, 62, 50)
    p.drawLine(82, 49, 90, 46)

    p.setBrush(QColor("#111111"))
    p.drawEllipse(44, 48, 5, 5)
    p.drawEllipse(70, 48, 5, 5)

    p.drawArc(51, 53, 8, 5, 180 * 16, 180 * 16)
    p.drawArc(58, 53, 8, 5, 180 * 16, 180 * 16)

    p.setPen(QPen(QColor("#111111"), 3.0))
    p.setBrush(QColor("#FFFFFF"))
    p.drawLine(42, 60, 59, 88)
    p.setPen(QPen(QColor("#6BA8E5"), 5.0))
    p.drawLine(40, 58, 44, 63)

    p.end()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def crop_and_compress_avatar_square(image_path: str, target_size: int = 256) -> Optional[bytes]:
    img = QImage(image_path)
    if img.isNull():
        return None
    side = min(img.width(), img.height())
    cropped = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
    scaled = cropped.scaled(target_size, target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    scaled.save(buf, "PNG", 85)
    buf.close()
    return bytes(data)


def pixmap_from_png_bytes(png_bytes: Optional[bytes], size: int = 64) -> QPixmap:
    if png_bytes:
        pm = QPixmap()
        if pm.loadFromData(png_bytes):
            return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return draw_fixed_app_icon_pixmap(size)


class LatexLecturePreview(QWidget):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.dark_mode = True
        self.web_view = QWebEngineView(self)
        layout.addWidget(self.web_view)
        self.pdf_exporter = PdfExporter(self)
        self.set_dark_mode(True)

    def set_dark_mode(self, dark: bool) -> None:
        self.dark_mode = dark
        self.web_view.page().setBackgroundColor(QColor("#121215" if dark else "#ffffff"))

    def render_lecture(self, lec: Dict[str, Any]) -> None:
        katex_dir = bundled_katex_dir()
        document = render_lecture_html(lec, katex_dir=katex_dir, dark_mode=self.dark_mode, with_header=False)
        base = QUrl.fromLocalFile(str(katex_dir.parent) + "/") if katex_dir else QUrl()
        self.web_view.setHtml(document, base)

    def export_pdf(self, lec: Dict[str, Any], save_path: str) -> None:
        """Результат придёт в сигнал pdf_exporter.finished."""
        self.pdf_exporter.export(lec, save_path)
