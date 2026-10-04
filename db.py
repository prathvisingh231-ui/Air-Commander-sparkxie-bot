import os, asyncpg, json, asyncio
from urllib.parse import urlparse
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None

async def init_db():
    """Initialize database connection and create all required tables"""
    global _pool
    if _pool or not DATABASE_URL:
        if not DATABASE_URL:
            print("⚠️ DATABASE_URL is not set; database features are disabled.")
        return
    
    parsed = urlparse(DATABASE_URL)
    host = (parsed.hostname or "").lower()
    
    if host.startswith("db.") and host.endswith(".supabase.co"):
        print("❌ Supabase direct database URL detected. Use Session pooler (port 5432) in DATABASE_URL.")
        return
    
    for attempt in range(1, 4):
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=8,
                command_timeout=30,
                timeout=15
            )
            async with _pool.acquire() as c:
                await c.execute("""
                CREATE TABLE IF NOT EXISTS players(
                    guild_id BIGINT,
                    user_id BIGINT,
                    coins BIGINT DEFAULT 100,
                    xp BIGINT DEFAULT 0,
                    level INT DEFAULT 1,
                    PRIMARY KEY(guild_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS player_stats(
                    guild_id BIGINT,
                    user_id BIGINT,
                    game TEXT,
                    wins INT DEFAULT 0,
                    losses INT DEFAULT 0,
                    score BIGINT DEFAULT 0,
                    data JSONB DEFAULT '{}'::jsonb,
                    PRIMARY KEY(guild_id,user_id,game)
                );
                CREATE TABLE IF NOT EXISTS inventories(
                    guild_id BIGINT,
                    user_id BIGINT,
                    item TEXT,
                    quantity INT DEFAULT 0,
                    PRIMARY KEY(guild_id,user_id,item)
                );
                CREATE TABLE IF NOT EXISTS game_sessions(
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT,
                    game TEXT,
                    owner_id BIGINT,
                    state JSONB DEFAULT '{}'::jsonb,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS game_players(
                    session_id BIGINT REFERENCES game_sessions(id) ON DELETE CASCADE,
                    user_id BIGINT,
                    state JSONB DEFAULT '{}'::jsonb,
                    PRIMARY KEY(session_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS achievements(
                    guild_id BIGINT,
                    user_id BIGINT,
                    achievement TEXT,
                    unlocked_at TIMESTAMPTZ DEFAULT NOW(),
                    PRIMARY KEY(guild_id,user_id,achievement)
                );
                CREATE TABLE IF NOT EXISTS missions(
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT,
                    user_id BIGINT,
                    mission TEXT,
                    reward INT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS bounties(
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT,
                    target_id BIGINT,
                    creator_id BIGINT,
                    challenge TEXT,
                    reward INT,
                    completed BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS market(
                    guild_id BIGINT,
                    item TEXT,
                    price INT,
                    stock INT DEFAULT 1,
                    PRIMARY KEY(guild_id,item)
                );
                CREATE TABLE IF NOT EXISTS territories(
                    guild_id BIGINT,
                    territory TEXT,
                    owner_team TEXT,
                    level INT DEFAULT 1,
                    resources INT DEFAULT 100,
                    PRIMARY KEY(guild_id,territory)
                );
                CREATE TABLE IF NOT EXISTS guild_settings(
                    guild_id BIGINT PRIMARY KEY,
                    prefix TEXT NOT NULL DEFAULT '!'
                );
                CREATE TABLE IF NOT EXISTS warnings(
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    moderator_id BIGINT NOT NULL,
                    reason TEXT NOT NULL,
                    evidence TEXT NOT NULL DEFAULT 'Not provided',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS command_logs(
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    username TEXT,
                    command_name TEXT NOT NULL,
                    command_type TEXT DEFAULT 'prefix',
                    arguments TEXT,
                    channel_id BIGINT,
                    channel_name TEXT,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT,
                    execution_time_ms FLOAT DEFAULT 0,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    INDEX idx_guild_logs (guild_id),
                    INDEX idx_user_logs (user_id),
                    INDEX idx_command_logs (command_name),
                    INDEX idx_created_at (created_at)
                );
                """)
            print("✅ PostgreSQL connected and Air Commander tables are ready.")
            return
        except Exception as e:
            _pool = None
            print(f"⚠️ PostgreSQL connection attempt {attempt}/3 failed: {type(e).__name__}: {e}")
            if attempt < 3:
                await asyncio.sleep(attempt * 3)
    
    print("❌ PostgreSQL unavailable. Database-backed features will be unavailable.")

# ======================== COMMAND LOGGING FUNCTIONS ========================

async def log_command(guild_id, user_id, username, command_name, command_type="prefix", 
                     arguments=None, channel_id=None, channel_name=None, 
                     success=True, error_message=None, execution_time_ms=0):
    """
    Log a command execution to the database
    
    Args:
        guild_id: Discord guild ID
        user_id: Discord user ID
        username: Username of the person who ran the command
        command_name: Name of the command
        command_type: 'prefix' or 'slash' (default: 'prefix')
        arguments: Command arguments as string or dict
        channel_id: Channel where command was executed
        channel_name: Name of the channel
        success: Whether the command succeeded
        error_message: Error message if command failed
        execution_time_ms: How long the command took to execute
    """
    if not _pool:
        return None
    
    try:
        # Convert arguments to JSON string if it's a dict
        args_str = json.dumps(arguments) if isinstance(arguments, dict) else (arguments or "")
        
        command_id = await _pool.fetchval("""
            INSERT INTO command_logs(
                guild_id, user_id, username, command_name, command_type,
                arguments, channel_id, channel_name, success, 
                error_message, execution_time_ms
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
        """, guild_id, user_id, username, command_name, command_type,
            args_str, channel_id, channel_name, success, error_message, execution_time_ms)
        
        return command_id
    except Exception as e:
        print(f"❌ Error logging command: {e}")
        return None

async def get_command_history(guild_id=None, user_id=None, command_name=None, limit=50):
    """
    Retrieve command history
    
    Args:
        guild_id: Filter by guild (optional)
        user_id: Filter by user (optional)
        command_name: Filter by command name (optional)
        limit: Number of records to return (default: 50, max: 500)
    """
    if not _pool:
        return []
    
    limit = min(limit, 500)
    
    query = "SELECT * FROM command_logs WHERE 1=1"
    params = []
    param_num = 1
    
    if guild_id:
        query += f" AND guild_id = ${param_num}"
        params.append(guild_id)
        param_num += 1
    
    if user_id:
        query += f" AND user_id = ${param_num}"
        params.append(user_id)
        param_num += 1
    
    if command_name:
        query += f" AND command_name ILIKE ${param_num}"
        params.append(f"%{command_name}%")
        param_num += 1
    
    query += f" ORDER BY created_at DESC LIMIT {limit}"
    
    try:
        rows = await _pool.fetch(query, *params)
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"❌ Error retrieving command history: {e}")
        return []

async def get_user_command_stats(guild_id, user_id):
    """Get command usage statistics for a user"""
    if not _pool:
        return None
    
    try:
        stats = await _pool.fetchrow("""
            SELECT 
                COUNT(*) as total_commands,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed,
                AVG(execution_time_ms) as avg_execution_time,
                MAX(created_at) as last_command
            FROM command_logs
            WHERE guild_id = $1 AND user_id = $2
        """, guild_id, user_id)
        return dict(stats) if stats else None
    except Exception as e:
        print(f"❌ Error retrieving user stats: {e}")
        return None

async def get_most_used_commands(guild_id, limit=10):
    """Get the most used commands in a guild"""
    if not _pool:
        return []
    
    try:
        rows = await _pool.fetch("""
            SELECT 
                command_name,
                COUNT(*) as usage_count,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful_uses,
                AVG(execution_time_ms) as avg_time
            FROM command_logs
            WHERE guild_id = $1
            GROUP BY command_name
            ORDER BY usage_count DESC
            LIMIT $2
        """, guild_id, limit)
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"❌ Error retrieving top commands: {e}")
        return []

async def get_failed_commands(guild_id, limit=20):
    """Get recent failed command executions"""
    if not _pool:
        return []
    
    try:
        rows = await _pool.fetch("""
            SELECT * FROM command_logs
            WHERE guild_id = $1 AND success = FALSE
            ORDER BY created_at DESC
            LIMIT $2
        """, guild_id, limit)
        return [dict(row) for row in rows]
    except Exception as e:
        print(f"❌ Error retrieving failed commands: {e}")
        return []

async def clear_old_logs(days=30):
    """Delete command logs older than specified days"""
    if not _pool:
        return 0
    
    try:
        deleted = await _pool.fetchval("""
            DELETE FROM command_logs
            WHERE created_at < NOW() - INTERVAL '%s days'
            RETURNING COUNT(*)
        """, days)
        return deleted or 0
    except Exception as e:
        print(f"❌ Error clearing old logs: {e}")
        return 0

# ======================== EXISTING PLAYER & GAME FUNCTIONS ========================

async def ensure_player(g, u):
    if _pool:
        await _pool.execute(
            "INSERT INTO players(guild_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING", g, u
        )

async def get_player(g, u):
    await ensure_player(g, u)
    if not _pool:
        return {"coins": 100, "xp": 0, "level": 1}
    return dict(await _pool.fetchrow(
        "SELECT coins,xp,level FROM players WHERE guild_id=$1 AND user_id=$2", g, u
    ))

async def add_coins(g, u, n):
    await ensure_player(g, u)
    if _pool:
        return await _pool.fetchval(
            "UPDATE players SET coins=GREATEST(0,coins+$3) WHERE guild_id=$1 AND user_id=$2 RETURNING coins",
            g, u, n
        )

async def add_xp(g, u, n):
    await ensure_player(g, u)
    if _pool:
        await _pool.execute(
            "UPDATE players SET xp=xp+$3,level=1+((xp+$3)/100) WHERE guild_id=$1 AND user_id=$2", g, u, n
        )

async def game_stat(g, u, game, win, score):
    if _pool:
        await _pool.execute(
            "INSERT INTO player_stats VALUES($1,$2,$3,$4,$5,$6,'{}') ON CONFLICT(guild_id,user_id,game) DO UPDATE SET wins=player_stats.wins+$4,losses=player_stats.losses+$5,score=player_stats.score+$6",
            g, u, game, int(win), int(not win), score
        )

async def new_session(g, game, u, state=None):
    if _pool:
        return await _pool.fetchval(
            "INSERT INTO game_sessions(guild_id,game,owner_id,state,status) VALUES($1,$2,$3,$4::jsonb,'lobby') RETURNING id",
            g, game, u, json.dumps(state or {})
        )

async def session_info(s):
    if not _pool:
        return None
    return await _pool.fetchrow("SELECT * FROM game_sessions WHERE id=$1", s)

async def session_players(s):
    if not _pool:
        return []
    return await _pool.fetch("SELECT user_id FROM game_players WHERE session_id=$1 ORDER BY user_id", s)

async def join_session(s, u):
    if not _pool:
        return False
    row = await _pool.fetchrow("SELECT status FROM game_sessions WHERE id=$1", s)
    if not row or row["status"] != "lobby":
        return False
    await _pool.execute(
        "INSERT INTO game_players(session_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING", s, u
    )
    return True

async def close_session(s, status="cancelled"):
    if _pool:
        await _pool.execute("UPDATE game_sessions SET status=$2 WHERE id=$1", s, status)

async def set_prefix(guild_id, prefix):
    if _pool:
        await _pool.execute(
            "INSERT INTO guild_settings(guild_id,prefix) VALUES($1,$2) ON CONFLICT(guild_id) DO UPDATE SET prefix=EXCLUDED.prefix",
            guild_id, prefix
        )

async def get_prefix(guild_id):
    if not _pool:
        return "!"
    value = await _pool.fetchval("SELECT prefix FROM guild_settings WHERE guild_id=$1", guild_id)
    return value or "!"

async def all_prefixes():
    if not _pool:
        return {}
    rows = await _pool.fetch("SELECT guild_id,prefix FROM guild_settings")
    return {row["guild_id"]: row["prefix"] for row in rows}

async def create_warning(guild_id, user_id, moderator_id, reason, evidence="Not provided"):
    if not _pool:
        return "AC-W0000", 0
    async with _pool.acquire() as conn:
        async with conn.transaction():
            warning_id = await conn.fetchval(
                "INSERT INTO warnings(guild_id,user_id,moderator_id,reason,evidence) VALUES($1,$2,$3,$4,$5) RETURNING id",
                guild_id, user_id, moderator_id, reason, evidence
            )
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM warnings WHERE guild_id=$1 AND user_id=$2", guild_id, user_id
            )
    return f"AC-W{warning_id:04d}", int(count)

async def get_warnings(guild_id, user_id):
    if not _pool:
        return []
    return await _pool.fetch(
        "SELECT id,moderator_id,reason,evidence,created_at,'AC-W' || LPAD(id::text,4,'0') AS case_code FROM warnings WHERE guild_id=$1 AND user_id=$2 ORDER BY created_at DESC LIMIT 25",
        guild_id, user_id
    )

# ======================== BOT HOOK ========================

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
