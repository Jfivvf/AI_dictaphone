"""Закладки к записи лекции: метки времени с короткой заметкой."""
from typing import Any, Dict, List

from .repositories import DatabaseManager


class BookmarkRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db
        with self.db.get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bookmarks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    lecture_id TEXT NOT NULL,
                    time_sec INTEGER NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (lecture_id) REFERENCES lectures(id) ON DELETE CASCADE
                )
                """
            )
            conn.commit()

    def get_for_lecture(self, lecture_id: str) -> List[Dict[str, Any]]:
        with self.db.get_connection() as conn:
            rows = conn.execute(
                "SELECT id, time_sec, note FROM bookmarks WHERE lecture_id = ? ORDER BY time_sec, id",
                (lecture_id,),
            ).fetchall()
        return [{"id": r["id"], "time_sec": r["time_sec"], "note": r["note"]} for r in rows]

    def replace_for_lecture(self, lecture_id: str, items: List[Dict[str, Any]]) -> None:
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM bookmarks WHERE lecture_id = ?", (lecture_id,))
            conn.executemany(
                "INSERT INTO bookmarks (lecture_id, time_sec, note) VALUES (?, ?, ?)",
                [(lecture_id, int(i["time_sec"]), i.get("note", "")) for i in items],
            )
            conn.commit()

    def delete(self, bookmark_id: int) -> None:
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM bookmarks WHERE id = ?", (bookmark_id,))
            conn.commit()
