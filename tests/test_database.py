import unittest
import sqlite3
import os
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_base_dir, get_db_path, get_connection, init_db, reset_thread_connection

class TestDatabase(unittest.TestCase):
    def setUp(self):
        reset_thread_connection()

        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "data" / "artist_reference.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        reset_thread_connection()
        try:
            shutil.rmtree(self.test_dir)
        except PermissionError:
            reset_thread_connection()
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_base_dir_frozen(self):
        with patch('sys.frozen', True, create=True), \
             patch('sys.executable', '/path/to/executable'):
            base_dir = get_base_dir()
            self.assertEqual(base_dir, Path('/path/to'))

    def test_get_base_dir_not_frozen(self):
        with patch('sys.frozen', False, create=True):
            base_dir = get_base_dir()
            # Should be the directory containing database.py
            expected = Path(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.assertEqual(base_dir, expected)

    def test_get_db_path(self):
        with patch('database.get_base_dir') as mock_base:
            mock_base.return_value = Path(self.test_dir)
            db_path = get_db_path()
            self.assertEqual(db_path, self.db_path)
            self.assertTrue(db_path.parent.exists())

    def test_init_db_fresh(self):
        with patch('database.get_db_path') as mock_db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            mock_db_path.return_value = self.db_path
            init_db()

            self.assertTrue(self.db_path.exists())

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Verify tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = [row[0] for row in cursor.fetchall()]
            expected_tables = ['images', 'collections', 'tags', 'collection_images', 'image_tags', 'workspace_state']
            for table in expected_tables:
                self.assertIn(table, tables)

            # Verify some columns in images
            cursor.execute("PRAGMA table_info(images)")
            columns = [row[1] for row in cursor.fetchall()]
            self.assertIn('id', columns)
            self.assertIn('file_path', columns)
            self.assertIn('is_favorite', columns)

            # Verify some columns in workspace_state
            cursor.execute("PRAGMA table_info(workspace_state)")
            columns = [row[1] for row in cursor.fetchall()]
            self.assertIn('slot_id', columns)
            self.assertIn('flip_h', columns)
            self.assertIn('flip_v', columns)

            # Verify indexes
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [row[0] for row in cursor.fetchall()]
            expected_indexes = ['idx_images_file_path', 'idx_image_tags_tag_id', 'idx_collections_images_col_id', 'idx_images_is_favorite']
            for idx in expected_indexes:
                self.assertIn(idx, indexes)

            conn.close()

    def test_workspace_state_migration(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "CREATE TABLE images (id INTEGER PRIMARY KEY, file_path TEXT UNIQUE NOT NULL, "
            "thumbnail_path TEXT, width INTEGER, height INTEGER)"
        )
        cursor.execute(
            "INSERT INTO images (id, file_path, thumbnail_path, width, height) "
            "VALUES (1, 'test.jpg', 'test.webp', 100, 100)"
        )
        cursor.execute("""
            CREATE TABLE workspace_state (
                file_path TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                scale REAL NOT NULL,
                z_order INTEGER NOT NULL,
                PRIMARY KEY (file_path)
            )
        """)
        cursor.execute("""
            INSERT INTO workspace_state (file_path, x, y, scale, z_order)
            VALUES ('test.jpg', 10.0, 20.0, 1.5, 1)
        """)
        conn.commit()
        conn.close()

        import database
        if hasattr(database._local, "connection"):
            del database._local.connection

        with patch('database.get_db_path') as mock_db_path:
            mock_db_path.return_value = self.db_path
            init_db()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT slot_id, image_id, file_path, x, y, scale, z_order, flip_h, flip_v "
            "FROM workspace_state"
        )
        row = cursor.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], 1)
        self.assertEqual(row[2], 'test.jpg')
        self.assertEqual(row[3], 10.0)
        conn.close()

    def test_graceful_migrations(self):
        # Create a database with tables missing some columns
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE images (id INTEGER PRIMARY KEY, file_path TEXT)")
        # workspace_state with slot_id but missing flip_h/flip_v
        cursor.execute("""
            CREATE TABLE workspace_state (
                slot_id INTEGER NOT NULL DEFAULT 1,
                file_path TEXT NOT NULL,
                x REAL NOT NULL,
                y REAL NOT NULL,
                scale REAL NOT NULL,
                z_order INTEGER NOT NULL,
                PRIMARY KEY (slot_id, file_path)
            )
        """)
        conn.commit()
        conn.close()

        with patch('database.get_db_path') as mock_db_path:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            mock_db_path.return_value = self.db_path
            init_db()

        # Verify columns were added
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("PRAGMA table_info(images)")
        columns = [row[1] for row in cursor.fetchall()]
        self.assertIn('is_favorite', columns)

        cursor.execute("PRAGMA table_info(workspace_state)")
        columns = [row[1] for row in cursor.fetchall()]
        self.assertIn('flip_h', columns)
        self.assertIn('flip_v', columns)

        conn.close()

    def test_foreign_key_cascade_on_image_delete(self):
        with patch('database.get_db_path') as mock_db_path:
            mock_db_path.return_value = self.db_path
            init_db()

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("PRAGMA foreign_keys")
            self.assertEqual(cursor.fetchone()[0], 1)

            cursor.execute(
                "INSERT INTO images (file_path, thumbnail_path, width, height) "
                "VALUES (?, ?, ?, ?)",
                ("/test/img.jpg", "/test/thumb.webp", 100, 100),
            )
            image_id = cursor.lastrowid
            cursor.execute("INSERT INTO tags (name) VALUES (?)", ("cascade-tag",))
            tag_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                (image_id, tag_id),
            )
            conn.commit()

            cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
            conn.commit()

            cursor.execute(
                "SELECT COUNT(*) FROM image_tags WHERE image_id = ?", (image_id,)
            )
            self.assertEqual(cursor.fetchone()[0], 0)
            reset_thread_connection()

    def test_workspace_image_id_migration(self):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE images (
                id INTEGER PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                thumbnail_path TEXT,
                width INTEGER,
                height INTEGER
            )
        """)
        cursor.execute(
            "INSERT INTO images (id, file_path, thumbnail_path, width, height) "
            "VALUES (1, '/lib/photo.jpg', '/lib/photo.webp', 100, 100)"
        )
        cursor.execute("""
            CREATE TABLE workspace_state (
                slot_id INTEGER NOT NULL DEFAULT 1,
                file_path TEXT NOT NULL,
                x REAL, y REAL, scale REAL, z_order INTEGER,
                flip_h BOOLEAN DEFAULT 0,
                flip_v BOOLEAN DEFAULT 0,
                PRIMARY KEY (slot_id, file_path)
            )
        """)
        cursor.execute(
            "INSERT INTO workspace_state VALUES (1, '/lib/photo.jpg', 10, 20, 1.0, 1, 0, 0)"
        )
        conn.commit()
        conn.close()

        import database
        if hasattr(database._local, "connection"):
            del database._local.connection

        with patch("database.get_db_path") as mock_db_path:
            mock_db_path.return_value = self.db_path
            init_db()

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(workspace_state)")
        columns = [row[1] for row in cursor.fetchall()]
        self.assertIn("image_id", columns)

        cursor.execute(
            "SELECT image_id, file_path FROM workspace_state WHERE slot_id=1"
        )
        row = cursor.fetchone()
        self.assertEqual(row[0], 1)
        self.assertEqual(row[1], "/lib/photo.jpg")

        conn.close()
        reset_thread_connection()
        with patch("database.get_db_path") as mock_db_path:
            mock_db_path.return_value = self.db_path
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM images WHERE id=1")
            conn.commit()
            cursor.execute("SELECT COUNT(*) FROM workspace_state")
            self.assertEqual(cursor.fetchone()[0], 0)
            reset_thread_connection()

    def test_collections_parent_name_unique(self):
        import database
        if hasattr(database._local, "connection"):
            del database._local.connection

        with patch("database.get_db_path") as mock_db_path:
            mock_db_path.return_value = self.db_path
            init_db()

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO collections (name, description, parent_id) VALUES (?, ?, ?)",
            ("Portraits", "", None),
        )
        parent_id = cursor.lastrowid
        cursor.execute(
            "INSERT INTO collections (name, description, parent_id) VALUES (?, ?, ?)",
            ("Portraits", "", parent_id),
        )
        conn.commit()
        reset_thread_connection()

if __name__ == '__main__':
    unittest.main()
