from database import get_connection

class CollectionManager:
    def create_collection(self, name: str, description: str = "", parent_id: int = None) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            # Ensure column exists for compatibility logic
            cursor.execute("PRAGMA table_info(collections)")
            cols = [c[1] for c in cursor.fetchall()]
            has_parent = "parent_id" in cols
            
            if has_parent:
                cursor.execute('''
                    INSERT INTO collections (name, description, parent_id)
                    VALUES (?, ?, ?)
                ''', (name, description, parent_id))
            else:
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
        
        cursor.execute("PRAGMA table_info(collections)")
        cols = [c[1] for c in cursor.fetchall()]
        has_parent = "parent_id" in cols
        
        if has_parent:
            cursor.execute("SELECT id, name, description, parent_id FROM collections ORDER BY parent_id, name")
        else:
            cursor.execute("SELECT id, name, description, NULL as parent_id FROM collections ORDER BY name")
            
        collections = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return collections
        
    def add_image_to_collection(self, image_id: int, collection_id: int) -> bool:
        return self.add_images_to_collection([image_id], collection_id)

    def add_images_to_collection(self, image_ids: list[int], collection_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany('''
                INSERT OR IGNORE INTO collection_images (image_id, collection_id)
                VALUES (?, ?)
            ''', [(img_id, collection_id) for img_id in image_ids])
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to add images to collection: {e}")
            return False

    def remove_image_from_collection(self, image_id: int, collection_id: int) -> bool:
        return self.remove_images_from_collection([image_id], collection_id)

    def remove_images_from_collection(self, image_ids: list[int], collection_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany('''
                DELETE FROM collection_images 
                WHERE image_id = ? AND collection_id = ?
            ''', [(img_id, collection_id) for img_id in image_ids])
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to remove images from collection: {e}")
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

    # ------------------------------------------------------------------ smart collections
    
    def create_smart_collection(self, name: str, tag_ids: list[int]) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO smart_collections (name, tag_ids)
                VALUES (?, ?)
            ''', (name, ",".join(map(str, tag_ids))))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to create smart collection: {e}")
            return False
            
    def get_smart_collections(self):
        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(smart_collections)")
        if not cursor.fetchall(): return []
            
        cursor.execute("SELECT id, name, tag_ids FROM smart_collections ORDER BY name")
        result = []
        for row in cursor.fetchall():
            d = dict(row)
            d['tag_ids'] = [int(x) for x in d['tag_ids'].split(",") if x]
            result.append(d)
        conn.close()
        return result
        
    def delete_smart_collection(self, sc_id: int) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM smart_collections WHERE id = ?", (sc_id,))
            conn.commit()
            return True
        except Exception as e:
            print(f"Failed to delete smart collection: {e}")
            return False
