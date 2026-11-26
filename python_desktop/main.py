import os
import re
import shutil
import sys
import json
from datetime import datetime
from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QIcon, QKeySequence, QShortcut, QPixmap
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QProgressBar,
    QProgressDialog, QPushButton, QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)
from audio_recorder import MicrophoneRecorder
from audio_worker import ExpandLectureWorker, ImportDocumentWorker, SetupWorker, TranscriptionWorker
from backup import BackupError, create_backup, read_manifest, restore_backup
from db.bookmarks import BookmarkRepository
from db.repositories import (
    DatabaseManager, LectureRepository, ProfileRepository, RevisionRepository,
    SettingsRepository, TaskRepository,
)
from export.exporters import (
    bundled_katex_dir, export_lecture_to_latex, export_lecture_to_markdown,
    repair_corrupted_latex, unpack_raw_json_lecture_if_needed,
)
from ml.engine import HardwareInspector
from ui.transcript_panel import TranscriptPanel
from ml.offline import offline_missing
from model_setup import is_offline_mode, setup_status
from ui.icons import make_icon
from ui.level_meter import LevelMeter
from ui.theme import THEME_CHOICES, THEMES, apply_theme
from ui.latex_preview import (
    LatexLecturePreview, crop_and_compress_avatar_square, draw_fixed_app_icon_pixmap,
    pixmap_from_png_bytes,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


def app_icon_pixmap(size: int = 64) -> QPixmap:
    # из репозитория лежит рядом (../public), в собранной программе — внутри неё (public)
    pix = QPixmap()
    for candidate in (os.path.join(BASE_DIR, "..", "public", "logo.png"), os.path.join(BASE_DIR, "public", "logo.png")):
        pix = QPixmap(os.path.abspath(candidate))
        if not pix.isNull():
            break
    if pix.isNull():
        return draw_fixed_app_icon_pixmap(size)

    return pix.scaled(
        size, size,
        Qt.KeepAspectRatio,
        Qt.SmoothTransformation,
    )

def format_mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds} сек"
    return f"{seconds // 60} мин {seconds % 60} сек"


NAV_ICONS = {
    "record": "mic", "history": "book", "deadlines": "calendar",
    "storage": "drive", "settings": "settings", "profile": "user",
}


NO_LECTURE_FILTER = "__no_lecture__"


class _CallWorker(QThread):
    """Выполняет функцию в фоне, чтобы тяжёлые проверки не замораживали окно."""

    done = Signal(object)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as err:  # noqa: BLE001
            self.done.emit(err)


class AxAIDesktopApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AxAI")
        self.resize(1260, 820)
        self.storage_path = os.path.expanduser("~/AxAI_Storage")
        self.audio_dir = os.path.join(self.storage_path, "audio")
        os.makedirs(self.audio_dir, exist_ok=True)
        self.db_manager = DatabaseManager(self.storage_path)
        self.lecture_repo = LectureRepository(self.db_manager)
        self.task_repo = TaskRepository(self.db_manager)
        self.revision_repo = RevisionRepository(self.db_manager)
        self.profile_repo = ProfileRepository(self.db_manager)
        self.settings_repo = SettingsRepository(self.db_manager)
        self.bookmark_repo = BookmarkRepository(self.db_manager)
        self._migrate_legacy_json_if_needed()
        self.lectures = self.lecture_repo.get_all_lectures()
        self.student_profile = self.profile_repo.get_profile()
        self.app_settings = self.settings_repo.get_settings()
        self.is_dark = apply_theme(QApplication.instance(), self.app_settings.get("theme", "dark"))
        self.current_lecture = None
        self.pending_bookmarks = []
        self.worker = None
        self.expand_worker = None
        self.import_worker = None
        self.hardware_checked = False
        self.setup_worker = None
        self._button_icons = {}
        self.setWindowIcon(QIcon(app_icon_pixmap(64)))
        self.recorder = MicrophoneRecorder()
        self.is_recording = False
        self.record_seconds = 0
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.update_record_timer)
        self.level_timer = QTimer(self)
        self.level_timer.timeout.connect(self._tick_level)
        self.expand_elapsed_sec = 0
        self.expand_timer = QTimer(self)
        self.expand_timer.timeout.connect(self._tick_expand_elapsed)

        self.init_ui()
        QShortcut(QKeySequence("Ctrl+M"), self).activated.connect(self.add_bookmark)
        QShortcut(QKeySequence("Ctrl+Space"), self).activated.connect(self.toggle_pause)

    def _migrate_legacy_json_if_needed(self):
        legacy_json = os.path.join(self.storage_path, "lectures.json")
        if not self.lecture_repo.get_all_lectures() and os.path.exists(legacy_json):
            try:
                with open(legacy_json, "r", encoding="utf-8") as f:
                    items = json.load(f)
                for item in items:
                    unpack_raw_json_lecture_if_needed(item)
                    self.lecture_repo.upsert_lecture(item)
            except Exception:
                pass

    def get_user_avatar_pixmap(self, size: int = 36):
        data = self.profile_repo.get_avatar_bytes()
        if data:
            return pixmap_from_png_bytes(data, size=size)
        return app_icon_pixmap(size)

    def choose_user_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Аватар", "",
            "Изображения (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if path:
            png_bytes = crop_and_compress_avatar_square(path, target_size=256)
            if png_bytes:
                self.profile_repo.save_avatar_bytes(png_bytes)
                self.refresh_user_avatar_widgets()

    def reset_user_avatar(self):
        self.profile_repo.clear_avatar()
        self.refresh_user_avatar_widgets()

    def refresh_user_avatar_widgets(self):
        self.header_avatar_btn.setIcon(QIcon(self.get_user_avatar_pixmap(24)))
        self.profile_avatar_lbl.setPixmap(self.get_user_avatar_pixmap(64))

    def init_ui(self):
        root_widget = QWidget()
        root_vbox = QVBoxLayout(root_widget)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(56)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(10)
        brand_icon = QLabel()
        brand_icon.setPixmap(app_icon_pixmap(32))
        #brand_icon = QLabel()
        #brand_icon.setPixmap(draw_fixed_app_icon_pixmap(32))
        brand_icon.setFixedSize(34, 34)
        header_layout.addWidget(brand_icon)

        brand_label = QLabel("AxAI")
        brand_label.setFont(QFont("Arial", 14, QFont.Bold))
        brand_label.setObjectName("brand")
        header_layout.addWidget(brand_label)
        header_layout.addStretch()

        self.header_avatar_btn = QPushButton()
        self.header_avatar_btn.setIconSize(QSize(24, 24))
        self.header_avatar_btn.clicked.connect(lambda: self.navigate_to("profile"))
        header_layout.addWidget(self.header_avatar_btn)
        root_vbox.addWidget(header)

        body_widget = QWidget()
        main_layout = QHBoxLayout(body_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(225)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(6)

        self.nav_buttons = {}
        for key, label in [
            ("record", "Запись"),
            ("history", "Мои проекты"),
            ("deadlines", "Дедлайны и задачи"),
            ("storage", "Память и резервные копии"),
            ("settings", "Настройки"),
            ("profile", "Профиль студента"),
        ]:
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setProperty("active", False)
            btn.clicked.connect(lambda checked=False, k=key: self.navigate_to(k))
            self._set_icon(btn, NAV_ICONS[key], "muted")
            sidebar_layout.addWidget(btn)
            self.nav_buttons[key] = btn
        sidebar_layout.addStretch()

        import_pdf_btn = QPushButton("Импорт PDF / .MD")
        import_pdf_btn.setObjectName("primaryBtn")
        import_pdf_btn.clicked.connect(self.handle_import_document)
        self._set_icon(import_pdf_btn, "upload", "white")
        sidebar_layout.addWidget(import_pdf_btn)
        main_layout.addWidget(sidebar)

        self.pages = QStackedWidget()
        self.page_record = self.create_record_page()
        self.page_history = self.create_history_page()
        self.page_viewer = self.create_viewer_page()
        self.page_deadlines = self.create_deadlines_page()
        self.page_storage = self.create_storage_page()
        self.page_settings = self.create_settings_page()
        self.page_profile = self.create_profile_page()
        for page in (
            self.page_record, self.page_history, self.page_viewer, self.page_deadlines,
            self.page_storage, self.page_settings, self.page_profile,
        ):
            self.pages.addWidget(page)

        main_layout.addWidget(self.pages)
        root_vbox.addWidget(body_widget)
        self.setCentralWidget(root_widget)

        self.refresh_profile_widgets()
        self.navigate_to("record")

    def navigate_to(self, page_name: str):
        mapping = {
            "record": 0, "history": 1, "viewer": 2, "deadlines": 3,
            "storage": 4, "settings": 5, "profile": 6,
        }
        if page_name == "deadlines":
            self.refresh_deadlines_list()
        elif page_name == "history":
            self.refresh_history_list()
        elif page_name == "storage":
            self.refresh_storage_info()
        elif page_name == "settings" and not self.hardware_checked:
            self.refresh_hardware_info()
        self.pages.setCurrentIndex(mapping.get(page_name, 0))
        for key, btn in self.nav_buttons.items():
            is_active = key == page_name
            btn.setProperty("active", is_active)
            self._set_icon(btn, NAV_ICONS[key], "white" if is_active else "muted")
            self._repolish(btn)

    def _icon_color(self, role: str) -> str:
        tokens = THEMES["dark" if self.is_dark else "light"]
        return {"text": tokens["text"], "muted": tokens["muted"], "white": "#ffffff"}[role]

    def _set_icon(self, button, name: str, role: str = "text"):
        self._button_icons[button] = (name, role)
        button.setIcon(make_icon(name, self._icon_color(role)))
        button.setIconSize(QSize(18, 18))

    def refresh_icons(self):
        for button, (name, role) in self._button_icons.items():
            button.setIcon(make_icon(name, self._icon_color(role)))

    @staticmethod
    def _repolish(widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def create_record_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(14)

        title = QLabel("Запись")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)
        subtitle = QLabel("Запись с микрофона в реальном времени или загрузка аудиофайла")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)

        info_card = QFrame()
        info_card.setObjectName("card")
        grid = QGridLayout(info_card)
        grid.setContentsMargins(18, 16, 18, 16)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        section = QLabel("ИНФОРМАЦИЯ О ЗАНЯТИИ")
        section.setObjectName("sectionTitle")
        grid.addWidget(section, 0, 0, 1, 3)
        self.input_subject = QLineEdit()
        self.input_subject.setPlaceholderText("Например: Высшая математика")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Тема")
        self.input_lecturer = QLineEdit()
        self.input_lecturer.setPlaceholderText("ФИО лектора")
        for col, (label, field) in enumerate((
            ("Дисциплина", self.input_subject),
            ("Тема", self.input_title),
            ("Преподаватель", self.input_lecturer),
        )):
            lbl = QLabel(label)
            lbl.setObjectName("fieldLabel")
            grid.addWidget(lbl, 1, col)
            grid.addWidget(field, 2, col)
        layout.addWidget(info_card)

        ctx_card = QFrame()
        ctx_card.setObjectName("card")
        ctx_layout = QVBoxLayout(ctx_card)
        ctx_layout.setContentsMargins(18, 16, 18, 16)
        ctx_layout.setSpacing(6)
        ctx_title = QLabel("КОНТЕКСТ")
        ctx_title.setObjectName("sectionTitle")
        ctx_layout.addWidget(ctx_title)
        self.input_record_context = QTextEdit()
        self.input_record_context.setPlaceholderText(
            "Повышает точность распознавания терминов и формул. "
        )
        self.input_record_context.setMaximumHeight(80)
        ctx_layout.addWidget(self.input_record_context)
        layout.addWidget(ctx_card)

        rec_card = QFrame()
        rec_card.setObjectName("card")
        rec_layout = QVBoxLayout(rec_card)
        rec_layout.setContentsMargins(18, 16, 18, 16)
        rec_layout.setSpacing(12)

        status_row = QHBoxLayout()
        self.rec_dot = QLabel()
        self.rec_dot.setObjectName("recDot")
        self.rec_dot.setProperty("state", "idle")
        self.rec_state_lbl = QLabel("Готов к записи")
        status_row.addWidget(self.rec_dot)
        status_row.addWidget(self.rec_state_lbl)
        status_row.addStretch()
        self.db_label = QLabel("-- dB")
        self.db_label.setObjectName("dbLabel")
        self.timer_label = QLabel("00:00")
        self.timer_label.setObjectName("bigTimer")
        status_row.addWidget(self.db_label)
        status_row.addSpacing(16)
        status_row.addWidget(self.timer_label)
        rec_layout.addLayout(status_row)
        self.level_meter = LevelMeter()
        rec_layout.addWidget(self.level_meter)
        btn_row = QHBoxLayout()
        self.btn_record = QPushButton("Начать запись")
        self.btn_record.setObjectName("recordBtn")
        self.btn_record.clicked.connect(self.start_recording)
        self._set_icon(self.btn_record, "mic", "white")

        self.btn_pause = QPushButton("Пауза")
        self.btn_pause.clicked.connect(self.toggle_pause)
        self._set_icon(self.btn_pause, "pause", "text")

        self.btn_bookmark = QPushButton("Метка (0)")
        self.btn_bookmark.clicked.connect(self.add_bookmark)
        self._set_icon(self.btn_bookmark, "bookmark", "text")

        self.btn_finish = QPushButton("Завершить и сохранить")
        self.btn_finish.setObjectName("primaryBtn")
        self.btn_finish.clicked.connect(self.finish_recording)
        self._set_icon(self.btn_finish, "stop", "white")

        self.btn_upload_audio = QPushButton("Загрузить аудиофайл")
        self.btn_upload_audio.clicked.connect(self.handle_upload_audio)
        self._set_icon(self.btn_upload_audio, "upload", "text")

        for widget in (self.btn_record, self.btn_pause, self.btn_bookmark, self.btn_finish):
            btn_row.addWidget(widget)
        btn_row.addStretch()
        hint = QLabel("Ctrl+Пробел: пауза   Ctrl+M: метка")
        hint.setObjectName("hint")
        btn_row.addWidget(hint)
        btn_row.addSpacing(12)
        btn_row.addWidget(self.btn_upload_audio)
        rec_layout.addLayout(btn_row)
        layout.addWidget(rec_card)

        self.record_progress = QProgressBar()
        self.record_progress.setVisible(False)
        layout.addWidget(self.record_progress)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setObjectName("accentText")
        layout.addWidget(self.status_label)

        cancel_row = QHBoxLayout()
        self.btn_cancel_ai = QPushButton("Отменить обработку")
        self.btn_cancel_ai.setVisible(False)
        self.btn_cancel_ai.clicked.connect(self.cancel_transcription)
        cancel_row.addStretch()
        cancel_row.addWidget(self.btn_cancel_ai)
        cancel_row.addStretch()
        layout.addLayout(cancel_row)

        layout.addStretch()
        self._set_record_state("idle")
        return page

    def _set_record_state(self, state: str):
        self.rec_dot.setProperty("state", state if state in ("recording", "paused") else "idle")
        self._repolish(self.rec_dot)
        self.rec_state_lbl.setText({
            "idle": "Готов к записи", "recording": "Идёт запись...",
            "paused": "Пауза", "busy": "Обработка записи...",
        }[state])
        active = state in ("recording", "paused")
        self.btn_record.setVisible(not active)
        self.btn_record.setEnabled(state == "idle")
        for widget in (self.btn_pause, self.btn_bookmark, self.btn_finish):
            widget.setVisible(active)
        paused = state == "paused"
        self.btn_pause.setText("Продолжить" if paused else "Пауза")
        self._set_icon(self.btn_pause, "play" if paused else "pause", "text")
        self.btn_upload_audio.setEnabled(state == "idle")
        if not active:
            self.db_label.setText("-- dB")

    def start_recording(self):
        wav_path = os.path.join(self.audio_dir, f"rec_{int(datetime.now().timestamp())}.wav")
        try:
            self.recorder.start(wav_path)
        except RuntimeError as err:
            QMessageBox.warning(self, "Микрофон", str(err))
            return
        self.is_recording = True
        self.record_seconds = 0
        self.timer_label.setText("00:00")
        self.btn_bookmark.setText("Метка (0)")
        self.level_meter.reset()
        self.status_label.setText("")
        self.record_timer.start(500)
        self.level_timer.start(100)
        self._set_record_state("recording")

    def toggle_pause(self):
        if not self.is_recording:
            return
        if self.recorder.paused:
            self.recorder.resume()
            self.record_timer.start(500)
            self.level_timer.start(100)
            self._set_record_state("recording")
        else:
            self.recorder.pause()
            self.record_timer.stop()
            self.level_timer.stop()
            self._set_record_state("paused")

    def finish_recording(self):
        if not self.is_recording:
            return
        self.is_recording = False
        self.record_timer.stop()
        self.level_timer.stop()
        saved_file = self.recorder.stop()
        self.pending_bookmarks = list(self.recorder.bookmarks)
        if saved_file:
            self.start_transcription(saved_file)
        else:
            self.status_label.setText("Звук не записан.")
            self._set_record_state("idle")

    def add_bookmark(self):
        if not self.is_recording:
            return
        mark = self.recorder.add_bookmark()
        self.btn_bookmark.setText(f"Метка ({len(self.recorder.bookmarks)})")
        self.status_label.setText(f"Метка поставлена: {format_mmss(mark['time_sec'])}")

    def update_record_timer(self):
        self.record_seconds = int(self.recorder.elapsed_seconds)
        self.timer_label.setText(format_mmss(self.record_seconds))

    def _tick_level(self):
        db = self.recorder.take_level_db()
        self.level_meter.push(db)
        self.db_label.setText(f"{round(db)} dB" if db > -79 else "-- dB")

    def handle_upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Аудиозапись лекции", "", "Аудио (*.wav *.mp3 *.m4a *.ogg *.webm)"
        )
        if path:
            target = os.path.join(
                self.audio_dir, f"up_{int(datetime.now().timestamp())}_{os.path.basename(path)}"
            )
            shutil.copy2(path, target)
            self.pending_bookmarks = []
            self.start_transcription(target)

    def start_transcription(self, audio_path: str):
        self.record_progress.setVisible(True)
        self.record_progress.setValue(5)
        self.btn_cancel_ai.setVisible(True)
        self._set_record_state("busy")
        self.status_label.setText("Подготовка распознавания речи...")

        self.worker = TranscriptionWorker(
            audio_path=audio_path,
            title=self.input_title.text().strip() or "Учебное занятие",
            subject=self.input_subject.text().strip() or "Учебная дисциплина",
            lecturer=self.input_lecturer.text().strip(),
            ai_context=self.input_record_context.toPlainText().strip(),
            settings=self.app_settings,
        )
        self.worker.progress.connect(self.on_transcription_progress)
        self.worker.finished.connect(lambda res: self.on_transcription_finished(res, audio_path))
        self.worker.error.connect(self.on_transcription_error)
        self.worker.start()

    def cancel_transcription(self):
        if self.worker is not None and self.worker.isRunning():
            self.worker.requestInterruption()
            self.status_label.setText("Отмена...")

    def _finish_processing_ui(self):
        self.record_progress.setVisible(False)
        self.btn_cancel_ai.setVisible(False)
        self._set_record_state("idle")

    def on_transcription_progress(self, val: int, text: str):
        self.record_progress.setValue(val)
        self.status_label.setText(text)

    def on_transcription_finished(self, result: dict, audio_path: str):
        self._finish_processing_ui()
        timing = result.get("timing") or {}
        if timing:
            self.status_label.setText(
                f"Готово. Распознавание: {format_duration(timing['asr_sec'])}, "
                f"конспект: {format_duration(timing['summary_sec'])}."
            )
        else:
            self.status_label.setText("Конспект сохранён.")

        segments = result.get("segments", [])
        if segments:
            duration_min = max(1, int(segments[-1].get("end", 0) // 60))
        else:
            duration_min = max(1, self.record_seconds // 60)

        lec_id = f"lec-{int(datetime.now().timestamp())}"
        new_lecture = {
            "id": lec_id,
            "title": self.input_title.text().strip() or "Конспект лекции",
            "subject": self.input_subject.text().strip() or "Учебное занятие",
            "lecturer": self.input_lecturer.text().strip() or "Преподаватель",
            "date": datetime.now().strftime("%d.%m.%Y"),
            "duration_min": duration_min,
            "text": repair_corrupted_latex(result.get("text", "")),
            "raw_transcript": result.get("raw_transcript", ""),
            "segments": segments,
            "tasks": result.get("tasks", []),
            "formulas": result.get("formulas", []),
            "audio_file": audio_path,
            "ai_context": self.input_record_context.toPlainText().strip(),
        }
        unpack_raw_json_lecture_if_needed(new_lecture)

        saved = self.lecture_repo.upsert_lecture(new_lecture)
        self.revision_repo.add_revision_if_new(lec_id, saved["text"], "Исходная версия")
        self.bookmark_repo.replace_for_lecture(lec_id, self.pending_bookmarks)
        self.pending_bookmarks = []

        self.lectures = self.lecture_repo.get_all_lectures()
        self.refresh_history_list()
        self.open_lecture_viewer(saved)
        if result.get("warning"):
            QMessageBox.warning(self, "Конспект", result["warning"])

    def on_transcription_error(self, err_msg: str):
        self._finish_processing_ui()
        self.status_label.setText("Обработка не выполнена")
        QMessageBox.warning(self, "Ошибка", err_msg)

    def create_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Мои проекты")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header.addWidget(title)
        header.addStretch()

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск по конспектам, формулам и предметам...")
        self.search_input.setFixedWidth(420)
        self.search_input.textChanged.connect(self.refresh_history_list)
        header.addWidget(self.search_input)

        import_btn = QPushButton("Импорт PDF / .MD")
        import_btn.setObjectName("primaryBtn")
        import_btn.clicked.connect(self.handle_import_document)
        self._set_icon(import_btn, "upload", "white")
        header.addWidget(import_btn)
        layout.addLayout(header)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.on_lecture_clicked)
        layout.addWidget(self.history_list)

        self.refresh_history_list()
        return page

    def refresh_history_list(self):
        if not hasattr(self, "history_list"):
            return
        query = self.search_input.text().strip() if hasattr(self, "search_input") else ""
        filtered = self.lecture_repo.search_lectures(query)
        self.lectures = self.lecture_repo.get_all_lectures()

        self.history_list.clear()
        for lec in filtered:
            unpack_raw_json_lecture_if_needed(lec)
            revs_count = len(lec.get("revisions", []))
            rev_badge = f"  ·  Версий: {revs_count}" if revs_count > 0 else ""
            item = QListWidgetItem(
                f"{lec.get('title', 'Лекция')}  ·  {lec.get('subject', '')}\n"
                f"{lec.get('date', '')}  ·  {lec.get('lecturer', '')}  ·  "
                f"Задач: {len(lec.get('tasks', []))}{rev_badge}"
            )
            item.setData(Qt.UserRole, lec)
            self.history_list.addItem(item)

    def on_lecture_clicked(self, item: QListWidgetItem):
        lec = item.data(Qt.UserRole)
        if lec:
            self.open_lecture_viewer(lec)

    def create_viewer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        back_btn = QPushButton("Назад к лекциям")
        back_btn.clicked.connect(lambda: self.navigate_to("history"))
        self._set_icon(back_btn, "back", "text")
        top_bar.addWidget(back_btn)
        top_bar.addStretch()

        self.revert_prev_btn = QPushButton("Вернуть предыдущую версию")
        self.revert_prev_btn.setObjectName("revertBtn")
        self.revert_prev_btn.clicked.connect(self.handle_revert_previous_version)
        self.revert_prev_btn.setVisible(False)
        top_bar.addWidget(self.revert_prev_btn)

        self.history_revs_btn = QPushButton("История версий (0)")
        self.history_revs_btn.clicked.connect(self.open_revisions_dialog)
        top_bar.addWidget(self.history_revs_btn)

        self.context_toggle_btn = QPushButton("Контекст")
        self.context_toggle_btn.clicked.connect(self.toggle_viewer_context_box)
        top_bar.addWidget(self.context_toggle_btn)

        self.expand_ai_btn = QPushButton("Сделать подробнее")
        self.expand_ai_btn.setObjectName("expandAiBtn")
        self.expand_ai_btn.clicked.connect(self.handle_expand_lecture_ai)
        top_bar.addWidget(self.expand_ai_btn)

        # одна кнопка «Скачать» с выбором формата
        self.btn_export_pdf = QPushButton("Скачать")
        self._set_icon(self.btn_export_pdf, "download", "text")
        export_menu = QMenu(self.btn_export_pdf)
        export_menu.addAction("PDF (.pdf)", self.export_current_pdf)
        export_menu.addAction("Markdown (.md)", self.export_current_markdown)
        export_menu.addAction("LaTeX (.tex)", self.export_current_latex)
        self.btn_export_pdf.setMenu(export_menu)
        top_bar.addWidget(self.btn_export_pdf)

        delete_lec_btn = QPushButton()
        self._set_icon(delete_lec_btn, "trash", "text")
        delete_lec_btn.setToolTip("Удалить эту лекцию")
        delete_lec_btn.clicked.connect(self.delete_current_lecture)
        top_bar.addWidget(delete_lec_btn)
        layout.addLayout(top_bar)

        self.viewer_title = QLabel("Название лекции")
        self.viewer_title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(self.viewer_title)

        self.viewer_meta = QLabel("")
        self.viewer_meta.setObjectName("muted")
        layout.addWidget(self.viewer_meta)

        self.expand_progress_card = QFrame()
        self.expand_progress_card.setObjectName("progressCard")
        self.expand_progress_card.setVisible(False)
        p_vbox = QVBoxLayout(self.expand_progress_card)
        p_vbox.setContentsMargins(16, 12, 16, 12)
        p_vbox.setSpacing(6)

        p_top = QHBoxLayout()
        self.expand_stage_lbl = QLabel("")
        self.expand_stage_lbl.setObjectName("stageText")
        p_top.addWidget(self.expand_stage_lbl)
        p_top.addStretch()
        self.expand_time_lbl = QLabel("Прошло: 0 сек")
        self.expand_time_lbl.setObjectName("hint")
        p_top.addWidget(self.expand_time_lbl)
        self.expand_cancel_btn = QPushButton("Отмена")
        self.expand_cancel_btn.clicked.connect(self.cancel_expand)
        p_top.addWidget(self.expand_cancel_btn)
        p_vbox.addLayout(p_top)

        self.expand_progress_bar = QProgressBar()
        self.expand_progress_bar.setRange(0, 100)
        p_vbox.addWidget(self.expand_progress_bar)
        layout.addWidget(self.expand_progress_card)

        self.viewer_context_card = QFrame()
        self.viewer_context_card.setObjectName("card")
        self.viewer_context_card.setVisible(False)
        c_vbox = QVBoxLayout(self.viewer_context_card)
        c_vbox.setContentsMargins(14, 10, 14, 10)
        c_vbox.setSpacing(6)
        c_vbox.addWidget(QLabel("Контекст:"))
        self.viewer_context_input = QTextEdit()
        self.viewer_context_input.setMaximumHeight(68)
        self.viewer_context_input.setPlaceholderText("Повышает точность распознавания терминов и формул")
        c_vbox.addWidget(self.viewer_context_input)
        c_btn_row = QHBoxLayout()
        c_btn_row.addStretch()
        run_ctx_btn = QPushButton("Сформировать подробный конспект")
        run_ctx_btn.setObjectName("primaryBtn")
        run_ctx_btn.clicked.connect(self.handle_expand_lecture_ai)
        c_btn_row.addWidget(run_ctx_btn)
        c_vbox.addLayout(c_btn_row)
        layout.addWidget(self.viewer_context_card)

        sub_tabs = QHBoxLayout()
        self.btn_sub_rendered = QPushButton("Конспект")
        self.btn_sub_rendered.setObjectName("primaryBtn")
        self.btn_sub_rendered.clicked.connect(lambda: self.switch_viewer_mode("rendered"))
        self.btn_sub_edit = QPushButton("Редактировать Markdown")
        self.btn_sub_edit.clicked.connect(lambda: self.switch_viewer_mode("edit"))
        self.btn_sub_transcript = QPushButton("Стенограмма и метки")
        self.btn_sub_transcript.clicked.connect(lambda: self.switch_viewer_mode("transcript"))

        self.save_edits_btn = QPushButton("Сохранить правки")
        self.save_edits_btn.setObjectName("primaryBtn")
        self.save_edits_btn.clicked.connect(self.save_current_lecture_text)
        self.save_edits_btn.setVisible(False)

        sub_tabs.addWidget(self.btn_sub_rendered)
        sub_tabs.addWidget(self.btn_sub_edit)
        sub_tabs.addWidget(self.btn_sub_transcript)
        sub_tabs.addStretch()
        sub_tabs.addWidget(self.save_edits_btn)
        layout.addLayout(sub_tabs)

        self.viewer_stack = QStackedWidget()
        self.latex_preview = LatexLecturePreview(parent=self)
        self.latex_preview.set_dark_mode(self.is_dark)
        self.latex_preview.pdf_exporter.finished.connect(self.on_pdf_exported)
        self.text_editor = QTextEdit()
        self.transcript_panel = TranscriptPanel(self)
        self.viewer_stack.addWidget(self.latex_preview)
        self.viewer_stack.addWidget(self.text_editor)
        self.viewer_stack.addWidget(self.transcript_panel)
        layout.addWidget(self.viewer_stack, stretch=1)
        return page

    def switch_viewer_mode(self, mode: str):
        if mode == "rendered":
            if self.current_lecture:
                self.current_lecture["text"] = self.text_editor.toPlainText()
                self.latex_preview.render_lecture(self.current_lecture)
            self.viewer_stack.setCurrentIndex(0)
            self.save_edits_btn.setVisible(False)
        elif mode == "edit":
            self.viewer_stack.setCurrentIndex(1)
            self.save_edits_btn.setVisible(True)
        elif mode == "transcript":
            self.viewer_stack.setCurrentIndex(2)
            self.save_edits_btn.setVisible(False)

    def toggle_viewer_context_box(self):
        self.viewer_context_card.setVisible(not self.viewer_context_card.isVisible())

    def _set_viewer_meta(self, lec: dict, text: str):
        self.viewer_meta.setText(
            f"{lec.get('subject', '')}  ·  {lec.get('lecturer', '')}  ·  {lec.get('date', '')}  ·  "
            f"{len(text.split())} слов"
        )

    def _build_transcript_text(self, lec: dict) -> str:
        segs = lec.get("segments", [])
        if segs:
            lines = []
            for s in segs:
                start_sec = int(s.get("start", 0))
                who = f"{s['speaker']}: " if s.get("speaker") else ""
                lines.append(f"[{s.get('time') or format_mmss(start_sec)}]  {who}{s.get('text', '')}")
            body = "\n\n".join(lines)
        else:
            body = lec.get("raw_transcript") or "Стенограмма отсутствует."

        marks = self.bookmark_repo.get_for_lecture(lec["id"])
        if marks:
            head = "\n".join(
                f"{format_mmss(m['time_sec'])}  {m['note'] or 'Метка'}" for m in marks
            )
            return f"Метки записи:\n{head}\n\n{'—' * 24}\n\n{body}"
        return body

    def open_lecture_viewer(self, lec: dict):
        unpack_raw_json_lecture_if_needed(lec)
        self.current_lecture = lec
        self.viewer_title.setText(lec.get("title", "Без названия"))

        clean_text = repair_corrupted_latex(lec.get("text", ""))
        self.current_lecture["text"] = clean_text
        self._set_viewer_meta(lec, clean_text)
        self.text_editor.setPlainText(clean_text)
        self.viewer_context_input.setPlainText(lec.get("ai_context", ""))
        self.transcript_panel.set_lecture(lec, self.bookmark_repo.get_for_lecture(lec["id"]), self.is_dark)

        self.latex_preview.render_lecture(self.current_lecture)
        self.viewer_stack.setCurrentIndex(0)
        self.save_edits_btn.setVisible(False)
        self._refresh_revision_buttons()
        self.navigate_to("viewer")

    def _get_previous_revision(self):
        if not self.current_lecture:
            return None
        revs = self.revision_repo.get_revisions(self.current_lecture["id"])
        current_trimmed = (self.current_lecture.get("text") or "").strip()
        for rev in reversed(revs):
            if rev["summaryMarkdown"].strip() != current_trimmed:
                return rev
        return None

    def _refresh_revision_buttons(self):
        if not self.current_lecture:
            return
        revs = self.revision_repo.get_revisions(self.current_lecture["id"])
        self.current_lecture["revisions"] = revs
        self.history_revs_btn.setText(f"История версий ({len(revs)})")
        prev_rev = self._get_previous_revision()
        self.revert_prev_btn.setVisible(prev_rev is not None)
        if prev_rev:
            self.revert_prev_btn.setToolTip(
                f"Вернуться к версии: {prev_rev['label']} ({prev_rev['wordCount']} слов)"
            )

    def handle_revert_previous_version(self):
        prev_rev = self._get_previous_revision()
        if prev_rev and self.current_lecture:
            self._restore_revision_object(prev_rev)

    def _restore_revision_object(self, rev: dict):
        if not self.current_lecture:
            return
        lec_id = self.current_lecture["id"]
        current_text = self.text_editor.toPlainText().strip()
        if current_text and current_text != rev["summaryMarkdown"].strip():
            existing = self.revision_repo.get_revisions(lec_id)
            self.revision_repo.add_revision_if_new(
                lec_id, current_text,
                "Исходная версия" if not existing else f"Сохранённая версия #{len(existing) + 1}",
            )

        self.current_lecture["text"] = rev["summaryMarkdown"]
        self.text_editor.setPlainText(rev["summaryMarkdown"])
        self.latex_preview.render_lecture(self.current_lecture)
        self.lecture_repo.upsert_lecture(self.current_lecture)
        self._refresh_revision_buttons()
        self._set_viewer_meta(self.current_lecture, rev["summaryMarkdown"])

    def open_revisions_dialog(self):
        if not self.current_lecture:
            return
        revs = self.revision_repo.get_revisions(self.current_lecture["id"])
        dlg = QDialog(self)
        dlg.setWindowTitle("История изменений конспекта")
        dlg.setMinimumSize(640, 420)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(10)

        info = QLabel(
            "Перед каждым расширением конспекта и ручным сохранением предыдущая версия "
            "сохраняется в базе. Выберите редакцию для восстановления:"
        )
        info.setWordWrap(True)
        info.setObjectName("muted")
        vbox.addWidget(info)

        list_w = QListWidget()
        current_trimmed = (self.current_lecture.get("text") or "").strip()
        for rev in reversed(revs):
            badge = "  [ТЕКУЩАЯ ВЕРСИЯ]" if rev["summaryMarkdown"].strip() == current_trimmed else ""
            preview = rev["summaryMarkdown"].replace("\n", " ")[:110]
            item = QListWidgetItem(
                f"{rev['label']}{badge}  ·  {rev['wordCount']} слов  ·  {rev['timestamp']}\n   {preview}..."
            )
            item.setData(Qt.UserRole, rev)
            list_w.addItem(item)
        vbox.addWidget(list_w, stretch=1)

        btn_row = QHBoxLayout()
        close_b = QPushButton("Закрыть")
        close_b.clicked.connect(dlg.reject)
        restore_b = QPushButton("Восстановить выбранную версию")
        restore_b.setObjectName("primaryBtn")

        def on_restore():
            sel = list_w.currentItem()
            if sel and sel.data(Qt.UserRole):
                self._restore_revision_object(sel.data(Qt.UserRole))
                dlg.accept()

        restore_b.clicked.connect(on_restore)
        btn_row.addStretch()
        btn_row.addWidget(close_b)
        btn_row.addWidget(restore_b)
        vbox.addLayout(btn_row)
        dlg.exec()

    def save_current_lecture_text(self):
        if not self.current_lecture:
            return
        lec_id = self.current_lecture["id"]
        old_text = (self.current_lecture.get("text") or "").strip()
        new_text = repair_corrupted_latex(self.text_editor.toPlainText().strip())

        if old_text and old_text != new_text:
            existing = self.revision_repo.get_revisions(lec_id)
            self.revision_repo.add_revision_if_new(
                lec_id, old_text,
                "Исходная версия" if not existing else f"Версия до правки #{len(existing) + 1}",
            )
            self.revision_repo.add_revision_if_new(lec_id, new_text, f"Ручное редактирование #{len(existing) + 2}")

        self.current_lecture["text"] = new_text
        self.lecture_repo.upsert_lecture(self.current_lecture)
        self.latex_preview.render_lecture(self.current_lecture)
        self._refresh_revision_buttons()
        self._set_viewer_meta(self.current_lecture, new_text)
        self.switch_viewer_mode("rendered")

    # Расширение конспекта
    def handle_expand_lecture_ai(self):
        if not self.current_lecture or (self.expand_worker is not None and self.expand_worker.isRunning()):
            return
        self.expand_ai_btn.setEnabled(False)
        self.expand_ai_btn.setText("Генерация подробного конспекта...")
        self.expand_elapsed_sec = 0
        self.expand_progress_bar.setValue(5)
        self.expand_stage_lbl.setText("Подготовка...")
        self.expand_time_lbl.setText("Прошло: 0 сек")
        self.expand_progress_card.setVisible(True)
        self.expand_timer.start(1000)

        extra_ctx = self.viewer_context_input.toPlainText().strip()
        self.current_lecture["ai_context"] = extra_ctx

        self.expand_worker = ExpandLectureWorker(
            title=self.current_lecture.get("title", "Лекция"),
            subject=self.current_lecture.get("subject", "Дисциплина"),
            current_markdown=self.text_editor.toPlainText(),
            raw_transcript=self.current_lecture.get("raw_transcript", ""),
            ai_context=extra_ctx,
            lecturer=self.current_lecture.get("lecturer", ""),
            settings=self.app_settings,
        )
        self.expand_worker.progress.connect(self.on_expand_worker_progress)
        self.expand_worker.finished.connect(self.on_expand_finished)
        self.expand_worker.error.connect(self.on_expand_error)
        self.expand_worker.start()

    def cancel_expand(self):
        if self.expand_worker is not None and self.expand_worker.isRunning():
            self.expand_worker.requestInterruption()
            self.expand_stage_lbl.setText("Отмена...")

    def _tick_expand_elapsed(self):
        self.expand_elapsed_sec += 1
        self.expand_time_lbl.setText(f"Прошло: {format_mmss(self.expand_elapsed_sec)}")

    def _reset_expand_ui(self):
        self.expand_timer.stop()
        self.expand_progress_card.setVisible(False)
        self.expand_ai_btn.setEnabled(True)
        self.expand_ai_btn.setText("Сделать подробнее (ИИ)")

    def on_expand_worker_progress(self, pct: int, stage_msg: str):
        self.expand_progress_bar.setValue(max(self.expand_progress_bar.value(), pct))
        if stage_msg:
            self.expand_stage_lbl.setText(stage_msg)

    def on_expand_finished(self, expanded_markdown: str):
        self._reset_expand_ui()
        if not (self.current_lecture and expanded_markdown):
            return
        lec_id = self.current_lecture["id"]
        previous_md = (self.current_lecture.get("text") or "").strip()
        clean_expanded = repair_corrupted_latex(expanded_markdown.strip())

        existing = self.revision_repo.get_revisions(lec_id)
        if previous_md:
            self.revision_repo.add_revision_if_new(
                lec_id, previous_md,
                "Исходная (лаконичная) версия" if not existing else f"Версия до расширения #{len(existing) + 1}",
            )
        updated = self.revision_repo.get_revisions(lec_id)
        self.revision_repo.add_revision_if_new(lec_id, clean_expanded, f"Подробная версия (ИИ) #{len(updated) + 1}")

        self.current_lecture["text"] = clean_expanded
        self.text_editor.setPlainText(clean_expanded)
        self.latex_preview.render_lecture(self.current_lecture)
        self.lecture_repo.upsert_lecture(self.current_lecture)
        self._refresh_revision_buttons()
        self._set_viewer_meta(self.current_lecture, clean_expanded)

    def on_expand_error(self, err: str):
        self._reset_expand_ui()
        QMessageBox.warning(self, "Ошибка ИИ", f"Не удалось расширить конспект: {err}")

    def delete_current_lecture(self):
        if not self.current_lecture:
            return
        reply = QMessageBox.question(
            self, "Удаление лекции", f"Удалить лекцию «{self.current_lecture.get('title', '')}» из базы данных?"
        )
        if reply == QMessageBox.Yes:
            self.lecture_repo.delete_lecture(self.current_lecture["id"])
            self.current_lecture = None
            self.refresh_history_list()
            self.navigate_to("history")

    # Экспорт
    def _export_payload(self) -> dict:
        lec = dict(self.current_lecture)
        lec["text"] = self.text_editor.toPlainText()
        lec["bookmarks"] = self.bookmark_repo.get_for_lecture(lec["id"])
        return lec

    def _safe_name(self) -> str:
        return re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))

    def export_current_markdown(self):
        if not self.current_lecture:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить Markdown (.md)", f"{self._safe_name()}_конспект.md", "Markdown (*.md)"
        )
        if save_path:
            export_lecture_to_markdown(self._export_payload(), save_path)
            QMessageBox.information(self, "Экспорт .MD", f"Файл сохранён:\n{save_path}")

    def export_current_latex(self):
        if not self.current_lecture:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить LaTeX (.tex)", f"{self._safe_name()}_конспект.tex", "LaTeX (*.tex)"
        )
        if save_path:
            export_lecture_to_latex(self._export_payload(), save_path)
            QMessageBox.information(self, "Экспорт .TEX", f"Документ LaTeX сохранён:\n{save_path}")

    def export_current_pdf(self):
        if not self.current_lecture or self.latex_preview.pdf_exporter.busy:
            return
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF (.pdf)", f"{self._safe_name()}_конспект.pdf", "PDF (*.pdf)"
        )
        if not save_path:
            return
        self.btn_export_pdf.setEnabled(False)
        self.btn_export_pdf.setText("Подготовка PDF...")
        self.latex_preview.export_pdf(self._export_payload(), save_path)

    def on_pdf_exported(self, ok: bool, message: str):
        self.btn_export_pdf.setEnabled(True)
        self.btn_export_pdf.setText("Скачать")
        if ok:
            QMessageBox.information(self, "Экспорт PDF", f"PDF сохранён:\n{message}")
        else:
            QMessageBox.warning(self, "Экспорт PDF", message)

    def create_deadlines_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title_box = QVBoxLayout()
        title = QLabel("Задачи и дедлайны")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        title_box.addWidget(title)
        subtitle = QLabel("Домашние задания, даты сдачи работ")
        subtitle.setObjectName("muted")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        add_task_btn = QPushButton("Добавить задачу")
        add_task_btn.setObjectName("primaryBtn")
        add_task_btn.clicked.connect(self.open_add_task_dialog)
        self._set_icon(add_task_btn, "plus", "white")
        header.addWidget(add_task_btn)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.deadline_status = QComboBox()
        self.deadline_status.addItem("Активные", "pending")
        self.deadline_status.addItem("Выполненные", "completed")
        self.deadline_status.addItem("Все задачи", "all")
        self.deadline_status.currentIndexChanged.connect(self.refresh_deadlines_list)
        self.deadline_subject = QComboBox()
        self.deadline_subject.addItem("Все предметы", "")
        self.deadline_subject.currentIndexChanged.connect(self.refresh_deadlines_list)
        self.deadline_counter = QLabel("")
        self.deadline_counter.setObjectName("muted")
        filters.addWidget(self.deadline_status)
        filters.addWidget(self.deadline_subject)
        filters.addStretch()
        filters.addWidget(self.deadline_counter)
        layout.addLayout(filters)

        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_container = QWidget()
        self.tasks_vbox = QVBoxLayout(self.tasks_container)
        self.tasks_vbox.setSpacing(10)
        self.tasks_scroll.setWidget(self.tasks_container)
        layout.addWidget(self.tasks_scroll)

        self.refresh_deadlines_list()
        return page

    def _sync_subject_filter(self):
        selected = self.deadline_subject.currentData()
        subjects = sorted({lec.get("subject", "") for lec in self.lectures if lec.get("tasks")})
        self.deadline_subject.blockSignals(True)
        self.deadline_subject.clear()
        self.deadline_subject.addItem("Все предметы", "")
        if self.task_repo.get_standalone_tasks():
            self.deadline_subject.addItem("Без лекции", NO_LECTURE_FILTER)
        for subject in subjects:
            self.deadline_subject.addItem(subject, subject)
        idx = self.deadline_subject.findData(selected)
        self.deadline_subject.setCurrentIndex(idx if idx >= 0 else 0)
        self.deadline_subject.blockSignals(False)

    def refresh_deadlines_list(self):
        if not hasattr(self, "tasks_vbox"):
            return
        while self.tasks_vbox.count():
            child = self.tasks_vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.lectures = self.lecture_repo.get_all_lectures()
        self._sync_subject_filter()

        status = self.deadline_status.currentData()
        subject = self.deadline_subject.currentData()
        weights = {"high": 3, "medium": 2, "low": 1}

        everything = [(lec, t) for lec in self.lectures for t in lec.get("tasks", [])]
        everything += [(None, t) for t in self.task_repo.get_standalone_tasks()]
        pending_total = sum(1 for _, t in everything if not t.get("completed"))
        done_total = len(everything) - pending_total
        self.deadline_counter.setText(f"Активных: {pending_total}  ·  Выполнено: {done_total}")

        items = [
            (lec, t) for lec, t in everything
            if (not subject
                or (lec is None and subject == NO_LECTURE_FILTER)
                or (lec is not None and lec.get("subject") == subject))
            and (status == "all" or (status == "pending") == (not t.get("completed")))
        ]
        items.sort(key=lambda p: (p[1].get("completed", False), -weights.get(p[1].get("priority", "medium"), 2)))

        if not items:
            empty = QLabel("Нет задач по выбранным фильтрам. Запишите лекцию, импортируйте PDF или добавьте задачу.")
            empty.setObjectName("emptyState")
            self.tasks_vbox.addWidget(empty)
            self.tasks_vbox.addStretch()
            return

        for lec, task in items:
            card = QFrame()
            card.setObjectName("card")
            row = QHBoxLayout(card)
            row.setContentsMargins(14, 12, 14, 12)
            row.setSpacing(12)

            cb = QCheckBox()
            cb.setChecked(bool(task.get("completed", False)))
            cb.toggled.connect(lambda checked, t_ref=task: self.on_toggle_task(t_ref, checked))
            row.addWidget(cb)

            info_col = QVBoxLayout()
            task_lbl = QLabel(task.get("task", ""))
            task_lbl.setWordWrap(True)
            task_lbl.setObjectName("taskTitleDone" if task.get("completed") else "taskTitle")
            info_col.addWidget(task_lbl)
            where = lec.get("subject", "") if lec else "Без лекции"
            meta_lbl = QLabel(f"{where}  ·  Срок: {task.get('deadline', 'По графику')}")
            meta_lbl.setObjectName("deadlineText")
            info_col.addWidget(meta_lbl)
            row.addLayout(info_col, stretch=1)

            prio_combo = QComboBox()
            prio_combo.addItem("Высокий", "high")
            prio_combo.addItem("Обычный", "medium")
            prio_combo.addItem("Низкий", "low")
            prio_combo.setCurrentIndex({"high": 0, "medium": 1, "low": 2}.get(task.get("priority", "medium"), 1))
            prio_combo.currentIndexChanged.connect(
                lambda _, combo=prio_combo, t_ref=task: self.on_change_task_priority(t_ref, combo.currentData())
            )
            row.addWidget(prio_combo)

            if lec is not None:
                open_btn = QPushButton("Открыть лекцию →")
                open_btn.clicked.connect(lambda checked=False, l_ref=lec: self.open_lecture_viewer(l_ref))
                row.addWidget(open_btn)
            self.tasks_vbox.addWidget(card)

        self.tasks_vbox.addStretch()

    def on_toggle_task(self, task_ref: dict, completed: bool):
        task_ref["completed"] = completed
        self.task_repo.toggle_task(task_ref["id"], completed)
        self.refresh_deadlines_list()

    def on_change_task_priority(self, task_ref: dict, new_priority: str):
        task_ref["priority"] = new_priority
        self.task_repo.update_priority(task_ref["id"], new_priority)
        self.refresh_deadlines_list()

    def open_add_task_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Добавить задачу или дедлайн")
        dlg.setFixedWidth(420)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(10)

        inp_task = QLineEdit()
        inp_task.setPlaceholderText("Что нужно сделать (напр.: Доказать критерий Поста)")
        inp_deadline = QLineEdit()
        inp_deadline.setPlaceholderText("Срок (напр.: К следующему семинару)")
        prio_cb = QComboBox()
        prio_cb.addItem("Высокий", "high")
        prio_cb.addItem("Обычный", "medium")
        prio_cb.addItem("Низкий", "low")

        lecture_cb = QComboBox()
        lecture_cb.addItem("Без лекции (просто задача)", None)
        for lec in self.lecture_repo.get_all_lectures():
            label = f"{lec.get('subject', '')} — {lec.get('title', '')} ({lec.get('date', '')})"
            lecture_cb.addItem(label, lec["id"])

        vbox.addWidget(QLabel("Задача:"))
        vbox.addWidget(inp_task)
        vbox.addWidget(QLabel("Срок / Дедлайн:"))
        vbox.addWidget(inp_deadline)
        vbox.addWidget(QLabel("Приоритет:"))
        vbox.addWidget(prio_cb)
        vbox.addWidget(QLabel("Привязать к лекции:"))
        vbox.addWidget(lecture_cb)

        btns = QHBoxLayout()
        cancel_b = QPushButton("Отмена")
        cancel_b.clicked.connect(dlg.reject)
        save_b = QPushButton("Создать")
        save_b.setObjectName("primaryBtn")

        def save_new():
            text = inp_task.text().strip()
            if not text:
                return
            target_id = lecture_cb.currentData()  # None -> задача без лекции

            self.task_repo.upsert_task(target_id, {
                "id": f"custom-{int(datetime.now().timestamp() * 1000)}",
                "task": text,
                "deadline": inp_deadline.text().strip() or "В ближайшее время",
                "completed": False,
                "priority": prio_cb.currentData(),
            })
            self.refresh_deadlines_list()
            dlg.accept()

        save_b.clicked.connect(save_new)
        btns.addStretch()
        btns.addWidget(cancel_b)
        btns.addWidget(save_b)
        vbox.addLayout(btns)
        dlg.exec()

    def create_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Память, файлы и резервные копии")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        c_vbox = QVBoxLayout(card)
        c_vbox.setContentsMargins(18, 16, 18, 16)
        self.storage_info_lbl = QLabel("")
        self.storage_info_lbl.setObjectName("storageInfo")
        self.storage_info_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        c_vbox.addWidget(self.storage_info_lbl)
        layout.addWidget(card)

        backup_card = QFrame()
        backup_card.setObjectName("card")
        b_vbox = QVBoxLayout(backup_card)
        b_vbox.setContentsMargins(18, 16, 18, 16)
        b_vbox.setSpacing(8)
        b_title = QLabel("Резервная копия")
        b_title.setObjectName("cardTitle")
        b_vbox.addWidget(b_title)
        b_hint = QLabel(
            "В один .zip попадают все лекции, задачи, формулы, история версий, закладки, профиль, "
            "аватарка и настройки. Сами аудиофайлы записей по умолчанию не включаются (они тяжёлые), "
            "их можно добавить галочкой ниже. Перед восстановлением текущая база сохраняется в папку backups_auto."
        )
        b_hint.setWordWrap(True)
        b_hint.setObjectName("muted")
        b_vbox.addWidget(b_hint)
        self.chk_backup_audio = QCheckBox("Добавить в копию аудиозаписи лекций (файл станет намного больше)")
        b_vbox.addWidget(self.chk_backup_audio)
        b_row = QHBoxLayout()
        make_btn = QPushButton("Создать резервную копию…")
        make_btn.setObjectName("primaryBtn")
        make_btn.clicked.connect(self.create_backup_dialog)
        self._set_icon(make_btn, "download", "white")
        restore_btn = QPushButton("Восстановить из копии…")
        restore_btn.clicked.connect(self.restore_backup_dialog)
        b_row.addWidget(make_btn)
        b_row.addWidget(restore_btn)
        b_row.addStretch()
        b_vbox.addLayout(b_row)
        layout.addWidget(backup_card)

        clear_btn = QPushButton("Очистить аудиозаписи")
        clear_btn.clicked.connect(self.clear_audio_files)
        self._set_icon(clear_btn, "trash", "text")
        layout.addWidget(clear_btn, alignment=Qt.AlignLeft)

        layout.addStretch()
        return page

    def refresh_storage_info(self):
        audio_files = [
            f for f in os.listdir(self.audio_dir) if os.path.isfile(os.path.join(self.audio_dir, f))
        ] if os.path.isdir(self.audio_dir) else []
        audio_mb = sum(os.path.getsize(os.path.join(self.audio_dir, f)) for f in audio_files) / (1024 * 1024)
        db_mb = os.path.getsize(self.db_manager.db_path) / (1024 * 1024) if os.path.exists(self.db_manager.db_path) else 0
        katex = "встроен" if bundled_katex_dir() else "не встроен — подгружается из интернета (для работы офлайн выполните python tools/vendor_katex.py)"
        self.storage_info_lbl.setText(
            f"• Папка данных: {self.storage_path}\n"
            f"• База данных: {self.db_manager.db_path} ({db_mb:.1f} МБ)\n"
            f"• Лекций: {len(self.lecture_repo.get_all_lectures())}\n"
            f"• Аудиозаписи: {len(audio_files)} файлов, {audio_mb:.1f} МБ ({self.audio_dir})\n"
            f"• KaTeX для формул в PDF: {katex}"
        )

    def create_backup_dialog(self):
        default = os.path.join(os.path.expanduser("~"), f"axai_backup_{datetime.now().strftime('%Y-%m-%d')}.zip")
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить резервную копию", default, "Резервная копия AxAI (*.zip)")
        if not path:
            return
        try:
            manifest = create_backup(
                self.storage_path, self.db_manager.db_path, path, self.audio_dir,
                include_audio=self.chk_backup_audio.isChecked(),
            )
        except Exception as err:
            QMessageBox.warning(self, "Резервная копия", f"Не удалось создать копию: {err}")
            return
        QMessageBox.information(
            self, "Резервная копия",
            f"Копия сохранена:\n{path}\n\nЛекций: {manifest['lectures']}, аудиофайлов: {manifest['audio_files']}",
        )

    def restore_backup_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "Выберите резервную копию", "", "Резервная копия AxAI (*.zip)")
        if not path:
            return
        try:
            manifest = read_manifest(path)
        except BackupError as err:
            QMessageBox.warning(self, "Восстановление", str(err))
            return
        reply = QMessageBox.question(
            self, "Восстановление",
            f"Копия от {manifest.get('created_at', '?')}: лекций {manifest.get('lectures', '?')}.\n\n"
            "Текущие данные будут заменены. Перед этим текущая база сохранится в папку backups_auto. Продолжить?",
        )
        if reply != QMessageBox.Yes:
            return
        try:
            restore_backup(path, self.storage_path, self.db_manager.db_path, self.audio_dir)
        except BackupError as err:
            QMessageBox.warning(self, "Восстановление", str(err))
            return
        except Exception as err:
            QMessageBox.warning(self, "Восстановление", f"Не удалось восстановить: {err}")
            return
        self.reload_after_restore()
        QMessageBox.information(self, "Восстановление", "Данные восстановлены из резервной копии.")

    def reload_after_restore(self):
        self.db_manager.init_schema()
        self.bookmark_repo = BookmarkRepository(self.db_manager)
        self.lectures = self.lecture_repo.get_all_lectures()
        self.student_profile = self.profile_repo.get_profile()
        self.app_settings = self.settings_repo.get_settings()
        self.current_lecture = None
        self.refresh_profile_widgets()
        self.refresh_history_list()
        self.refresh_deadlines_list()
        self.refresh_storage_info()

    def clear_audio_files(self):
        reply = QMessageBox.question(
            self, "Подтверждение",
            "Удалить аудиозаписи с диска? Конспекты, задачи и стенограммы сохранены в бд.",
        )
        if reply != QMessageBox.Yes:
            return
        count = 0
        for name in os.listdir(self.audio_dir):
            full = os.path.join(self.audio_dir, name)
            if os.path.isfile(full):
                os.remove(full)
                count += 1
        with self.db_manager.get_connection() as conn:
            conn.execute("UPDATE lectures SET audio_file = ''")
            conn.commit()
        self.refresh_storage_info()
        QMessageBox.information(self, "Очищено", f"Удалено аудиофайлов: {count}")

    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Настройки")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        layout.addWidget(QLabel("Оформление:"))
        self.cb_theme = QComboBox()
        for value, label in THEME_CHOICES:
            self.cb_theme.addItem(label, value)
        self._select_data(self.cb_theme, self.app_settings.get("theme", "dark"))
        self.cb_theme.currentIndexChanged.connect(self.on_theme_changed)
        layout.addWidget(self.cb_theme)

        hw_card = QFrame()
        hw_card.setObjectName("card")
        hw_vbox = QVBoxLayout(hw_card)
        hw_vbox.setContentsMargins(16, 12, 16, 12)
        self.hw_lbl = QLabel("Нажмите «Проверить», чтобы узнать характеристики ПК и состояние Ollama.")
        self.hw_lbl.setWordWrap(True)
        self.hw_lbl.setObjectName("accentText")
        hw_vbox.addWidget(self.hw_lbl)
        hw_btn = QPushButton("Проверить железо и Ollama")
        hw_btn.clicked.connect(self.refresh_hardware_info)
        hw_vbox.addWidget(hw_btn, alignment=Qt.AlignLeft)
        layout.addWidget(hw_card)

        layout.addWidget(QLabel("Режим распознавания речи:"))
        self.cb_asr_mode = QComboBox()
        self.cb_asr_mode.addItem("Whisper (модели скачиваются один раз)", "local_whisper")
        self.cb_asr_mode.addItem("Офлайн-пакет sherpa (без интернета, со спикерами)", "sherpa_offline")
        self._select_data(self.cb_asr_mode, self.app_settings.get("transcriber_backend", "local_whisper"))
        layout.addWidget(self.cb_asr_mode)

        layout.addWidget(QLabel("Язык офлайн-распознавания:"))
        self.cb_offline_lang = QComboBox()
        self.cb_offline_lang.addItem("Русский", "ru")
        self.cb_offline_lang.addItem("English", "en")
        self._select_data(self.cb_offline_lang, self.app_settings.get("offline_language", "ru"))
        layout.addWidget(self.cb_offline_lang)

        self.diar_check = QCheckBox("Разделять речь по спикерам (офлайн-режим)")
        self.diar_check.setChecked(bool(self.app_settings.get("diarization", True)))
        layout.addWidget(self.diar_check)

        layout.addWidget(QLabel("Модель Whisper для распознавания речи:"))
        self.cb_whisper_size = QComboBox()
        self.cb_whisper_size.addItem("Автоподбор под железо", "auto")
        self.cb_whisper_size.addItem("large-v3-turbo (максимальная точность)", "large-v3-turbo")
        self.cb_whisper_size.addItem("small (для компактных ноутбуков)", "small")
        self.cb_whisper_size.addItem("base (самая лёгкая)", "base")
        self._select_data(self.cb_whisper_size, self.app_settings.get("whisper_model_size", "auto"))
        layout.addWidget(self.cb_whisper_size)

        layout.addWidget(QLabel("Скорость распознавания:"))
        self.cb_speed = QComboBox()
        self.cb_speed.addItem("Быстро (меньше времени, чуть ниже точность)", "fast")
        self.cb_speed.addItem("Баланс", "balanced")
        self.cb_speed.addItem("Максимальная точность (медленнее)", "accurate")
        self._select_data(self.cb_speed, self.app_settings.get("whisper_speed", "balanced"))
        layout.addWidget(self.cb_speed)

        layout.addWidget(QLabel("Подробность первичного конспекта:"))
        self.cb_detail = QComboBox()
        self.cb_detail.addItem("Быстрый и сжатый", "fast")
        self.cb_detail.addItem("Подробный", "full")
        self._select_data(self.cb_detail, self.app_settings.get("summary_detail", "fast"))
        layout.addWidget(self.cb_detail)

        setup_btn = QPushButton("Установить или проверить модели")
        setup_btn.clicked.connect(self.offer_model_setup)
        layout.addWidget(setup_btn, alignment=Qt.AlignLeft)

        layout.addWidget(QLabel("Конспекты, формулы и дедлайны:"))
        ollama_row = QHBoxLayout()
        self.inp_ollama_model = QComboBox()
        self.inp_ollama_model.setEditable(True)
        self.inp_ollama_model.addItems(["qwen2.5:3b", "qwen2.5:7b"])
        self.inp_ollama_model.setCurrentText(self.app_settings.get("ollama_model", "qwen2.5:3b"))
        self.inp_ollama_url = QLineEdit(self.app_settings.get("ollama_url", "http://localhost:11434"))
        ollama_row.addWidget(QLabel("Модель:"))
        ollama_row.addWidget(self.inp_ollama_model)
        ollama_row.addWidget(QLabel("Адрес:"))
        ollama_row.addWidget(self.inp_ollama_url)
        layout.addLayout(ollama_row)
        llm_hint = QLabel(
            "qwen2.5:3b входит в офлайн-пакет: быстрее и работает без интернета (нужна установленная Ollama). "
            "qwen2.5:7b скачивается из интернета (около 4,7 ГБ): конспект точнее, но на процессоре заметно медленнее."
        )
        llm_hint.setWordWrap(True)
        layout.addWidget(llm_hint)

        self.noise_check = QCheckBox("Фильтрация тишины и шума аудитории")
        self.noise_check.setChecked(bool(self.app_settings.get("silero_vad", True)))
        layout.addWidget(self.noise_check)

        self.tasks_check = QCheckBox("Искать дедлайны по ключевым словам, если модель недоступна")
        self.tasks_check.setChecked(bool(self.app_settings.get("auto_extract_tasks", True)))
        layout.addWidget(self.tasks_check)

        save_btn = QPushButton("Сохранить настройки")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_ai_settings)
        layout.addWidget(save_btn)

        layout.addStretch()
        # Страница длиннее окна: без прокрутки Qt сжимает элементы (обрезает карточки и кнопки).
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _select_data(combo: QComboBox, value):
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def on_theme_changed(self):
        name = self.cb_theme.currentData()
        self.app_settings["theme"] = name
        self.settings_repo.save_settings({"theme": name})
        self.is_dark = apply_theme(QApplication.instance(), name)
        self.latex_preview.set_dark_mode(self.is_dark)
        self.refresh_icons()
        if self.current_lecture:
            self.latex_preview.render_lecture(self.current_lecture)

    def refresh_hardware_info(self):
        if getattr(self, "_hw_worker", None) is not None and self._hw_worker.isRunning():
            return
        self.hardware_checked = True
        self.hw_lbl.setText("Проверка...")
        url = self.inp_ollama_url.text().strip() or "http://localhost:11434"
        self._hw_worker = _CallWorker(lambda: HardwareInspector.inspect(url), self)
        self._hw_worker.done.connect(self._show_hardware_info)
        self._hw_worker.start()

    def _show_hardware_info(self, hw):
        if not isinstance(hw, dict):
            self.hw_lbl.setText("Не удалось определить характеристики ПК.")
            return
        if hw["ollama_online"]:
            ollama = f"работает, модели: {', '.join(hw['ollama_models'][:5]) or 'не установлены'}"
        else:
            ollama = "не запущена"
        self.hw_lbl.setText(
            f"Ядер CPU: {hw['cpu_cores']}  ·  ОЗУ: {hw['ram_gb']} ГБ  ·  Ускоритель: {hw['gpu_name']}\n"
            f"Рекомендуется: Whisper «{hw['recommended_whisper']}», LLM «{hw['recommended_llm']}»\n"
            f"Ollama: {ollama}"
        )

    def save_ai_settings(self):
        self.app_settings = {
            **self.app_settings,
            "transcriber_backend": self.cb_asr_mode.currentData(),
            "offline_language": self.cb_offline_lang.currentData(),
            "diarization": self.diar_check.isChecked(),
            "whisper_model_size": self.cb_whisper_size.currentData(),
            "whisper_speed": self.cb_speed.currentData(),
            "summary_detail": self.cb_detail.currentData(),
            "ollama_model": self.inp_ollama_model.currentText().strip() or "qwen2.5:3b",
            "ollama_url": self.inp_ollama_url.text().strip() or "http://localhost:11434",
            "silero_vad": self.noise_check.isChecked(),
            "auto_extract_tasks": self.tasks_check.isChecked(),
        }
        self.settings_repo.save_settings(self.app_settings)
        offline = is_offline_mode(self.app_settings)
        QMessageBox.information(
            self, "Настройки",
            "Настройки сохранены.\nРежим распознавания: "
            + ("офлайн-пакет sherpa." if offline else "Whisper."),
        )
        if offline and offline_missing(
            self.app_settings.get("offline_language", "ru"), bool(self.app_settings.get("diarization", True))
        ):
            self.offer_model_setup()

    def create_profile_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Профиль")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        id_card = QFrame()
        id_card.setObjectName("card")
        card_row = QHBoxLayout(id_card)
        card_row.setContentsMargins(16, 16, 16, 16)
        card_row.setSpacing(16)

        self.profile_avatar_lbl = QLabel()
        self.profile_avatar_lbl.setFixedSize(64, 64)
        card_row.addWidget(self.profile_avatar_lbl)

        avatar_col = QVBoxLayout()
        upload_btn = QPushButton("Загрузить аватар")
        upload_btn.clicked.connect(self.choose_user_avatar)
        avatar_col.addWidget(upload_btn)
        reset_btn = QPushButton("Сбросить")
        reset_btn.clicked.connect(self.reset_user_avatar)
        avatar_col.addWidget(reset_btn)
        card_row.addLayout(avatar_col)
        card_row.addStretch()
        layout.addWidget(id_card)

        self.prof_name = QLineEdit()
        self.prof_email = QLineEdit()
        self.prof_uni = QLineEdit()
        self.prof_faculty = QLineEdit()
        self.prof_group = QLineEdit()
        for label, field in (
            ("ФИО студента:", self.prof_name),
            ("Электронная почта:", self.prof_email),
            ("ВУЗ:", self.prof_uni),
            ("Факультет / Институт:", self.prof_faculty),
            ("Академическая группа:", self.prof_group),
        ):
            layout.addWidget(QLabel(label))
            layout.addWidget(field)

        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_profile_data)
        layout.addWidget(save_btn)
        layout.addStretch()
        return page

    def refresh_profile_widgets(self):
        p = self.student_profile
        self.prof_name.setText(p.get("name", ""))
        self.prof_email.setText(p.get("email", ""))
        self.prof_uni.setText(p.get("university", ""))
        self.prof_faculty.setText(p.get("faculty", ""))
        self.prof_group.setText(p.get("group", ""))
        first_name = (p.get("name") or "Студент").split()[0]
        self.header_avatar_btn.setText(f"  {first_name} ({p.get('group', '')})")
        self.refresh_user_avatar_widgets()

    def save_profile_data(self):
        self.student_profile = {
            "name": self.prof_name.text().strip() or "Студент",
            "email": self.prof_email.text().strip() or "student@university.ru",
            "university": self.prof_uni.text().strip() or "Университет",
            "faculty": self.prof_faculty.text().strip() or "Факультет",
            "group": self.prof_group.text().strip() or "Б26-XXX",
            "semester": self.student_profile.get("semester", 3),
        }
        self.profile_repo.save_profile(self.student_profile)
        self.refresh_profile_widgets()
        QMessageBox.information(self, "Профиль", "Профиль сохранён.")

    def handle_import_document(self):
        if self.import_worker is not None and self.import_worker.isRunning():
            return
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Учебный документ (PDF / Markdown / текст)", "", "Документы (*.pdf *.md *.txt *.tex)"
        )
        if not file_path:
            return

        dialog = QProgressDialog("Чтение документа...", "Отмена", 0, 100, self)
        dialog.setWindowTitle("Импорт документа")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)

        worker = ImportDocumentWorker(file_path, self.app_settings)
        self.import_worker = worker
        worker.progress.connect(lambda pct, msg: (dialog.setValue(pct), dialog.setLabelText(msg)))
        dialog.canceled.connect(worker.requestInterruption)
        worker.finished.connect(lambda res: self._on_import_done(dialog, res))
        worker.error.connect(lambda msg: self._on_import_error(dialog, msg))
        worker.start()

    def _on_import_error(self, dialog: QProgressDialog, message: str):
        dialog.close()
        if "отменён" not in message:
            QMessageBox.warning(self, "Импорт документа", message)

    def _on_import_done(self, dialog: QProgressDialog, parsed: dict):
        dialog.close()
        lec_id = f"doc-{int(datetime.now().timestamp())}"
        new_lecture = {
            "id": lec_id,
            "title": parsed["title"],
            "subject": parsed["subject"],
            "lecturer": parsed["lecturer"],
            "date": parsed["date"],
            "duration_min": parsed["duration_min"],
            "text": parsed["text"],
            "raw_transcript": parsed.get("raw_transcript", ""),
            "tasks": parsed["tasks"],
            "formulas": parsed.get("formulas", []),
        }
        unpack_raw_json_lecture_if_needed(new_lecture)
        saved = self.lecture_repo.upsert_lecture(new_lecture)
        self.revision_repo.add_revision_if_new(lec_id, saved["text"], "Импортированная версия документа")
        self.refresh_history_list()
        self.refresh_deadlines_list()
        self.open_lecture_viewer(saved)
        if parsed.get("warning"):
            QMessageBox.warning(self, "Импорт документа", parsed["warning"])

    def check_models_on_start(self):
        if self.app_settings.get("setup_prompt_dismissed"):
            return
        settings = dict(self.app_settings)
        self._start_check = _CallWorker(lambda: setup_status(settings), self)

        def on_status(result):
            if isinstance(result, dict) and not result["ready"]:
                self.offer_model_setup(status=result, allow_dismiss=True)

        self._start_check.done.connect(on_status)
        self._start_check.start()

    def offer_model_setup(self, status=None, allow_dismiss=False):
        if self.setup_worker is not None and self.setup_worker.isRunning():
            return
        status = status if isinstance(status, dict) else setup_status(self.app_settings)
        if status["ready"]:
            QMessageBox.information(self, "Модели", "Все нужные модели уже установлены.")
            return
        needs = "\n".join(f"• {item}" for item in status["needs"])
        box = QMessageBox(self)
        box.setWindowTitle("Установка моделей")
        box.setText(
            "Для работы без интернета нужно один раз скачать:\n\n"
            f"{needs}\n\nВсего около {status['need_mb'] / 1024:.1f} ГБ. "
            "Данные записей при этом никуда не отправляются."
        )
        install_btn = box.addButton("Установить", QMessageBox.AcceptRole)
        box.addButton("Позже", QMessageBox.RejectRole)
        never_btn = box.addButton("Больше не спрашивать", QMessageBox.RejectRole) if allow_dismiss else None
        box.exec()
        if box.clickedButton() is install_btn:
            self.run_model_setup()
        elif never_btn is not None and box.clickedButton() is never_btn:
            self.app_settings["setup_prompt_dismissed"] = True
            self.settings_repo.save_settings({"setup_prompt_dismissed": True})

    def run_model_setup(self):
        dialog = QProgressDialog("Подготовка...", "Отмена", 0, 100, self)
        dialog.setWindowTitle("Установка моделей")
        dialog.setWindowModality(Qt.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setMinimumWidth(480)
        dialog.setValue(0)

        worker = SetupWorker(self.app_settings)
        self.setup_worker = worker
        worker.progress.connect(lambda pct, msg: (dialog.setValue(pct), dialog.setLabelText(msg)))
        dialog.canceled.connect(worker.requestInterruption)

        def on_done(message: str):
            dialog.close()
            QMessageBox.information(self, "Установка моделей", message)

        def on_error(message: str):
            dialog.close()
            QMessageBox.warning(self, "Установка моделей", message)

        worker.finished.connect(on_done)
        worker.error.connect(on_error)
        worker.start()

    def closeEvent(self, event):
        self.transcript_panel.stop()
        if self.is_recording:
            self.recorder.stop()
        for worker in (self.worker, self.expand_worker, self.import_worker, self.setup_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(3000)
        super().closeEvent(event)


def install_crash_log() -> None:
    """Пишет аварии в ~/AxAI_Storage/crash.log: и ошибки Python, и вылеты из нативного кода."""
    try:
        import faulthandler
        import traceback
        from paths import STORAGE_DIR

        log_file = open(os.path.join(STORAGE_DIR, "crash.log"), "a", encoding="utf-8", buffering=1)
        log_file.write(f"\n=== запуск {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        faulthandler.enable(file=log_file, all_threads=True)

        def hook(exc_type, exc, tb):
            log_file.write("".join(traceback.format_exception(exc_type, exc, tb)))
            sys.__excepthook__(exc_type, exc, tb) if sys.__stderr__ else None

        sys.excepthook = hook
    except Exception:
        pass


if __name__ == "__main__":
    install_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName("AxAI")
    app.setWindowIcon(QIcon(app_icon_pixmap(256)))
    window = AxAIDesktopApp()
    window.show()
    QTimer.singleShot(800, window.check_models_on_start)
    sys.exit(app.exec())
