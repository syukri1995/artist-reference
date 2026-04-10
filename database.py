import sqlite3
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
    
    cursor.execute("PRAGMA journal_mode=WAL")

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

    cursor.execute("PRAGMA table_info(workspace_state)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if columns and "slot_id" not in columns:
        cursor.execute("ALTER TABLE workspace_state RENAME TO workspace_state_old")
        
        cursor.execute("""
            CREATE TABLE workspace_state (
                slot_id INTEGER NOT NULL DEFAULT 1,
                file_path TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                scale REAL NOT NULL,
                z_order INTEGER NOT NULL,
                flip_h BOOLEAN DEFAULT 0,
                flip_v BOOLEAN DEFAULT 0,
                PRIMARY KEY (slot_id, file_path)
            )
        """)
        
        if "flip_h" in columns and "flip_v" in columns:
            cursor.execute("""
                INSERT INTO workspace_state (slot_id, file_path, x, y, scale, z_order, flip_h, flip_v)
                SELECT 1, file_path, x, y, scale, z_order, flip_h, flip_v FROM workspace_state_old
            """)
        else:
            cursor.execute("""
                INSERT INTO workspace_state (slot_id, file_path, x, y, scale, z_order)
                SELECT 1, file_path, x, y, scale, z_order FROM workspace_state_old
            """)
        cursor.execute("DROP TABLE workspace_state_old")
    else:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS workspace_state (
                slot_id INTEGER NOT NULL DEFAULT 1,
                file_path TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                scale REAL NOT NULL,
                z_order INTEGER NOT NULL,
                flip_h BOOLEAN DEFAULT 0,
                flip_v BOOLEAN DEFAULT 0,
                PRIMARY KEY (slot_id, file_path)
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

    # Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_file_path ON images(file_path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_tag_id ON image_tags(tag_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_collections_images_col_id ON collection_images(collection_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_is_favorite ON images(is_favorite)")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
