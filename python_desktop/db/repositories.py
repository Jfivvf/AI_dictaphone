import os
import json
import sqlite3
from datetime import datetime
from typing import List, Dict, Any, Optional


class DatabaseManager:
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        os.makedirs(self.storage_path, exist_ok=True)
        self.db_path = os.path.join(self.storage_path, "axai_database.db")
        self.init_schema()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=15.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def init_schema(self):
        with self.get_connection() as conn:
            cur = conn.cursor()

            # Профиль
            cur.execute("""
                CREATE TABLE IF NOT EXISTS student_profile (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    name TEXT NOT NULL DEFAULT 'Алексей Смирнов',
                    email TEXT NOT NULL DEFAULT 'student@university.ru',
                    university TEXT NOT NULL DEFAULT 'МГУ им. М. В. Ломоносова',
                    faculty TEXT NOT NULL DEFAULT 'Механико-математический факультет',
                    group_name TEXT NOT NULL DEFAULT '204-Б',
                    semester INTEGER NOT NULL DEFAULT 3,
                    avatar_blob BLOB DEFAULT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            existing_cols = {
                row["name"] for row in cur.execute("PRAGMA table_info(student_profile)").fetchall()
            }
            if "semester" not in existing_cols:
                cur.execute("ALTER TABLE student_profile ADD COLUMN semester INTEGER NOT NULL DEFAULT 3")
            if "avatar_blob" not in existing_cols:
                cur.execute("ALTER TABLE student_profile ADD COLUMN avatar_blob BLOB DEFAULT NULL")

            # Список лекций
            cur.execute("""
                CREATE TABLE IF NOT EXISTS lectures (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    lecturer TEXT NOT NULL,
                    date TEXT NOT NULL,
                    duration_min INTEGER DEFAULT 60,
                    summary_markdown TEXT NOT NULL,
                    raw_transcript TEXT DEFAULT '',
                    segments_json TEXT DEFAULT '[]',
                    formulas_json TEXT DEFAULT '[]',
                    audio_file TEXT DEFAULT '',
                    ai_context TEXT DEFAULT '',
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    updated_at INTEGER DEFAULT (strftime('%s', 'now'))
                )
            """)
            lec_cols = {
                row["name"] for row in cur.execute("PRAGMA table_info(lectures)").fetchall()
            }
            for col_name, col_def in [
                ("segments_json", "TEXT DEFAULT '[]'"),
                ("formulas_json", "TEXT DEFAULT '[]'"),
                ("audio_file", "TEXT DEFAULT ''"),
                ("ai_context", "TEXT DEFAULT ''"),
                ("created_at", "INTEGER DEFAULT 0"),
                ("updated_at", "INTEGER DEFAULT 0"),
            ]:
                if col_name not in lec_cols:
                    cur.execute(f"ALTER TABLE lectures ADD COLUMN {col_name} {col_def}")

            # 3. Список задач и дедлайнов
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    lecture_id TEXT,
                    task TEXT NOT NULL,
                    deadline TEXT NOT NULL,
                    priority TEXT DEFAULT 'medium',
                    completed INTEGER DEFAULT 0,
                    FOREIGN KEY (lecture_id) REFERENCES lectures(id) ON DELETE CASCADE
                )
            """)
            # Миграция: раньше lecture_id был обязательным, а задача без лекции хранилась нельзя.
            task_cols = cur.execute("PRAGMA table_info(tasks)").fetchall()
            if any(c["name"] == "lecture_id" and c["notnull"] for c in task_cols):
                cur.execute("ALTER TABLE tasks RENAME TO tasks_old")
                cur.execute("""
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY,
                        lecture_id TEXT,
                        task TEXT NOT NULL,
                        deadline TEXT NOT NULL,
                        priority TEXT DEFAULT 'medium',
                        completed INTEGER DEFAULT 0,
                        FOREIGN KEY (lecture_id) REFERENCES lectures(id) ON DELETE CASCADE
                    )
                """)
                cur.execute(
                    "INSERT INTO tasks (id, lecture_id, task, deadline, priority, completed) "
                    "SELECT id, lecture_id, task, deadline, priority, completed FROM tasks_old"
                )
                cur.execute("DROP TABLE tasks_old")

            # Таблица истории версий конспекта
            cur.execute("""
                CREATE TABLE IF NOT EXISTS lecture_revisions (
                    id TEXT PRIMARY KEY,
                    lecture_id TEXT NOT NULL,
                    label TEXT NOT NULL,
                    summary_markdown TEXT NOT NULL,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    timestamp TEXT NOT NULL,
                    created_at INTEGER DEFAULT (strftime('%s', 'now')),
                    FOREIGN KEY (lecture_id) REFERENCES lectures(id) ON DELETE CASCADE
                )
            """)

            # Настройки приложения
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)

            # поиск FTS5 по лекциям
            try:
                cur.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS lectures_fts USING fts5(
                        lecture_id UNINDEXED,
                        title,
                        subject,
                        summary_markdown,
                        raw_transcript
                    )
                """)
            except sqlite3.OperationalError:
                pass

            conn.commit()


def _count_words(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    return len(cleaned.split())


class RevisionRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_revisions(self, lecture_id: str) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, lecture_id, label, summary_markdown, word_count, timestamp
                FROM lecture_revisions
                WHERE lecture_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (lecture_id,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "lecture_id": r["lecture_id"],
                    "label": r["label"],
                    "summaryMarkdown": r["summary_markdown"],
                    "wordCount": r["word_count"],
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]

    def add_revision_if_new(
        self, lecture_id: str, summary_markdown: str, label: str
    ) -> List[Dict[str, Any]]:
        trimmed = (summary_markdown or "").strip()
        if not trimmed:
            return self.get_revisions(lecture_id)

        existing = self.get_revisions(lecture_id)
        if any(r["summaryMarkdown"].strip() == trimmed for r in existing):
            return existing

        rev_id = f"rev-{int(datetime.now().timestamp() * 1000)}-{len(existing) + 1}"
        ts_str = datetime.now().strftime("%H:%M:%S")
        words = _count_words(trimmed)

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO lecture_revisions (id, lecture_id, label, summary_markdown, word_count, timestamp, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (rev_id, lecture_id, label, trimmed, words, ts_str, int(datetime.now().timestamp())),
            )
            conn.commit()

        return self.get_revisions(lecture_id)


class TaskRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_tasks_for_lecture(self, lecture_id: str) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, lecture_id, task, deadline, priority, completed FROM tasks WHERE lecture_id = ? ORDER BY rowid ASC",
                (lecture_id,),
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "lecture_id": r["lecture_id"],
                    "task": r["task"],
                    "deadline": r["deadline"],
                    "priority": r["priority"],
                    "completed": bool(r["completed"]),
                }
                for r in rows
            ]

    def get_standalone_tasks(self) -> List[Dict[str, Any]]:
        """Задачи, не привязанные ни к одной лекции."""
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, task, deadline, priority, completed FROM tasks WHERE lecture_id IS NULL ORDER BY rowid ASC"
            ).fetchall()
            return [
                {
                    "id": r["id"],
                    "lecture_id": None,
                    "task": r["task"],
                    "deadline": r["deadline"],
                    "priority": r["priority"],
                    "completed": bool(r["completed"]),
                }
                for r in rows
            ]

    def upsert_task(self, lecture_id: Optional[str], task: Dict[str, Any]) -> None:
        task_id = task.get("id") or f"task-{int(datetime.now().timestamp() * 1000)}"
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, lecture_id, task, deadline, priority, completed)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    task = excluded.task,
                    deadline = excluded.deadline,
                    priority = excluded.priority,
                    completed = excluded.completed
                """,
                (
                    task_id,
                    lecture_id,
                    task.get("task", ""),
                    task.get("deadline", "К следующему занятию"),
                    task.get("priority", "medium"),
                    1 if task.get("completed") else 0,
                ),
            )
            conn.commit()

    def toggle_task(self, task_id: str, completed: bool) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET completed = ? WHERE id = ?",
                (1 if completed else 0, task_id),
            )
            conn.commit()

    def update_priority(self, task_id: str, priority: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                "UPDATE tasks SET priority = ? WHERE id = ?",
                (priority, task_id),
            )
            conn.commit()

    def delete_task(self, task_id: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
            conn.commit()


class LectureRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.task_repo = TaskRepository(db)
        self.revision_repo = RevisionRepository(db)

    def get_all_lectures(self) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, title, subject, lecturer, date, duration_min,
                       summary_markdown, raw_transcript, segments_json,
                       formulas_json, audio_file, ai_context
                FROM lectures
                ORDER BY created_at DESC, rowid DESC
                """
            ).fetchall()

            lectures: List[Dict[str, Any]] = []
            for r in rows:
                lec_id = r["id"]
                tasks = self.task_repo.get_tasks_for_lecture(lec_id)
                revisions = self.revision_repo.get_revisions(lec_id)
                try:
                    segments = json.loads(r["segments_json"] or "[]")
                except Exception:
                    segments = []
                try:
                    formulas = json.loads(r["formulas_json"] or "[]")
                except Exception:
                    formulas = []

                lectures.append({
                    "id": lec_id,
                    "title": r["title"],
                    "subject": r["subject"],
                    "lecturer": r["lecturer"],
                    "date": r["date"],
                    "duration_min": r["duration_min"],
                    "text": r["summary_markdown"],
                    "raw_transcript": r["raw_transcript"] or "",
                    "segments": segments,
                    "formulas": formulas,
                    "audio_file": r["audio_file"] or "",
                    "ai_context": r["ai_context"] or "",
                    "tasks": tasks,
                    "revisions": revisions,
                })
            return lectures

    def upsert_lecture(self, lec: Dict[str, Any]) -> Dict[str, Any]:
        now_ts = int(datetime.now().timestamp())
        lec_id = lec.get("id") or f"lec-{now_ts}"
        lec["id"] = lec_id

        segments_json = json.dumps(lec.get("segments", []), ensure_ascii=False)
        formulas_json = json.dumps(lec.get("formulas", []), ensure_ascii=False)

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO lectures (
                    id, title, subject, lecturer, date, duration_min,
                    summary_markdown, raw_transcript, segments_json,
                    formulas_json, audio_file, ai_context, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    title = excluded.title,
                    subject = excluded.subject,
                    lecturer = excluded.lecturer,
                    date = excluded.date,
                    duration_min = excluded.duration_min,
                    summary_markdown = excluded.summary_markdown,
                    raw_transcript = excluded.raw_transcript,
                    segments_json = excluded.segments_json,
                    formulas_json = excluded.formulas_json,
                    audio_file = excluded.audio_file,
                    ai_context = excluded.ai_context,
                    updated_at = excluded.updated_at
                """,
                (
                    lec_id,
                    lec.get("title", "Лекция"),
                    lec.get("subject", "Учебная дисциплина"),
                    lec.get("lecturer", "Преподаватель"),
                    lec.get("date", datetime.now().strftime("%d.%m.%Y")),
                    int(lec.get("duration_min", 60)),
                    lec.get("text", ""),
                    lec.get("raw_transcript", ""),
                    segments_json,
                    formulas_json,
                    lec.get("audio_file", ""),
                    lec.get("ai_context", ""),
                    now_ts,
                    now_ts,
                ),
            )

            incoming_tasks = lec.get("tasks", [])
            incoming_ids = set()
            for idx, t in enumerate(incoming_tasks):
                t_id = t.get("id") or f"{lec_id}-task-{idx}"
                t["id"] = t_id
                incoming_ids.add(t_id)
                cur.execute(
                    """
                    INSERT INTO tasks (id, lecture_id, task, deadline, priority, completed)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        task = excluded.task,
                        deadline = excluded.deadline,
                        priority = excluded.priority,
                        completed = excluded.completed
                    """,
                    (
                        t_id,
                        lec_id,
                        t.get("task", ""),
                        t.get("deadline", "К следующему занятию"),
                        t.get("priority", "medium"),
                        1 if t.get("completed") else 0,
                    ),
                )

            if incoming_ids:
                placeholders = ",".join("?" for _ in incoming_ids)
                cur.execute(
                    f"DELETE FROM tasks WHERE lecture_id = ? AND id NOT IN ({placeholders})",
                    (lec_id, *incoming_ids),
                )
            else:
                cur.execute("DELETE FROM tasks WHERE lecture_id = ?", (lec_id,))

            try:
                cur.execute("DELETE FROM lectures_fts WHERE lecture_id = ?", (lec_id,))
                cur.execute(
                    """
                    INSERT INTO lectures_fts (lecture_id, title, subject, summary_markdown, raw_transcript)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        lec_id,
                        lec.get("title", ""),
                        lec.get("subject", ""),
                        lec.get("text", ""),
                        lec.get("raw_transcript", ""),
                    ),
                )
            except sqlite3.OperationalError:
                pass

            conn.commit()

        lec["revisions"] = self.revision_repo.get_revisions(lec_id)
        return lec

    def delete_lecture(self, lecture_id: str) -> None:
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM lectures WHERE id = ?", (lecture_id,))
            try:
                conn.execute("DELETE FROM lectures_fts WHERE lecture_id = ?", (lecture_id,))
            except sqlite3.OperationalError:
                pass
            conn.commit()

    def search_lectures(self, query: str) -> List[Dict[str, Any]]:
        q = (query or "").strip()
        all_lecs = self.get_all_lectures()
        if not q:
            return all_lecs

        try:
            with self.db.get_connection() as conn:
                safe_fts = '"' + q.replace('"', '""') + '"*'
                rows = conn.execute(
                    "SELECT lecture_id FROM lectures_fts WHERE lectures_fts MATCH ? ORDER BY rank",
                    (safe_fts,),
                ).fetchall()
                if rows:
                    matched_ids = {r["lecture_id"] for r in rows}
                    return [l for l in all_lecs if l["id"] in matched_ids]
        except Exception:
            pass

        q_low = q.lower()
        return [
            l for l in all_lecs
            if q_low in l.get("title", "").lower()
            or q_low in l.get("subject", "").lower()
            or q_low in l.get("lecturer", "").lower()
            or q_low in l.get("text", "").lower()
        ]


class ProfileRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.avatar_cache_path = os.path.join(self.db.storage_path, "user_avatar_256.png")

    def get_profile(self) -> Dict[str, Any]:
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT name, email, university, faculty, group_name, semester, avatar_blob FROM student_profile WHERE id = 1"
            ).fetchone()
            if row:
                if row["avatar_blob"] and not os.path.exists(self.avatar_cache_path):
                    try:
                        with open(self.avatar_cache_path, "wb") as f:
                            f.write(row["avatar_blob"])
                    except Exception:
                        pass
                return {
                    "name": row["name"],
                    "email": row["email"],
                    "university": row["university"],
                    "faculty": row["faculty"],
                    "group": row["group_name"],
                    "semester": int(row["semester"] or 3),
                    "has_custom_avatar": bool(row["avatar_blob"]) or os.path.exists(self.avatar_cache_path),
                }

        default_profile = {
            "name": "Иван Иванов",
            "email": "student@university.ru",
            "university": "НИЯУ МИФИ",
            "faculty": "Институт Лазерных и Плазменных технологий",
            "group": "Б26-205",
            "semester": 1,
            "has_custom_avatar": False,
        }
        self.save_profile(default_profile)
        return default_profile

    def save_profile(self, profile: Dict[str, Any]) -> None:
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO student_profile (id, name, email, university, faculty, group_name, semester, updated_at)
                VALUES (1, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    email = excluded.email,
                    university = excluded.university,
                    faculty = excluded.faculty,
                    group_name = excluded.group_name,
                    semester = excluded.semester,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    profile.get("name", "Студент"),
                    profile.get("email", "student@university.ru"),
                    profile.get("university", "Университет"),
                    profile.get("faculty", "Факультет"),
                    profile.get("group", "204-Б"),
                    int(profile.get("semester", 3)),
                ),
            )
            conn.commit()

    def save_avatar_bytes(self, png_bytes: bytes) -> None:
        with open(self.avatar_cache_path, "wb") as f:
            f.write(png_bytes)
        with self.db.get_connection() as conn:
            self.get_profile()
            conn.execute(
                "UPDATE student_profile SET avatar_blob = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
                (sqlite3.Binary(png_bytes),),
            )
            conn.commit()

    def clear_avatar(self) -> None:
        if os.path.exists(self.avatar_cache_path):
            try:
                os.remove(self.avatar_cache_path)
            except Exception:
                pass
        with self.db.get_connection() as conn:
            conn.execute("UPDATE student_profile SET avatar_blob = NULL WHERE id = 1")
            conn.commit()

    def get_avatar_bytes(self) -> Optional[bytes]:
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT avatar_blob FROM student_profile WHERE id = 1").fetchone()
            if row and row["avatar_blob"]:
                return bytes(row["avatar_blob"])
        if os.path.exists(self.avatar_cache_path):
            try:
                with open(self.avatar_cache_path, "rb") as f:
                    return f.read()
            except Exception:
                pass
        return None


class SettingsRepository:
    DEFAULTS = {
       "theme": "dark",
       "transcriber_backend": "local_whisper",
       "summarizer_backend": "auto",
       "allow_cloud_fallback": False,
       "whisper_model_size": "auto",
       "ollama_model": "qwen2.5:3b",
       "ollama_url": "http://localhost:11434",
       "ollama_num_ctx": 16384,
       "ollama_timeout": 600,
       "silero_vad": True,
       "auto_extract_tasks": True,
       "offline_language": "ru",
       "diarization": True,
   }

    def __init__(self, db: DatabaseManager):
        self.db = db

    def get_settings(self) -> Dict[str, Any]:
        result = dict(self.DEFAULTS)
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
            for r in rows:
                try:
                    result[r["key"]] = json.loads(r["value"])
                except Exception:
                    result[r["key"]] = r["value"]
        return result

    def save_settings(self, settings: Dict[str, Any]) -> None:
        with self.db.get_connection() as conn:
            for k, v in settings.items():
                conn.execute(
                    """
                    INSERT INTO app_settings (key, value)
                    VALUES (?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (k, json.dumps(v, ensure_ascii=False)),
                )
            conn.commit()
