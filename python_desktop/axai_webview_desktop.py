"""
AxAI — Десктопное приложение на Python + PySide6 (1-в-1 с веб-версией)
Использует PySide6 QMainWindow + QWebEngineView для отображения интерфейса AxAI
со всеми формулами KaTeX, базой Firebase Firestore, записью микрофона и экспортом PDF/MD/TEX.

Запуск из корня проекта или из папки python_desktop:
    pip install PySide6 PySide6-Addons
    python python_desktop/axai_webview_desktop.py
"""
import os
import sys
import time
import socket
import subprocess
from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import QApplication, QMainWindow, QFileDialog, QMessageBox
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineDownloadRequest


def create_axolotl_window_icon() -> QIcon:
    """Создает иконку розового аксолотля AxAI для заголовка окна и панели задач."""
    pixmap = QPixmap(120, 120)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Нежно-голубой скругленный фон
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#B3D7EE"))
    painter.drawRoundedRect(0, 0, 120, 120, 26, 26)

    pen = QPen(QColor("#111111"), 3.2)
    painter.setPen(pen)

    # Жабры
    painter.setBrush(QColor("#E97486"))
    painter.drawEllipse(14, 34, 24, 10)
    painter.drawEllipse(12, 46, 24, 10)
    painter.drawEllipse(14, 58, 24, 10)
    painter.drawEllipse(82, 34, 24, 10)
    painter.drawEllipse(84, 46, 24, 10)
    painter.drawEllipse(82, 58, 24, 10)

    # Тело аксолотля
    painter.setBrush(QColor("#F8BAC2"))
    painter.drawRoundedRect(30, 28, 60, 68, 28, 28)

    # Животик
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor("#FBE5C8"))
    painter.drawEllipse(42, 64, 34, 28)

    # Круглые очки
    painter.setPen(QPen(QColor("#111111"), 3.2))
    painter.setBrush(QColor(251, 208, 214, 120))
    painter.drawEllipse(36, 41, 20, 20)
    painter.drawEllipse(62, 41, 20, 20)
    painter.drawLine(56, 51, 62, 51)

    # Глазки
    painter.setBrush(QColor("#111111"))
    painter.drawEllipse(44, 49, 5, 5)
    painter.drawEllipse(70, 49, 5, 5)

    # Ручка в лапках
    painter.setBrush(QColor("#FFFFFF"))
    painter.drawPolygon([
        pixmap.rect().topLeft() + Qt.QPoint(42, 62) if hasattr(Qt, "QPoint") else None
    ][:0])
    painter.drawLine(43, 62, 60, 88)

    painter.end()
    return QIcon(pixmap)


def is_port_in_use(port: int = 3000) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


class AxAIWebPage(QWebEnginePage):
    """Разрешает автоматический доступ к микрофону и всплывающим окнам авторизации."""
    def __init__(self, profile: QWebEngineProfile, parent=None):
        super().__init__(profile, parent)
        self.featurePermissionRequested.connect(self.on_feature_permission_requested)

    def on_feature_permission_requested(self, security_origin: QUrl, feature: QWebEnginePage.Feature):
        if feature in (
            QWebEnginePage.Feature.MediaAudioCapture,
            QWebEnginePage.Feature.MediaVideoCapture,
            QWebEnginePage.Feature.MediaAudioVideoCapture,
            QWebEnginePage.Feature.Notifications,
        ):
            self.setFeaturePermission(
                security_origin,
                feature,
                QWebEnginePage.PermissionPolicy.PermissionGrantedByUser,
            )
        else:
            self.setFeaturePermission(
                security_origin,
                feature,
                QWebEnginePage.PermissionPolicy.PermissionGrantedByUser,
            )


class AxAIDesktopWindow(QMainWindow):
    def __init__(self, app_url: str = "http://localhost:3000"):
        super().__init__()
        self.app_url = app_url
        self.server_process = None

        self.setWindowTitle("AxAI")
        self.resize(1280, 820)
        self.setMinimumSize(900, 620)
        self.setStyleSheet("QMainWindow { background-color: #0a0a0a; }")

        # Если рядом лежит кастомная иконка, используем ее, иначе рисуем иконку аксолотля
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        svg_icon_path = os.path.join(project_root, "public", "axai-icon.svg")
        if os.path.exists(svg_icon_path):
            self.setWindowIcon(QIcon(svg_icon_path))

        # Запускаем локальный сервер Express + Vite, если порт 3000 еще не занят
        if not is_port_in_use(3000):
            self.start_backend_server(project_root)

        # Настраиваем QWebEngineProfile с сохранением сессии и поддержкой скачивания PDF/MD/TEX
        storage_dir = os.path.expanduser("~/.axai_desktop_profile")
        os.makedirs(storage_dir, exist_ok=True)
        self.profile = QWebEngineProfile("AxAIDesktopProfile", self)
        self.profile.setPersistentStoragePath(storage_dir)
        self.profile.setPersistentCookiesPolicy(
            QWebEngineProfile.PersistentCookiesPolicy.ForcePersistentCookies
        )
        self.profile.downloadRequested.connect(self.on_download_requested)

        self.webview = QWebEngineView(self)
        self.page = AxAIWebPage(self.profile, self.webview)
        self.webview.setPage(self.page)
        self.setCentralWidget(self.webview)

        # Подключаемся к серверу как только он готов
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.check_server_ready)
        self.poll_timer.start(300)

    def start_backend_server(self, project_root: str):
        npm_cmd = "npm.cmd" if sys.platform.startswith("win") else "npm"
        try:
            self.server_process = subprocess.Popen(
                [npm_cmd, "run", "dev"],
                cwd=project_root,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "AxAI Server",
                f"Не удалось автоматически запустить npm run dev: {e}\n"
                "Запустите 'npm run dev' в терминале или используйте автономный python_desktop/main.py.",
            )

    def check_server_ready(self):
        if is_port_in_use(3000):
            self.poll_timer.stop()
            self.webview.load(QUrl(self.app_url))

    def on_download_requested(self, download: QWebEngineDownloadRequest):
        suggested_name = download.downloadFileName()
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить файл конспекта",
            os.path.join(os.path.expanduser("~/Downloads"), suggested_name),
        )
        if save_path:
            download.setDownloadDirectory(os.path.dirname(save_path))
            download.setDownloadFileName(os.path.basename(save_path))
            download.accept()
        else:
            download.cancel()

    def closeEvent(self, event):
        if self.server_process and self.server_process.poll() is None:
            self.server_process.terminate()
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("AxAI")
    window = AxAIDesktopWindow()
    window.show()
    sys.exit(app.exec())
