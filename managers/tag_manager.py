import logging

from database import get_connection

logger = logging.getLogger(__name__)


class TagManager:
    def create_tag(self, name: str) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO tags (name)
                VALUES (?)
            ''', (name,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to create tag: {e}")
            return False

    def get_tags(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM tags ORDER BY name")
        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tags

    def get_popular_tags(self, limit: int = 15):
        """Returns the most frequently used tags."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT t.id, t.name, COUNT(it.image_id) as count
            FROM tags t
            LEFT JOIN image_tags it ON t.id = it.tag_id
            GROUP BY t.id
            ORDER BY count DESC, t.name ASC
            LIMIT ?
        """, (limit,))
        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tags

    def tag_image(self, image_id: int, tag_id: int) -> bool:
        return self.tag_images([image_id], tag_id)

    def tag_images(self, image_ids: list[int], tag_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany('''
                INSERT OR IGNORE INTO image_tags (image_id, tag_id)
                VALUES (?, ?)
            ''', [(img_id, tag_id) for img_id in image_ids])
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to tag images: {e}")
            return False

    def remove_tag_from_image(self, image_id: int, tag_id: int) -> bool:
        return self.remove_tag_from_images([image_id], tag_id)

    def remove_tag_from_images(self, image_ids: list[int], tag_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany('''
                DELETE FROM image_tags
                WHERE image_id = ? AND tag_id = ?
            ''', [(img_id, tag_id) for img_id in image_ids])
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to untag images: {e}")
            return False

    def get_tag_by_name(self, name: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM tags WHERE name = ?", (name,))
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_tags_for_image(self, image_id: int) -> list:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT t.id, t.name, it.is_ai, it.confidence FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = ?",
            (image_id,)
        )
        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tags

    def tag_image_ai(self, image_id: int, tag_name: str, confidence: float) -> bool:
        """Apply an AI-generated tag to an image."""
        return self.tag_image_ai_batch(image_id, [(tag_name, confidence)])

    def tag_image_ai_batch(self, image_id: int, tags: list[tuple[str, float]]) -> bool:
        """Apply multiple AI-generated tags to an image in a single transaction."""
        try:
            conn = get_connection()
            cursor = conn.cursor()

            # Always clear existing AI tags before applying new ones to handle re-scans
            cursor.execute("DELETE FROM image_tags WHERE image_id = ? AND is_ai = 1", (image_id,))

            if not tags:
                conn.commit()
                return True

            tag_links = []
            for tag_name, confidence in tags:
                # Ensure tag exists
                cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag_name,))
                cursor.execute("SELECT id FROM tags WHERE name = ?", (tag_name,))
                row = cursor.fetchone()
                if row:
                    tag_id = row["id"]
                    tag_links.append((image_id, tag_id, confidence))

            if tag_links:
                # Link with AI flag and confidence
                cursor.executemany('''
                    INSERT OR REPLACE INTO image_tags (image_id, tag_id, is_ai, confidence)
                    VALUES (?, ?, 1, ?)
                ''', tag_links)

            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to apply AI tags batch: {e}")
            return False

    def remove_all_tags_from_image(self, image_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to remove all tags from image: {e}")
            return False

    def apply_danbooru_tags_to_image(self, image_id: int, tag_names: list[str]) -> int:
        """Create tags if needed and link them to an image. Returns count linked."""
        unique: list[str] = []
        seen: set[str] = set()
        for raw in tag_names:
            name = raw.strip()
            if not name or name in seen:
                continue
            seen.add(name)
            unique.append(name)
        if not unique:
            return 0
        try:
            conn = get_connection()
            cursor = conn.cursor()
            tag_ids: list[int] = []
            cursor.executemany("INSERT OR IGNORE INTO tags (name) VALUES (?)", [(name,) for name in unique])
            chunk_size = 900
            for i in range(0, len(unique), chunk_size):
                chunk = unique[i:i + chunk_size]
                placeholders = ",".join("?" * len(chunk))
                cursor.execute(f"SELECT id FROM tags WHERE name IN ({placeholders})", chunk)
                rows = cursor.fetchall()
                tag_ids.extend([int(row["id"]) for row in rows])
            if tag_ids:
                cursor.executemany(
                    "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                    [(image_id, tid) for tid in tag_ids],
                )
            conn.commit()
            conn.close()
            return len(tag_ids)
        except Exception as exc:
            logger.error("apply_danbooru_tags_to_image failed: %s", exc)
            return 0

    def add_tags_to_image(self, image_id: int, tag_ids: list) -> bool:
        if not tag_ids:
            return True
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                "INSERT OR IGNORE INTO image_tags (image_id, tag_id) VALUES (?, ?)",
                [(image_id, tid) for tid in tag_ids]
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to add tags to image: {e}")
            return False

    def delete_tag(self, tag_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            # Delete references first
            cursor.execute("DELETE FROM image_tags WHERE tag_id = ?", (tag_id,))
            # Delete tag string
            cursor.execute("DELETE FROM tags WHERE id = ?", (tag_id,))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete global tag: {e}")
            return False
