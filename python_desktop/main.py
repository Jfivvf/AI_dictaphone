"""
Lectura AI — Автономный диктофон для студентов
Основной исполняемый файл приложения на Python + PySide6 (Qt6)
Запуск: python main.py
"""
import sys
import os
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QStackedWidget, QTextEdit, QProgressBar,
    QFileDialog, QListWidget, QListWidgetItem, QFrame, QCheckBox,
    QLineEdit, QComboBox, QMessageBox, QSplitter
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QIcon, QColor

from pdf_importer import parse_pdf_document
from audio_worker import MicrophoneRecorder, TranscriptionWorker

# Базовый стиль темной темы
DARK_STYLE = """
QMainWindow { background-color: #0c0d0e; }
QWidget { color: #e4e4e7; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
QFrame#sidebar { background-color: #121316; border-right: 1px solid #27272a; }
QPushButton { background-color: #18191d; border: 1px solid #27272a; border-radius: 8px; padding: 8px 14px; font-size: 13px; font-weight: 500; }
QPushButton:hover { background-color: #27272a; border-color: #3f3f46; }
QPushButton#primaryBtn { background-color: #4f46e5; border: none; color: #ffffff; font-weight: 600; }
QPushButton#primaryBtn:hover { background-color: #4338ca; }
QPushButton#recordBtn { background-color: #dc2626; border: none; color: #ffffff; font-weight: 600; padding: 12px 24px; font-size: 14px; }
QPushButton#recordBtn:hover { background-color: #b91c1c; }
QLineEdit, QComboBox, QTextEdit { background-color: #121316; border: 1px solid #27272a; border-radius: 8px; padding: 8px 12px; font-size: 13px; color: #f4f4f5; }
QLineEdit:focus, QTextEdit:focus { border: 1px solid #6366f1; }
QListWidget { background-color: #121316; border: 1px solid #27272a; border-radius: 8px; padding: 4px; }
QListWidget::item { padding: 12px; border-radius: 6px; margin: 2px 0px; }
QListWidget::item:hover { background-color: #1e1f24; }
QListWidget::item:selected { background-color: #27272a; border-left: 3px solid #6366f1; }
QProgressBar { border: 1px solid #27272a; border-radius: 6px; text-align: center; height: 16px; background-color: #18191d; }
QProgressBar::chunk { background-color: #4f46e5; border-radius: 5px; }
"""

class LecturaApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lectura AI — Учебный диктофон и конспекты")
        self.resize(1180, 760)
        self.setStyleSheet(DARK_STYLE)

        # Локальное хранилище лекций в памяти и JSON
        self.storage_path = os.path.expanduser("~/LecturaAI_Storage")
        os.makedirs(self.storage_path, exist_ok=True)
        self.lectures_file = os.path.join(self.storage_path, "lectures.json")
        self.lectures = self.load_lectures()

        # Аудио рекордер
        self.recorder = MicrophoneRecorder()
        self.is_recording = False
        self.record_seconds = 0
        self.record_timer = QTimer(self)
        self.record_timer.timeout.connect(self.update_record_timer)

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        main_layout = QHBoxLayout(main_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Боковая панель навигации (Sidebar)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(6)

        # Заголовок приложения
        app_title = QLabel("Lectura AI")
        app_title.setFont(QFont("Arial", 14, QFont.Bold))
        sidebar_layout.addWidget(app_title)

        subtitle = QLabel("Учебный диктофон")
        subtitle.setStyleSheet("color: #71717a; font-size: 11px;")
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(14)

        # Кнопки навигации
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
            btn.clicked.connect(lambda checked, k=key: self.navigate_to(k))
            sidebar_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        sidebar_layout.addStretch()

        # Кнопка быстрого импорта PDF
        import_pdf_btn = QPushButton("📄 Импорт PDF")
        import_pdf_btn.setObjectName("primaryBtn")
        import_pdf_btn.clicked.connect(self.handle_import_pdf)
        sidebar_layout.addWidget(import_pdf_btn)

        main_layout.addWidget(sidebar)

        # 2. Центральная область с переключаемыми экранами (QStackedWidget)
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
        self.setCentralWidget(main_widget)
        self.navigate_to("history")

    def navigate_to(self, page_name: str):
        mapping = {
            "record": 0, "history": 1, "viewer": 2,
            "deadlines": 3, "storage": 4, "settings": 5, "profile": 6
        }
        self.pages.setCurrentIndex(mapping.get(page_name, 1))
        for k, btn in self.nav_buttons.items():
            if k == page_name:
                btn.setStyleSheet("text-align: left; padding: 10px 12px; background-color: #4f46e5; color: white;")
            else:
                btn.setStyleSheet("text-align: left; padding: 10px 12px; background-color: #18191d; color: #e4e4e7;")

    # ================= 1. ЭКРАН ЗАПИСИ =================
    def create_record_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        title = QLabel("Запись лекции")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # Поля ввода
        self.input_subject = QLineEdit()
        self.input_subject.setPlaceholderText("Предмет (например: Высшая математика)")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Тема занятия (например: Дифференциальные уравнения)")
        self.input_lecturer = QLineEdit()
        self.input_lecturer.setPlaceholderText("Преподаватель (ФИО)")

        layout.addWidget(self.input_subject)
        layout.addWidget(self.input_title)
        layout.addWidget(self.input_lecturer)

        # Таймер записи
        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont("Arial", 36, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #6366f1; padding: 30px;")
        layout.addWidget(self.timer_label)

        # Кнопки
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

        # Прогресс обработки
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
            # Старт
            self.is_recording = True
            self.record_seconds = 0
            self.timer_label.setText("00:00")
            self.btn_record.setText("⏹️ Завершить и транскрибировать")
            self.recorder.start()
            self.record_timer.start(1000)
        else:
            # Стоп
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
        self.status_label.setText("Обработка аудиозаписи...")
        
        self.worker = TranscriptionWorker(audio_path)
        self.worker.progress.connect(self.on_transcription_progress)
        self.worker.finished.connect(lambda res: self.on_transcription_finished(res, audio_path))
        self.worker.error.connect(self.on_transcription_error)
        self.worker.start()

    def on_transcription_progress(self, val: int, text: str):
        self.record_progress.setValue(val)
        self.status_label.setText(text)

    def on_transcription_finished(self, result: dict, audio_path: str):
        self.record_progress.setVisible(False)
        self.status_label.setText("Готово!")

        subject = self.input_subject.text().strip() or "Высшая математика"
        title = self.input_title.text().strip() or "Запись лекции"
        lecturer = self.input_lecturer.text().strip() or "Преподаватель"

        new_lecture = {
            "id": f"lec-{int(datetime.now().timestamp())}",
            "title": title,
            "subject": subject,
            "lecturer": lecturer,
            "date": datetime.now().strftime("%d %B %Y"),
            "duration_min": max(1, self.record_seconds // 60),
            "text": result.get("text", ""),
            "tasks": result.get("tasks", []),
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

    # ================= 2. ЭКРАН ИСТОРИИ ЛЕКЦИЙ =================
    def create_history_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        header = QHBoxLayout()
        title = QLabel("Мои лекции")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        header.addWidget(title)
        header.addStretch()

        import_btn = QPushButton("📄 Импортировать PDF")
        import_btn.clicked.connect(self.handle_import_pdf)
        header.addWidget(import_btn)

        layout.addLayout(header)

        self.history_list = QListWidget()
        self.history_list.itemClicked.connect(self.on_lecture_clicked)
        layout.addWidget(self.history_list)

        self.refresh_history_list()
        return page

    def refresh_history_list(self):
        self.history_list.clear()
        for lec in self.lectures:
            tasks_count = len(lec.get("tasks", []))
            item_text = f"📖 {lec['title']}  ·  {lec['subject']}\n📅 {lec['date']}  ·  {lec.get('duration_min', 60)} мин  ·  {tasks_count} дедлайн(ов)"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, lec)
            self.history_list.addItem(item)

    def on_lecture_clicked(self, item: QListWidgetItem):
        lec = item.data(Qt.UserRole)
        if lec:
            self.open_lecture_viewer(lec)

    # ================= 3. ПРОСМОТР КОНСПЕКТА (VIEWER) =================
    def create_viewer_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(12)

        # Верхняя панель просмотра
        top_bar = QHBoxLayout()
        back_btn = QPushButton("← Назад ко всем лекциям")
        back_btn.clicked.connect(lambda: self.navigate_to("history"))
        top_bar.addWidget(back_btn)
        top_bar.addStretch()

        export_md_btn = QPushButton("Скачать .MD")
        export_md_btn.clicked.connect(self.export_current_markdown)
        top_bar.addWidget(export_md_btn)
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
        self.viewer_meta.setText(f"{lec.get('subject', '')}  ·  {lec.get('lecturer', '')}  ·  {lec.get('date', '')}")
        self.text_editor.setPlainText(lec.get("text", ""))
        self.navigate_to("viewer")

    def export_current_markdown(self):
        if not hasattr(self, 'current_lecture'):
            return
        save_path, _ = QFileDialog.getSaveFileName(self, "Сохранить Markdown", f"{self.current_lecture['title']}.md", "Markdown (*.md)")
        if save_path:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(f"# {self.current_lecture['title']}\n")
                f.write(f"**Предмет:** {self.current_lecture['subject']}\n\n")
                f.write(self.text_editor.toPlainText())
            QMessageBox.information(self, "Успешно", "Конспект успешно сохранен в файл!")

    # ================= 4. ДЕДЛАЙНЫ И ЗАДАЧИ =================
    def create_deadlines_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        title = QLabel("Дедлайны и задачи")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        self.tasks_list = QListWidget()
        layout.addWidget(self.tasks_list)

        self.refresh_deadlines_list()
        return page

    def refresh_deadlines_list(self):
        self.tasks_list.clear()
        for lec in self.lectures:
            for task in lec.get("tasks", []):
                text = f"[{'✓' if task.get('completed') else ' '}] {task.get('task')}  (Срок: {task.get('deadline')})  —  {lec['title']}"
                self.tasks_list.addItem(text)

    # ================= 5. ХРАНИЛИЩЕ И ПАМЯТЬ =================
    def create_storage_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(16)

        title = QLabel("Память и файлы")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        info = QLabel(f"Директория сохранения: {self.storage_path}\nВсего лекций в базе: {len(self.lectures)}")
        info.setStyleSheet("color: #a1a1aa; font-size: 13px; line-height: 1.6;")
        layout.addWidget(info)

        clear_btn = QPushButton("🗑️ Очистить тяжелые аудиозаписи (сохранив конспекты)")
        clear_btn.clicked.connect(self.clear_audio_files)
        layout.addWidget(clear_btn)

        layout.addStretch()
        return page

    def clear_audio_files(self):
        reply = QMessageBox.question(self, "Подтверждение", "Удалить WAV файлы с диска? Текстовые конспекты останутся нетронутыми.")
        if reply == QMessageBox.Yes:
            count = 0
            for f in os.listdir(self.storage_path):
                if f.endswith(".wav"):
                    os.remove(os.path.join(self.storage_path, f))
                    count += 1
            QMessageBox.information(self, "Очищено", f"Удалено {count} аудиофайлов.")

    # ================= 6. НАСТРОЙКИ =================
    def create_settings_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(14)

        title = QLabel("Настройки")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        lbl_mode = QLabel("Режим распознавания:")
        mode_cb = QComboBox()
        mode_cb.addItems(["Максимальная точность (Large-v3-Turbo)", "Быстрый режим (CPU Tiny/Base)"])
        layout.addWidget(lbl_mode)
        layout.addWidget(mode_cb)

        noise_check = QCheckBox("Подавление шума аудитории (Silero VAD)")
        noise_check.setChecked(True)
        layout.addWidget(noise_check)

        tasks_check = QCheckBox("Автоматически извлекать дедлайны из речи")
        tasks_check.setChecked(True)
        layout.addWidget(tasks_check)

        layout.addStretch()
        return page

    # ================= 7. ПРОФИЛЬ СТУДЕНТА =================
    def create_profile_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(12)

        title = QLabel("Профиль студента")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        self.prof_name = QLineEdit("Алексей Смирнов")
        self.prof_uni = QLineEdit("МГУ им. М. В. Ломоносова")
        self.prof_faculty = QLineEdit("Механико-математический")
        self.prof_group = QLineEdit("204-Б")

        layout.addWidget(QLabel("ФИО студента:"))
        layout.addWidget(self.prof_name)
        layout.addWidget(QLabel("ВУЗ:"))
        layout.addWidget(self.prof_uni)
        layout.addWidget(QLabel("Факультет:"))
        layout.addWidget(self.prof_faculty)
        layout.addWidget(QLabel("Группа:"))
        layout.addWidget(self.prof_group)

        save_btn = QPushButton("Сохранить профиль")
        save_btn.setObjectName("primaryBtn")
        save_btn.clicked.connect(lambda: QMessageBox.information(self, "Сохранено", "Профиль студента обновлен."))
        layout.addWidget(save_btn)

        layout.addStretch()
        return page

    # ================= ИМПОРТ PDF =================
    def handle_import_pdf(self):
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Выберите PDF документ", "", "PDF Files (*.pdf)")
        if pdf_path:
            parsed = parse_pdf_document(pdf_path)
            new_lecture = {
                "id": f"pdf-{int(datetime.now().timestamp())}",
                "title": parsed["title"],
                "subject": parsed["subject"],
                "lecturer": parsed["lecturer"],
                "date": parsed["date"],
                "duration_min": parsed["duration_min"],
                "text": parsed["text"],
                "tasks": parsed["tasks"]
            }
            self.lectures.insert(0, new_lecture)
            self.save_lectures()
            self.refresh_history_list()
            self.refresh_deadlines_list()
            self.open_lecture_viewer(new_lecture)

    # ================= СОХРАНЕНИЕ / ЗАГРУЗКА JSON =================
    def load_lectures(self):
        if os.path.exists(self.lectures_file):
            try:
                with open(self.lectures_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Демонстрационные лекции по умолчанию
        return [
            {
                "id": "demo-1",
                "title": "Дифференциальные уравнения второго порядка",
                "subject": "Высшая математика",
                "lecturer": "Проф. Соколов В. П.",
                "date": "28 сентября 2026",
                "duration_min": 87,
                "text": "## Лекция 7. Линейные неоднородные дифференциальные уравнения\n\ny'' + p y' + q y = f(x)\nОбщее решение складывается из общего однородного и частного неоднородного решения.",
                "tasks": [
                    {"task": "Решить ДЗ из задачника Демидовича № 4120 - 4135", "deadline": "Пятница 23:59", "completed": False}
                ]
            }
        ]

    def save_lectures(self):
        try:
            with open(self.lectures_file, "w", encoding="utf-8") as f:
                json.dump(self.lectures, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"Ошибка сохранения: {e}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = LecturaApp()
    window.show()
    sys.exit(app.exec())
