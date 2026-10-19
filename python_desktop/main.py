"""
AxAI — Нативное десктопное приложение для студентов на Python + PySide6 (Qt6)

Архитектура разделена по модульным пакетам (в соответствии с ревью):
- `db/repositories.py` — SQLite репозитории (`LectureRepository`, `TaskRepository`, `RevisionRepository`,
  `ProfileRepository`, `SettingsRepository`) с точечными транзакционными `INSERT ... ON CONFLICT DO UPDATE`,
  полнотекстовым поиском FTS5 и хранением истории версий конспекта.
- `ml/engine.py` — интерфейсы `BaseTranscriber` и `BaseSummarizer` с облачной (Gemini) и локальной
  (`faster-whisper` + Silero VAD, `Ollama / Qwen 2.5 7B` с Map-Reduce для лекций >1 часа и JSON-схемой)
  реализациями + `HardwareInspector` (проверка CPU/RAM/GPU).
- `export/exporters.py` — рендеринг формул LaTeX (локальный KaTeX + 100% офлайн-типограф), экспорт в .PDF, .MD, .TEX.
- `ui/latex_preview.py` — нативный виджет просмотра конспекта с формулами (`QWebEngineView` / `QTextBrowser`),
  а также раздельное хранение неизменной иконки приложения AxAI и пользовательской аватарки (256x256 квадрат в SQLite BLOB).

Запуск:
    cd python_desktop
    python main.py
"""
import sys
import os
import re
import json
from datetime import datetime

# Обеспечиваем корректный импорт пакетов db/, ml/, export/, ui/ при запуске из любой папки
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTextEdit, QProgressBar,
    QFileDialog, QListWidget, QListWidgetItem, QFrame, QCheckBox,
    QLineEdit, QComboBox, QMessageBox, QScrollArea, QDialog
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QIcon

from db.repositories import (
    DatabaseManager,
    LectureRepository,
    TaskRepository,
    RevisionRepository,
    ProfileRepository,
    SettingsRepository,
)
from ml.engine import HardwareInspector
from export.exporters import (
    repair_corrupted_latex,
    unpack_raw_json_lecture_if_needed,
    export_lecture_to_markdown,
    export_lecture_to_latex,
    ensure_local_katex_assets,
)
from ui.latex_preview import (
    draw_fixed_app_icon_pixmap,
    crop_and_compress_avatar_square,
    pixmap_from_png_bytes,
    LatexLecturePreview,
)
from pdf_importer import parse_pdf_document
from audio_worker import MicrophoneRecorder, TranscriptionWorker, ExpandLectureWorker


DARK_STYLE = """
QMainWindow, QDialog { background-color: #0a0a0a; }
QWidget { color: #e5e5e5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
QFrame#headerBar { background-color: #171717; border-bottom: 1px solid #262626; }
QFrame#sidebar { background-color: #171717; border-right: 1px solid #262626; }
QFrame#card { background-color: #171717; border: 1px solid #262626; border-radius: 12px; }
QFrame#progressCard { background-color: #14141d; border: 1px solid #4338ca; border-radius: 12px; }
QPushButton { background-color: #1f1f23; border: 1px solid #2e2e34; border-radius: 8px; padding: 7px 13px; font-size: 12px; font-weight: 500; color: #e5e5e5; }
QPushButton:hover { background-color: #2a2a30; border-color: #3f3f46; }
QPushButton:disabled { opacity: 0.5; color: #71717a; }
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


class AxAIDesktopApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AxAI — Учебный конспектатор с ИИ и LaTeX")
        self.resize(1260, 820)
        self.setStyleSheet(DARK_STYLE)

        # 1. Инициализация хранилища и слоя SQLite-репозиториев
        self.storage_path = os.path.expanduser("~/AxAI_Storage")
        os.makedirs(self.storage_path, exist_ok=True)
        self.db_manager = DatabaseManager(self.storage_path)
        self.lecture_repo = LectureRepository(self.db_manager)
        self.task_repo = TaskRepository(self.db_manager)
        self.revision_repo = RevisionRepository(self.db_manager)
        self.profile_repo = ProfileRepository(self.db_manager)
        self.settings_repo = SettingsRepository(self.db_manager)

        # Миграция старых лекций из lectures.json (если были созданы в ранних версиях)
        self._migrate_legacy_json_if_needed()

        self.lectures = self.lecture_repo.get_all_lectures()
        self.student_profile = self.profile_repo.get_profile()
        self.app_settings = self.settings_repo.get_settings()
        self.current_lecture = None

        # 2. Неизменная системная иконка приложения AxAI (не зависит от аватарки пользователя!)
        self.setWindowIcon(QIcon(draw_fixed_app_icon_pixmap(64)))

        # 3. Аудио-рекордер и таймеры
        self.recorder = MicrophoneRecorder()
        self.is_recording = False
        self.record_seconds = 0
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.update_record_timer)

        # Таймер плавного прогресс-бара для «Сделать подробнее (ИИ)»
        self.expand_elapsed_sec = 0
        self.expand_progress_val = 0
        self.expand_timer = QTimer(self)
        self.expand_timer.timeout.connect(self._tick_expand_progress)

        self.init_ui()

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

    # ================= ИКОНКА ПРИЛОЖЕНИЯ vs АВАТАРКА ПОЛЬЗОВАТЕЛЯ =================
    def get_user_avatar_pixmap(self, size: int = 36):
        """Возвращает пользовательскую аватарку (256x256 из SQLite BLOB) или аксолотля по умолчанию."""
        avatar_bytes = self.profile_repo.get_avatar_bytes()
        return pixmap_from_png_bytes(avatar_bytes, size=size)

    def choose_user_avatar(self):
        """Загружает, обрезает до квадрата 256x256 и сохраняет ТОЛЬКО аватарку профиля (не меняя иконку приложения)."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите фото для аватарки профиля (будет обрезано до квадрата 256×256)",
            "",
            "Изображения (*.jpg *.jpeg *.png *.webp *.bmp)",
        )
        if path:
            png_bytes = crop_and_compress_avatar_square(path, target_size=256)
            if png_bytes:
                self.profile_repo.save_avatar_bytes(png_bytes)
                self.refresh_user_avatar_widgets()
                QMessageBox.information(
                    self,
                    "Аватарка обновлена",
                    "Аватарка профиля сжата до 256×256 и сохранена в SQLite БД.\nИконка приложения AxAI осталась неизменной.",
                )

    def reset_user_avatar(self):
        self.profile_repo.clear_avatar()
        self.refresh_user_avatar_widgets()

    def refresh_user_avatar_widgets(self):
        if hasattr(self, "header_avatar_btn"):
            self.header_avatar_btn.setIcon(QIcon(self.get_user_avatar_pixmap(24)))
        if hasattr(self, "profile_avatar_lbl"):
            self.profile_avatar_lbl.setPixmap(self.get_user_avatar_pixmap(64))

    # ================= ПОСТРОЕНИЕ ИНТЕРФЕЙСА =================
    def init_ui(self):
        root_widget = QWidget()
        root_vbox = QVBoxLayout(root_widget)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # Верхняя панель: слева фиксированный логотип бренда AxAI, справа кнопка профиля со своей аватаркой
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(56)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(10)

        self.brand_icon_lbl = QLabel()
        self.brand_icon_lbl.setPixmap(draw_fixed_app_icon_pixmap(32))
        self.brand_icon_lbl.setFixedSize(34, 34)
        self.brand_icon_lbl.setToolTip("AxAI — Фирменная иконка приложения (закреплена)")
        header_layout.addWidget(self.brand_icon_lbl)

        brand_label = QLabel("AxAI")
        brand_label.setFont(QFont("Arial", 14, QFont.Bold))
        brand_label.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(brand_label)

        header_layout.addStretch()

        self.header_avatar_btn = QPushButton(
            f"  {self.student_profile.get('name', 'Студент').split()[0]} ({self.student_profile.get('group', '204-Б')})"
        )
        self.header_avatar_btn.setIcon(QIcon(self.get_user_avatar_pixmap(24)))
        self.header_avatar_btn.setIconSize(QSize(24, 24))
        self.header_avatar_btn.setToolTip("Открыть профиль студента и настройки аватарки")
        self.header_avatar_btn.clicked.connect(lambda: self.navigate_to("profile"))
        header_layout.addWidget(self.header_avatar_btn)

        root_vbox.addWidget(header)

        # Рабочая область (Sidebar + QStackedWidget)
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
        nav_items = [
            ("record", "🎙️  Запись"),
            ("history", "📚  Мои проекты"),
            ("deadlines", "📅  Дедлайны и задачи"),
            ("storage", "💾  Память и БД SQLite"),
            ("settings", "⚙️  Настройки ИИ"),
            ("profile", "👤  Профиль студента"),
        ]

        for key, label in nav_items:
            btn = QPushButton(label)
            btn.setStyleSheet("text-align: left; padding: 10px 12px;")
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

        self.pages.addWidget(self.page_record)     # 0
        self.pages.addWidget(self.page_history)    # 1
        self.pages.addWidget(self.page_viewer)     # 2
        self.pages.addWidget(self.page_deadlines)  # 3
        self.pages.addWidget(self.page_storage)    # 4
        self.pages.addWidget(self.page_settings)   # 5
        self.pages.addWidget(self.page_profile)    # 6

        main_layout.addWidget(self.pages)
        root_vbox.addWidget(body_widget)

        self.setCentralWidget(root_widget)
        self.navigate_to("record")

    def navigate_to(self, page_name: str):
        mapping = {
            "record": 0, "history": 1, "viewer": 2,
            "deadlines": 3, "storage": 4, "settings": 5, "profile": 6,
        }
        if page_name == "deadlines":
            self.refresh_deadlines_list()
        elif page_name == "history":
            self.refresh_history_list()
        self.pages.setCurrentIndex(mapping.get(page_name, 0))
        for k, btn in self.nav_buttons.items():
            if k == page_name:
                btn.setStyleSheet(
                    "text-align: left; padding: 10px 12px; background-color: #4f46e5; color: white; font-weight: 600;"
                )
            else:
                btn.setStyleSheet(
                    "text-align: left; padding: 10px 12px; background-color: #18191d; color: #e4e4e7;"
                )

    # ================= 1. ЭКРАН ЗАПИСИ С ЖИВЫМ КОНТЕКСТОМ =================
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
        self.input_subject.setPlaceholderText("Предмет (напр.: Дискретная математика)")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Тема занятия (напр.: Функциональная полнота и критерий Поста)")
        self.input_lecturer = QLineEdit()
        self.input_lecturer.setPlaceholderText("Преподаватель (ФИО)")
        meta_row.addWidget(self.input_subject)
        meta_row.addWidget(self.input_title)
        meta_row.addWidget(self.input_lecturer)
        layout.addLayout(meta_row)

        ctx_lbl = QLabel("Контекст:")
        ctx_lbl.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(ctx_lbl)

        self.input_record_context = QTextEdit()
        self.input_record_context.setPlaceholderText(
            "Повышает точность распознавания терминов и формул"
        )
        self.input_record_context.setMaximumHeight(95)
        layout.addWidget(self.input_record_context)

        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont("Arial", 36, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #6366f1; padding: 14px;")
        layout.addWidget(self.timer_label)

        btn_box = QHBoxLayout()
        self.btn_record = QPushButton("🔴 Начать запись с микрофона")
        self.btn_record.setObjectName("recordBtn")
        self.btn_record.clicked.connect(self.toggle_recording)

        self.btn_upload_audio = QPushButton("📁 Загрузить аудиофайл (WAV/MP3/M4A)")
        self.btn_upload_audio.clicked.connect(self.handle_upload_audio)

        btn_box.addStretch()
        btn_box.addWidget(self.btn_record)
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

        layout.addStretch()
        return page

    def toggle_recording(self):
        if not self.is_recording:
            self.is_recording = True
            self.record_seconds = 0
            self.timer_label.setText("00:00")
            self.btn_record.setText("⏹️ Завершить и сформировать конспект")
            self.recorder.start()
            self.record_timer.start(1000)
        else:
            self.is_recording = False
            self.record_timer.stop()
            self.btn_record.setText("🔴 Начать запись с микрофона")
            wav_path = os.path.join(self.storage_path, f"rec_{int(datetime.now().timestamp())}.wav")
            saved_file = self.recorder.stop(wav_path)
            if saved_file and os.path.exists(saved_file):
                self.start_transcription(saved_file)

    def update_record_timer(self):
        self.record_seconds += 1
        m = self.record_seconds // 60
        s = self.record_seconds % 60
        self.timer_label.setText(f"{m:02d}:{s:02d}")

    def handle_upload_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Выберите аудиозапись лекции", "", "Аудио (*.wav *.mp3 *.m4a *.ogg *.webm)"
        )
        if path:
            self.start_transcription(path)

    def start_transcription(self, audio_path: str):
        self.record_progress.setVisible(True)
        self.record_progress.setValue(5)
        self.status_label.setText("Инициализация распознавания речи и генерации конспекта...")

        subject = self.input_subject.text().strip() or "Учебная дисциплина"
        title = self.input_title.text().strip() or "Учебное занятие"
        ai_ctx = self.input_record_context.toPlainText().strip()

        self.worker = TranscriptionWorker(
            audio_path=audio_path,
            title=title,
            subject=subject,
            ai_context=ai_ctx,
            settings=self.app_settings,
        )
        self.worker.progress.connect(self.on_transcription_progress)
        self.worker.finished.connect(lambda res: self.on_transcription_finished(res, audio_path))
        self.worker.error.connect(self.on_transcription_error)
        self.worker.start()

    def on_transcription_progress(self, val: int, text: str):
        self.record_progress.setValue(val)
        self.status_label.setText(text)

    def on_transcription_finished(self, result: dict, audio_path: str):
        self.record_progress.setVisible(False)
        self.status_label.setText("Конспект успешно сформирован и сохранен в SQLite!")

        subject = self.input_subject.text().strip() or "Учебное занятие"
        title = self.input_title.text().strip() or "Конспект лекции"
        lecturer = self.input_lecturer.text().strip() or "Преподаватель"
        ai_ctx = self.input_record_context.toPlainText().strip()

        lec_id = f"lec-{int(datetime.now().timestamp())}"
        summary_text = repair_corrupted_latex(result.get("text", ""))

        new_lecture = {
            "id": lec_id,
            "title": title,
            "subject": subject,
            "lecturer": lecturer,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "duration_min": max(1, self.record_seconds // 60),
            "text": summary_text,
            "raw_transcript": result.get("raw_transcript", ""),
            "segments": result.get("segments", []),
            "tasks": result.get("tasks", []),
            "formulas": result.get("formulas", []),
            "audio_file": audio_path,
            "ai_context": ai_ctx,
        }
        unpack_raw_json_lecture_if_needed(new_lecture)

        # Сохраняем точечно в SQLite через репозиторий и записываем первую версию в историю
        saved_lec = self.lecture_repo.upsert_lecture(new_lecture)
        self.revision_repo.add_revision_if_new(
            lec_id, saved_lec["text"], "Исходная (первичная) версия"
        )
        self.lectures = self.lecture_repo.get_all_lectures()
        self.refresh_history_list()
        self.open_lecture_viewer(saved_lec)

    def on_transcription_error(self, err_msg: str):
        self.record_progress.setVisible(False)
        self.status_label.setText("Ошибка обработки аудио")
        QMessageBox.warning(self, "Ошибка", f"Не удалось обработать аудио: {err_msg}")

    # ================= 2. ЭКРАН МОИХ ЛЕКЦИЙ (С ПОЛНОТЕКСТОВЫМ ПОИСКОМ FTS5) =================
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
        self.search_input.setPlaceholderText("🔍 Полнотекстовый поиск FTS5 по конспектам, формулам и предметам...")
        self.search_input.setFixedWidth(420)
        self.search_input.textChanged.connect(self.refresh_history_list)
        header.addWidget(self.search_input)

        import_btn = QPushButton("📄 Импорт PDF / .MD")
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
            tasks_count = len(lec.get("tasks", []))
            revs_count = len(lec.get("revisions", []))
            rev_badge = f"  ·  🕒 Версий: {revs_count}" if revs_count > 0 else ""
            item_text = (
                f"📖 {lec.get('title', 'Лекция')}  ·  {lec.get('subject', '')}\n"
                f"📅 {lec.get('date', '')}  ·  {lec.get('lecturer', '')}  ·  Задач: {tasks_count}{rev_badge}"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, lec)
            self.history_list.addItem(item)

    def on_lecture_clicked(self, item: QListWidgetItem):
        lec = item.data(Qt.UserRole)
        if lec:
            self.open_lecture_viewer(lec)

    # ================= 3. ПРОСМОТР КОНСПЕКТА (РЕНДЕР ФОРМУЛ, ПРОГРЕСС-БАР И ИСТОРИЯ ВЕРСИЙ) =================
    def create_viewer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 20, 28, 20)
        layout.setSpacing(10)

        # Панель действий
        top_bar = QHBoxLayout()
        back_btn = QPushButton("← Назад к лекциям")
        back_btn.clicked.connect(lambda: self.navigate_to("history"))
        top_bar.addWidget(back_btn)

        top_bar.addStretch()

        # Кнопка отката к предыдущей (лаконичной) версии в 1 клик
        self.revert_prev_btn = QPushButton("⏪ Вернуть предыдущую версию")
        self.revert_prev_btn.setObjectName("revertBtn")
        self.revert_prev_btn.setToolTip("Вернуться к предыдущей (более лаконичной) редакции конспекта")
        self.revert_prev_btn.clicked.connect(self.handle_revert_previous_version)
        self.revert_prev_btn.setVisible(False)
        top_bar.addWidget(self.revert_prev_btn)

        # Кнопка открытия окна истории всех версий
        self.history_revs_btn = QPushButton("🕒 История версий (0)")
        self.history_revs_btn.clicked.connect(self.open_revisions_dialog)
        top_bar.addWidget(self.history_revs_btn)

        # Кнопка контекста для ИИ
        self.context_toggle_btn = QPushButton("💡 Контекст")
        self.context_toggle_btn.clicked.connect(self.toggle_viewer_context_box)
        top_bar.addWidget(self.context_toggle_btn)

        # Кнопка «Сделать подробнее (ИИ)»
        self.expand_ai_btn = QPushButton("✨ Сделать подробнее (ИИ)")
        self.expand_ai_btn.setObjectName("expandAiBtn")
        self.expand_ai_btn.clicked.connect(self.handle_expand_lecture_ai)
        top_bar.addWidget(self.expand_ai_btn)

        export_pdf_btn = QPushButton("🖨️ Скачать PDF")
        export_pdf_btn.clicked.connect(self.export_current_pdf)
        top_bar.addWidget(export_pdf_btn)

        export_md_btn = QPushButton("⬇️ .MD")
        export_md_btn.clicked.connect(self.export_current_markdown)
        top_bar.addWidget(export_md_btn)

        export_tex_btn = QPushButton("📄 .TEX")
        export_tex_btn.clicked.connect(self.export_current_latex)
        top_bar.addWidget(export_tex_btn)

        delete_lec_btn = QPushButton("🗑️")
        delete_lec_btn.setToolTip("Удалить эту лекцию")
        delete_lec_btn.clicked.connect(self.delete_current_lecture)
        top_bar.addWidget(delete_lec_btn)

        layout.addLayout(top_bar)

        # Заголовок и метаданные лекции
        self.viewer_title = QLabel("Название лекции")
        self.viewer_title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(self.viewer_title)

        self.viewer_meta = QLabel("Предмет · Преподаватель · Дата")
        self.viewer_meta.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(self.viewer_meta)

        # Блок индикатора прогресса (Progress Bar) при генерации подробного конспекта
        self.expand_progress_card = QFrame()
        self.expand_progress_card.setObjectName("progressCard")
        self.expand_progress_card.setVisible(False)
        p_vbox = QVBoxLayout(self.expand_progress_card)
        p_vbox.setContentsMargins(16, 12, 16, 12)
        p_vbox.setSpacing(6)

        p_top = QHBoxLayout()
        self.expand_stage_lbl = QLabel("1. Анализ исходного конспекта и стенограммы...")
        self.expand_stage_lbl.setStyleSheet("color: #c7d2fe; font-weight: 600; font-size: 12px;")
        p_top.addWidget(self.expand_stage_lbl)
        p_top.addStretch()
        self.expand_time_lbl = QLabel("Прошло: 0 сек · Осталось ~28 сек")
        self.expand_time_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        p_top.addWidget(self.expand_time_lbl)
        p_vbox.addLayout(p_top)

        self.expand_progress_bar = QProgressBar()
        self.expand_progress_bar.setRange(0, 100)
        self.expand_progress_bar.setValue(8)
        p_vbox.addWidget(self.expand_progress_bar)

        layout.addWidget(self.expand_progress_card)

        # Выдвижная панель «Контекст для ИИ» внутри просмотра лекции
        self.viewer_context_card = QFrame()
        self.viewer_context_card.setObjectName("card")
        self.viewer_context_card.setVisible(False)
        c_vbox = QVBoxLayout(self.viewer_context_card)
        c_vbox.setContentsMargins(14, 10, 14, 10)
        c_vbox.setSpacing(6)
        c_vbox.addWidget(QLabel("Контекст:"))
        self.viewer_context_input = QTextEdit()
        self.viewer_context_input.setMaximumHeight(68)
        self.viewer_context_input.setPlaceholderText(
            "Повышает точность распознавания терминов и формул"
        )
        c_vbox.addWidget(self.viewer_context_input)
        c_btn_row = QHBoxLayout()
        c_btn_row.addStretch()
        run_ctx_btn = QPushButton("✨ Сформировать подробный конспект с этим контекстом")
        run_ctx_btn.setObjectName("primaryBtn")
        run_ctx_btn.clicked.connect(self.handle_expand_lecture_ai)
        c_btn_row.addWidget(run_ctx_btn)
        c_vbox.addLayout(c_btn_row)
        layout.addWidget(self.viewer_context_card)

        # Переключатель вкладок внутри лекции: Рендер с формулами LaTeX | Редактор Markdown | Стенограмма
        sub_tabs = QHBoxLayout()
        self.btn_sub_rendered = QPushButton("📖 Конспект с формулами LaTeX")
        self.btn_sub_rendered.setObjectName("primaryBtn")
        self.btn_sub_rendered.clicked.connect(lambda: self.switch_viewer_mode("rendered"))

        self.btn_sub_edit = QPushButton("✏️ Редактировать Markdown")
        self.btn_sub_edit.clicked.connect(lambda: self.switch_viewer_mode("edit"))

        self.btn_sub_transcript = QPushButton("💬 Стенограмма аудио")
        self.btn_sub_transcript.clicked.connect(lambda: self.switch_viewer_mode("transcript"))

        self.save_edits_btn = QPushButton("💾 Сохранить правки")
        self.save_edits_btn.setObjectName("primaryBtn")
        self.save_edits_btn.clicked.connect(self.save_current_lecture_text)
        self.save_edits_btn.setVisible(False)

        sub_tabs.addWidget(self.btn_sub_rendered)
        sub_tabs.addWidget(self.btn_sub_edit)
        sub_tabs.addWidget(self.btn_sub_transcript)
        sub_tabs.addStretch()
        sub_tabs.addWidget(self.save_edits_btn)
        layout.addLayout(sub_tabs)

        # Стек области чтения: 0 = LatexLecturePreview (с рендером формул), 1 = QTextEdit (редактор), 2 = Стенограмма
        self.viewer_stack = QStackedWidget()
        self.latex_preview = LatexLecturePreview(storage_path=self.storage_path, parent=self)
        self.text_editor = QTextEdit()
        self.transcript_viewer = QTextEdit()
        self.transcript_viewer.setReadOnly(True)

        self.viewer_stack.addWidget(self.latex_preview)      # 0
        self.viewer_stack.addWidget(self.text_editor)        # 1
        self.viewer_stack.addWidget(self.transcript_viewer)  # 2
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

    def open_lecture_viewer(self, lec: dict):
        unpack_raw_json_lecture_if_needed(lec)
        self.current_lecture = lec
        self.viewer_title.setText(lec.get("title", "Без названия"))

        words = len((lec.get("text") or "").split())
        self.viewer_meta.setText(
            f"{lec.get('subject', '')}  ·  {lec.get('lecturer', '')}  ·  {lec.get('date', '')}  ·  {words} слов"
        )

        clean_text = repair_corrupted_latex(lec.get("text", ""))
        self.current_lecture["text"] = clean_text
        self.text_editor.setPlainText(clean_text)
        self.viewer_context_input.setPlainText(lec.get("ai_context", ""))

        # Заполняем стенограмму
        segs = lec.get("segments", [])
        if segs:
            lines = []
            for s in segs:
                start_sec = int(s.get("start", 0))
                time_str = s.get("time") or f"{start_sec // 60:02d}:{start_sec % 60:02d}"
                lines.append(f"[{time_str}]  {s.get('text', '')}")
            self.transcript_viewer.setPlainText("\n\n".join(lines))
        else:
            self.transcript_viewer.setPlainText(lec.get("raw_transcript") or "Стенограмма отсутствует.")

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
        if not prev_rev or not self.current_lecture:
            return
        self._restore_revision_object(prev_rev)

    def _restore_revision_object(self, rev: dict):
        if not self.current_lecture:
            return
        lec_id = self.current_lecture["id"]
        current_text = self.text_editor.toPlainText().strip()
        if current_text and current_text != rev["summaryMarkdown"].strip():
            existing = self.revision_repo.get_revisions(lec_id)
            self.revision_repo.add_revision_if_new(
                lec_id,
                current_text,
                "Исходная (лаконичная) версия" if not existing else f"Сохраненная версия #{len(existing) + 1}",
            )

        self.current_lecture["text"] = rev["summaryMarkdown"]
        self.text_editor.setPlainText(rev["summaryMarkdown"])
        self.latex_preview.render_lecture(self.current_lecture)
        self.lecture_repo.upsert_lecture(self.current_lecture)
        self._refresh_revision_buttons()

        words = len(rev["summaryMarkdown"].split())
        self.viewer_meta.setText(
            f"{self.current_lecture.get('subject', '')}  ·  {self.current_lecture.get('lecturer', '')}  ·  "
            f"{self.current_lecture.get('date', '')}  ·  {words} слов"
        )

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
            "Перед каждым нажатием «Сделать подробнее (ИИ)» или ручным сохранением предыдущая версия "
            "автоматически сохраняется в SQLite. Выберите любую редакцию для мгновенного восстановления:"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        vbox.addWidget(info)

        list_w = QListWidget()
        current_trimmed = (self.current_lecture.get("text") or "").strip()
        for rev in reversed(revs):
            is_cur = rev["summaryMarkdown"].strip() == current_trimmed
            badge = "  [ТЕКУЩАЯ ВЕРСИЯ]" if is_cur else ""
            preview = rev["summaryMarkdown"].replace("\n", " ")[:110]
            item = QListWidgetItem(
                f"📌 {rev['label']}{badge}  ·  {rev['wordCount']} слов  ·  {rev['timestamp']}\n"
                f"   {preview}..."
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
            if not sel:
                return
            target_rev = sel.data(Qt.UserRole)
            if target_rev:
                self._restore_revision_object(target_rev)
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
                lec_id,
                old_text,
                "Исходная (лаконичная) версия" if not existing else f"Версия до правки #{len(existing) + 1}",
            )
            self.revision_repo.add_revision_if_new(
                lec_id,
                new_text,
                f"Ручное редактирование #{len(existing) + 2}",
            )

        self.current_lecture["text"] = new_text
        self.lecture_repo.upsert_lecture(self.current_lecture)
        self.latex_preview.render_lecture(self.current_lecture)
        self._refresh_revision_buttons()
        self.switch_viewer_mode("rendered")
        QMessageBox.information(self, "Сохранено", "Изменения сохранены в SQLite и добавлены в историю версий.")

    # ================= ГЕНЕРАЦИЯ ПОДРОБНОГО КОНСПЕКТА С ПРОГРЕСС-БАРОМ =================
    def handle_expand_lecture_ai(self):
        if not self.current_lecture:
            return
        self.expand_ai_btn.setEnabled(False)
        self.expand_ai_btn.setText("⏳ Генерация подробного конспекта...")

        # Запускаем визуальный индикатор прогресса (Progress Bar)
        self.expand_elapsed_sec = 0
        self.expand_progress_val = 6
        self.expand_progress_bar.setValue(6)
        self.expand_stage_lbl.setText("1. Анализ исходного конспекта, стенограммы и контекста лекции...")
        self.expand_time_lbl.setText("Прошло: 0 сек · Осталось ~28 сек")
        self.expand_progress_card.setVisible(True)
        self.expand_timer.start(500)

        extra_ctx = self.viewer_context_input.toPlainText().strip()
        self.current_lecture["ai_context"] = extra_ctx

        self.expand_worker = ExpandLectureWorker(
            title=self.current_lecture.get("title", "Лекция"),
            subject=self.current_lecture.get("subject", "Дисциплина"),
            current_markdown=self.text_editor.toPlainText(),
            raw_transcript=self.current_lecture.get("raw_transcript", ""),
            ai_context=extra_ctx,
            settings=self.app_settings,
        )
        self.expand_worker.progress.connect(self.on_expand_worker_progress)
        self.expand_worker.finished.connect(self.on_expand_finished)
        self.expand_worker.error.connect(self.on_expand_error)
        self.expand_worker.start()

    def _tick_expand_progress(self):
        self.expand_elapsed_sec += 0.5
        elapsed = int(self.expand_elapsed_sec)
        import math
        curved = min(95, max(self.expand_progress_val, int(96 * (1.0 - math.exp(-self.expand_elapsed_sec / 13.0)))))
        self.expand_progress_val = curved
        self.expand_progress_bar.setValue(curved)

        if curved < 28:
            self.expand_stage_lbl.setText("1. Анализ исходного конспекта, стенограммы и контекста лекции...")
        elif curved < 56:
            self.expand_stage_lbl.setText("2. Формирование теоретического разбора, теорем и строгих определений...")
        elif curved < 82:
            self.expand_stage_lbl.setText("3. Вывод математических формул LaTeX и разбор практических примеров...")
        else:
            self.expand_stage_lbl.setText("4. Составление итоговых выводов и экзаменационных вопросов с ответами...")

        rem = max(3, 30 - elapsed) if elapsed < 28 else 2
        self.expand_time_lbl.setText(f"Прошло: {elapsed} сек · Осталось ~{rem} сек")

    def on_expand_worker_progress(self, pct: int, stage_msg: str):
        self.expand_progress_val = max(self.expand_progress_val, pct)
        self.expand_progress_bar.setValue(self.expand_progress_val)
        if stage_msg:
            self.expand_stage_lbl.setText(stage_msg)

    def on_expand_finished(self, expanded_markdown: str):
        self.expand_timer.stop()
        self.expand_progress_bar.setValue(100)
        self.expand_stage_lbl.setText("Готово! Подробный конспект успешно сформирован.")
        QTimer.singleShot(600, lambda: self.expand_progress_card.setVisible(False))

        self.expand_ai_btn.setEnabled(True)
        self.expand_ai_btn.setText("✨ Сделать подробнее (ИИ)")

        if self.current_lecture and expanded_markdown:
            lec_id = self.current_lecture["id"]
            previous_md = (self.current_lecture.get("text") or "").strip()
            clean_expanded = repair_corrupted_latex(expanded_markdown.strip())

            # 1. Сохраняем предыдущую (лаконичную) версию в историю SQLite перед перезаписью
            existing = self.revision_repo.get_revisions(lec_id)
            if previous_md:
                self.revision_repo.add_revision_if_new(
                    lec_id,
                    previous_md,
                    "Исходная (лаконичная) версия" if not existing else f"Версия до расширения #{len(existing) + 1}",
                )

            # 2. Сохраняем новую расширенную версию в историю SQLite
            updated_revs = self.revision_repo.get_revisions(lec_id)
            self.revision_repo.add_revision_if_new(
                lec_id,
                clean_expanded,
                f"Подробная версия (ИИ) #{len(updated_revs) + 1}",
            )

            self.current_lecture["text"] = clean_expanded
            self.text_editor.setPlainText(clean_expanded)
            self.latex_preview.render_lecture(self.current_lecture)
            self.lecture_repo.upsert_lecture(self.current_lecture)
            self._refresh_revision_buttons()

            words = len(clean_expanded.split())
            self.viewer_meta.setText(
                f"{self.current_lecture.get('subject', '')}  ·  {self.current_lecture.get('lecturer', '')}  ·  "
                f"{self.current_lecture.get('date', '')}  ·  {words} слов"
            )

    def on_expand_error(self, err: str):
        self.expand_timer.stop()
        self.expand_progress_card.setVisible(False)
        self.expand_ai_btn.setEnabled(True)
        self.expand_ai_btn.setText("✨ Сделать подробнее (ИИ)")
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

    # ================= ЭКСПОРТ PDF (С ФОРМУЛАМИ) / MD / TEX =================
    def export_current_markdown(self):
        if not self.current_lecture:
            return
        self.current_lecture["text"] = self.text_editor.toPlainText()
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить Markdown (.md)", f"{safe_name}_конспект.md", "Markdown (*.md)"
        )
        if save_path:
            export_lecture_to_markdown(self.current_lecture, save_path)
            QMessageBox.information(self, "Экспорт .MD", f"Файл успешно сохранен:\n{save_path}")

    def export_current_latex(self):
        if not self.current_lecture:
            return
        self.current_lecture["text"] = self.text_editor.toPlainText()
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить LaTeX (.tex)", f"{safe_name}_конспект.tex", "LaTeX (*.tex)"
        )
        if save_path:
            export_lecture_to_latex(self.current_lecture, save_path)
            QMessageBox.information(self, "Экспорт .TEX", f"Документ LaTeX успешно сохранен:\n{save_path}")

    def export_current_pdf(self):
        if not self.current_lecture:
            return
        self.current_lecture["text"] = self.text_editor.toPlainText()
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF (.pdf)", f"{safe_name}_конспект.pdf", "PDF Document (*.pdf)"
        )
        if save_path:
            self.latex_preview.export_pdf_with_formulas(self.current_lecture, save_path)
            QMessageBox.information(
                self, "Экспорт PDF", f"PDF-документ с математическими формулами успешно сохранен:\n{save_path}"
            )

    # ================= 4. ДЕДЛАЙНЫ И ЗАДАЧИ (ТОЧЕЧНОЕ ОБНОВЛЕНИЕ В SQLITE) =================
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

    def refresh_deadlines_list(self):
        if not hasattr(self, "tasks_vbox"):
            return
        while self.tasks_vbox.count():
            child = self.tasks_vbox.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.lectures = self.lecture_repo.get_all_lectures()
        priority_weights = {"high": 3, "medium": 2, "low": 1}
        all_items = []
        for lec in self.lectures:
            for t in lec.get("tasks", []):
                all_items.append((lec, t))

        all_items.sort(
            key=lambda pair: (
                pair[1].get("completed", False),
                -priority_weights.get(pair[1].get("priority", "medium"), 2),
            )
        )

        if not all_items:
            empty_lbl = QLabel(
                "Нет активных дедлайнов. Запишите лекцию, импортируйте PDF или добавьте задачу вручную."
            )
            empty_lbl.setStyleSheet("color: #71717a; padding: 24px;")
            self.tasks_vbox.addWidget(empty_lbl)
            self.tasks_vbox.addStretch()
            return

        for lec, task in all_items:
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
            if task.get("completed"):
                task_lbl.setStyleSheet("color: #71717a; text-decoration: line-through; font-size: 13px;")
            else:
                task_lbl.setStyleSheet("color: #f4f4f5; font-weight: 600; font-size: 13px;")
            info_col.addWidget(task_lbl)

            meta_lbl = QLabel(f"{lec.get('subject', '')}  ·  Срок: {task.get('deadline', 'По графику')}")
            meta_lbl.setStyleSheet("color: #fbbf24; font-size: 11px;")
            info_col.addWidget(meta_lbl)
            row.addLayout(info_col, stretch=1)

            prio_combo = QComboBox()
            prio_combo.addItem("🔴 Высокий", "high")
            prio_combo.addItem("🟡 Обычный", "medium")
            prio_combo.addItem("🔵 Низкий", "low")
            current_prio = task.get("priority", "medium")
            idx = {"high": 0, "medium": 1, "low": 2}.get(current_prio, 1)
            prio_combo.setCurrentIndex(idx)
            prio_combo.currentIndexChanged.connect(
                lambda _, combo=prio_combo, t_ref=task: self.on_change_task_priority(t_ref, combo.currentData())
            )
            row.addWidget(prio_combo)

            open_lec_btn = QPushButton("Открыть лекцию →")
            open_lec_btn.clicked.connect(lambda checked=False, l_ref=lec: self.open_lecture_viewer(l_ref))
            row.addWidget(open_lec_btn)

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

        vbox.addWidget(QLabel("Задача:"))
        vbox.addWidget(inp_task)
        vbox.addWidget(QLabel("Срок / Дедлайн:"))
        vbox.addWidget(inp_deadline)
        vbox.addWidget(QLabel("Приоритет:"))
        vbox.addWidget(prio_cb)

        btns = QHBoxLayout()
        cancel_b = QPushButton("Отмена")
        cancel_b.clicked.connect(dlg.reject)
        save_b = QPushButton("Создать")
        save_b.setObjectName("primaryBtn")

        def save_new():
            txt = inp_task.text().strip()
            if not txt:
                return
            self.lectures = self.lecture_repo.get_all_lectures()
            if not self.lectures:
                base_lec = self.lecture_repo.upsert_lecture({
                    "id": f"lec-{int(datetime.now().timestamp())}",
                    "title": "Общие учебные задачи",
                    "subject": "Общее",
                    "lecturer": "Самостоятельная работа",
                    "date": datetime.now().strftime("%d.%m.%Y"),
                    "duration_min": 30,
                    "text": "## Общие задачи семестра",
                    "tasks": [],
                })
                target_lec_id = base_lec["id"]
            else:
                target_lec_id = self.lectures[0]["id"]

            self.task_repo.upsert_task(
                target_lec_id,
                {
                    "id": f"custom-{int(datetime.now().timestamp() * 1000)}",
                    "task": txt,
                    "deadline": inp_deadline.text().strip() or "В ближайшее время",
                    "completed": False,
                    "priority": prio_cb.currentData(),
                },
            )
            self.refresh_deadlines_list()
            dlg.accept()

        save_b.clicked.connect(save_new)
        btns.addStretch()
        btns.addWidget(cancel_b)
        btns.addWidget(save_b)
        vbox.addLayout(btns)
        dlg.exec()

    # ================= 5. ХРАНИЛИЩЕ И ПАМЯТЬ SQLITE =================
    def create_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Память, файлы и база данных SQLite")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        card = QFrame()
        card.setObjectName("card")
        c_vbox = QVBoxLayout(card)
        c_vbox.setContentsMargins(18, 16, 18, 16)
        c_vbox.setSpacing(8)

        info = QLabel(
            f"• Директория хранения AxAI: {self.storage_path}\n"
            f"• Файл реляционной БД SQLite (WAL + FTS5): {self.db_manager.db_path}\n"
            f"• Всего лекций в репозитории: {len(self.lectures)}"
        )
        info.setStyleSheet("color: #e4e4e7; font-size: 13px;")
        c_vbox.addWidget(info)
        layout.addWidget(card)

        katex_btn = QPushButton("📦 Скачать / обновить локальный пакет KaTeX для офлайн-рендера формул")
        katex_btn.clicked.connect(self.download_katex_offline)
        layout.addWidget(katex_btn)

        clear_btn = QPushButton("🗑️ Очистить аудиозаписи")
        clear_btn.clicked.connect(self.clear_audio_files)
        layout.addWidget(clear_btn)

        layout.addStretch()
        return page

    def download_katex_offline(self):
        assets = ensure_local_katex_assets(self.storage_path)
        if assets.get("js_path"):
            QMessageBox.information(
                self,
                "KaTeX установлен локально",
                f"Файлы KaTeX сохранены в:\n{os.path.dirname(assets['js_path'])}\n"
                "Теперь рендеринг формул в QWebEngineView работает полностью локально без CDN.",
            )
        else:
            QMessageBox.information(
                self,
                "Офлайн-типограф активен",
                "Не удалось подключиться к сети, используется встроенный автономный математический типограф LaTeX.",
            )

    def clear_audio_files(self):
        reply = QMessageBox.question(
            self, "Подтверждение", "Удалить исходные WAV-файлы с диска? Все конспекты и задачи в SQLite останутся."
        )
        if reply == QMessageBox.Yes:
            count = 0
            for f in os.listdir(self.storage_path):
                if f.endswith(".wav"):
                    os.remove(os.path.join(self.storage_path, f))
                    count += 1
            QMessageBox.information(self, "Очищено", f"Удалено аудиофайлов: {count}")

    # ================= 6. НАСТРОЙКИ ИИ + ДИАГНОСТИКА ЖЕЛЕЗА =================
    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        title = QLabel("Настройки ИИ-движка (Transcriber & Summarizer) и проверка железа")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # Карточка автопроверки железа (HardwareInspector)
        hw = HardwareInspector.inspect(self.app_settings.get("ollama_url", "http://localhost:11434"))
        hw_card = QFrame()
        hw_card.setObjectName("card")
        hw_vbox = QVBoxLayout(hw_card)
        hw_vbox.setContentsMargins(16, 12, 16, 12)
        ollama_status = (
            f"Подключен ({', '.join(hw['ollama_models'][:3]) or 'без моделей'})"
            if hw["ollama_online"]
            else "Не запущен (для локальной LLM запустите `ollama run qwen2.5:7b`)"
        )
        hw_lbl = QLabel(
            f"🖥️ Диагностика ПК: Ядер CPU: {hw['cpu_cores']}  ·  ОЗУ: {hw['ram_gb']} ГБ  ·  Ускоритель: {hw['gpu_name']}\n"
            f"🤖 Рекомендовано под ваше железо: Whisper «{hw['recommended_whisper']}»  +  Локальная LLM «{hw['recommended_llm']}»\n"
            f"🔌 Статус локального сервера Ollama: {ollama_status}"
        )
        hw_lbl.setStyleSheet("color: #a5b4fc; font-size: 12px;")
        hw_vbox.addWidget(hw_lbl)
        layout.addWidget(hw_card)

        # Выбор реализации Transcriber
        layout.addWidget(QLabel("1. Движок распознавания речи (интерфейс Transcriber):"))
        self.cb_transcriber = QComboBox()
        self.cb_transcriber.addItem("Автоматически (Локальный Faster-Whisper + Silero VAD)", "auto")
        self.cb_transcriber.addItem("Локальный Faster-Whisper (100% офлайн на ПК)", "local_whisper")
        self.cb_transcriber.addItem("Облачный Gemini File API (при наличии GEMINI_API_KEY)", "gemini_cloud")
        idx_tr = {"auto": 0, "local_whisper": 1, "gemini_cloud": 2}.get(
            self.app_settings.get("transcriber_backend", "auto"), 0
        )
        self.cb_transcriber.setCurrentIndex(idx_tr)
        layout.addWidget(self.cb_transcriber)

        # Модель Faster-Whisper (Режим максимальной точности по умолчанию)
        layout.addWidget(QLabel("Локальная модель Faster-Whisper (Режим максимальной точности):"))
        self.cb_whisper_size = QComboBox()
        self.cb_whisper_size.addItem("large-v3-turbo (Максимальная точность терминов и формул — по умолчанию)", "large-v3-turbo")
        self.cb_whisper_size.addItem(f"Автоподбор под текущее железо ({hw['recommended_whisper']})", "auto")
        self.cb_whisper_size.addItem("small (Облегченная модель для компактных ноутбуков)", "small")
        idx_ws = {"large-v3-turbo": 0, "auto": 1, "small": 2}.get(
            self.app_settings.get("whisper_model_size", "large-v3-turbo"), 0
        )
        self.cb_whisper_size.setCurrentIndex(idx_ws)
        layout.addWidget(self.cb_whisper_size)

        # Выбор реализации Summarizer
        layout.addWidget(QLabel("2. Генератор конспектов, формул и дедлайнов (интерфейс Summarizer):"))
        self.cb_summarizer = QComboBox()
        self.cb_summarizer.addItem("Авто (Gemini при наличии ключа, иначе локальная Ollama)", "auto")
        self.cb_summarizer.addItem("Локальная LLM через Ollama (Qwen 2.5 7B + Map-Reduce + JSON Schema)", "local_ollama")
        self.cb_summarizer.addItem("Облачный Gemini 2.5 Flash (GEMINI_API_KEY)", "gemini_cloud")
        idx_sm = {"auto": 0, "local_ollama": 1, "gemini_cloud": 2}.get(
            self.app_settings.get("summarizer_backend", "auto"), 0
        )
        self.cb_summarizer.setCurrentIndex(idx_sm)
        layout.addWidget(self.cb_summarizer)

        ollama_row = QHBoxLayout()
        self.inp_ollama_model = QLineEdit(self.app_settings.get("ollama_model", "qwen2.5:7b"))
        self.inp_ollama_model.setPlaceholderText("Модель Ollama (напр. qwen2.5:7b)")
        self.inp_ollama_url = QLineEdit(self.app_settings.get("ollama_url", "http://localhost:11434"))
        self.inp_ollama_url.setPlaceholderText("URL Ollama (http://localhost:11434)")
        ollama_row.addWidget(QLabel("Модель Ollama:"))
        ollama_row.addWidget(self.inp_ollama_model)
        ollama_row.addWidget(QLabel("Адрес Ollama:"))
        ollama_row.addWidget(self.inp_ollama_url)
        layout.addLayout(ollama_row)

        self.noise_check = QCheckBox("Фильтрация тишины и шума аудитории (Silero VAD)")
        self.noise_check.setChecked(bool(self.app_settings.get("silero_vad", True)))
        layout.addWidget(self.noise_check)

        self.tasks_check = QCheckBox("Автоматически извлекать дедлайны и формулы по JSON-схеме")
        self.tasks_check.setChecked(bool(self.app_settings.get("auto_extract_tasks", True)))
        layout.addWidget(self.tasks_check)

        save_settings_btn = QPushButton("💾 Сохранить настройки ИИ в SQLite")
        save_settings_btn.setObjectName("primaryBtn")
        save_settings_btn.clicked.connect(self.save_ai_settings)
        layout.addWidget(save_settings_btn)

        layout.addStretch()
        return page

    def save_ai_settings(self):
        self.app_settings = {
            "transcriber_backend": self.cb_transcriber.currentData(),
            "whisper_model_size": self.cb_whisper_size.currentData(),
            "summarizer_backend": self.cb_summarizer.currentData(),
            "ollama_model": self.inp_ollama_model.text().strip() or "qwen2.5:7b",
            "ollama_url": self.inp_ollama_url.text().strip() or "http://localhost:11434",
            "silero_vad": self.noise_check.isChecked(),
            "auto_extract_tasks": self.tasks_check.isChecked(),
        }
        self.settings_repo.save_settings(self.app_settings)
        QMessageBox.information(self, "Настройки сохранены", "Конфигурация Transcriber и Summarizer сохранена в SQLite.")

    # ================= 7. ПРОФИЛЬ СТУДЕНТА (ОТДЕЛЬНАЯ АВАТАРКА 256x256 В SQLITE BLOB) =================
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
        self.profile_avatar_lbl.setPixmap(self.get_user_avatar_pixmap(64))
        self.profile_avatar_lbl.setFixedSize(64, 64)
        card_row.addWidget(self.profile_avatar_lbl)

        avatar_btns_col = QVBoxLayout()
        upload_photo_btn = QPushButton("📷 Загрузить аватарку профиля (256×256 в SQLite)")
        upload_photo_btn.clicked.connect(self.choose_user_avatar)
        avatar_btns_col.addWidget(upload_photo_btn)

        reset_photo_btn = QPushButton("🔄 Сбросить к аксолотлю по умолчанию")
        reset_photo_btn.clicked.connect(self.reset_user_avatar)
        avatar_btns_col.addWidget(reset_photo_btn)

        hint_lbl = QLabel("Иконка окна приложения AxAI закреплена и не меняется при смене вашей аватарки.")
        hint_lbl.setStyleSheet("color: #a1a1aa; font-size: 11px;")
        avatar_btns_col.addWidget(hint_lbl)

        card_row.addLayout(avatar_btns_col)
        card_row.addStretch()
        layout.addWidget(id_card)

        self.prof_name = QLineEdit(self.student_profile.get("name", "Алексей Смирнов"))
        self.prof_email = QLineEdit(self.student_profile.get("email", "student@university.ru"))
        self.prof_uni = QLineEdit(self.student_profile.get("university", "МГУ им. М. В. Ломоносова"))
        self.prof_faculty = QLineEdit(self.student_profile.get("faculty", "Механико-математический факультет"))
        self.prof_group = QLineEdit(self.student_profile.get("group", "204-Б"))

        layout.addWidget(QLabel("ФИО студента:"))
        layout.addWidget(self.prof_name)
        layout.addWidget(QLabel("Электронная почта:"))
        layout.addWidget(self.prof_email)
        layout.addWidget(QLabel("ВУЗ / Университет:"))
        layout.addWidget(self.prof_uni)
        layout.addWidget(QLabel("Факультет / Институт:"))
        layout.addWidget(self.prof_faculty)
        layout.addWidget(QLabel("Академическая группа:"))
        layout.addWidget(self.prof_group)

        save_btn = QPushButton("💾 Сохранить профиль в SQLite")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(self.save_profile_data)
        layout.addWidget(save_btn)

        layout.addStretch()
        return page

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
        self.header_avatar_btn.setText(
            f"  {self.student_profile['name'].split()[0]} ({self.student_profile['group']})"
        )
        QMessageBox.information(self, "Сохранено", "Профиль студента успешно сохранен в SQLite.")

    # ================= ИМПОРТ PDF / MARKDOWN =================
    def handle_import_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите учебный документ (PDF / Markdown / Текст)", "", "Документы (*.pdf *.md *.txt *.tex)"
        )
        if file_path:
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
            self.revision_repo.add_revision_if_new(
                lec_id, saved["text"], "Импортированная версия документа"
            )
            self.refresh_history_list()
            self.refresh_deadlines_list()
            self.open_lecture_viewer(saved)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("AxAI")
    window = AxAIDesktopApp()
    window.show()
    sys.exit(app.exec())
