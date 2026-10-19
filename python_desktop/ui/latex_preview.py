"""
Модуль нативного отображения конспектов с формулами LaTeX и раздельной графики
(фиксированная иконка приложения AxAI vs. аватарка пользователя 256x256).

Реализует рекомендации код-ревью:
1. Встраивает `QWebEngineView` (с локальным KaTeX и встроенным офлайн-типографом формул)
   только для области чтения конспекта и печати в PDF, оставляя весь остальной интерфейс
   на быстрых нативных виджетах `PySide6.QtWidgets`. Если `QtWebEngineWidgets` не установлен
   в окружении — прозрачно переключается на `QTextBrowser` с математической HTML-версткой.
2. Полностью разделяет системную иконку приложения (`draw_fixed_app_icon_pixmap`) и
   пользовательскую аватарку (`crop_and_compress_avatar_square`, обрезаемую до квадрата 256x256).
"""
import os
from typing import Dict, Any, Optional

from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PySide6.QtCore import Qt, QBuffer, QIODevice, QByteArray, QUrl
from PySide6.QtGui import QPixmap, QImage, QPainter, QPen, QColor, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from export.exporters import render_lecture_html_with_math

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    HAS_WEBENGINE = True
except Exception:
    HAS_WEBENGINE = False


def draw_fixed_app_icon_pixmap(size: int = 64) -> QPixmap:
    """
    Рисует неизменную фирменную иконку приложения AxAI (розовый аксолотль в очках с ручкой).
    Используется для иконки окна (`setWindowIcon`) и логотипа бренда в шапке.
    Не перезаписывается при смене аватарки пользователя!
    """
    pixmap = QPixmap(120, 120)
    pixmap.fill(Qt.transparent)
    p = QPainter(pixmap)
    p.setRenderHint(QPainter.Antialiasing)

    # Нежно-голубой фон
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#B3D7EE"))
    p.drawRoundedRect(0, 0, 120, 120, 26, 26)

    # Жабры слева и справа
    p.setPen(QPen(QColor("#111111"), 3.0))
    p.setBrush(QColor("#E97486"))
    for y in (34, 46, 58):
        p.drawEllipse(12, y, 24, 10)
        p.drawEllipse(84, y, 24, 10)

    # Хвостик справа снизу
    p.drawEllipse(78, 72, 26, 18)

    # Тело аксолотля
    p.setBrush(QColor("#F8BAC2"))
    p.drawRoundedRect(30, 28, 60, 68, 28, 28)

    # Светлый животик
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#FBE5C8"))
    p.drawEllipse(42, 64, 34, 28)

    # Румянец
    p.setBrush(QColor("#EE8D9E"))
    p.drawEllipse(38, 53, 8, 8)
    p.drawEllipse(70, 53, 8, 8)

    # Круглые очки
    p.setPen(QPen(QColor("#111111"), 3.2))
    p.setBrush(QColor(251, 208, 214, 110))
    p.drawEllipse(36, 40, 20, 20)
    p.drawEllipse(62, 40, 20, 20)
    p.drawLine(56, 50, 62, 50)
    p.drawLine(82, 49, 90, 46)

    # Глазки
    p.setBrush(QColor("#111111"))
    p.drawEllipse(44, 48, 5, 5)
    p.drawEllipse(70, 48, 5, 5)

    # Улыбка :3
    p.drawArc(51, 53, 8, 5, 180 * 16, 180 * 16)
    p.drawArc(58, 53, 8, 5, 180 * 16, 180 * 16)

    # Ручка в лапках
    p.setPen(QPen(QColor("#111111"), 3.0))
    p.setBrush(QColor("#FFFFFF"))
    p.drawLine(42, 60, 59, 88)
    p.setPen(QPen(QColor("#6BA8E5"), 5.0))
    p.drawLine(40, 58, 44, 63)

    p.end()
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def crop_and_compress_avatar_square(image_path: str, target_size: int = 256) -> Optional[bytes]:
    """
    Обрезает выбранное пользователем фото по центру до квадрата 1:1 и сжимает до 256x256 PNG
    для компактного хранения в SQLite BLOB (и/или облаке).
    """
    img = QImage(image_path)
    if img.isNull():
        return None

    w = img.width()
    h = img.height()
    side = min(w, h)
    x = (w - side) // 2
    y = (h - side) // 2

    cropped = img.copy(x, y, side, side)
    scaled = cropped.scaled(target_size, target_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    scaled.save(buf, "PNG", 85)
    buf.close()
    return bytes(ba)


def pixmap_from_png_bytes(png_bytes: Optional[bytes], size: int = 64) -> QPixmap:
    """Преобразует байты аватарки из SQLite BLOB в QPixmap или возвращает аксолотля по умолчанию."""
    if png_bytes:
        pm = QPixmap()
        if pm.loadFromData(png_bytes):
            return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return draw_fixed_app_icon_pixmap(size)


class LatexLecturePreview(QWidget):
    """
    Виджет рендеринга конспекта с формулами LaTeX.
    Использует единичный встроенный `QWebEngineView` с локальным KaTeX (или `QTextBrowser` с офлайн-рендером),
    а также позволяет экспортировать конспект в PDF с отрендеренными математическими формулами.
    """

    def __init__(self, storage_path: str = "", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.storage_path = storage_path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if HAS_WEBENGINE:
            self.web_view = QWebEngineView(self)
            self.web_view.setStyleSheet("background-color: #121215; border-radius: 10px;")
            layout.addWidget(self.web_view)
            self.text_browser = None
        else:
            self.web_view = None
            self.text_browser = QTextBrowser(self)
            self.text_browser.setOpenExternalLinks(True)
            self.text_browser.setStyleSheet(
                "QTextBrowser { background-color: #121215; border: 1px solid #27272a; border-radius: 10px; padding: 14px; color: #e4e4e7; }"
            )
            layout.addWidget(self.text_browser)

    def render_lecture(self, lec: Dict[str, Any]) -> None:
        html_doc = render_lecture_html_with_math(
            markdown_text=lec.get("text", ""),
            title=lec.get("title", ""),
            subject=lec.get("subject", ""),
            lecturer=lec.get("lecturer", ""),
            date=lec.get("date", ""),
            formulas=lec.get("formulas", []),
            dark_mode=True,
            storage_path=self.storage_path,
        )
        base_url = QUrl.fromLocalFile(os.path.abspath(self.storage_path) + "/") if self.storage_path else QUrl()
        if self.web_view is not None:
            self.web_view.setHtml(html_doc, base_url)
        elif self.text_browser is not None:
            self.text_browser.setHtml(html_doc)

    def export_pdf_with_formulas(self, lec: Dict[str, Any], save_path: str) -> None:
        """Экспортирует конспект в PDF с отрендеренными математическими формулами LaTeX."""
        printable_html = render_lecture_html_with_math(
            markdown_text=lec.get("text", ""),
            title=lec.get("title", "Лекция"),
            subject=lec.get("subject", ""),
            lecturer=lec.get("lecturer", ""),
            date=lec.get("date", ""),
            formulas=lec.get("formulas", []),
            dark_mode=False,
            storage_path=self.storage_path,
        )

        # Вариант 1: печать через QTextDocument.setHtml с математической версткой (мгновенно и синхронно)
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(save_path)

        doc = QTextDocument()
        doc.setHtml(printable_html)
        doc.print_(printer)
