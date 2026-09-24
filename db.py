import os
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv('DATABASE_URL')

def get_db_connection():
    if not DATABASE_URL:
        return None
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)
    return conn

def init_db():
    conn = get_db_connection()
    if not conn:
        print("⚠️ DATABASE_URL not found. Running without persistent storage.")
        return
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS guild_configs (
                guild_id BIGINT PRIMARY KEY,
                prefix TEXT DEFAULT '!',
                log_channel BIGINT,
                welcome_channel BIGINT
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                guild_id BIGINT,
                user_id BIGINT,
                moderator_id BIGINT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        conn.commit()
        cur.close()
        conn.close()
        print("🗄️ Database tables verified/initialized successfully.")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

if DATABASE_URL:
    init_db()
