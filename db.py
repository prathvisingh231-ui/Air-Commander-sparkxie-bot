import os, asyncpg, json
DATABASE_URL=os.getenv("DATABASE_URL"); _pool=None
async def init_db():
 global _pool
 if _pool or not DATABASE_URL:return
 _pool=await asyncpg.create_pool(DATABASE_URL,min_size=1,max_size=8)
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
CREATE TABLE IF NOT EXISTS territories(guild_id BIGINT,territory TEXT,owner_team TEXT,level INT DEFAULT 1,resources INT DEFAULT 100,PRIMARY KEY(guild_id,territory));""")
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
