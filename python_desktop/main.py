"""
AxAI — Нативное десктопное приложение для студентов на Python + PySide6 (Qt6)
Поддерживает:
- Запись лекций с микрофона (sounddevice + QThread) и распознавание речи (Faster-Whisper + Gemini API)
- Умный импорт PDF / Markdown документов с автоматической версткой подробного конспекта
- Кнопку «✨ Сделать подробнее (ИИ)» для расширения конспектов в 3-4 раза
- Полноценный экспорт в .PDF (QPrinter), .MD (UTF-8 BOM) и .TEX (с полной конвертацией Markdown -> LaTeX)
- Трекер дедлайнов с интерактивной сменой приоритета (Высокий / Обычный / Низкий) и автосортировкой
- Профиль студента с установкой собственной картинки/логотипа AxAI

Запуск:
    python main.py
"""
import sys
import os
import re
import json
import sqlite3
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTextEdit, QProgressBar,
    QFileDialog, QListWidget, QListWidgetItem, QFrame, QCheckBox,
    QLineEdit, QComboBox, QMessageBox, QScrollArea, QDialog
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QFont, QIcon, QColor, QPixmap, QPainter, QPen, QTextDocument
from PySide6.QtPrintSupport import QPrinter

from pdf_importer import parse_pdf_document, repair_corrupted_latex
from audio_worker import MicrophoneRecorder, TranscriptionWorker, ExpandLectureWorker


DARK_STYLE = """
QMainWindow, QDialog { background-color: #0a0a0a; }
QWidget { color: #e5e5e5; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
QFrame#headerBar { background-color: #171717; border-bottom: 1px solid #262626; }
QFrame#sidebar { background-color: #171717; border-right: 1px solid #262626; }
QFrame#card { background-color: #171717; border: 1px solid #262626; border-radius: 12px; }
QPushButton { background-color: #1f1f23; border: 1px solid #2e2e34; border-radius: 8px; padding: 7px 13px; font-size: 12px; font-weight: 500; color: #e5e5e5; }
QPushButton:hover { background-color: #2a2a30; border-color: #3f3f46; }
QPushButton#primaryBtn { background-color: #4f46e5; border: none; color: #ffffff; font-weight: 600; }
QPushButton#primaryBtn:hover { background-color: #4338ca; }
QPushButton#expandAiBtn { background-color: #1e1b4b; border: 1px solid #4338ca; color: #a5b4fc; font-weight: 600; }
QPushButton#expandAiBtn:hover { background-color: #312e81; }
QPushButton#recordBtn { background-color: #e11d48; border: none; color: #ffffff; font-weight: 600; padding: 12px 24px; font-size: 13px; border-radius: 10px; }
QPushButton#recordBtn:hover { background-color: #be123c; }
QLineEdit, QComboBox, QTextEdit { background-color: #121214; border: 1px solid #27272a; border-radius: 8px; padding: 8px 12px; font-size: 13px; color: #f4f4f5; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid #6366f1; }
QListWidget { background-color: #141417; border: 1px solid #262626; border-radius: 10px; padding: 6px; }
QListWidget::item { padding: 12px; border-radius: 8px; margin: 3px 0px; }
QListWidget::item:hover { background-color: #1f1f24; }
QListWidget::item:selected { background-color: #27272a; border-left: 3px solid #6366f1; }
QProgressBar { border: 1px solid #27272a; border-radius: 6px; text-align: center; height: 16px; background-color: #18191d; }
QProgressBar::chunk { background-color: #4f46e5; border-radius: 5px; }
"""


def draw_default_axolotl_pixmap(size: int = 64) -> QPixmap:
    """Рисует фирменного розового аксолотля AxAI в круглых очках с ручкой."""
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


def markdown_to_latex_body(raw_markdown: str) -> str:
    """Полный конвертер текста конспекта из Markdown в компилируемый LaTeX (.tex)."""
    clean_md = repair_corrupted_latex(raw_markdown)
    lines = clean_md.split("\n")
    out = []
    in_ul = False
    in_ol = False
    in_block_math = False
    math_buf = []

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("\\end{itemize}")
            in_ul = False
        if in_ol:
            out.append("\\end{enumerate}")
            in_ol = False

    def format_inline(text: str) -> str:
        parts = re.split(r"(\$[^$]+\$)", text)
        res = []
        for part in parts:
            if part.startswith("$") and part.endswith("$") and len(part) > 2:
                res.append(part)
            else:
                s = part.replace("%", "\\%").replace("&", "\\&").replace("#", "\\#").replace("_", "\\_")
                s = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", s)
                s = re.sub(r"\*([^*]+)\*", r"\\textit{\1}", s)
                s = re.sub(r"`([^`]+)`", r"\\texttt{\1}", s)
                res.append(s)
        return "".join(res)

    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith("$$") and trimmed.endswith("$$") and len(trimmed) > 4:
            close_lists()
            out.append("\\begin{equation*}")
            out.append(trimmed[2:-2].strip())
            out.append("\\end{equation*}")
            continue

        if trimmed == "$$":
            close_lists()
            if not in_block_math:
                in_block_math = True
                math_buf = []
            else:
                in_block_math = False
                out.append("\\begin{equation*}")
                out.extend(math_buf)
                out.append("\\end{equation*}")
            continue

        if in_block_math:
            math_buf.append(line)
            continue

        if trimmed.startswith("### "):
            close_lists()
            out.append(f"\\subsubsection*{{{format_inline(trimmed[4:])}}}")
            continue
        if trimmed.startswith("## "):
            close_lists()
            out.append(f"\\subsection*{{{format_inline(trimmed[3:])}}}")
            continue
        if trimmed.startswith("# "):
            close_lists()
            out.append(f"\\section*{{{format_inline(trimmed[2:])}}}")
            continue

        if trimmed.startswith("- ") or trimmed.startswith("* "):
            if in_ol:
                out.append("\\end{enumerate}")
                in_ol = False
            if not in_ul:
                out.append("\\begin{itemize}")
                in_ul = True
            out.append(f"  \\item {format_inline(trimmed[2:])}")
            continue

        m = re.match(r"^(\d+)\.\s+(.*)", trimmed)
        if m:
            if in_ul:
                out.append("\\end{itemize}")
                in_ul = False
            if not in_ol:
                out.append("\\begin{enumerate}")
                in_ol = True
            out.append(f"  \\item {format_inline(m.group(2))}")
            continue

        if not trimmed:
            close_lists()
            out.append("")
            continue

        close_lists()
        out.append(format_inline(line))

    close_lists()
    return "\n".join(out)


class AxAIDesktopApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AxAI")
        self.resize(1220, 780)
        self.setStyleSheet(DARK_STYLE)

        # Локальное хранилище лекций (SQLite БД + JSON), профиля и кастомной картинки логотипа
        self.storage_path = os.path.expanduser("~/AxAI_Storage")
        os.makedirs(self.storage_path, exist_ok=True)
        self.db_path = os.path.join(self.storage_path, "axai_database.db")
        self.lectures_file = os.path.join(self.storage_path, "lectures.json")
        self.profile_file = os.path.join(self.storage_path, "profile.json")
        self.custom_logo_path = os.path.join(self.storage_path, "custom_logo.png")

        self.init_sqlite_db()
        self.lectures = self.load_lectures()
        self.student_profile = self.load_profile()
        self.current_lecture = None

        self.setWindowIcon(QIcon(self.get_logo_pixmap(64)))

        # Аудио рекордер
        self.recorder = MicrophoneRecorder()
        self.is_recording = False
        self.record_seconds = 0
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.update_record_timer)

        self.init_ui()

    def get_logo_pixmap(self, size: int = 36) -> QPixmap:
        if os.path.exists(self.custom_logo_path):
            pm = QPixmap(self.custom_logo_path)
            if not pm.isNull():
                return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        return draw_default_axolotl_pixmap(size)

    def choose_custom_logo(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите свою картинку логотипа / аватарку (например 5341532723484501807.jpg)",
            "",
            "Изображения (*.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if path:
            pm = QPixmap(path)
            if not pm.isNull():
                pm.save(self.custom_logo_path, "PNG")
                self.refresh_all_logos()

    def refresh_all_logos(self):
        self.setWindowIcon(QIcon(self.get_logo_pixmap(64)))
        if hasattr(self, "header_logo_btn"):
            self.header_logo_btn.setIcon(QIcon(self.get_logo_pixmap(32)))
        if hasattr(self, "header_avatar_btn"):
            self.header_avatar_btn.setIcon(QIcon(self.get_logo_pixmap(24)))
        if hasattr(self, "profile_avatar_lbl"):
            self.profile_avatar_lbl.setPixmap(self.get_logo_pixmap(64))

    def init_ui(self):
        root_widget = QWidget()
        root_vbox = QVBoxLayout(root_widget)
        root_vbox.setContentsMargins(0, 0, 0, 0)
        root_vbox.setSpacing(0)

        # Верхняя панель AxAI (без трех точек светофора и без подписи "Учебный диктофон")
        header = QFrame()
        header.setObjectName("headerBar")
        header.setFixedHeight(56)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 0, 16, 0)
        header_layout.setSpacing(10)

        self.header_logo_btn = QPushButton()
        self.header_logo_btn.setIcon(QIcon(self.get_logo_pixmap(32)))
        self.header_logo_btn.setIconSize(QSize(32, 32))
        self.header_logo_btn.setFixedSize(36, 36)
        self.header_logo_btn.setStyleSheet("border: none; background: transparent;")
        self.header_logo_btn.setToolTip("Нажмите, чтобы загрузить свою картинку логотипа / аватарку")
        self.header_logo_btn.clicked.connect(self.choose_custom_logo)
        header_layout.addWidget(self.header_logo_btn)

        brand_label = QLabel("AxAI")
        brand_label.setFont(QFont("Arial", 14, QFont.Bold))
        brand_label.setStyleSheet("color: #ffffff;")
        header_layout.addWidget(brand_label)

        header_layout.addStretch()

        self.header_avatar_btn = QPushButton(
            f"  {self.student_profile.get('name', 'Студент').split()[0]} ({self.student_profile.get('group', '204-Б')})"
        )
        self.header_avatar_btn.setIcon(QIcon(self.get_logo_pixmap(24)))
        self.header_avatar_btn.setIconSize(QSize(24, 24))
        self.header_avatar_btn.clicked.connect(lambda: self.navigate_to("profile"))
        header_layout.addWidget(self.header_avatar_btn)

        root_vbox.addWidget(header)

        # Основная рабочая область (Sidebar + QStackedWidget)
        body_widget = QWidget()
        main_layout = QHBoxLayout(body_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(6)

        self.nav_buttons = {}
        nav_items = [
            ("record", "🎙️  Запись лекции"),
            ("history", "📚  Мои лекции"),
            ("deadlines", "📅  Дедлайны и задачи"),
            ("storage", "💾  Память и файлы"),
            ("settings", "⚙️  Настройки"),
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
            "deadlines": 3, "storage": 4, "settings": 5, "profile": 6
        }
        if page_name == "deadlines":
            self.refresh_deadlines_list()
        elif page_name == "history":
            self.refresh_history_list()
        self.pages.setCurrentIndex(mapping.get(page_name, 0))
        for k, btn in self.nav_buttons.items():
            if k == page_name:
                btn.setStyleSheet("text-align: left; padding: 10px 12px; background-color: #4f46e5; color: white; font-weight: 600;")
            else:
                btn.setStyleSheet("text-align: left; padding: 10px 12px; background-color: #18191d; color: #e4e4e7;")

    # ================= 1. ЭКРАН ЗАПИСИ =================
    def create_record_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Запись лекции")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        self.input_subject = QLineEdit()
        self.input_subject.setPlaceholderText("Предмет (например: Математический анализ)")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Тема занятия (например: Ряды Фурье и интегралы)")
        self.input_lecturer = QLineEdit()
        self.input_lecturer.setPlaceholderText("Преподаватель (ФИО)")

        layout.addWidget(self.input_subject)
        layout.addWidget(self.input_title)
        layout.addWidget(self.input_lecturer)

        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont("Arial", 38, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #6366f1; padding: 24px;")
        layout.addWidget(self.timer_label)

        btn_box = QHBoxLayout()
        self.btn_record = QPushButton("🔴 Начать запись с микрофона")
        self.btn_record.setObjectName("recordBtn")
        self.btn_record.clicked.connect(self.toggle_recording)

        self.btn_upload_audio = QPushButton("📁 Загрузить аудиофайл (WAV/MP3)")
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
        self.status_label.setStyleSheet("color: #a1a1aa; font-size: 12px;")
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
        path, _ = QFileDialog.getOpenFileName(self, "Выберите аудио лекции", "", "Аудио (*.wav *.mp3 *.m4a *.ogg)")
        if path:
            self.start_transcription(path)

    def start_transcription(self, audio_path: str):
        self.record_progress.setVisible(True)
        self.status_label.setText("Обработка аудиозаписи и верстка подробного конспекта...")
        subject = self.input_subject.text().strip() or "Учебная дисциплина"
        title = self.input_title.text().strip() or "Запись лекции"

        self.worker = TranscriptionWorker(audio_path, title=title, subject=subject)
        self.worker.progress.connect(self.on_transcription_progress)
        self.worker.finished.connect(lambda res: self.on_transcription_finished(res, audio_path))
        self.worker.error.connect(self.on_transcription_error)
        self.worker.start()

    def on_transcription_progress(self, val: int, text: str):
        self.record_progress.setValue(val)
        self.status_label.setText(text)

    def on_transcription_finished(self, result: dict, audio_path: str):
        self.record_progress.setVisible(False)
        self.status_label.setText("Конспект готов!")

        subject = self.input_subject.text().strip() or "Высшая математика"
        title = self.input_title.text().strip() or "Запись лекции"
        lecturer = self.input_lecturer.text().strip() or "Преподаватель"

        new_lecture = {
            "id": f"lec-{int(datetime.now().timestamp())}",
            "title": title,
            "subject": subject,
            "lecturer": lecturer,
            "date": datetime.now().strftime("%d.%m.%Y"),
            "duration_min": max(1, self.record_seconds // 60),
            "text": result.get("text", ""),
            "raw_transcript": result.get("raw_transcript", ""),
            "tasks": result.get("tasks", []),
            "formulas": result.get("formulas", []),
            "audio_file": audio_path
        }
        self.lectures.insert(0, new_lecture)
        self.save_lectures()
        self.refresh_history_list()
        self.open_lecture_viewer(new_lecture)

    def on_transcription_error(self, err_msg: str):
        self.record_progress.setVisible(False)
        self.status_label.setText("Ошибка обработки")
        QMessageBox.warning(self, "Ошибка", f"Не удалось обработать аудио: {err_msg}")

    # ================= 2. ЭКРАН МОИХ ЛЕКЦИЙ =================
    def create_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Мои лекции")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header.addWidget(title)
        header.addStretch()

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
        self.history_list.clear()
        for lec in self.lectures:
            tasks_count = len(lec.get("tasks", []))
            item_text = (
                f"📖 {lec.get('title', 'Лекция')}  ·  {lec.get('subject', '')}\n"
                f"📅 {lec.get('date', '')}  ·  {lec.get('lecturer', '')}  ·  Задач: {tasks_count}"
            )
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, lec)
            self.history_list.addItem(item)

    def on_lecture_clicked(self, item: QListWidgetItem):
        lec = item.data(Qt.UserRole)
        if lec:
            self.open_lecture_viewer(lec)

    # ================= 3. ПРОСМОТР КОНСПЕКТА + ЭКСПОРТ PDF / MD / TEX =================
    def create_viewer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(12)

        top_bar = QHBoxLayout()
        back_btn = QPushButton("← Назад к лекциям")
        back_btn.clicked.connect(lambda: self.navigate_to("history"))
        top_bar.addWidget(back_btn)

        top_bar.addStretch()

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

        save_edits_btn = QPushButton("💾 Сохранить правки")
        save_edits_btn.setObjectName("primaryBtn")
        save_edits_btn.clicked.connect(self.save_current_lecture_text)
        top_bar.addWidget(save_edits_btn)

        layout.addLayout(top_bar)

        self.viewer_title = QLabel("Название лекции")
        self.viewer_title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(self.viewer_title)

        self.viewer_meta = QLabel("Предмет · Преподаватель · Дата")
        self.viewer_meta.setStyleSheet("color: #a1a1aa; font-size: 12px;")
        layout.addWidget(self.viewer_meta)

        self.text_editor = QTextEdit()
        layout.addWidget(self.text_editor)

        return page

    def open_lecture_viewer(self, lec: dict):
        self.current_lecture = lec
        self.viewer_title.setText(lec.get("title", "Без названия"))
        self.viewer_meta.setText(
            f"{lec.get('subject', '')}  ·  {lec.get('lecturer', '')}  ·  {lec.get('date', '')}"
        )
        clean_text = repair_corrupted_latex(lec.get("text", ""))
        self.text_editor.setPlainText(clean_text)
        self.navigate_to("viewer")

    def save_current_lecture_text(self):
        if not self.current_lecture:
            return
        self.current_lecture["text"] = self.text_editor.toPlainText()
        self.save_lectures()
        QMessageBox.information(self, "Сохранено", "Изменения в конспекте сохранены.")

    def handle_expand_lecture_ai(self):
        if not self.current_lecture:
            return
        self.expand_ai_btn.setEnabled(False)
        self.expand_ai_btn.setText("⏳ Генерация подробного конспекта...")

        self.expand_worker = ExpandLectureWorker(
            title=self.current_lecture.get("title", "Лекция"),
            subject=self.current_lecture.get("subject", "Дисциплина"),
            current_markdown=self.text_editor.toPlainText(),
            raw_transcript=self.current_lecture.get("raw_transcript", ""),
        )
        self.expand_worker.finished.connect(self.on_expand_finished)
        self.expand_worker.error.connect(self.on_expand_error)
        self.expand_worker.start()

    def on_expand_finished(self, expanded_markdown: str):
        self.expand_ai_btn.setEnabled(True)
        self.expand_ai_btn.setText("✨ Сделать подробнее (ИИ)")
        if self.current_lecture and expanded_markdown:
            clean = repair_corrupted_latex(expanded_markdown)
            self.current_lecture["text"] = clean
            self.text_editor.setPlainText(clean)
            self.save_lectures()

    def on_expand_error(self, err: str):
        self.expand_ai_btn.setEnabled(True)
        self.expand_ai_btn.setText("✨ Сделать подробнее (ИИ)")
        QMessageBox.warning(self, "Ошибка ИИ", f"Не удалось расширить конспект: {err}")

    def export_current_markdown(self):
        if not self.current_lecture:
            return
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить Markdown (.md)", f"{safe_name}_конспект.md", "Markdown (*.md)"
        )
        if save_path:
            body = repair_corrupted_latex(self.text_editor.toPlainText())
            md = f"# {self.current_lecture.get('title', '')}\n\n"
            md += f"- **Предмет:** {self.current_lecture.get('subject', '')}\n"
            md += f"- **Преподаватель:** {self.current_lecture.get('lecturer', '')}\n"
            md += f"- **Дата:** {self.current_lecture.get('date', '')}\n\n---\n\n"
            md += f"{body}\n\n"

            tasks = self.current_lecture.get("tasks", [])
            if tasks:
                md += "---\n\n## Задачи и дедлайны\n\n"
                for t in tasks:
                    mark = "x" if t.get("completed") else " "
                    md += f"- [{mark}] **{t.get('task', '')}** *(Срок: {t.get('deadline', '')})*\n"

            # Записываем с UTF-8 BOM (\ufeff), чтобы редакторы на Windows корректно читали кириллицу и формулы
            with open(save_path, "w", encoding="utf-8-sig") as f:
                f.write(md)
            QMessageBox.information(self, "Экспорт .MD", f"Файл успешно сохранен:\n{save_path}")

    def export_current_latex(self):
        if not self.current_lecture:
            return
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить LaTeX (.tex)", f"{safe_name}_конспект.tex", "LaTeX (*.tex)"
        )
        if save_path:
            body_tex = markdown_to_latex_body(self.text_editor.toPlainText())
            tex = (
                "\\documentclass[12pt,a4paper]{article}\n"
                "\\usepackage[utf8]{inputenc}\n"
                "\\usepackage[T2A]{fontenc}\n"
                "\\usepackage[russian]{babel}\n"
                "\\usepackage{amsmath,amssymb,amsfonts}\n"
                "\\usepackage[margin=2cm]{geometry}\n"
                "\\usepackage{hyperref}\n\n"
                f"\\title{{{self.current_lecture.get('title', '')}}}\n"
                f"\\author{{{self.current_lecture.get('lecturer', '')} \\\\ \\small {self.current_lecture.get('subject', '')}}}\n"
                f"\\date{{{self.current_lecture.get('date', '')}}}\n\n"
                "\\begin{document}\n"
                "\\maketitle\n\n"
                f"{body_tex}\n\n"
            )
            tasks = self.current_lecture.get("tasks", [])
            if tasks:
                tex += "\\section*{Задачи и дедлайны}\n\\begin{itemize}\n"
                for t in tasks:
                    tex += f"  \\item \\textbf{{{t.get('task', '')}}} --- \\textit{{Срок: {t.get('deadline', '')}}}\n"
                tex += "\\end{itemize}\n\n"
            tex += "\\end{document}\n"

            with open(save_path, "w", encoding="utf-8-sig") as f:
                f.write(tex)
            QMessageBox.information(self, "Экспорт .TEX", f"Документ LaTeX успешно сохранен:\n{save_path}")

    def export_current_pdf(self):
        if not self.current_lecture:
            return
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', "_", self.current_lecture.get("title", "Лекция"))
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Сохранить PDF (.pdf)", f"{safe_name}_конспект.pdf", "PDF Document (*.pdf)"
        )
        if not save_path:
            return

        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(save_path)

        doc = QTextDocument()
        md_content = (
            f"# {self.current_lecture.get('title', '')}\n\n"
            f"**Предмет:** {self.current_lecture.get('subject', '')} | "
            f"**Преподаватель:** {self.current_lecture.get('lecturer', '')} | "
            f"**Дата:** {self.current_lecture.get('date', '')}\n\n---\n\n"
            f"{repair_corrupted_latex(self.text_editor.toPlainText())}"
        )
        doc.setMarkdown(md_content)
        doc.print_(printer)
        QMessageBox.information(self, "Экспорт PDF", f"PDF-документ успешно сохранен:\n{save_path}")

    # ================= 4. ДЕДЛАЙНЫ И ЗАДАЧИ (СО СМЕНОЙ ПРИОРИТЕТА) =================
    def create_deadlines_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Задачи и дедлайны (отсортированы по приоритету)")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header.addWidget(title)
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

        priority_weights = {"high": 3, "medium": 2, "low": 1}
        all_items = []
        for lec in self.lectures:
            for t in lec.get("tasks", []):
                all_items.append((lec, t))

        all_items.sort(
            key=lambda pair: (
                pair[1].get("completed", False),
                -priority_weights.get(pair[1].get("priority", "medium"), 2)
            )
        )

        if not all_items:
            empty_lbl = QLabel("Нет активных дедлайнов. Запишите лекцию, импортируйте PDF или добавьте задачу вручную.")
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

            # Выпадающий список изменения приоритета прямо в карточке задачи
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
        self.save_lectures()
        self.refresh_deadlines_list()

    def on_change_task_priority(self, task_ref: dict, new_priority: str):
        task_ref["priority"] = new_priority
        self.save_lectures()
        self.refresh_deadlines_list()

    def open_add_task_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Добавить задачу или дедлайн")
        dlg.setFixedWidth(420)
        vbox = QVBoxLayout(dlg)
        vbox.setContentsMargins(20, 20, 20, 20)
        vbox.setSpacing(10)

        inp_task = QLineEdit()
        inp_task.setPlaceholderText("Что нужно сделать (например: Сдать типовой расчет №2)")
        inp_deadline = QLineEdit()
        inp_deadline.setPlaceholderText("Срок (например: Пятница, 18:00)")

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
            if not self.lectures:
                self.lectures.append({
                    "id": f"lec-{int(datetime.now().timestamp())}",
                    "title": "Общие учебные задачи",
                    "subject": "Общее",
                    "lecturer": "Самостоятельная работа",
                    "date": datetime.now().strftime("%d.%m.%Y"),
                    "duration_min": 30,
                    "text": "## Общие задачи семестра",
                    "tasks": [],
                })
            self.lectures[0].setdefault("tasks", []).insert(0, {
                "id": f"custom-{int(datetime.now().timestamp())}",
                "task": txt,
                "deadline": inp_deadline.text().strip() or "В ближайшее время",
                "completed": False,
                "priority": prio_cb.currentData(),
            })
            self.save_lectures()
            self.refresh_deadlines_list()
            dlg.accept()

        save_b.clicked.connect(save_new)
        btns.addStretch()
        btns.addWidget(cancel_b)
        btns.addWidget(save_b)
        vbox.addLayout(btns)
        dlg.exec()

    # ================= 5. ХРАНИЛИЩЕ И ПАМЯТЬ =================
    def create_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(16)

        title = QLabel("Память и файлы")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        info = QLabel(f"Директория хранения AxAI: {self.storage_path}\nВсего лекций в базе: {len(self.lectures)}")
        info.setStyleSheet("color: #a1a1aa; font-size: 13px;")
        layout.addWidget(info)

        clear_btn = QPushButton("🗑️ Очистить тяжелые WAV-аудиозаписи (сохранив текстовые конспекты)")
        clear_btn.clicked.connect(self.clear_audio_files)
        layout.addWidget(clear_btn)

        layout.addStretch()
        return page

    def clear_audio_files(self):
        reply = QMessageBox.question(
            self, "Подтверждение", "Удалить исходные WAV-файлы с диска? Все конспекты и задачи останутся."
        )
        if reply == QMessageBox.Yes:
            count = 0
            for f in os.listdir(self.storage_path):
                if f.endswith(".wav"):
                    os.remove(os.path.join(self.storage_path, f))
                    count += 1
            QMessageBox.information(self, "Очищено", f"Удалено аудиофайлов: {count}")

    # ================= 6. НАСТРОЙКИ =================
    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Настройки")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        lbl_mode = QLabel("Режим распознавания речи:")
        mode_cb = QComboBox()
        mode_cb.addItems([
            "Гибридный ИИ: Gemini + Faster-Whisper Large-v3-Turbo",
            "Автономный офлайн-режим (CPU Faster-Whisper Base/Small)"
        ])
        layout.addWidget(lbl_mode)
        layout.addWidget(mode_cb)

        noise_check = QCheckBox("Фильтрация шума аудитории (Silero VAD)")
        noise_check.setChecked(True)
        layout.addWidget(noise_check)

        tasks_check = QCheckBox("Автоматически извлекать дедлайны и назначать приоритеты")
        tasks_check.setChecked(True)
        layout.addWidget(tasks_check)

        layout.addStretch()
        return page

    # ================= 7. ПРОФИЛЬ СТУДЕНТА (БЕЗ ПЛАШКИ ОБЛАЧНОГО АККАУНТА) =================
    def create_profile_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(14)

        title = QLabel("Профиль студента")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # Карточка студента с аватаркой AxAI
        id_card = QFrame()
        id_card.setObjectName("card")
        card_row = QHBoxLayout(id_card)
        card_row.setContentsMargins(16, 16, 16, 16)
        card_row.setSpacing(16)

        self.profile_avatar_lbl = QLabel()
        self.profile_avatar_lbl.setPixmap(self.get_logo_pixmap(64))
        self.profile_avatar_lbl.setFixedSize(64, 64)
        card_row.addWidget(self.profile_avatar_lbl)

        upload_photo_btn = QPushButton("📷 Загрузить свое фото / логотип")
        upload_photo_btn.clicked.connect(self.choose_custom_logo)
        card_row.addWidget(upload_photo_btn)
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

        save_btn = QPushButton("💾 Сохранить профиль")
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
        }
        try:
            with open(self.profile_file, "w", encoding="utf-8") as f:
                json.dump(self.student_profile, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        self.header_avatar_btn.setText(
            f"  {self.student_profile['name'].split()[0]} ({self.student_profile['group']})"
        )
        QMessageBox.information(self, "Сохранено", "Профиль студента успешно сохранен.")

    # ================= ИМПОРТ PDF / MARKDOWN =================
    def handle_import_document(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите учебный документ (PDF / Markdown / Текст)", "", "Документы (*.pdf *.md *.txt *.tex)"
        )
        if file_path:
            parsed = parse_pdf_document(file_path)
            new_lecture = {
                "id": f"doc-{int(datetime.now().timestamp())}",
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
            self.lectures.insert(0, new_lecture)
            self.save_lectures()
            self.refresh_history_list()
            self.refresh_deadlines_list()
            self.open_lecture_viewer(new_lecture)

    # ================= БАЗА ДАННЫХ SQLITE + JSON =================
    def init_sqlite_db(self):
        """Создает таблицы в локальной реляционной БД SQLite (axai_database.db)."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS student_profile (
                        id INTEGER PRIMARY KEY CHECK (id = 1),
                        name TEXT NOT NULL,
                        email TEXT NOT NULL,
                        university TEXT NOT NULL,
                        faculty TEXT NOT NULL,
                        group_name TEXT NOT NULL
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS lectures (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        lecturer TEXT NOT NULL,
                        date TEXT NOT NULL,
                        duration_min INTEGER DEFAULT 60,
                        summary_markdown TEXT NOT NULL,
                        raw_transcript TEXT DEFAULT ''
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS tasks (
                        id TEXT PRIMARY KEY,
                        lecture_id TEXT NOT NULL,
                        task TEXT NOT NULL,
                        deadline TEXT NOT NULL,
                        priority TEXT DEFAULT 'medium',
                        completed INTEGER DEFAULT 0,
                        FOREIGN KEY (lecture_id) REFERENCES lectures(id) ON DELETE CASCADE
                    )
                """)
                conn.commit()
        except Exception as e:
            print(f"Ошибка инициализации SQLite: {e}")

    def load_lectures(self):
        # 1. Читаем из реляционной БД SQLite
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("SELECT id, title, subject, lecturer, date, duration_min, summary_markdown, raw_transcript FROM lectures ORDER BY rowid DESC")
                rows = cur.fetchall()
                if rows:
                    loaded = []
                    for r in rows:
                        lec_id = r[0]
                        cur.execute("SELECT id, task, deadline, priority, completed FROM tasks WHERE lecture_id = ?", (lec_id,))
                        task_rows = cur.fetchall()
                        tasks = [
                            {
                                "id": tr[0],
                                "task": tr[1],
                                "deadline": tr[2],
                                "priority": tr[3],
                                "completed": bool(tr[4]),
                            }
                            for tr in task_rows
                        ]
                        loaded.append({
                            "id": lec_id,
                            "title": r[1],
                            "subject": r[2],
                            "lecturer": r[3],
                            "date": r[4],
                            "duration_min": r[5],
                            "text": r[6],
                            "raw_transcript": r[7],
                            "tasks": tasks,
                        })
                    return loaded
        except Exception:
            pass

        # 2. Резервное чтение из JSON
        if os.path.exists(self.lectures_file):
            try:
                with open(self.lectures_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return []

    def save_lectures(self):
        # Сохраняем одновременно в реляционную БД SQLite и в JSON
        try:
            with sqlite3.connect(self.db_path) as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM tasks")
                cur.execute("DELETE FROM lectures")
                for lec in self.lectures:
                    lec_id = lec.get("id", f"lec-{int(datetime.now().timestamp())}")
                    cur.execute(
                        "INSERT OR REPLACE INTO lectures (id, title, subject, lecturer, date, duration_min, summary_markdown, raw_transcript) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            lec_id,
                            lec.get("title", "Лекция"),
                            lec.get("subject", "Предмет"),
                            lec.get("lecturer", "Преподаватель"),
                            lec.get("date", ""),
                            int(lec.get("duration_min", 60)),
                            lec.get("text", ""),
                            lec.get("raw_transcript", ""),
                        ),
                    )
                    for idx, t in enumerate(lec.get("tasks", [])):
                        t_id = t.get("id", f"{lec_id}-t-{idx}")
                        cur.execute(
                            "INSERT OR REPLACE INTO tasks (id, lecture_id, task, deadline, priority, completed) VALUES (?, ?, ?, ?, ?, ?)",
                            (
                                t_id,
                                lec_id,
                                t.get("task", ""),
                                t.get("deadline", ""),
                                t.get("priority", "medium"),
                                1 if t.get("completed") else 0,
                            ),
                        )
                conn.commit()
        except Exception as e:
            print(f"Ошибка сохранения в SQLite: {e}")

        try:
            with open(self.lectures_file, "w", encoding="utf-8") as f:
                json.dump(self.lectures, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения лекций в JSON: {e}")

    def load_profile(self):
        if os.path.exists(self.profile_file):
            try:
                with open(self.profile_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "name": "Алексей Смирнов",
            "email": "student@university.ru",
            "university": "МГУ им. М. В. Ломоносова",
            "faculty": "Механико-математический факультет",
            "group": "204-Б",
        }


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("AxAI")
    window = AxAIDesktopApp()
    window.show()
    sys.exit(app.exec())
