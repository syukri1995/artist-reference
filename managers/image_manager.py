import shutil
from pathlib import Path
from PIL import Image
import os
from database import get_connection, get_base_dir

class ImageManager:
    def __init__(self):
        self.base_dir = get_base_dir()
        self.images_dir = self.base_dir / "data" / "images"
        self.thumbs_dir = self.base_dir / "data" / "thumbnails"
        
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        
    def import_image(self, file_path: str) -> bool:
        """Copies an image to the managed library, generates thumbnail, and saves to DB."""
        source_path = Path(file_path)
        if not source_path.exists():
            return False

        # Copy original
        dest_path = self.images_dir / source_path.name
        
        # Handle duplicate filenames
        counter = 1
        while dest_path.exists():
            dest_path = self.images_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
            counter += 1
            
        shutil.copy2(source_path, dest_path)
        
        # Generate WebP thumbnail
        thumb_path = self.thumbs_dir / f"{dest_path.stem}.webp"
        
        width, height = self._generate_thumbnail(str(dest_path), str(thumb_path))
        
        # Compute Hash
        import hashlib
        hash_md5 = hashlib.md5()
        with open(dest_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        file_hash = hash_md5.hexdigest()

        # Save to DB
        success = self._save_to_db(str(dest_path), str(thumb_path), width, height, file_hash)
        if not success:
            # Cleanup on failure
            if dest_path.exists(): os.remove(dest_path)
            if thumb_path.exists(): os.remove(thumb_path)
            return False
            
        return True

    def _generate_thumbnail(self, source_path: str, thumb_path: str, max_size=(200, 200)) -> tuple[int, int]:
        try:
            with Image.open(source_path) as img:
                width, height = img.size
                
                # Convert to RGB mode if not
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                    
                img.thumbnail(max_size, Image.Resampling.LANCZOS)
                img.save(thumb_path, "WEBP", quality=80)
                
                return width, height
        except Exception as e:
            print(f"Error generating thumbnail for {source_path}: {e}")
            return 0, 0

    def _save_to_db(self, file_path: str, thumb_path: str, width: int, height: int, file_hash: str) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO images (file_path, thumbnail_path, width, height, file_hash)
                VALUES (?, ?, ?, ?, ?)
            ''', (str(file_path), str(thumb_path), width, height, file_hash))
            conn.commit()
            return True
        except Exception as e:
            print(f"Database error: {e}")
            return False

    def check_duplicate_by_hash(self, file_hash: str) -> str | None:
        """Checks if a file with the given hash already exists in the database. Returns filename if match."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM images WHERE file_hash = ?", (file_hash,))
            row = cursor.fetchone()
            conn.close()
            if row:
                return Path(row['file_path']).name
            return None
        except Exception as e:
            print(f"Duplicate check error: {e}")
            return None
            
    def query_images(self, collection_id=None, tag_id=None, search_term=None, only_favorites=False):
        """Query images detached from DB references to avoid cross-thread issues."""
        conn = get_connection()
        cursor = conn.cursor()
        
        query = "SELECT DISTINCT i.id, i.file_path, i.thumbnail_path, i.width, i.height, i.is_favorite FROM images i"
        joins = []
        conditions = []
        params = []
        
        if only_favorites:
            conditions.append("i.is_favorite = 1")
        
        if collection_id is not None:
            joins.append("JOIN collection_images ci ON i.id = ci.image_id")
            conditions.append("ci.collection_id = ?")
            params.append(collection_id)
            
        if tag_id is not None:
            joins.append("JOIN image_tags it ON i.id = it.image_id")
            conditions.append("it.tag_id = ?")
            params.append(tag_id)
            
        if search_term:
            if "JOIN image_tags it" not in " ".join(joins):
                joins.append("LEFT JOIN image_tags it ON i.id = it.image_id")
            joins.append("LEFT JOIN tags t ON it.tag_id = t.id")
            
            search_param = f"%{search_term}%"
            conditions.append("(i.file_path LIKE ? OR t.name LIKE ?)")
            params.append(search_param)
            params.append(search_param)
            
        final_query = query + " " + " ".join(joins)
        if conditions:
            final_query += " WHERE " + " AND ".join(conditions)
            
        final_query += " ORDER BY i.date_added DESC"
        
        cursor.execute(final_query, tuple(params))
        images = [dict(row) for row in cursor.fetchall()] # Convert sqlite3.Row to dict to detach from DB
        conn.close()
        return images
        
    def delete_image(self, file_path: str):
        """Deletes image metadata and its physical thumbnail and library representations."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT thumbnail_path FROM images WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            
            if row:
                thumb_path = Path(row['thumbnail_path'])
                img_path = Path(file_path)
                
                if thumb_path.exists():
                    try: os.remove(thumb_path)
                    except: pass
                    
                if img_path.exists():
                    try: os.remove(img_path)
                    except: pass
                    
                cursor.execute("DELETE FROM images WHERE file_path = ?", (file_path,))
                
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Failed to delete image {file_path}: {e}")
            return False

    def toggle_favorite(self, file_path: str) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("UPDATE images SET is_favorite = NOT is_favorite WHERE file_path = ?", (file_path,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Failed to toggle favorite: {e}")
            return False
