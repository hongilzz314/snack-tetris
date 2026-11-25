import sqlite3
from pathlib import Path
from datetime import datetime

def get_db_path():
    # Persistent per-user DB directory, independent of where the EXE is installed.
    base = Path.home() / ".snack_tetris"
    base.mkdir(parents=True, exist_ok=True)
    return base / "snack_tetris.db"

def init_db():
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS game_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_name TEXT NOT NULL,
                score INTEGER NOT NULL,
                lines INTEGER NOT NULL DEFAULT 0,
                level INTEGER NOT NULL DEFAULT 1,
                played_at TEXT NOT NULL
            )
        """)

def save_record(player_name, score, lines, level):
    with sqlite3.connect(get_db_path()) as conn:
        conn.execute("""
            INSERT INTO game_records (player_name, score, lines, level, played_at)
            VALUES (?, ?, ?, ?, ?)
        """, (player_name, score, lines, level,
              datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

def get_top_records(limit=10):
    with sqlite3.connect(get_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute("""
            SELECT player_name, score, lines, level, played_at
            FROM game_records
            ORDER BY score DESC, played_at DESC
            LIMIT ?
        """, (limit,)).fetchall()
