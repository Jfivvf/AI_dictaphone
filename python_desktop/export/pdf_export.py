from typing import Any, Dict, Optional
from PySide6.QtCore import QMarginsF, QObject, QTimer, QUrl, Signal
from PySide6.QtGui import QPageLayout, QPageSize
from PySide6.QtWebEngineCore import QWebEnginePage
from .exporters import bundled_katex_dir, render_lecture_html

POLL_INTERVAL_MS = 150
RENDER_TIMEOUT_MS = 20000
SETTLE_DELAY_MS = 300


class PdfExporter(QObject):
    finished = Signal(bool, str)
    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._page: Optional[QWebEnginePage] = None
        self._save_path = ""
        self._elapsed_ms = 0
        self._poll_pending = False
        self._busy = False
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)

    @property
    def busy(self) -> bool:
        return self._busy

    def export(self, lecture: Dict[str, Any], save_path: str) -> None:
        if self._busy:
            return
        katex_dir = bundled_katex_dir()

        self._busy = True
        self._save_path = save_path
        self._elapsed_ms = 0
        self._poll_pending = False
        document = render_lecture_html(lecture, katex_dir=katex_dir, dark_mode=False, with_header=True)
        self._page = QWebEnginePage(self)
        self._page.loadFinished.connect(self._on_loaded)
        self._page.pdfPrintingFinished.connect(self._on_printed)
        base = QUrl.fromLocalFile(str(katex_dir.parent) + "/") if katex_dir else QUrl()
        self._page.setHtml(document, base)

    def _on_loaded(self, ok: bool) -> None:
        if not ok:
            self._finish(False, "Не удалось загрузить страницу для печати.")
            return
        self._timer.start()

    def _poll(self) -> None:
        if self._poll_pending or self._page is None:
            return
        self._elapsed_ms += POLL_INTERVAL_MS
        if self._elapsed_ms > RENDER_TIMEOUT_MS:
            self._timer.stop()
            self._finish(False, "Формулы не отрисовались за 20 секунд.")
            return
        self._poll_pending = True
        self._page.runJavaScript("window.__axDone === true ? (window.__axError || '') : null", self._on_poll)

    def _on_poll(self, result: Any) -> None:
        self._poll_pending = False
        if result is None or self._page is None:
            return
        self._timer.stop()
        if "KATEX_MISSING" in str(result):
            self._finish(
                False,
                "Не удалось загрузить KaTeX для формул: нет встроенных файлов и нет интернета. "
                "Подключитесь к интернету или выполните python tools/vendor_katex.py.",
            )
            return
        QTimer.singleShot(SETTLE_DELAY_MS, self._print)

    def _print(self) -> None:
        if self._page is None:
            return
        layout = QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4),
            QPageLayout.Orientation.Portrait,
            QMarginsF(15, 15, 15, 18),
            QPageLayout.Unit.Millimeter,
        )
        self._page.printToPdf(self._save_path, layout)

    def _on_printed(self, file_path: str, success: bool) -> None:
        self._finish(success, file_path if success else "Chromium не смог сохранить PDF.")

    def _finish(self, success: bool, message: str) -> None:
        self._timer.stop()
        if self._page is not None:
            self._page.deleteLater()
            self._page = None
        self._busy = False
        self.finished.emit(success, message)
