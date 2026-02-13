import sqlite3
conn = sqlite3.connect('./data/bot_data.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print('=== TABLES ===')
print(tables)

for t in tables:
    cursor.execute(f'PRAGMA table_info({t})')
    cols = [(r[1], r[2]) for r in cursor.fetchall()]
    print(f'\n=== {t} ===')
    for c in cols:
        print(f'  {c[0]}: {c[1]}')

conn.close()
