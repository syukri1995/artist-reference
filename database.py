import sqlite3
import os
import sys
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent

def get_db_path() -> Path:
    # Use a localized database relative to the project directory or executable
    base_dir = get_base_dir()
    db_path = base_dir / "data" / "artist_reference.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # Create tables based on standard specifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            thumbnail_path TEXT,
            width INTEGER,
            height INTEGER,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS collection_images (
            collection_id INTEGER,
            image_id INTEGER,
            PRIMARY KEY (collection_id, image_id),
            FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS image_tags (
            image_id INTEGER,
            tag_id INTEGER,
            PRIMARY KEY (image_id, tag_id),
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS workspace_state (
            file_path TEXT PRIMARY KEY,
            x REAL NOT NULL,
            y REAL NOT NULL,
            scale REAL NOT NULL,
            z_order INTEGER NOT NULL,
            flip_h BOOLEAN DEFAULT 0,
            flip_v BOOLEAN DEFAULT 0
        )
    """)

    # Graceful migration for existing tables
    try:
        cursor.execute("ALTER TABLE images ADD COLUMN is_favorite BOOLEAN DEFAULT 0")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE workspace_state ADD COLUMN flip_h BOOLEAN DEFAULT 0")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE workspace_state ADD COLUMN flip_v BOOLEAN DEFAULT 0")
    except Exception:
        pass

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
