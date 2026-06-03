"""Zip backup and restore for database + media folders."""

import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from database import get_base_dir, get_db_path

logger = logging.getLogger(__name__)

_BACKUP_VERSION = 1


class BackupManager:
    def __init__(self) -> None:
        self.base_dir = get_base_dir()
        self.data_dir = self.base_dir / "data"
        self.images_dir = self.data_dir / "images"
        self.thumbs_dir = self.data_dir / "thumbnails"

    def create_backup(self, dest_zip: str) -> str:
        """Create a zip containing artist_reference.db, images/, and thumbnails/."""
        dest = Path(dest_zip)
        if dest.suffix.lower() != ".zip":
            dest = dest.with_suffix(".zip")

        db_path = get_db_path()
        if not db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "backup_manifest.txt",
                f"version={_BACKUP_VERSION}\n"
                f"created={datetime.now(timezone.utc).isoformat()}\n",
            )
            zf.write(db_path, "artist_reference.db")
            for folder, arc_prefix in (
                (self.images_dir, "images"),
                (self.thumbs_dir, "thumbnails"),
            ):
                if not folder.exists():
                    continue
                for path in folder.rglob("*"):
                    if path.is_file():
                        zf.write(path, f"{arc_prefix}/{path.relative_to(folder).as_posix()}")

        return str(dest)

    def restore_backup(self, src_zip: str) -> None:
        """Restore from a backup zip into the data directory (overwrites DB and media)."""
        src = Path(src_zip)
        if not src.exists():
            raise FileNotFoundError(src)

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.thumbs_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(src, "r") as zf:
            names = zf.namelist()
            if "artist_reference.db" not in names:
                raise ValueError("Invalid backup: missing artist_reference.db")

            db_dest = get_db_path()
            db_dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open("artist_reference.db") as src_db, open(db_dest, "wb") as out_db:
                shutil.copyfileobj(src_db, out_db)

            for prefix, dest_dir in (("images/", self.images_dir), ("thumbnails/", self.thumbs_dir)):
                for name in names:
                    if not name.startswith(prefix) or name.endswith("/"):
                        continue
                    rel = name[len(prefix) :]
                    target = dest_dir / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(name) as src_f, open(target, "wb") as out_f:
                        shutil.copyfileobj(src_f, out_f)
