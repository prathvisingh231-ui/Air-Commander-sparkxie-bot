import os
import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None

async def init_db():
    global _pool
    if _pool:
        return
    if not DATABASE_URL:
        print("DATABASE_URL not set; running without persistence.")
        return
    _pool = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=5)
    async with _pool.acquire() as c:
        await c.execute("""
        CREATE TABLE IF NOT EXISTS mod_cases (
          id BIGSERIAL PRIMARY KEY, case_code TEXT UNIQUE NOT NULL,
          guild_id BIGINT NOT NULL, target_id BIGINT NOT NULL, moderator_id BIGINT NOT NULL,
          action TEXT NOT NULL, reason TEXT NOT NULL, evidence TEXT, created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS suggestions (
          id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, author_id BIGINT NOT NULL,
          text TEXT NOT NULL, status TEXT DEFAULT 'Pending', staff_response TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS activity (
          id BIGSERIAL PRIMARY KEY, guild_id BIGINT NOT NULL, channel_id BIGINT NOT NULL,
          user_id BIGINT NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS activity_guild_channel_idx ON activity(guild_id, channel_id, created_at);
        """)

async def next_case(guild_id, target_id, moderator_id, action, reason, evidence):
    if not _pool:
        import time
        code=f"AC-{int(time.time()*1000)%9000+1000}"
        return code
    async with _pool.acquire() as c:
        row=await c.fetchrow("INSERT INTO mod_cases(case_code,guild_id,target_id,moderator_id,action,reason,evidence) VALUES('TEMP',$1,$2,$3,$4,$5,$6) RETURNING id",
          guild_id,target_id,moderator_id,action,reason,evidence)
        code=f"AC-{1000+row['id']}"
        await c.execute("UPDATE mod_cases SET case_code=$1 WHERE id=$2",code,row["id"])
        return code

async def save_suggestion(guild_id, author_id, text):
    if not _pool: return None
    return await _pool.fetchval("INSERT INTO suggestions(guild_id,author_id,text) VALUES($1,$2,$3) RETURNING id",guild_id,author_id,text)

async def log_activity(guild_id, channel_id, user_id):
    if _pool:
        await _pool.execute("INSERT INTO activity(guild_id,channel_id,user_id) VALUES($1,$2,$3)",guild_id,channel_id,user_id)

async def activity_counts(guild_id):
    if not _pool: return []
    return await _pool.fetch("SELECT channel_id, COUNT(*) AS messages FROM activity WHERE guild_id=$1 GROUP BY channel_id ORDER BY messages DESC LIMIT 15",guild_id)


async def update_suggestion(suggestion_id, guild_id, status=None, staff_response=None):
    if not _pool: return False
    row = await _pool.fetchrow("SELECT id FROM suggestions WHERE id=$1 AND guild_id=$2", suggestion_id, guild_id)
    if not row: return False
    await _pool.execute("UPDATE suggestions SET status=COALESCE($1,status), staff_response=COALESCE($2,staff_response) WHERE id=$3 AND guild_id=$4", status, staff_response, suggestion_id, guild_id)
    return True
