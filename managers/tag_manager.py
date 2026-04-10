from database import get_connection

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
