import time
import os
import sys

# Change working directory so database path works properly
sys.path.append(os.getcwd())

from managers.workspace_manager import WorkspaceManager
from database import init_db, get_connection

def setup_db():
    init_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM workspace_state")

    # insert a lot of rows
    data_to_insert = [
        (1, f"path/to/file_{i}.jpg", i * 1.5, i * 2.5, 1.0, i, False, False)
        for i in range(200000)
    ]
    cursor.executemany("""
        INSERT INTO workspace_state (slot_id, file_path, x, y, scale, z_order, flip_h, flip_v)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, data_to_insert)
    conn.commit()
    conn.close()

def load_state_old(mgr, slot_id=1):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT file_path, x, y, scale, z_order, flip_h, flip_v FROM workspace_state WHERE slot_id=? ORDER BY z_order ASC", (slot_id,))
        rows = cursor.fetchall()
    except Exception:
        pass
    conn.close()

    state_dict = {}
    for row in rows:
        state_dict[row['file_path']] = {
            'x': row['x'],
            'y': row['y'],
            'scale': row['scale'],
            'z_order': row['z_order'],
            'flip_h': bool(row['flip_h']),
            'flip_v': bool(row['flip_v'])
        }
    return state_dict

def load_state_new(mgr, slot_id=1):
    conn = get_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT file_path, x, y, scale, z_order, flip_h, flip_v FROM workspace_state WHERE slot_id=? ORDER BY z_order ASC", (slot_id,))
        rows = cursor.fetchall()
    except Exception:
        pass
    conn.close()

    state_dict = {
        row['file_path']: {
            'x': row['x'],
            'y': row['y'],
            'scale': row['scale'],
            'z_order': row['z_order'],
            'flip_h': bool(row['flip_h']),
            'flip_v': bool(row['flip_v'])
        }
        for row in rows
    }
    return state_dict


def run_benchmark():
    mgr = WorkspaceManager()

    # Warmup
    load_state_old(mgr)
    load_state_new(mgr)

    iterations = 20

    start_time = time.time()
    for _ in range(iterations):
        state = load_state_old(mgr, slot_id=1)
    end_time = time.time()
    old_time = (end_time - start_time) / iterations

    start_time = time.time()
    for _ in range(iterations):
        state = load_state_new(mgr, slot_id=1)
    end_time = time.time()
    new_time = (end_time - start_time) / iterations

    print(f"Loaded {len(state)} items.")
    print(f"Old implementation: {old_time:.4f} seconds on average")
    print(f"New implementation: {new_time:.4f} seconds on average")
    if old_time > new_time:
        improvement = (old_time - new_time) / old_time * 100
        print(f"Improvement: {improvement:.2f}% faster")
    else:
        improvement = (new_time - old_time) / old_time * 100
        print(f"Slower by: {improvement:.2f}%")

if __name__ == "__main__":
    setup_db()
    run_benchmark()
