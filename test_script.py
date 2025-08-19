import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()  # Load variables from .env

db_url = os.getenv("DATABASE_URL")

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT NOW();")
    result = cur.fetchone()
    print("✅ Database is alive! Current time:", result[0])
    cur.close()
    conn.close()
except Exception as e:
    print("❌ DB connection failed:", e)
