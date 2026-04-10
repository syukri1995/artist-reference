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
        for i in range(100000)
    ]
    cursor.executemany("""
        INSERT INTO workspace_state (slot_id, file_path, x, y, scale, z_order, flip_h, flip_v)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, data_to_insert)
    conn.commit()
    conn.close()

def run_benchmark():
    mgr = WorkspaceManager()

    start_time = time.time()
    for _ in range(10): # run multiple times to get a better measurement
        state = mgr.load_state(slot_id=1)
    end_time = time.time()

    print(f"Loaded {len(state)} items in {(end_time - start_time) / 10:.4f} seconds on average")

if __name__ == "__main__":
    setup_db()
    run_benchmark()
