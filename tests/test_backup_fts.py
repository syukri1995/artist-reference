import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db_path, init_db, rebuild_images_fts, reset_thread_connection
from managers.backup_manager import BackupManager
from managers.image_manager import ImageManager


class TestBackupAndFts(unittest.TestCase):
    def setUp(self):
        reset_thread_connection()
        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "data" / "artist_reference.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        (self.test_dir / "data" / "images").mkdir(parents=True)
        (self.test_dir / "data" / "thumbnails").mkdir(parents=True)

    def tearDown(self):
        reset_thread_connection()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _patch_paths(self):
        return patch("database.get_db_path", return_value=self.db_path), patch(
            "database.get_base_dir", return_value=Path(self.test_dir)
        ), patch("managers.image_manager.get_base_dir", return_value=Path(self.test_dir)), patch(
            "managers.backup_manager.get_base_dir", return_value=Path(self.test_dir)
        ), patch("managers.backup_manager.get_db_path", return_value=self.db_path)

    def test_fts_migration_and_search(self):
        with self._patch_paths()[0], self._patch_paths()[1], self._patch_paths()[2]:
            init_db()
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                "INSERT INTO images (file_path, thumbnail_path, width, height, file_hash) "
                "VALUES (?, ?, 100, 100, ?)",
                (str(self.test_dir / "data" / "images" / "hero.png"), "t.webp", "abc"),
            )
            conn.execute("INSERT INTO tags (name) VALUES ('dragon')")
            conn.execute(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (1, 1)"
            )
            conn.commit()
            conn.close()
            rebuild_images_fts()

            im = ImageManager()
            im.images_dir = Path(self.test_dir) / "data" / "images"
            im.thumbs_dir = Path(self.test_dir) / "data" / "thumbnails"
            count = im.count_images(search_term="dragon")
            self.assertEqual(count, 1)

    def test_backup_roundtrip(self):
        with (
            self._patch_paths()[0],
            self._patch_paths()[1],
            self._patch_paths()[2],
            self._patch_paths()[3],
        ):
            init_db()
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO images (file_path, thumbnail_path, width, height, file_hash) "
                "VALUES ('x.png', 't.webp', 1, 1, 'h')"
            )
            conn.commit()
            conn.close()

            img_file = Path(self.test_dir) / "data" / "images" / "sample.png"
            img_file.write_bytes(b"png")
            zip_path = Path(self.test_dir) / "backup.zip"
            BackupManager().create_backup(str(zip_path))
            self.assertTrue(zip_path.exists())

            conn = sqlite3.connect(self.db_path)
            conn.execute("DELETE FROM images")
            conn.commit()
            conn.close()
            img_file.unlink()

            reset_thread_connection()
            BackupManager().restore_backup(str(zip_path))
            self.assertTrue(get_db_path().exists())
            self.assertTrue(img_file.exists())

            with zipfile.ZipFile(zip_path) as zf:
                self.assertIn("artist_reference.db", zf.namelist())


if __name__ == "__main__":
    unittest.main()
