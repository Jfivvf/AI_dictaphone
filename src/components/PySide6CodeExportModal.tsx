import React, { useState } from 'react';
import { 
  X, 
  Copy, 
  Check, 
  FileCode, 
  Terminal, 
  Download
} from 'lucide-react';

interface PySide6CodeExportModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const PySide6CodeExportModal: React.FC<PySide6CodeExportModalProps> = ({
  isOpen,
  onClose,
}) => {
  const [activeFile, setActiveFile] = useState<'main.py' | 'pdf_importer.py' | 'audio_worker.py' | 'requirements.txt'>('main.py');
  const [copied, setCopied] = useState(false);

  if (!isOpen) return null;

  const files = {
    'main.py': `"""
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
    QLineEdit, QComboBox, QMessageBox
)
from PySide6.QtCore import Qt, QTimer, Slot
from PySide6.QtGui import QFont, QIcon, QColor

from pdf_importer import parse_pdf_document
from audio_worker import MicrophoneRecorder, TranscriptionWorker

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

        self.storage_path = os.path.expanduser("~/LecturaAI_Storage")
        os.makedirs(self.storage_path, exist_ok=True)
        self.lectures_file = os.path.join(self.storage_path, "lectures.json")
        self.lectures = self.load_lectures()

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

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(14, 16, 14, 16)
        sidebar_layout.setSpacing(6)

        app_title = QLabel("Lectura AI")
        app_title.setFont(QFont("Arial", 14, QFont.Bold))
        sidebar_layout.addWidget(app_title)

        subtitle = QLabel("Учебный диктофон")
        subtitle.setStyleSheet("color: #71717a; font-size: 11px;")
        sidebar_layout.addWidget(subtitle)
        sidebar_layout.addSpacing(14)

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

        import_pdf_btn = QPushButton("📄 Импорт PDF")
        import_pdf_btn.setObjectName("primaryBtn")
        import_pdf_btn.clicked.connect(self.handle_import_pdf)
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

        self.input_subject = QLineEdit()
        self.input_subject.setPlaceholderText("Предмет (например: Высшая математика)")
        self.input_title = QLineEdit()
        self.input_title.setPlaceholderText("Тема занятия (например: Дифференциальные уравнения)")
        self.input_lecturer = QLineEdit()
        self.input_lecturer.setPlaceholderText("Преподаватель (ФИО)")

        layout.addWidget(self.input_subject)
        layout.addWidget(self.input_title)
        layout.addWidget(self.input_lecturer)

        self.timer_label = QLabel("00:00")
        self.timer_label.setFont(QFont("Arial", 36, QFont.Bold))
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setStyleSheet("color: #6366f1; padding: 30px;")
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
            self.btn_record.setText("⏹️ Завершить и транскрибировать")
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
            item_text = f"📖 {lec['title']}  ·  {lec['subject']}\\n📅 {lec['date']}  ·  {lec.get('duration_min', 60)} мин  ·  {tasks_count} дедлайн(ов)"
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
                f.write(f"# {self.current_lecture['title']}\\n")
                f.write(f"**Предмет:** {self.current_lecture['subject']}\\n\\n")
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

        info = QLabel(f"Директория сохранения: {self.storage_path}\\nВсего лекций в базе: {len(self.lectures)}")
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
        return []

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
`,
    'pdf_importer.py': `"""
Модуль извлечения текста и структуры из PDF файлов для Lectura AI.
Использует библиотеку pypdf для локального чтения без интернета.
"""
import os
import re
from datetime import datetime
from typing import Dict, Any, List

def parse_pdf_document(file_path: str) -> Dict[str, Any]:
    try:
        from pypdf import PdfReader
        reader = PdfReader(file_path)
        full_text = ""
        
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            full_text += f"\\n\\n### Страница {i + 1}\\n" + page_text.strip()
    except Exception as e:
        full_text = f"Не удалось прочитать PDF файл: {str(e)}"

    file_name = os.path.basename(file_path)
    title = os.path.splitext(file_name)[0].replace("_", " ")

    task_keywords = [
        "задание", "домашн", "сдать", "дедлайн", "подготовить", 
        "коллоквиум", "лабораторн", "контрольн", "экзамен", "контест"
    ]
    
    tasks: List[Dict[str, Any]] = []
    lines = full_text.split("\\n")
    for idx, line in enumerate(lines):
        line_clean = line.strip()
        lower = line_clean.lower()
        if any(kw in lower for kw in task_keywords) and 10 < len(line_clean) < 180:
            tasks.append({
                "id": f"task-pdf-{idx}",
                "task": re.sub(r"^[-*•\\d.)\\s]+", "", line_clean),
                "deadline": "По графику учебного курса",
                "completed": False
            })

    if not tasks:
        tasks.append({
            "id": f"task-default-pdf",
            "task": f"Ознакомиться с материалами файла {file_name}",
            "deadline": "К следующему занятию",
            "completed": False
        })

    return {
        "title": title,
        "subject": "Импортированные материалы",
        "lecturer": "Материалы курса (PDF)",
        "date": datetime.now().strftime("%d %B %Y"),
        "duration_min": 60,
        "text": full_text,
        "tasks": tasks[:8]
    }
`,
    'audio_worker.py': `"""
Модуль фоновой аудиозаписи и офлайн транскрибации для PySide6.
"""
import os
import wave
import numpy as np
from PySide6.QtCore import QThread, Signal

class MicrophoneRecorder:
    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self.is_recording = False
        self.frames = []

    def start(self):
        try:
            import sounddevice as sd
            self.is_recording = True
            self.frames = []

            def callback(indata, frames, time, status):
                if self.is_recording:
                    self.frames.append(indata.copy())

            self.stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="int16",
                callback=callback
            )
            self.stream.start()
        except Exception as e:
            print(f"Ошибка захвата звука: {e}")

    def stop(self, output_path: str) -> str:
        self.is_recording = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()

        if not self.frames:
            return ""

        audio_data = np.concatenate(self.frames, axis=0)
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with wave.open(output_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())

        return output_path


class TranscriptionWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, audio_path: str, model_size="large-v3-turbo", device="auto"):
        super().__init__()
        self.audio_path = audio_path
        self.model_size = model_size
        self.device = device

    def run(self):
        try:
            self.progress.emit(20, "Загрузка модели Faster-Whisper...")
            from faster_whisper import WhisperModel

            device = "cuda" if self.device == "cuda" else "cpu"
            model = WhisperModel(
                self.model_size,
                device=device,
                compute_type="int8",
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )

            self.progress.emit(50, "Распознавание речи...")
            segments, info = model.transcribe(self.audio_path, language="ru", beam_size=5)

            transcript_list = []
            full_text = ""
            for seg in segments:
                transcript_list.append({"start": seg.start, "end": seg.end, "text": seg.text})
                full_text += f"{seg.text} "

            self.progress.emit(85, "Поиск дедлайнов и задач...")
            tasks = []
            for line in full_text.split("."):
                lower = line.lower()
                if any(w in lower for w in ["сдать", "домашн", "задание", "дедлайн"]):
                    if len(line.strip()) > 10:
                        tasks.append({"task": line.strip(), "deadline": "К следующей паре", "completed": False})

            self.progress.emit(100, "Готово!")
            self.finished.emit({"text": full_text.strip(), "segments": transcript_list, "tasks": tasks[:5]})

        except Exception as e:
            self.error.emit(str(e))
`,
    'requirements.txt': `PySide6>=6.6.0
faster-whisper>=1.0.3
sounddevice>=0.4.6
soundfile>=0.12.1
numpy>=1.24.0
pypdf>=4.2.0
`
  };

  const handleCopyCode = () => {
    navigator.clipboard.writeText(files[activeFile]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownloadFile = () => {
    const content = files[activeFile];
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = activeFile;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-neutral-900 border border-neutral-800 rounded-2xl w-full max-w-4xl max-h-[88vh] flex flex-col shadow-2xl overflow-hidden">
        
        {/* Modal Header */}
        <div className="p-4 px-6 border-b border-neutral-800 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <FileCode className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-white">
                Исходный код десктопного приложения на Python + PySide6
              </h2>
              <p className="text-[11px] text-neutral-400">
                Все файлы проекта для запуска на вашем локальном компьютере
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* File Tabs & Actions */}
        <div className="px-6 py-2 bg-neutral-950 border-b border-neutral-850 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2 overflow-x-auto">
            {(['main.py', 'pdf_importer.py', 'audio_worker.py', 'requirements.txt'] as const).map((fname) => (
              <button
                key={fname}
                onClick={() => setActiveFile(fname)}
                className={`px-3 py-1.5 rounded-lg text-xs font-mono transition-colors ${
                  activeFile === fname
                    ? 'bg-neutral-850 text-indigo-400 border border-neutral-750 font-semibold'
                    : 'text-neutral-400 hover:text-neutral-200'
                }`}
              >
                {fname}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleDownloadFile}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs font-medium transition-colors"
              title="Скачать текущий файл на диск"
            >
              <Download className="w-3.5 h-3.5 text-indigo-400" />
              Скачать файл
            </button>

            <button
              onClick={handleCopyCode}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5" />
                  Скопировано!
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  Копировать
                </>
              )}
            </button>
          </div>
        </div>

        {/* Code View Area */}
        <div className="flex-1 overflow-y-auto p-6 bg-neutral-950">
          <pre className="font-mono text-xs text-neutral-300 leading-relaxed overflow-x-auto select-text">
            <code>{files[activeFile]}</code>
          </pre>
        </div>

        {/* Footer */}
        <div className="p-4 px-6 bg-neutral-900 border-t border-neutral-800 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs shrink-0">
          <div className="flex items-center gap-2 text-neutral-400 font-mono text-[11px]">
            <Terminal className="w-3.5 h-3.5 text-indigo-400" />
            <span>Запуск: pip install -r requirements.txt && python main.py</span>
          </div>

          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-xs font-medium"
          >
            Закрыть
          </button>
        </div>

      </div>
    </div>
  );
};
