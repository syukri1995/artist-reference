import hashlib
import logging
import os
import shutil
from pathlib import Path

from PIL import Image

from database import get_base_dir, get_connection

logger = logging.getLogger(__name__)


class ImageManager:
    def __init__(self):
        self.base_dir = get_base_dir()
        self.images_dir = self.base_dir / "data" / "images"
        self.thumbs_dir = self.base_dir / "data" / "thumbnails"
        
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)
        
    @staticmethod
    def _compute_file_hash(path: Path) -> str:
        hash_md5 = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()

    def import_image(self, file_path: str) -> bool:
        """Copies an image to the managed library, generates thumbnail, and saves to DB."""
        source_path = Path(file_path)
        if not source_path.exists():
            return False

        file_hash = self._compute_file_hash(source_path)
        if self.check_duplicate_by_hash(file_hash):
            logger.info("Skipping duplicate import: %s", source_path.name)
            return False

        dest_path = self.images_dir / source_path.name

        counter = 1
        while dest_path.exists():
            dest_path = self.images_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
            counter += 1

        shutil.copy2(source_path, dest_path)

        thumb_path = self.thumbs_dir / f"{dest_path.stem}.webp"
        width, height = self._generate_thumbnail(str(dest_path), str(thumb_path))

        success = self._save_to_db(str(dest_path), str(thumb_path), width, height, file_hash)
        if not success:
            if dest_path.exists():
                os.remove(dest_path)
            if thumb_path.exists():
                os.remove(thumb_path)
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
            logger.error("Error generating thumbnail for %s: %s", source_path, e)
            return 0, 0

    def _save_to_db(self, file_path: str, thumb_path: str, width: int, height: int, file_hash: str) -> bool:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO images (file_path, thumbnail_path, width, height, file_hash)
                VALUES (?, ?, ?, ?, ?)
            ''', (str(file_path), str(thumb_path), width, height, file_hash))
            image_id = cursor.lastrowid
            conn.commit()
            self.index_image_fts(image_id)
            return True
        except Exception as e:
            logger.error("Database error: %s", e)
            return False

    def get_image_id_by_path(self, file_path: str) -> int | None:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM images WHERE file_path = ?", (file_path,))
            row = cursor.fetchone()
            conn.close()
            return int(row["id"]) if row else None
        except Exception as e:
            logger.error("get_image_id_by_path failed: %s", e)
            return None

    def get_image_id_by_hash(self, file_hash: str) -> int | None:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM images WHERE file_hash = ? LIMIT 1", (file_hash,))
            row = cursor.fetchone()
            conn.close()
            return int(row["id"]) if row else None
        except Exception as e:
            logger.error("get_image_id_by_hash failed: %s", e)
            return None

    def get_file_path_by_id(self, image_id: int) -> str | None:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT file_path FROM images WHERE id = ?", (image_id,))
            row = cursor.fetchone()
            conn.close()
            return row["file_path"] if row else None
        except Exception as e:
            logger.error("get_file_path_by_id failed: %s", e)
            return None

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
            logger.error("Duplicate check error: %s", e)
            return None
            
    SORT_OPTIONS = {
        "date_added_desc": "i.date_added DESC",
        "date_added_asc": "i.date_added ASC",
        "name_asc": "LOWER(i.file_path) ASC",
        "name_desc": "LOWER(i.file_path) DESC",
        "last_viewed_desc": "i.last_viewed DESC NULLS LAST",
        "favorite_first": "i.is_favorite DESC, i.date_added DESC",
    }

    def _build_query_parts(
        self,
        collection_id=None,
        tag_ids=None,
        search_term=None,
        only_favorites=False,
        only_recent=False,
        image_id=None,
    ):
        joins = []
        conditions = []
        params = []

        if only_favorites:
            conditions.append("i.is_favorite = 1")

        if only_recent:
            conditions.append("i.last_viewed IS NOT NULL")

        if collection_id is not None:
            joins.append("JOIN collection_images ci ON i.id = ci.image_id")
            conditions.append("ci.collection_id = ?")
            params.append(collection_id)

        if tag_ids:
            if isinstance(tag_ids, int):
                tag_ids = [tag_ids]

            # Use GROUP BY to enforce AND logic for all required tags.
            qmarks = ",".join(["?"] * len(tag_ids))
            joins.append(f"""
                JOIN (
                    SELECT image_id
                    FROM image_tags
                    WHERE tag_id IN ({qmarks})
                    GROUP BY image_id
                    HAVING COUNT(DISTINCT tag_id) = {len(tag_ids)}
                ) st ON i.id = st.image_id
            """)
            params.extend(tag_ids)

        if image_id is not None:
            conditions.append("i.id = ?")
            params.append(image_id)

        if search_term:
            fts_query = self._fts_query(search_term)
            if fts_query:
                joins.append("JOIN images_fts fts ON fts.image_id = i.id")
                conditions.append("images_fts MATCH ?")
                params.append(fts_query)
            else:
                if "JOIN image_tags it" not in " ".join(joins):
                    joins.append("LEFT JOIN image_tags it ON i.id = it.image_id")
                joins.append("LEFT JOIN tags t ON it.tag_id = t.id")
                search_param = f"%{search_term}%"
                conditions.append("(i.file_path LIKE ? OR t.name LIKE ?)")
                params.extend([search_param, search_param])

        return joins, conditions, params

    @staticmethod
    def _fts_query(search_term: str) -> str | None:
        tokens = [t for t in search_term.strip().split() if t]
        if not tokens:
            return None
        parts = []
        for token in tokens:
            safe = token.replace('"', '""')
            parts.append(f'"{safe}"*')
        return " ".join(parts)

    def _order_clause(self, sort_by: str, only_recent: bool) -> str:
        if only_recent:
            return " ORDER BY i.last_viewed DESC"
        clause = self.SORT_OPTIONS.get(sort_by, self.SORT_OPTIONS["date_added_desc"])
        if "NULLS LAST" in clause:
            return f" ORDER BY {clause.replace(' NULLS LAST', '')} DESC NULLS LAST"
        return f" ORDER BY {clause}"

    def count_images(
        self,
        collection_id=None,
        tag_ids=None,
        search_term=None,
        only_favorites=False,
        only_recent=False,
        image_id=None,
    ) -> int:
        conn = get_connection()
        cursor = conn.cursor()

        joins, conditions, params = self._build_query_parts(
            collection_id=collection_id,
            tag_ids=tag_ids,
            search_term=search_term,
            only_favorites=only_favorites,
            only_recent=only_recent,
            image_id=image_id,
        )

        query = "SELECT COUNT(DISTINCT i.id) AS total FROM images i " + " ".join(joins)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        cursor.execute(query, tuple(params))
        row = cursor.fetchone()
        conn.close()
        return int(row["total"]) if row else 0

    def query_images(
        self,
        collection_id=None,
        tag_ids=None,
        search_term=None,
        only_favorites=False,
        only_recent=False,
        limit=None,
        offset=None,
        sort_by: str = "date_added_desc",
        image_id=None,
    ):
        """Query images detached from DB references to avoid cross-thread issues."""
        conn = get_connection()
        cursor = conn.cursor()

        joins, conditions, params = self._build_query_parts(
            collection_id=collection_id,
            tag_ids=tag_ids,
            search_term=search_term,
            only_favorites=only_favorites,
            only_recent=only_recent,
            image_id=image_id,
        )

        query = (
            "SELECT DISTINCT i.id, i.file_path, i.thumbnail_path, i.width, i.height, "
            "i.is_favorite, i.last_viewed, i.date_added FROM images i "
            + " ".join(joins)
        )
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if only_recent:
            limit = 20
        query += self._order_clause(sort_by, only_recent)

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        if offset is not None:
            query += " OFFSET ?"
            params.append(offset)

        cursor.execute(query, tuple(params))
        images = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return images

    def get_image_detail(self, image_id: int) -> dict | None:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, file_path, thumbnail_path, width, height, is_favorite,
                   last_viewed, date_added, file_hash
            FROM images WHERE id = ?
            """,
            (image_id,),
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None

    def get_page_for_image(
        self,
        image_id: int,
        per_page: int,
        sort_by: str = "date_added_desc",
        collection_id=None,
        tag_ids=None,
        search_term=None,
        only_favorites=False,
        only_recent=False,
    ) -> int:
        """Return 1-based page index for image_id under current filters and sort."""
        conn = get_connection()
        cursor = conn.cursor()
        joins, conditions, params = self._build_query_parts(
            collection_id=collection_id,
            tag_ids=tag_ids,
            search_term=search_term,
            only_favorites=only_favorites,
            only_recent=only_recent,
        )
        order_sql = (
            "i.last_viewed DESC"
            if only_recent
            else self.SORT_OPTIONS.get(sort_by, self.SORT_OPTIONS["date_added_desc"])
        )
        order_sql = order_sql.replace(" NULLS LAST", "")
        inner = (
            "SELECT DISTINCT i.id, i.file_path, i.date_added, i.last_viewed, i.is_favorite "
            "FROM images i " + " ".join(joins)
        )
        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        cursor.execute(
            f"""
            WITH ranked AS (
                SELECT id, ROW_NUMBER() OVER (ORDER BY {order_sql}) AS rn
                FROM ({inner}{where}) AS sorted
            )
            SELECT CAST((rn - 1) / ? AS INTEGER) + 1 FROM ranked WHERE id = ?
            """,
            tuple(params) + (per_page, image_id),
        )
        row = cursor.fetchone()
        conn.close()
        return int(row[0]) if row else 1

    def index_image_fts(self, image_id: int) -> None:
        """Update FTS row for one image (after import or tag change)."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='images_fts'"
        )
        if not cursor.fetchone():
            conn.close()
            return
        cursor.execute("DELETE FROM images_fts WHERE image_id = ?", (image_id,))
        cursor.execute(
            """
            SELECT i.file_path,
                   COALESCE((
                       SELECT group_concat(t.name, ' ')
                       FROM image_tags it
                       JOIN tags t ON t.id = it.tag_id
                       WHERE it.image_id = i.id
                   ), '') AS tags
            FROM images i WHERE i.id = ?
            """,
            (image_id,),
        )
        row = cursor.fetchone()
        if row:
            filename = Path(row["file_path"]).name if row["file_path"] else ""
            cursor.execute(
                "INSERT INTO images_fts (image_id, filename, tags) VALUES (?, ?, ?)",
                (image_id, filename, row["tags"] or ""),
            )
        conn.commit()
        conn.close()
        
    def delete_image(self, file_path: str):
        """Deletes image metadata and its physical thumbnail and library representations."""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT id, thumbnail_path FROM images WHERE file_path = ?", (file_path,)
            )
            row = cursor.fetchone()

            if row:
                image_id = row["id"]
                thumb_path = Path(row["thumbnail_path"])
                img_path = Path(file_path)

                if thumb_path.exists():
                    try:
                        os.remove(thumb_path)
                    except OSError:
                        pass

                if img_path.exists():
                    try:
                        os.remove(img_path)
                    except OSError:
                        pass

                cursor.execute("DELETE FROM workspace_state WHERE image_id = ?", (image_id,))
                cursor.execute(
                    "DELETE FROM workspace_state WHERE file_path = ?", (file_path,)
                )
                cursor.execute("DELETE FROM images_fts WHERE image_id = ?", (image_id,))
                cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
                
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            logger.error("Failed to delete image %s: %s", file_path, e)
            return False

    def toggle_favorite(self, file_path: str) -> bool:
        return self.toggle_favorites([file_path])

    def toggle_favorites(self, file_paths: list[str]) -> bool:
        conn = None
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                "UPDATE images SET is_favorite = NOT is_favorite WHERE file_path = ?",
                [(p,) for p in file_paths]
            )
            conn.commit()
            return True
        except Exception as e:
            logger.error("Failed to toggle favorites: %s", e)
            return False
        finally:
            if conn:
                conn.close()

    def check_health(self) -> list[str]:
        """Scans the DB for images whose file no longer exists on disk."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT file_path FROM images")
        rows = cursor.fetchall()
        conn.close()
        
        missing_images = []
        for row in rows:
            path_str = row['file_path']
            if not Path(path_str).exists():
                missing_images.append(path_str)
                
        return missing_images
        
    def remove_missing_images(self, missing_paths: list[str]):
        """Removes the given missing paths from the database and scrubs their thumbnails."""
        conn = get_connection()
        cursor = conn.cursor()
        
        for p in missing_paths:
            cursor.execute(
                "SELECT id, thumbnail_path FROM images WHERE file_path = ?", (p,)
            )
            row = cursor.fetchone()
            if row:
                image_id = row["id"]
                thumb_path = Path(row["thumbnail_path"])
                if thumb_path.exists():
                    try:
                        os.remove(thumb_path)
                    except OSError:
                        pass
                cursor.execute("DELETE FROM workspace_state WHERE image_id = ?", (image_id,))
                cursor.execute(
                    "DELETE FROM workspace_state WHERE file_path = ?", (p,)
                )
                cursor.execute("DELETE FROM images WHERE id = ?", (image_id,))
            
        conn.commit()
        conn.close()

    def mark_as_viewed(self, file_paths: list[str]):
        """Updates the last_viewed timestamp for the given image paths."""
        if not file_paths:
            return
        conn = get_connection()
        cursor = conn.cursor()
        try:
            cursor.executemany(
                "UPDATE images SET last_viewed = CURRENT_TIMESTAMP WHERE file_path = ?",
                [(p,) for p in file_paths]
            )
            conn.commit()
        except Exception as e:
            logger.error("Failed to mark as viewed: %s", e)
        finally:
            conn.close()
