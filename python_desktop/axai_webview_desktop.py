"""
AxAI — Десктопное приложение на Python + PySide6 (1-в-1 с веб-версией)
Использует PySide6 QMainWindow + QWebEngineView для отображения интерфейса AxAI
со всеми формулами KaTeX, базой Firebase Firestore, записью микрофона,
поддержкой всплывающих окон OAuth-авторизации Google (createWindow) и экспортом PDF/MD/TEX.

Запуск из корня проекта:
    python python_desktop/axai_webview_desktop.py
"""
import os
import sys
import socket
import subprocess
from PySide6.QtCore import QUrl, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QFileDialog, QMessageBox, QDialog, QVBoxLayout
)
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineDownloadRequest, QWebEngineSettings
)


def is_port_in_use(port: int = 3000) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


class AxAIWebPage(QWebEnginePage):
    """
    Кастомная страница QWebEnginePage:
    1. Автоматически разрешает доступ к микрофону (MediaAudioCapture).
    2. Поддерживает всплывающие окна (createWindow) для Google OAuth (signInWithPopup).
    """
    def __init__(self, profile: QWebEngineProfile, parent_window=None):
        super().__init__(profile, parent_window)
        self.parent_window = parent_window
        self.popup_dialogs = []
        self.featurePermissionRequested.connect(self.on_feature_permission_requested)

    def on_feature_permission_requested(self, security_origin: QUrl, feature: QWebEnginePage.Feature):
        self.setFeaturePermission(
            security_origin,
            feature,
            QWebEnginePage.PermissionPolicy.PermissionGrantedByUser,
        )

    def createWindow(self, _type):
        """Открывает дочернее окно PySide6 для входа через Google (Firebase signInWithPopup)."""
        popup_dialog = QDialog(self.parent_window)
        popup_dialog.setWindowTitle("Вход через аккаунт Google — AxAI")
        popup_dialog.resize(520, 680)
        layout = QVBoxLayout(popup_dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        popup_view = QWebEngineView(popup_dialog)
        popup_page = AxAIWebPage(self.profile(), popup_dialog)
        popup_view.setPage(popup_page)
        layout.addWidget(popup_view)

        # Автоматически закрываем всплывающее окно после успешного входа
        popup_page.windowCloseRequested.connect(popup_dialog.close)

        self.popup_dialogs.append(popup_dialog)
        popup_dialog.show()
        return popup_page


class AxAIDesktopWindow(QMainWindow):
    def __init__(self, app_url: str = "http://localhost:3000"):
        super().__init__()
        self.app_url = app_url
        self.server_process = None

        self.setWindowTitle("AxAI")
        self.resize(1280, 820)
        self.setMinimumSize(900, 620)
        self.setStyleSheet("QMainWindow { background-color: #0a0a0a; }")

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
        # Стандартный User-Agent Chrome, чтобы Google OAuth разрешал вход во всплывающем окне
        self.profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        self.profile.downloadRequested.connect(self.on_download_requested)

        self.webview = QWebEngineView(self)
        self.page = AxAIWebPage(self.profile, self)
        self.webview.setPage(self.page)

        # Разрешаем открытие окон JS и доступ к локальному хранилищу
        settings = self.webview.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)

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
