import os, asyncpg, json, asyncio
from urllib.parse import urlparse
DATABASE_URL=os.getenv("DATABASE_URL"); _pool=None

async def init_db():
 global _pool
 if _pool or not DATABASE_URL:
  if not DATABASE_URL: print("⚠️ DATABASE_URL is not set; database features are disabled.")
  return
 parsed=urlparse(DATABASE_URL)
 host=(parsed.hostname or "").lower()
 if host.startswith("db.") and host.endswith(".supabase.co"):
  print("❌ Supabase direct database URL detected. Render uses IPv4, while Supabase direct connections are IPv6 on free projects. Use Supabase Connect → Session pooler (port 5432) in DATABASE_URL.")
  return
 for attempt in range(1,4):
  try:
   _pool=await asyncpg.create_pool(DATABASE_URL,min_size=1,max_size=8,command_timeout=30,timeout=15)
   async with _pool.acquire() as c:
    await c.execute("""CREATE TABLE IF NOT EXISTS players(guild_id BIGINT,user_id BIGINT,coins BIGINT DEFAULT 100,xp BIGINT DEFAULT 0,level INT DEFAULT 1,PRIMARY KEY(guild_id,user_id));
CREATE TABLE IF NOT EXISTS player_stats(guild_id BIGINT,user_id BIGINT,game TEXT,wins INT DEFAULT 0,losses INT DEFAULT 0,score BIGINT DEFAULT 0,data JSONB DEFAULT '{}'::jsonb,PRIMARY KEY(guild_id,user_id,game));
CREATE TABLE IF NOT EXISTS inventories(guild_id BIGINT,user_id BIGINT,item TEXT,quantity INT DEFAULT 0,PRIMARY KEY(guild_id,user_id,item));
CREATE TABLE IF NOT EXISTS game_sessions(id BIGSERIAL PRIMARY KEY,guild_id BIGINT,game TEXT,owner_id BIGINT,state JSONB DEFAULT '{}'::jsonb,status TEXT DEFAULT 'active',created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS game_players(session_id BIGINT REFERENCES game_sessions(id) ON DELETE CASCADE,user_id BIGINT,state JSONB DEFAULT '{}'::jsonb,PRIMARY KEY(session_id,user_id));
CREATE TABLE IF NOT EXISTS achievements(guild_id BIGINT,user_id BIGINT,achievement TEXT,unlocked_at TIMESTAMPTZ DEFAULT NOW(),PRIMARY KEY(guild_id,user_id,achievement));
CREATE TABLE IF NOT EXISTS missions(id BIGSERIAL PRIMARY KEY,guild_id BIGINT,user_id BIGINT,mission TEXT,reward INT,completed BOOLEAN DEFAULT FALSE,created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS bounties(id BIGSERIAL PRIMARY KEY,guild_id BIGINT,target_id BIGINT,creator_id BIGINT,challenge TEXT,reward INT,completed BOOLEAN DEFAULT FALSE,created_at TIMESTAMPTZ DEFAULT NOW());
CREATE TABLE IF NOT EXISTS market(guild_id BIGINT,item TEXT,price INT,stock INT DEFAULT 1,PRIMARY KEY(guild_id,item));
CREATE TABLE IF NOT EXISTS territories(guild_id BIGINT,territory TEXT,owner_team TEXT,level INT DEFAULT 1,resources INT DEFAULT 100,PRIMARY KEY(guild_id,territory));
CREATE TABLE IF NOT EXISTS guild_settings(guild_id BIGINT PRIMARY KEY,prefix TEXT NOT NULL DEFAULT '!');
CREATE TABLE IF NOT EXISTS warnings(id BIGSERIAL PRIMARY KEY,guild_id BIGINT NOT NULL,user_id BIGINT NOT NULL,moderator_id BIGINT NOT NULL,reason TEXT NOT NULL,evidence TEXT NOT NULL DEFAULT 'Not provided',created_at TIMESTAMPTZ DEFAULT NOW());""")
         await init_ticket_db()
    await init_ticket_advanced_db()
   print("✅ PostgreSQL connected and Air Commander tables are ready.")
   return
  except Exception as e:
   _pool=None
   print(f"⚠️ PostgreSQL connection attempt {attempt}/3 failed: {type(e).__name__}: {e}")
   if attempt < 3: await asyncio.sleep(attempt*3)
 print("❌ PostgreSQL unavailable. Discord bot will stay online; database-backed features will be unavailable until DATABASE_URL is fixed.")

async def ensure_player(g,u):
 if _pool: await _pool.execute("INSERT INTO players(guild_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",g,u)
async def get_player(g,u):
 await ensure_player(g,u)
 if not _pool:return {"coins":100,"xp":0,"level":1}
 return dict(await _pool.fetchrow("SELECT coins,xp,level FROM players WHERE guild_id=$1 AND user_id=$2",g,u))
async def add_coins(g,u,n):
 await ensure_player(g,u)
 if _pool:return await _pool.fetchval("UPDATE players SET coins=GREATEST(0,coins+$3) WHERE guild_id=$1 AND user_id=$2 RETURNING coins",g,u,n)
async def add_xp(g,u,n):
 await ensure_player(g,u)
 if _pool: await _pool.execute("UPDATE players SET xp=xp+$3,level=1+((xp+$3)/100) WHERE guild_id=$1 AND user_id=$2",g,u,n)
async def game_stat(g,u,game,win,score):
 if _pool: await _pool.execute("INSERT INTO player_stats VALUES($1,$2,$3,$4,$5,$6,'{}') ON CONFLICT(guild_id,user_id,game) DO UPDATE SET wins=player_stats.wins+$4,losses=player_stats.losses+$5,score=player_stats.score+$6",g,u,game,int(win),int(not win),score)
async def new_session(g,game,u,state=None):
 if _pool:
  return await _pool.fetchval("INSERT INTO game_sessions(guild_id,game,owner_id,state,status) VALUES($1,$2,$3,$4::jsonb,'lobby') RETURNING id",g,game,u,json.dumps(state or {}))
async def session_info(s):
 if not _pool:return None
 return await _pool.fetchrow("SELECT * FROM game_sessions WHERE id=$1",s)
async def session_players(s):
 if not _pool:return []
 return await _pool.fetch("SELECT user_id FROM game_players WHERE session_id=$1 ORDER BY user_id",s)
async def join_session(s,u):
 if not _pool:return False
 row=await _pool.fetchrow("SELECT status FROM game_sessions WHERE id=$1",s)
 if not row or row["status"]!="lobby":return False
 await _pool.execute("INSERT INTO game_players(session_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING",s,u)
 return True
async def close_session(s,status="cancelled"):
 if _pool:await _pool.execute("UPDATE game_sessions SET status=$2 WHERE id=$1",s,status)

async def set_prefix(guild_id, prefix):
 if _pool:
  await _pool.execute("INSERT INTO guild_settings(guild_id,prefix) VALUES($1,$2) ON CONFLICT(guild_id) DO UPDATE SET prefix=EXCLUDED.prefix",guild_id,prefix)

async def get_prefix(guild_id):
 if not _pool:return "!"
 value=await _pool.fetchval("SELECT prefix FROM guild_settings WHERE guild_id=$1",guild_id)
 return value or "!"

async def all_prefixes():
 if not _pool:return {}
 rows=await _pool.fetch("SELECT guild_id,prefix FROM guild_settings")
 return {row["guild_id"]: row["prefix"] for row in rows}

async def create_warning(guild_id, user_id, moderator_id, reason, evidence="Not provided"):
 if not _pool:
  return "AC-W0000", 0
 async with _pool.acquire() as conn:
  async with conn.transaction():
   warning_id=await conn.fetchval("INSERT INTO warnings(guild_id,user_id,moderator_id,reason,evidence) VALUES($1,$2,$3,$4,$5) RETURNING id",guild_id,user_id,moderator_id,reason,evidence)
   count=await conn.fetchval("SELECT COUNT(*) FROM warnings WHERE guild_id=$1 AND user_id=$2",guild_id,user_id)
 return f"AC-W{warning_id:04d}", int(count)

async def get_warnings(guild_id, user_id):
 if not _pool:return []
 return await _pool.fetch("SELECT id,moderator_id,reason,evidence,created_at,'AC-W' || LPAD(id::text,4,'0') AS case_code FROM warnings WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 25",guild_id,user_id)

# The main bot imports db before constructing commands.Bot. This hook lets the
# moderation module register its commands and dynamic prefix without changing bot.py.
try:
 from discord.ext import commands as _commands
 _original_bot_init = _commands.Bot.__init__
 def _air_bot_init(self, *args, **kwargs):
  _original_bot_init(self, *args, **kwargs)
  try:
   import moderation_extra
   moderation_extra.setup(self)
  except Exception as exc:
   print(f"Moderation module setup error: {type(exc).__name__}: {exc}")
 _commands.Bot.__init__ = _air_bot_init
except Exception as exc:
 print(f"Bot hook setup error: {type(exc).__name__}: {exc}")


# =========================================================
# TICKET ADVANCED SETTINGS MIGRATION
# =========================================================

async def init_ticket_advanced_db():
    global _pool

    if _pool is None:
        return

    async with _pool.acquire() as conn:

        await conn.execute("""
            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS auto_close_minutes INTEGER DEFAULT 0
        """)

        await conn.execute("""
            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS auto_delete_minutes INTEGER DEFAULT 0
        """)

        await conn.execute("""
            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS user_can_close BOOLEAN DEFAULT TRUE
        """)

        await conn.execute("""
            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS max_open_tickets INTEGER DEFAULT 1
        """)

        await conn.execute("""
            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS ticket_naming TEXT
            DEFAULT 'ticket-{number}-{user}'
        """)
     # =========================================================
# GET OPEN TICKETS
# =========================================================

async def get_open_tickets(guild_id):
    global _pool

    if _pool is None:
        return []

    async with _pool.acquire() as conn:

        rows = await conn.fetch("""
            SELECT *
            FROM tickets
            WHERE guild_id = $1
              AND status = 'open'
            ORDER BY created_at ASC
        """, guild_id)

        return [dict(row) for row in rows]
