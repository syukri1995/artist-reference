from database import get_connection

class WorkspaceManager:
    def __init__(self):
        pass

    def save_state(self, state_list):
        """
        state_list should be a list of dicts:
        [{'file_path': str, 'x': float, 'y': float, 'scale': float, 'z_order': int}, ...]
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        # Clear existing state (a simple full replacement logic)
        cursor.execute("DELETE FROM workspace_state")
        
        if state_list:
            data_to_insert = [
                (item['file_path'], item['x'], item['y'], item['scale'], item['z_order'], item.get('flip_h', False), item.get('flip_v', False))
                for item in state_list
            ]
            cursor.executemany("""
                INSERT INTO workspace_state (file_path, x, y, scale, z_order, flip_h, flip_v)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, data_to_insert)
            
        conn.commit()
        conn.close()

    def load_state(self):
        """
        Returns a dict of saved state:
        {file_path: {'x': float, 'y': float, 'scale': float, 'z_order': int, 'flip_h': bool, 'flip_v': bool}, ...}
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("SELECT file_path, x, y, scale, z_order, flip_h, flip_v FROM workspace_state ORDER BY z_order ASC")
            rows = cursor.fetchall()
        except Exception:
            cursor.execute("SELECT file_path, x, y, scale, z_order FROM workspace_state ORDER BY z_order ASC")
            rows_old = cursor.fetchall()
            rows = []
            for r in rows_old:
                d = dict(r)
                d['flip_h'] = 0
                d['flip_v'] = 0
                rows.append(d)

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
