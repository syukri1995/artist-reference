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
                )
                for image_id, item in by_image_id.items()
            ]
            cursor.executemany(
                """
                INSERT OR REPLACE INTO workspace_state
                  (slot_id, image_id, file_path, x, y, scale, z_order, flip_h, flip_v, opacity)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                data_to_insert,
            )

        conn.commit()
        conn.close()

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
            if has_opacity:
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
                }
            elif d.get("file_path"):
                conn2 = get_connection()
                c2 = conn2.cursor()
                c2.execute("SELECT id FROM images WHERE file_path = ?", (d["file_path"],))
                id_row = c2.fetchone()
                conn2.close()
                if id_row:
                    image_id = int(id_row["id"])
                    state_dict[image_id] = {
                        "file_path": d["file_path"],
                        "x": d["x"],
                        "y": d["y"],
                        "scale": d["scale"],
                        "z_order": d["z_order"],
                        "flip_h": bool(d.get("flip_h", 0)),
                        "flip_v": bool(d.get("flip_v", 0)),
                        "opacity": float(d.get("opacity", 1.0) or 1.0),
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
