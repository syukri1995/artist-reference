import sqlite3
import os
import sys
import threading
from pathlib import Path

def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).parent

def get_db_path() -> Path:
    # Use a localized database relative to the project directory or executable
    base_dir = get_base_dir()
    data_dir = os.environ.get("ARTIST_REF_DATA_DIR")
    if data_dir:
        db_path = Path(data_dir) / "artist_reference.db"
    else:
        db_path = base_dir / "data" / "artist_reference.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path

class PersistentConnection(sqlite3.Connection):
    def close(self):
        """No-op to keep the connection alive for thread-local reuse.
        Rolls back any uncommitted transaction to ensure a clean state for the next use."""
        try:
            self.rollback()
        except sqlite3.ProgrammingError:
            # Connection might already be closed in some edge cases
            pass

    def force_close(self) -> None:
        """Actually close the connection (tests and application shutdown)."""
        sqlite3.Connection.close(self)

_local = threading.local()

def _enable_foreign_keys(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys=ON")

def reset_thread_connection() -> None:
    """Close and discard the thread-local connection (used by tests)."""
    if hasattr(_local, "connection"):
        _local.connection.force_close()
        del _local.connection


def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "connection"):
        conn = sqlite3.connect(get_db_path(), factory=PersistentConnection)
        conn.row_factory = sqlite3.Row
        _enable_foreign_keys(conn)
        _local.connection = conn
    return _local.connection

def _migrate_collections_unique(cursor) -> None:
    """Replace global UNIQUE(name) with per-parent uniqueness."""
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_collections_parent_name'"
    )
    if cursor.fetchone():
        return

    cursor.execute("""
        CREATE TABLE collections_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            parent_id INTEGER REFERENCES collections(id) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        INSERT INTO collections_new (id, name, description, parent_id)
        SELECT id, name, description, parent_id FROM collections
    """)
    cursor.execute("DROP TABLE collections")
    cursor.execute("ALTER TABLE collections_new RENAME TO collections")
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_collections_root_name
        ON collections(name) WHERE parent_id IS NULL
    """)
    cursor.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_collections_parent_name
        ON collections(parent_id, name) WHERE parent_id IS NOT NULL
    """)


def _migrate_workspace_opacity(cursor) -> None:
    cursor.execute("PRAGMA table_info(workspace_state)")
    columns = {col[1] for col in cursor.fetchall()}
    if "opacity" not in columns:
        try:
            cursor.execute(
                "ALTER TABLE workspace_state ADD COLUMN opacity REAL NOT NULL DEFAULT 1.0"
            )
        except Exception:
            pass


def _migrate_images_fts(cursor) -> None:
    """Create FTS5 index for filename and tag search."""
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='images_fts'"
    )
    if not cursor.fetchone():
        cursor.execute("""
            CREATE VIRTUAL TABLE images_fts USING fts5(
                image_id UNINDEXED,
                filename,
                tags,
                tokenize='unicode61 remove_diacritics 2'
            )
        """)
    _rebuild_images_fts(cursor)


def rebuild_images_fts(conn=None) -> None:
    """Rebuild the FTS index (call after bulk tag/import changes)."""
    if conn is None:
        conn = get_connection()
    cursor = conn.cursor()
    _rebuild_images_fts(cursor)
    conn.commit()


def _rebuild_images_fts(cursor) -> None:
    cursor.execute("DELETE FROM images_fts")
    cursor.execute("""
        SELECT i.id, i.file_path,
               COALESCE((
                   SELECT group_concat(t.name, ' ')
                   FROM image_tags it
                   JOIN tags t ON t.id = it.tag_id
                   WHERE it.image_id = i.id
               ), '') AS tags
        FROM images i
    """)
    rows = cursor.fetchall()
    for row in rows:
        filename = Path(row["file_path"]).name if row["file_path"] else ""
        cursor.execute(
            "INSERT INTO images_fts (image_id, filename, tags) VALUES (?, ?, ?)",
            (row["id"], filename, row["tags"] or ""),
        )


def _migrate_workspace_image_id(cursor) -> None:
    """Migrate workspace layouts from file_path PK to image_id PK."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='workspace_state'")
    if not cursor.fetchone():
        return

    cursor.execute("PRAGMA table_info(workspace_state)")
    columns = {col[1] for col in cursor.fetchall()}
    if "image_id" in columns:
        cursor.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='workspace_state'"
        )
        row = cursor.fetchone()
        if row and "image_id" in (row[0] or "") and "PRIMARY KEY (slot_id, image_id)" in (row[0] or ""):
            return

    cursor.execute("""
        CREATE TABLE workspace_state_new (
            slot_id INTEGER NOT NULL DEFAULT 1,
            image_id INTEGER NOT NULL,
            file_path TEXT,
            x REAL NOT NULL,
            y REAL NOT NULL,
            scale REAL NOT NULL,
            z_order INTEGER NOT NULL,
            flip_h BOOLEAN DEFAULT 0,
            flip_v BOOLEAN DEFAULT 0,
            PRIMARY KEY (slot_id, image_id),
            FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
        )
    """)
    if "image_id" in columns:
        cursor.execute("""
            INSERT INTO workspace_state_new
              (slot_id, image_id, file_path, x, y, scale, z_order, flip_h, flip_v)
            SELECT slot_id, image_id, file_path, x, y, scale, z_order, flip_h, flip_v
            FROM workspace_state
            WHERE image_id IS NOT NULL
        """)
    else:
        cursor.execute("""
            INSERT INTO workspace_state_new
              (slot_id, image_id, file_path, x, y, scale, z_order, flip_h, flip_v)
            SELECT ws.slot_id, i.id, ws.file_path, ws.x, ws.y, ws.scale, ws.z_order,
                   ws.flip_h, ws.flip_v
            FROM workspace_state ws
            INNER JOIN images i ON i.file_path = ws.file_path
        """)
    cursor.execute("DROP TABLE workspace_state")
    cursor.execute("ALTER TABLE workspace_state_new RENAME TO workspace_state")


def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("PRAGMA journal_mode=WAL")
    _enable_foreign_keys(conn)

    # Create tables based on standard specifications
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            thumbnail_path TEXT,
            width INTEGER,
            height INTEGER,
            date_added DATETIME DEFAULT CURRENT_TIMESTAMP,
            file_hash TEXT
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
        CREATE TABLE IF NOT EXISTS smart_collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            tag_ids TEXT NOT NULL
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
                image_id INTEGER NOT NULL,
                file_path TEXT,
                x REAL NOT NULL,
                y REAL NOT NULL,
                scale REAL NOT NULL,
                z_order INTEGER NOT NULL,
                flip_h BOOLEAN DEFAULT 0,
                flip_v BOOLEAN DEFAULT 0,
                PRIMARY KEY (slot_id, image_id),
                FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE
            )
        """)

    # Graceful migration for existing tables
    try:
        cursor.execute("ALTER TABLE images ADD COLUMN is_favorite BOOLEAN DEFAULT 0")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE images ADD COLUMN last_viewed DATETIME")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE collections ADD COLUMN parent_id INTEGER REFERENCES collections(id) ON DELETE CASCADE")
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE images ADD COLUMN file_hash TEXT")

        # Calculate hashes for existing images
        cursor.execute("SELECT id, file_path FROM images WHERE file_hash IS NULL")
        rows = cursor.fetchall()

        import hashlib
        for row in rows:
            img_id = row['id']
            file_path = Path(row['file_path'])
            if file_path.exists():
                hash_md5 = hashlib.md5()
                with open(file_path, "rb") as f:
                    for chunk in iter(lambda: f.read(4096), b""):
                        hash_md5.update(chunk)
                cursor.execute("UPDATE images SET file_hash = ? WHERE id = ?", (hash_md5.hexdigest(), img_id))
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

    _migrate_collections_unique(cursor)
    _migrate_workspace_image_id(cursor)
    _migrate_workspace_opacity(cursor)
    _migrate_images_fts(cursor)

    # Performance Indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_file_path ON images(file_path)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_image_tags_tag_id ON image_tags(tag_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_collections_images_col_id ON collection_images(collection_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_is_favorite ON images(is_favorite)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_images_file_hash ON images(file_hash)")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
