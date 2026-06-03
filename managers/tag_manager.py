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
            print(f"Failed to create tag: {e}")
            return False

    def get_tags(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name FROM tags ORDER BY name")
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
            print(f"Failed to tag images: {e}")
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
            print(f"Failed to untag images: {e}")
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
            "SELECT t.id, t.name FROM tags t JOIN image_tags it ON t.id = it.tag_id WHERE it.image_id = ?",
            (image_id,)
        )
        tags = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return tags

    def remove_all_tags_from_image(self, image_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM image_tags WHERE image_id = ?", (image_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to remove all tags from image: {e}")
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
            for name in unique:
                cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
                cursor.execute("SELECT id FROM tags WHERE name = ?", (name,))
                row = cursor.fetchone()
                if row:
                    tag_ids.append(int(row["id"]))
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
            print(f"Failed to add tags to image: {e}")
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
            print(f"Failed to delete global tag: {e}")
            return False
