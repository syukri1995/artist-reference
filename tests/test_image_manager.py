import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import init_db, reset_thread_connection
from managers.image_manager import ImageManager


class TestImageManager(unittest.TestCase):
    def setUp(self):
        reset_thread_connection()

        self.test_dir = Path(tempfile.mkdtemp())
        self.db_path = self.test_dir / "data" / "artist_reference.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.source_image = self.test_dir / "source.png"
        Image.new("RGB", (10, 10), color="red").save(self.source_image)

    def tearDown(self):
        reset_thread_connection()
        shutil.rmtree(self.test_dir)

    def test_import_duplicate_hash_rejected(self):
        with patch("database.get_db_path", return_value=self.db_path), patch(
            "managers.image_manager.get_base_dir", return_value=self.test_dir
        ):
            init_db()
            mgr = ImageManager()
            self.assertTrue(mgr.import_image(str(self.source_image)))

            duplicate_source = self.test_dir / "source_copy.png"
            shutil.copy2(self.source_image, duplicate_source)
            self.assertFalse(mgr.import_image(str(duplicate_source)))

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM images")
            count = cursor.fetchone()[0]
            conn.close()
            self.assertEqual(count, 1)
            reset_thread_connection()

    def test_count_images_empty_library(self):
        with patch("database.get_db_path", return_value=self.db_path), patch(
            "managers.image_manager.get_base_dir", return_value=self.test_dir
        ):
            init_db()
            mgr = ImageManager()
            self.assertEqual(mgr.count_images(), 0)
            reset_thread_connection()

    def test_count_images_by_tag_id(self):
        with patch("database.get_db_path", return_value=self.db_path), patch(
            "managers.image_manager.get_base_dir", return_value=self.test_dir
        ):
            init_db()
            mgr = ImageManager()
            self.assertTrue(mgr.import_image(str(self.source_image)))

            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT id FROM images LIMIT 1")
            image_id = cur.fetchone()[0]
            cur.execute("INSERT INTO tags (name) VALUES (?)", ("portrait",))
            tag_id = cur.lastrowid
            cur.execute(
                "INSERT INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                (image_id, tag_id),
            )
            conn.commit()
            conn.close()

            self.assertEqual(mgr.count_images(), 1)
            self.assertEqual(mgr.count_images(tag_ids=tag_id), 1)
            self.assertEqual(mgr.count_images(tag_ids=tag_id + 999), 0)
            reset_thread_connection()


if __name__ == "__main__":
    unittest.main()
