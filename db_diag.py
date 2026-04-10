from database import get_connection, init_db

init_db()
conn = get_connection()
cursor = conn.cursor()

# Check tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", [dict(r) for r in cursor.fetchall()])
