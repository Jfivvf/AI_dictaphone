"""
Запуск:
    cd python_desktop
    python main.py
"""
import os
import re
import shutil
import sys
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QProgressBar,
    QPushButton, QScrollArea, QStackedWidget, QTextEdit, QVBoxLayout, QWidget,
)

from audio_recorder import MicrophoneRecorder
from audio_worker import ExpandLectureWorker, TranscriptionWorker
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
from pdf_importer import parse_pdf_document
from ui.latex_preview import (
    LatexLecturePreview, crop_and_compress_avatar_square, draw_fixed_app_icon_pixmap,
    pixmap_from_png_bytes,
)


DARK_STYLE = """
QMainWindow, QDialog { background-color: #0a0a0a; }
QWidget { color: #e5e5e5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
QFrame#headerBar { background-color: #171717; border-bottom: 1px solid #262626; }
QFrame#sidebar { background-color: #171717; border-right: 1px solid #262626; }
QFrame#card { background-color: #171717; border: 1px solid #262626; border-radius: 12px; }
QFrame#progressCard { background-color: #14141d; border: 1px solid #4338ca; border-radius: 12px; }
QPushButton { background-color: #1f1f23; border: 1px solid #2e2e34; border-radius: 8px; padding: 7px 13px; font-size: 12px; font-weight: 500; color: #e5e5e5; }
QPushButton:hover { background-color: #2a2a30; border-color: #3f3f46; }
QPushButton:disabled { color: #71717a; }
QPushButton#primaryBtn { background-color: #4f46e5; border: none; color: #ffffff; font-weight: 600; }
QPushButton#primaryBtn:hover { background-color: #4338ca; }
QPushButton#expandAiBtn { background-color: #1e1b4b; border: 1px solid #4338ca; color: #a5b4fc; font-weight: 600; }
QPushButton#expandAiBtn:hover { background-color: #312e81; }
QPushButton#revertBtn { background-color: #2e1f0f; border: 1px solid #b45309; color: #fcd34d; font-weight: 600; }
QPushButton#revertBtn:hover { background-color: #452c14; }
QPushButton#recordBtn { background-color: #e11d48; border: none; color: #ffffff; font-weight: 600; padding: 12px 24px; font-size: 13px; border-radius: 10px; }
QPushButton#recordBtn:hover { background-color: #be123c; }
QLineEdit, QComboBox, QTextEdit { background-color: #121214; border: 1px solid #27272a; border-radius: 8px; padding: 8px 12px; font-size: 13px; color: #f4f4f5; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid #6366f1; }
QListWidget { background-color: #141417; border: 1px solid #262626; border-radius: 10px; padding: 6px; }
QListWidget::item { padding: 12px; border-radius: 8px; margin: 3px 0px; }
QListWidget::item:hover { background-color: #1f1f24; }
QListWidget::item:selected { background-color: #27272a; border-left: 3px solid #6366f1; }
QProgressBar { border: 1px solid #27272a; border-radius: 6px; text-align: center; height: 16px; background-color: #18191d; color: #ffffff; font-size: 11px; font-weight: 600; }
QProgressBar::chunk { background-color: #4f46e5; border-radius: 5px; }
"""

NAV_ACTIVE = "text-align: left; padding: 10px 12px; background-color: #4f46e5; color: white; font-weight: 600;"
NAV_IDLE = "text-align: left; padding: 10px 12px; background-color: #18191d; color: #e4e4e7;"


def format_mmss(seconds: int) -> str:
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class AxAIDesktopApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AxAI")
        self.resize(1260, 820)
        self.setStyleSheet(DARK_STYLE)

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
        self.current_lecture = None
        self.pending_bookmarks = []
        self.worker = None
        self.expand_worker = None
        self.hardware_checked = False

        self.setWindowIcon(QIcon(draw_fixed_app_icon_pixmap(64)))

        self.recorder = MicrophoneRecorder()
        self.is_recording = False
        self.record_seconds = 0
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.update_record_timer)

        self.expand_elapsed_sec = 0
        self.expand_timer = QTimer(self)
        self.expand_timer.timeout.connect(self._tick_expand_elapsed)

        self.init_ui()
        QShortcut(QKeySequence("Ctrl+M"), self).activated.connect(self.add_bookmark)

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

    # аватарка 
    def get_user_avatar_pixmap(self, size: int = 36):
        return pixmap_from_png_bytes(self.profile_repo.get_avatar_bytes(), size=size)

    def choose_user_avatar(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Фото", "",
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

    # интерфей 
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
        brand_icon.setPixmap(draw_fixed_app_icon_pixmap(32))
        brand_icon.setFixedSize(34, 34)
        header_layout.addWidget(brand_icon)

        brand_label = QLabel("AxAI")
        brand_label.setFont(QFont("Arial", 14, QFont.Bold))
        brand_label.setStyleSheet("color: #ffffff;")
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
            ("profile", "Профиль"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(NAV_IDLE)
            btn.clicked.connect(lambda checked=False, k=key: self.navigate_to(k))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[key] = btn
        sidebar_layout.addStretch()

        import_pdf_btn = QPushButton("📄 Импорт PDF / .MD")
        import_pdf_btn.setObjectName("primaryBtn")
        import_pdf_btn.clicked.connect(self.handle_import_document)
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
            btn.setStyleSheet(NAV_ACTIVE if key == page_name else NAV_IDLE)

    # запись
    def create_record_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Запись")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        meta_row = QHBoxLayout()
        self.input_subject = QLineEdit()
        self.input_subject.setPlaceholderText("Дисциплина")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Тема")
        self.input_lecturer = QLineEdit()
        self.input_lecturer.setPlaceholderText("Преподаватель")
        for field in (self.input_subject, self.input_title, self.input_lecturer):
            meta_row.addWidget(field)
        layout.addLayout(meta_row)

        ctx_lbl = QLabel("Контекст:")
        ctx_lbl.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(ctx_lbl)

        self.input_record_context = QTextEdit()
        self.input_record_context.setPlaceholderText(
            "Повышает точность распознавания терминов и формул. "
        )
        self.input_record_context.setMaximumHeight(95)
        layout.addWidget(self.input_record_context)

        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont("Arial", 36, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #6366f1; padding: 14px;")
        layout.addWidget(self.timer_label)

        btn_box = QHBoxLayout()
        self.btn_record = QPushButton("Начать запись с микрофона")
        self.btn_record.setObjectName("recordBtn")
        self.btn_record.clicked.connect(self.toggle_recording)

        self.btn_bookmark = QPushButton("Метка (Ctrl+M)")
        self.btn_bookmark.setEnabled(False)
        self.btn_bookmark.clicked.connect(self.add_bookmark)

        self.btn_upload_audio = QPushButton("Загрузить аудиофайл (WAV/MP3/M4A)")
        self.btn_upload_audio.clicked.connect(self.handle_upload_audio)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_record)
        btn_box.addWidget(self.btn_bookmark)
        btn_box.addWidget(self.btn_upload_audio)
        btn_box.addStretch()
        layout.addLayout(btn_box)

        self.record_progress = QProgressBar()
        self.record_progress.setVisible(False)
        layout.addWidget(self.record_progress)

        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("color: #a5b4fc; font-size: 12px; font-weight: 500;")
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
        return page

    def toggle_recording(self):
        if not self.is_recording:
            wav_path = os.path.join(self.audio_dir, f"rec_{int(datetime.now().timestamp())}.wav")
            try:
                self.recorder.start(wav_path)
            except RuntimeError as err:
                QMessageBox.warning(self, "Микрофон", str(err))
                return
            self.is_recording = True
            self.record_seconds = 0
            self.timer_label.setText("00:00")
            self.btn_record.setText("Завершить")
            self.btn_bookmark.setEnabled(True)
            self.btn_upload_audio.setEnabled(False)
            self.record_timer.start(1000)
        else:
            self.is_recording = False
            self.record_timer.stop()
            self.btn_record.setText("Начать запись с микрофона")
            self.btn_bookmark.setEnabled(False)
            self.btn_upload_audio.setEnabled(True)
            saved_file = self.recorder.stop()
            self.pending_bookmarks = list(self.recorder.bookmarks)
            if saved_file:
                self.start_transcription(saved_file)
            else:
                self.status_label.setText("Звук не записан.")

    def add_bookmark(self):
        if not self.is_recording:
            return
        mark = self.recorder.add_bookmark()
        self.status_label.setText(f"Метка поставлена: {format_mmss(mark['time_sec'])}")

    def update_record_timer(self):
        self.record_seconds += 1
        self.timer_label.setText(format_mmss(self.record_seconds))

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
        self.btn_record.setEnabled(False)
        self.btn_upload_audio.setEnabled(False)
        self.status_label.setText("Подготовка распознавания речи...")

        self.worker = TranscriptionWorker(
            audio_path=audio_path,
            title=self.input_title.text().strip() or "Занятие",
            subject=self.input_subject.text().strip() or "Дисциплина",
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
        self.btn_record.setEnabled(True)
        self.btn_upload_audio.setEnabled(True)

    def on_transcription_progress(self, val: int, text: str):
        self.record_progress.setValue(val)
        self.status_label.setText(text)

    def on_transcription_finished(self, result: dict, audio_path: str):
        self._finish_processing_ui()
        self.status_label.setText("Конспект сохранён.")

        segments = result.get("segments", [])
        if segments:
            duration_min = max(1, int(segments[-1].get("end", 0) // 60))
        else:
            duration_min = max(1, self.record_seconds // 60)

        lec_id = f"lec-{int(datetime.now().timestamp())}"
        new_lecture = {
            "id": lec_id,
            "title": self.input_title.text().strip() or "Конспект",
            "subject": self.input_subject.text().strip() or "Занятие",
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

    # моои проекты
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
        self.search_input.setPlaceholderText("Поиск по конспектам")
        self.search_input.setFixedWidth(420)
        self.search_input.textChanged.connect(self.refresh_history_list)
        header.addWidget(self.search_input)

        import_btn = QPushButton("Импорт PDF / MD")
        import_btn.setObjectName("primaryBtn")
        import_btn.clicked.connect(self.handle_import_document)
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

    # просмотр конспекта
    def create_viewer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(10)

        top_bar = QHBoxLayout()
        back_btn = QPushButton("← Назад к лекциям")
        back_btn.clicked.connect(lambda: self.navigate_to("history"))
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

        self.btn_export_pdf = QPushButton("Скачать PDF")
        self.btn_export_pdf.clicked.connect(self.export_current_pdf)
        top_bar.addWidget(self.btn_export_pdf)

        export_md_btn = QPushButton("MD")
        export_md_btn.clicked.connect(self.export_current_markdown)
        top_bar.addWidget(export_md_btn)

        export_tex_btn = QPushButton("TEX")
        export_tex_btn.clicked.connect(self.export_current_latex)
        top_bar.addWidget(export_tex_btn)

        delete_lec_btn = QPushButton("🗑️")
        delete_lec_btn.setToolTip("Удалить")
        delete_lec_btn.clicked.connect(self.delete_current_lecture)
        top_bar.addWidget(delete_lec_btn)
        layout.addLayout(top_bar)

        self.viewer_title = QLabel("Название")
        self.viewer_title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(self.viewer_title)

        self.viewer_meta = QLabel("")
        self.viewer_meta.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(self.viewer_meta)

        self.expand_progress_card = QFrame()
        self.expand_progress_card.setObjectName("progressCard")
        self.expand_progress_card.setVisible(False)
        p_vbox = QVBoxLayout(self.expand_progress_card)
        p_vbox.setContentsMargins(16, 12, 16, 12)
        p_vbox.setSpacing(6)

        p_top = QHBoxLayout()
        self.expand_stage_lbl = QLabel("")
        self.expand_stage_lbl.setStyleSheet("color: #c7d2fe; font-weight: 600; font-size: 12px;")
        p_top.addWidget(self.expand_stage_lbl)
        p_top.addStretch()
        self.expand_time_lbl = QLabel("Прошло: 0 сек")
        self.expand_time_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
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
        self.btn_sub_edit = QPushButton("Редактировать")
        self.btn_sub_edit.clicked.connect(lambda: self.switch_viewer_mode("edit"))
        self.btn_sub_transcript = QPushButton("Стенограмма")
        self.btn_sub_transcript.clicked.connect(lambda: self.switch_viewer_mode("transcript"))

        self.save_edits_btn = QPushButton("Сохранить")
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
        self.latex_preview.pdf_exporter.finished.connect(self.on_pdf_exported)
        self.text_editor = QTextEdit()
        self.transcript_viewer = QTextEdit()
        self.transcript_viewer.setReadOnly(True)
        self.viewer_stack.addWidget(self.latex_preview)
        self.viewer_stack.addWidget(self.text_editor)
        self.viewer_stack.addWidget(self.transcript_viewer)
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
                lines.append(f"[{s.get('time') or format_mmss(start_sec)}]  {s.get('text', '')}")
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
        self.transcript_viewer.setPlainText(self._build_transcript_text(lec))

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
        self.history_revs_btn.setText(f"🕒 История версий ({len(revs)})")
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
        info.setStyleSheet("color: #a1a1aa; font-size: 12px;")
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
        restore_b = QPushButton("⏪ Восстановить выбранную версию")
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
                "Исходная (лаконичная) версия" if not existing else f"Версия до правки #{len(existing) + 1}",
            )
            self.revision_repo.add_revision_if_new(lec_id, new_text, f"Ручное редактирование #{len(existing) + 2}")

        self.current_lecture["text"] = new_text
        self.lecture_repo.upsert_lecture(self.current_lecture)
        self.latex_preview.render_lecture(self.current_lecture)
        self._refresh_revision_buttons()
        self._set_viewer_meta(self.current_lecture, new_text)
        self.switch_viewer_mode("rendered")

    # Конспект
    def handle_expand_lecture_ai(self):
        if not self.current_lecture or (self.expand_worker is not None and self.expand_worker.isRunning()):
            return
        self.expand_ai_btn.setEnabled(False)
        self.expand_ai_btn.setText("⏳ Генерация подробного конспекта...")
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
        self.expand_ai_btn.setText("✨ Сделать подробнее (ИИ)")

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
        self.btn_export_pdf.setText("⏳ Подготовка PDF...")
        self.latex_preview.export_pdf(self._export_payload(), save_path)

    def on_pdf_exported(self, ok: bool, message: str):
        self.btn_export_pdf.setEnabled(True)
        self.btn_export_pdf.setText("🖨️ Скачать PDF")
        if ok:
            QMessageBox.information(self, "Экспорт PDF", f"PDF сохранён:\n{message}")
        else:
            QMessageBox.warning(self, "Экспорт PDF", message)

    # дедлайны
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
        subtitle.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()

        add_task_btn = QPushButton("➕ Добавить задачу")
        add_task_btn.setObjectName("primaryBtn")
        add_task_btn.clicked.connect(self.open_add_task_dialog)
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
        self.deadline_counter.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        filters.addWidget(self.deadline_status)
        filters.addWidget(self.deadline_subject)
        filters.addStretch()
        filters.addWidget(self.deadline_counter)
        layout.addLayout(filters)

        self.tasks_scroll = QScrollArea()
        self.tasks_scroll.setWidgetResizable(True)
        self.tasks_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
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
        pending_total = sum(1 for _, t in everything if not t.get("completed"))
        done_total = len(everything) - pending_total
        self.deadline_counter.setText(f"Активных: {pending_total}  ·  Выполнено: {done_total}")

        items = [
            (lec, t) for lec, t in everything
            if (not subject or lec.get("subject") == subject)
            and (status == "all" or (status == "pending") == (not t.get("completed")))
        ]
        items.sort(key=lambda p: (p[1].get("completed", False), -weights.get(p[1].get("priority", "medium"), 2)))

        if not items:
            empty = QLabel("Нет задач по выбранным фильтрам. Запишите лекцию, импортируйте PDF или добавьте задачу.")
            empty.setStyleSheet("color: #71717a; padding: 24px;")
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
            task_lbl.setStyleSheet(
                "color: #71717a; text-decoration: line-through; font-size: 13px;"
                if task.get("completed") else "color: #f4f4f5; font-weight: 600; font-size: 13px;"
            )
            info_col.addWidget(task_lbl)
            meta_lbl = QLabel(f"{lec.get('subject', '')}  ·  Срок: {task.get('deadline', 'По графику')}")
            meta_lbl.setStyleSheet("color: #fbbf24; font-size: 11px;")
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

            open_btn = QPushButton("Открыть лекцию")
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
        inp_task.setPlaceholderText("Что нужно сделать?")
        inp_deadline = QLineEdit()
        inp_deadline.setPlaceholderText("Срок")
        prio_cb = QComboBox()
        prio_cb.addItem("Высокий", "high")
        prio_cb.addItem("Обычный", "medium")
        prio_cb.addItem("Низкий", "low")

        vbox.addWidget(QLabel("Задача:"))
        vbox.addWidget(inp_task)
        vbox.addWidget(QLabel("Дедлайн:"))
        vbox.addWidget(inp_deadline)
        vbox.addWidget(QLabel("Приоритет:"))
        vbox.addWidget(prio_cb)

        btns = QHBoxLayout()
        cancel_b = QPushButton("Отмена")
        cancel_b.clicked.connect(dlg.reject)
        save_b = QPushButton("Создать")
        save_b.setObjectName("primaryBtn")

        def save_new():
            text = inp_task.text().strip()
            if not text:
                return
            self.lectures = self.lecture_repo.get_all_lectures()
            if not self.lectures:
                base = self.lecture_repo.upsert_lecture({
                    "id": f"lec-{int(datetime.now().timestamp())}",
                    "title": "Общие учебные задачи",
                    "subject": "Общее",
                    "lecturer": "Самостоятельная работа",
                    "date": datetime.now().strftime("%d.%m.%Y"),
                    "duration_min": 30,
                    "text": "## Общие задачи семестра",
                    "tasks": [],
                })
                target_id = base["id"]
            else:
                target_id = self.lectures[0]["id"]

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

    # память и резервные копии
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
        self.storage_info_lbl.setStyleSheet("color: #e4e4e7; font-size: 13px;")
        self.storage_info_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
        c_vbox.addWidget(self.storage_info_lbl)
        layout.addWidget(card)

        backup_card = QFrame()
        backup_card.setObjectName("card")
        b_vbox = QVBoxLayout(backup_card)
        b_vbox.setContentsMargins(18, 16, 18, 16)
        b_vbox.setSpacing(8)
        b_title = QLabel("Резервная копия")
        b_title.setStyleSheet("font-weight: 600; font-size: 14px;")
        b_vbox.addWidget(b_title)
        b_hint = QLabel(
            "В один .zip попадают все лекции, задачи, формулы, история версий, закладки, профиль, "
            "аватарка и настройки. Перед восстановлением текущая база сохраняется в папку backups_auto."
        )
        b_hint.setWordWrap(True)
        b_hint.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        b_vbox.addWidget(b_hint)
        self.chk_backup_audio = QCheckBox("Включить аудиозаписи (файл будет значительно больше)")
        b_vbox.addWidget(self.chk_backup_audio)
        b_row = QHBoxLayout()
        make_btn = QPushButton("💾 Создать резервную копию…")
        make_btn.setObjectName("primaryBtn")
        make_btn.clicked.connect(self.create_backup_dialog)
        restore_btn = QPushButton("♻️ Восстановить из копии…")
        restore_btn.clicked.connect(self.restore_backup_dialog)
        b_row.addWidget(make_btn)
        b_row.addWidget(restore_btn)
        b_row.addStretch()
        b_vbox.addLayout(b_row)
        layout.addWidget(backup_card)

        clear_btn = QPushButton("🗑️ Очистить аудиозаписи")
        clear_btn.clicked.connect(self.clear_audio_files)
        layout.addWidget(clear_btn, alignment=Qt.AlignLeft)

        layout.addStretch()
        return page

    def refresh_storage_info(self):
        audio_files = [
            f for f in os.listdir(self.audio_dir) if os.path.isfile(os.path.join(self.audio_dir, f))
        ] if os.path.isdir(self.audio_dir) else []
        audio_mb = sum(os.path.getsize(os.path.join(self.audio_dir, f)) for f in audio_files) / (1024 * 1024)
        db_mb = os.path.getsize(self.db_manager.db_path) / (1024 * 1024) if os.path.exists(self.db_manager.db_path) else 0
        katex = "встроен" if bundled_katex_dir() else "НЕ НАЙДЕН (PDF с формулами недоступен)"
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
            "Удалить аудиозаписи с диска? Конспекты, задачи и стенограммы в базе останутся.",
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

    # ------------------------------------------------------------------
    # 6. Настройки ИИ
    # ------------------------------------------------------------------
    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Настройки ИИ: распознавание речи и конспекты")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        hw_card = QFrame()
        hw_card.setObjectName("card")
        hw_vbox = QVBoxLayout(hw_card)
        hw_vbox.setContentsMargins(16, 12, 16, 12)
        self.hw_lbl = QLabel("Нажмите «Проверить», чтобы узнать характеристики ПК и состояние Ollama.")
        self.hw_lbl.setWordWrap(True)
        self.hw_lbl.setStyleSheet("color: #a5b4fc; font-size: 12px;")
        hw_vbox.addWidget(self.hw_lbl)
        hw_btn = QPushButton("🔍 Проверить железо и Ollama")
        hw_btn.clicked.connect(self.refresh_hardware_info)
        hw_vbox.addWidget(hw_btn, alignment=Qt.AlignLeft)
        layout.addWidget(hw_card)

        layout.addWidget(QLabel("1. Распознавание речи:"))
        self.cb_transcriber = QComboBox()
        self.cb_transcriber.addItem("Локальный Faster-Whisper + Silero VAD (офлайн)", "local_whisper")
        self.cb_transcriber.addItem("Облачный Gemini (нужен GEMINI_API_KEY, аудио уходит в облако)", "gemini_cloud")
        self._select_data(self.cb_transcriber, self.app_settings.get("transcriber_backend", "local_whisper"))
        layout.addWidget(self.cb_transcriber)

        layout.addWidget(QLabel("Модель Whisper:"))
        self.cb_whisper_size = QComboBox()
        self.cb_whisper_size.addItem("Автоподбор под железо", "auto")
        self.cb_whisper_size.addItem("large-v3-turbo (максимальная точность)", "large-v3-turbo")
        self.cb_whisper_size.addItem("small (для компактных ноутбуков)", "small")
        self.cb_whisper_size.addItem("base (самая лёгкая)", "base")
        self._select_data(self.cb_whisper_size, self.app_settings.get("whisper_model_size", "auto"))
        layout.addWidget(self.cb_whisper_size)

        layout.addWidget(QLabel("2. Конспект, формулы и дедлайны:"))
        self.cb_summarizer = QComboBox()
        self.cb_summarizer.addItem("Авто: локальная Ollama (облако только если разрешено ниже)", "auto")
        self.cb_summarizer.addItem("Только локальная Ollama", "local_ollama")
        self.cb_summarizer.addItem("Облачный Gemini (нужен GEMINI_API_KEY, текст уходит в облако)", "gemini_cloud")
        self._select_data(self.cb_summarizer, self.app_settings.get("summarizer_backend", "auto"))
        layout.addWidget(self.cb_summarizer)

        self.chk_cloud_fallback = QCheckBox("Если Ollama недоступна, использовать облачный Gemini (данные уйдут в облако)")
        self.chk_cloud_fallback.setChecked(bool(self.app_settings.get("allow_cloud_fallback", False)))
        layout.addWidget(self.chk_cloud_fallback)

        ollama_row = QHBoxLayout()
        self.inp_ollama_model = QLineEdit(self.app_settings.get("ollama_model", "qwen2.5:7b"))
        self.inp_ollama_url = QLineEdit(self.app_settings.get("ollama_url", "http://localhost:11434"))
        ollama_row.addWidget(QLabel("Модель Ollama:"))
        ollama_row.addWidget(self.inp_ollama_model)
        ollama_row.addWidget(QLabel("Адрес:"))
        ollama_row.addWidget(self.inp_ollama_url)
        layout.addLayout(ollama_row)

        self.noise_check = QCheckBox("Фильтрация тишины и шума аудитории (Silero VAD)")
        self.noise_check.setChecked(bool(self.app_settings.get("silero_vad", True)))
        layout.addWidget(self.noise_check)

        self.tasks_check = QCheckBox("Искать дедлайны по ключевым словам, если модель недоступна")
        self.tasks_check.setChecked(bool(self.app_settings.get("auto_extract_tasks", True)))
        layout.addWidget(self.tasks_check)

        save_btn = QPushButton("💾 Сохранить настройки")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_ai_settings)
        layout.addWidget(save_btn)

        layout.addStretch()
        return page

    @staticmethod
    def _select_data(combo: QComboBox, value):
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def refresh_hardware_info(self):
        self.hardware_checked = True
        self.hw_lbl.setText("Проверка...")
        QApplication.processEvents()
        hw = HardwareInspector.inspect(self.inp_ollama_url.text().strip() or "http://localhost:11434")
        if hw["ollama_online"]:
            ollama = f"работает, модели: {', '.join(hw['ollama_models'][:5]) or 'не установлены'}"
        else:
            ollama = "не запущена (установите Ollama и выполните: ollama pull qwen2.5:7b)"
        self.hw_lbl.setText(
            f"Ядер CPU: {hw['cpu_cores']}  ·  ОЗУ: {hw['ram_gb']} ГБ  ·  Ускоритель: {hw['gpu_name']}\n"
            f"Рекомендуется: Whisper «{hw['recommended_whisper']}», LLM «{hw['recommended_llm']}»\n"
            f"Ollama: {ollama}"
        )

    def save_ai_settings(self):
        self.app_settings = {
            **self.app_settings,
            "transcriber_backend": self.cb_transcriber.currentData(),
            "whisper_model_size": self.cb_whisper_size.currentData(),
            "summarizer_backend": self.cb_summarizer.currentData(),
            "allow_cloud_fallback": self.chk_cloud_fallback.isChecked(),
            "ollama_model": self.inp_ollama_model.text().strip() or "qwen2.5:7b",
            "ollama_url": self.inp_ollama_url.text().strip() or "http://localhost:11434",
            "silero_vad": self.noise_check.isChecked(),
            "auto_extract_tasks": self.tasks_check.isChecked(),
        }
        self.settings_repo.save_settings(self.app_settings)
        QMessageBox.information(self, "Настройки", "Настройки сохранены.")

    # профиль
    def create_profile_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Профиль студента")
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
        upload_btn = QPushButton("📷 Загрузить аватарку (256×256)")
        upload_btn.clicked.connect(self.choose_user_avatar)
        avatar_col.addWidget(upload_btn)
        reset_btn = QPushButton("🔄 Сбросить к аксолотлю по умолчанию")
        reset_btn.clicked.connect(self.reset_user_avatar)
        avatar_col.addWidget(reset_btn)
        hint = QLabel("Иконка приложения AxAI не меняется при смене аватарки.")
        hint.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        avatar_col.addWidget(hint)
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
            ("ВУЗ / Университет:", self.prof_uni),
            ("Факультет / Институт:", self.prof_faculty),
            ("Академическая группа:", self.prof_group),
        ):
            layout.addWidget(QLabel(label))
            layout.addWidget(field)

        save_btn = QPushButton("💾 Сохранить профиль")
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
            "group": self.prof_group.text().strip() or "101-А",
            "semester": self.student_profile.get("semester", 3),
        }
        self.profile_repo.save_profile(self.student_profile)
        self.refresh_profile_widgets()
        QMessageBox.information(self, "Профиль", "Профиль сохранён.")

    # импорт pdf markdown
    def handle_import_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Учебный документ (PDF / Markdown / текст)", "", "Документы (*.pdf *.md *.txt *.tex)"
        )
        if not file_path:
            return
        parsed = parse_pdf_document(file_path)
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

    def closeEvent(self, event):
        if self.is_recording:
            self.recorder.stop()
        for worker in (self.worker, self.expand_worker):
            if worker is not None and worker.isRunning():
                worker.requestInterruption()
                worker.wait(3000)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("AxAI")
    window = AxAIDesktopApp()
    window.show()
    sys.exit(app.exec())
