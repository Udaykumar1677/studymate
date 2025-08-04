import sqlite3

conn = sqlite3.connect('database.db')
c = conn.cursor()

# Drop the old notes table
c.execute('DROP TABLE IF EXISTS notes')

# Recreate notes table with correct columns
c.execute('''
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    title TEXT NOT NULL,
    content TEXT,
    file_path TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
''')

conn.commit()
conn.close()

print("✅ Notes table reset successfully.")

