from database import get_connection


class WorkspaceManager:
    def save_state(self, state_list, slot_id=1):
        """
        state_list: [{'image_id': int, 'file_path': str, 'x', 'y', 'scale', 'z_order', ...}, ...]
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workspace_state WHERE slot_id=?", (slot_id,))

        if state_list:
            # One row per image_id (scene can briefly hold duplicates during edits).
            by_image_id: dict[int, dict] = {}
            for item in state_list:
                image_id = item.get("image_id")
                if image_id is not None:
                    by_image_id[int(image_id)] = item

            data_to_insert = [
                (
                    slot_id,
                    image_id,
                    item.get("file_path"),
                    item["x"],
                    item["y"],
                    item["scale"],
                    item["z_order"],
                    item.get("flip_h", False),
                    item.get("flip_v", False),
                    float(item.get("opacity", 1.0)),
                    bool(item.get("grayscale", False)),
                )
                for image_id, item in by_image_id.items()
            ]
            cursor.executemany(
                """
                INSERT OR REPLACE INTO workspace_state
                  (slot_id, image_id, file_path, x, y, scale, z_order, flip_h, flip_v, opacity, grayscale)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data_to_insert,
            )

        conn.commit()
        conn.close()

    def save_notes(self, notes_list, slot_id=1):
        """
        notes_list: [{'text': str, 'x', 'y', 'width', 'height', 'z_order', 'color': str}, ...]
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM workspace_notes WHERE slot_id=?", (slot_id,))

        if notes_list:
            data_to_insert = [
                (
                    slot_id,
                    n.get("text", ""),
                    n["x"],
                    n["y"],
                    n["width"],
                    n["height"],
                    n["z_order"],
                    n.get("color", "#FDE047"),
                )
                for n in notes_list
            ]
            cursor.executemany(
                """
                INSERT INTO workspace_notes
                  (slot_id, text, x, y, width, height, z_order, color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data_to_insert,
            )

        conn.commit()
        conn.close()

    def load_notes(self, slot_id=1):
        """
        Returns list of dicts for notes in the given slot.
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, text, x, y, width, height, z_order, color
            FROM workspace_notes
            WHERE slot_id=?
            ORDER BY z_order ASC
            """,
            (slot_id,),
        )
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for n, r in enumerate(rows)]

    def get_slot_counts(self) -> dict[int, int]:
        """Returns {slot_id: count_of_images}."""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT slot_id, COUNT(*) FROM workspace_state GROUP BY slot_id")
        rows = cursor.fetchall()
        conn.close()
        return {int(row[0]): int(row[1]) for row in rows}

    def load_state(self, slot_id=1):
        """
        Returns {image_id: {'file_path', 'x', 'y', 'scale', 'z_order', 'flip_h', 'flip_v'}}
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(workspace_state)")
        columns = {col[1] for col in cursor.fetchall()}

        if "image_id" in columns:
            cursor.execute("PRAGMA table_info(workspace_state)")
            ws_cols = {col[1] for col in cursor.fetchall()}
            has_opacity = "opacity" in ws_cols
            has_grayscale = "grayscale" in ws_cols
            if has_opacity and has_grayscale:
                cursor.execute(
                    """
                    SELECT image_id, file_path, x, y, scale, z_order, flip_h, flip_v, opacity, grayscale
                    FROM workspace_state
                    WHERE slot_id=?
                    ORDER BY z_order ASC
                    """,
                    (slot_id,),
                )
            elif has_opacity:
                cursor.execute(
                    """
                    SELECT image_id, file_path, x, y, scale, z_order, flip_h, flip_v, opacity
                    FROM workspace_state
                    WHERE slot_id=?
                    ORDER BY z_order ASC
                    """,
                    (slot_id,),
                )
            else:
                cursor.execute(
                    """
                    SELECT image_id, file_path, x, y, scale, z_order, flip_h, flip_v
                    FROM workspace_state
                    WHERE slot_id=?
                    ORDER BY z_order ASC
                    """,
                    (slot_id,),
                )
        else:
            cursor.execute(
                """
                SELECT file_path, x, y, scale, z_order, flip_h, flip_v
                FROM workspace_state
                WHERE slot_id=?
                ORDER BY z_order ASC
                """,
                (slot_id,),
            )

        rows = cursor.fetchall()
        conn.close()

        state_dict = {}
        missing_image_ids = []

        for row in rows:
            d = dict(row)
            if "image_id" in d and d["image_id"] is not None:
                image_id = int(d["image_id"])
                state_dict[image_id] = {
                    "file_path": d.get("file_path"),
                    "x": d["x"],
                    "y": d["y"],
                    "scale": d["scale"],
                    "z_order": d["z_order"],
                    "flip_h": bool(d.get("flip_h", 0)),
                    "flip_v": bool(d.get("flip_v", 0)),
                    "opacity": float(d.get("opacity", 1.0) or 1.0),
                    "grayscale": bool(d.get("grayscale", 0)),
                }
            elif d.get("file_path"):
                missing_image_ids.append(d)

        if missing_image_ids:
            conn2 = get_connection()
            c2 = conn2.cursor()

            # Extract unique file paths
            file_paths = list({d["file_path"] for d in missing_image_ids})
            path_to_id = {}

            # Batch query in chunks of 900 to avoid SQLite limits
            chunk_size = 900
            for i in range(0, len(file_paths), chunk_size):
                chunk = file_paths[i:i + chunk_size]
                placeholders = ",".join(["?"] * len(chunk))
                c2.execute(f"SELECT id, file_path FROM images WHERE file_path IN ({placeholders})", chunk)
                for id_row in c2.fetchall():
                    path_to_id[id_row["file_path"]] = int(id_row["id"])

            conn2.close()

            for d in missing_image_ids:
                if d["file_path"] in path_to_id:
                    image_id = path_to_id[d["file_path"]]
                    state_dict[image_id] = {
                        "file_path": d["file_path"],
                        "x": d["x"],
                        "y": d["y"],
                        "scale": d["scale"],
                        "z_order": d["z_order"],
                        "flip_h": bool(d.get("flip_h", 0)),
                        "flip_v": bool(d.get("flip_v", 0)),
                        "opacity": float(d.get("opacity", 1.0) or 1.0),
                        "grayscale": bool(d.get("grayscale", 0)),
                    }

        return state_dict

    def delete_for_image_ids(self, image_ids: list[int]) -> None:
        if not image_ids:
            return
        conn = get_connection()
        cursor = conn.cursor()
        placeholders = ",".join(["?"] * len(image_ids))
        cursor.execute(
            f"DELETE FROM workspace_state WHERE image_id IN ({placeholders})",
            image_ids,
        )
        conn.commit()
        conn.close()
