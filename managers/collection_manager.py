from database import get_connection

class CollectionManager:
    def create_collection(self, name: str, description: str = "") -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO collections (name, description)
                VALUES (?, ?)
            ''', (name, description))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to create collection: {e}")
            return False
            
    def get_collections(self):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, name, description FROM collections ORDER BY name")
        collections = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return collections
        
    def add_image_to_collection(self, image_id: int, collection_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR IGNORE INTO collection_images (image_id, collection_id)
                VALUES (?, ?)
            ''', (image_id, collection_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to add image to collection: {e}")
            return False

    def remove_image_from_collection(self, image_id: int, collection_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM collection_images 
                WHERE image_id = ? AND collection_id = ?
            ''', (image_id, collection_id))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to remove image from collection: {e}")
            return False
            
    def delete_collection(self, collection_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM collections WHERE id = ?", (collection_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to delete collection: {e}")
            return False
