import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.expanduser("~"), ".yt_downloader_history.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            url TEXT NOT NULL,
            download_date TEXT NOT NULL,
            save_path TEXT NOT NULL
        )
    """)
    # Migration: add format and quality columns if they do not exist
    try:
        cursor.execute("ALTER TABLE history ADD COLUMN format TEXT DEFAULT 'mp3'")
        cursor.execute("ALTER TABLE history ADD COLUMN quality TEXT DEFAULT '320'")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def add_to_history(title: str, artist: str, url: str, save_path: str, format_type: str = "mp3", quality: str = "320"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute(
        "INSERT INTO history (title, artist, url, download_date, save_path, format, quality) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (title, artist, url, now, save_path, format_type, quality)
    )
    conn.commit()
    conn.close()

def get_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM history ORDER BY download_date DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def clear_history():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM history")
    conn.commit()
    conn.close()
