"""One-time migration: add UNIQUE(parsed_table, parsed_id) to activities."""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()
url = os.environ["DATABASE_URL"]

conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

# Check if the constraint already exists before adding it
cur.execute("""
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'activities_parsed_table_parsed_id_key'
""")
if cur.fetchone():
    print("Constraint already exists — nothing to do.")
else:
    cur.execute("""
        ALTER TABLE activities
        ADD CONSTRAINT activities_parsed_table_parsed_id_key
        UNIQUE (parsed_table, parsed_id)
    """)
    print("Unique constraint added successfully.")

cur.close()
conn.close()
