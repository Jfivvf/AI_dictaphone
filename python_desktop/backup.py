import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from typing import Any, Dict

BACKUP_FORMAT = 1
DB_NAME = "axai_database.db"
AVATAR_NAME = "user_avatar_256.png"
MANIFEST_NAME = "manifest.json"
AUDIO_PREFIX = "audio/"


class BackupError(Exception):
   pass


def _snapshot(src_path: str, dst_path: str) -> None:
    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def _count_lectures(db_path: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute("SELECT COUNT(*) FROM lectures").fetchone()[0]
    finally:
        conn.close()


def create_backup(storage_path: str, db_path: str, dest_zip: str, audio_dir: str = "", include_audio: bool = False) -> Dict[str, Any]:
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = os.path.join(tmp, DB_NAME)
        _snapshot(db_path, snapshot)

        audio_files = []
        if include_audio and audio_dir and os.path.isdir(audio_dir):
            audio_files = [f for f in sorted(os.listdir(audio_dir)) if os.path.isfile(os.path.join(audio_dir, f))]

        manifest = {
            "format": BACKUP_FORMAT,
            "app": "AxAI",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "lectures": _count_lectures(snapshot),
            "audio_files": len(audio_files),
        }
        with zipfile.ZipFile(dest_zip, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, DB_NAME)
            avatar = os.path.join(storage_path, AVATAR_NAME)
            if os.path.exists(avatar):
                z.write(avatar, AVATAR_NAME)
            for name in audio_files:
                z.write(os.path.join(audio_dir, name), AUDIO_PREFIX + name, compress_type=zipfile.ZIP_STORED)
            z.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def read_manifest(zip_path: str) -> Dict[str, Any]:
    try:
        with zipfile.ZipFile(zip_path) as z:
            names = set(z.namelist())
            if MANIFEST_NAME not in names or DB_NAME not in names:
                raise BackupError("Это не резервная копия AxAI: нет manifest.json или базы данных.")
            manifest = json.loads(z.read(MANIFEST_NAME).decode("utf-8"))
    except zipfile.BadZipFile as err:
        raise BackupError("Файл повреждён или не является zip-архивом.") from err
    if int(manifest.get("format", 0)) > BACKUP_FORMAT:
        raise BackupError("Копия создана более новой версией AxAI. Обновите приложение.")
    return manifest


def restore_backup(zip_path: str, storage_path: str, db_path: str, audio_dir: str) -> Dict[str, Any]:
    manifest = read_manifest(zip_path)
    os.makedirs(audio_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(zip_path) as z:
            new_db = os.path.join(tmp, DB_NAME)
            with z.open(DB_NAME) as src, open(new_db, "wb") as dst:
                shutil.copyfileobj(src, dst)

            try:
                conn = sqlite3.connect(new_db)
                try:
                    if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise BackupError("База данных в копии повреждена.")
                    conn.execute("SELECT COUNT(*) FROM lectures").fetchone()
                finally:
                    conn.close()
            except sqlite3.DatabaseError as err:
                raise BackupError(f"База данных в копии не читается: {err}") from err

            if os.path.exists(db_path):
                safety_dir = os.path.join(storage_path, "backups_auto")
                os.makedirs(safety_dir, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                _snapshot(db_path, os.path.join(safety_dir, f"axai_before_restore_{stamp}.db"))

            for suffix in ("-wal", "-shm"):
                if os.path.exists(db_path + suffix):
                    os.remove(db_path + suffix)
            shutil.copy2(new_db, db_path)

            if AVATAR_NAME in z.namelist():
                with z.open(AVATAR_NAME) as src, open(os.path.join(storage_path, AVATAR_NAME), "wb") as dst:
                    shutil.copyfileobj(src, dst)

            for info in z.infolist():
                if info.filename.startswith(AUDIO_PREFIX) and not info.is_dir():
                    name = os.path.basename(info.filename)
                    if name:
                        with z.open(info) as src, open(os.path.join(audio_dir, name), "wb") as dst:
                            shutil.copyfileobj(src, dst)

    conn = sqlite3.connect(db_path)
    try:
        for lec_id, audio in conn.execute("SELECT id, audio_file FROM lectures WHERE audio_file != ''").fetchall():
            local = os.path.join(audio_dir, os.path.basename(audio))
            conn.execute("UPDATE lectures SET audio_file = ? WHERE id = ?", (local if os.path.exists(local) else "", lec_id))
        conn.commit()
    finally:
        conn.close()
    return manifest
