# =========================================================
# DATABASE — AIR COMMANDER
# Prefix: ,
# =========================================================

import os
import json
import asyncio
import asyncpg

from urllib.parse import urlparse


DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None


# =========================================================
# DATABASE INIT
# =========================================================

async def init_db():
    global _pool

    if _pool or not DATABASE_URL:
        if not DATABASE_URL:
            print("⚠️ DATABASE_URL is not set.")
        return

    parsed = urlparse(DATABASE_URL)
    host = (parsed.hostname or "").lower()

    if host.startswith("db.") and host.endswith(".supabase.co"):
        print(
            "❌ Supabase direct database URL detected. "
            "Use Supabase Session Pooler in DATABASE_URL."
        )
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

            async with _pool.acquire() as conn:

                # =================================================
                # PLAYERS / GAMES
                # =================================================

                await conn.execute("""
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
                        session_id BIGINT
                            REFERENCES game_sessions(id)
                            ON DELETE CASCADE,
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
                        prefix TEXT NOT NULL DEFAULT ','
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
                """)

            # =====================================================
            # TICKET DATABASE
            # =====================================================

            await init_ticket_db()
            await init_ticket_advanced_db()

            print("✅ PostgreSQL connected and Air Commander DB is ready.")
            return

        except Exception as e:
            _pool = None

            print(
                f"⚠️ PostgreSQL attempt {attempt}/3 failed: "
                f"{type(e).__name__}: {e}"
            )

            if attempt < 3:
                await asyncio.sleep(attempt * 3)

    print("❌ PostgreSQL unavailable.")


# =========================================================
# PLAYER FUNCTIONS
# =========================================================

async def ensure_player(guild_id, user_id):
    if _pool:
        await _pool.execute(
            """
            INSERT INTO players(guild_id,user_id)
            VALUES($1,$2)
            ON CONFLICT DO NOTHING
            """,
            guild_id,
            user_id
        )


async def get_player(guild_id, user_id):
    await ensure_player(guild_id, user_id)

    if not _pool:
        return {
            "coins": 100,
            "xp": 0,
            "level": 1
        }

    row = await _pool.fetchrow(
        """
        SELECT coins,xp,level
        FROM players
        WHERE guild_id=$1 AND user_id=$2
        """,
        guild_id,
        user_id
    )

    return dict(row)


async def add_coins(guild_id, user_id, amount):
    await ensure_player(guild_id, user_id)

    if _pool:
        return await _pool.fetchval(
            """
            UPDATE players
            SET coins=GREATEST(0,coins+$3)
            WHERE guild_id=$1 AND user_id=$2
            RETURNING coins
            """,
            guild_id,
            user_id,
            amount
        )


async def add_xp(guild_id, user_id, amount):
    await ensure_player(guild_id, user_id)

    if _pool:
        await _pool.execute(
            """
            UPDATE players
            SET xp=xp+$3,
                level=1+((xp+$3)/100)
            WHERE guild_id=$1 AND user_id=$2
            """,
            guild_id,
            user_id,
            amount
        )


# =========================================================
# GAME FUNCTIONS
# =========================================================

async def game_stat(guild_id, user_id, game, win, score):
    if _pool:
        await _pool.execute(
            """
            INSERT INTO player_stats
            VALUES($1,$2,$3,$4,$5,$6,'{}')
            ON CONFLICT(guild_id,user_id,game)
            DO UPDATE SET
                wins=player_stats.wins+$4,
                losses=player_stats.losses+$5,
                score=player_stats.score+$6
            """,
            guild_id,
            user_id,
            game,
            int(win),
            int(not win),
            score
        )


async def new_session(guild_id, game, user_id, state=None):
    if _pool:
        return await _pool.fetchval(
            """
            INSERT INTO game_sessions(
                guild_id,game,owner_id,state,status
            )
            VALUES($1,$2,$3,$4::jsonb,'lobby')
            RETURNING id
            """,
            guild_id,
            game,
            user_id,
            json.dumps(state or {})
        )


async def session_info(session_id):
    if not _pool:
        return None

    return await _pool.fetchrow(
        "SELECT * FROM game_sessions WHERE id=$1",
        session_id
    )


async def session_players(session_id):
    if not _pool:
        return []

    return await _pool.fetch(
        """
        SELECT user_id
        FROM game_players
        WHERE session_id=$1
        ORDER BY user_id
        """,
        session_id
    )


async def join_session(session_id, user_id):
    if not _pool:
        return False

    row = await _pool.fetchrow(
        "SELECT status FROM game_sessions WHERE id=$1",
        session_id
    )

    if not row or row["status"] != "lobby":
        return False

    await _pool.execute(
        """
        INSERT INTO game_players(session_id,user_id)
        VALUES($1,$2)
        ON CONFLICT DO NOTHING
        """,
        session_id,
        user_id
    )

    return True


async def close_session(session_id, status="cancelled"):
    if _pool:
        await _pool.execute(
            """
            UPDATE game_sessions
            SET status=$2
            WHERE id=$1
            """,
            session_id,
            status
        )


# =========================================================
# PREFIX
# =========================================================

async def set_prefix(guild_id, prefix=","):
    if not _pool:
        return

    await _pool.execute(
        """
        INSERT INTO guild_settings(guild_id,prefix)
        VALUES($1,$2)
        ON CONFLICT(guild_id)
        DO UPDATE SET prefix=EXCLUDED.prefix
        """,
        guild_id,
        prefix
    )


async def get_prefix(guild_id):
    if not _pool:
        return ","

    value = await _pool.fetchval(
        """
        SELECT prefix
        FROM guild_settings
        WHERE guild_id=$1
        """,
        guild_id
    )

    return value or ","


async def all_prefixes():
    if not _pool:
        return {}

    rows = await _pool.fetch(
        "SELECT guild_id,prefix FROM guild_settings"
    )

    return {
        row["guild_id"]: row["prefix"]
        for row in rows
    }


# =========================================================
# WARNINGS
# =========================================================

async def create_warning(
    guild_id,
    user_id,
    moderator_id,
    reason,
    evidence="Not provided"
):
    if not _pool:
        return "AC-W0000", 0

    async with _pool.acquire() as conn:

        async with conn.transaction():

            warning_id = await conn.fetchval(
                """
                INSERT INTO warnings(
                    guild_id,
                    user_id,
                    moderator_id,
                    reason,
                    evidence
                )
                VALUES($1,$2,$3,$4,$5)
                RETURNING id
                """,
                guild_id,
                user_id,
                moderator_id,
                reason,
                evidence
            )

            count = await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM warnings
                WHERE guild_id=$1
                AND user_id=$2
                """,
                guild_id,
                user_id
            )

    return f"AC-W{warning_id:04d}", int(count)


async def get_warnings(guild_id, user_id):
    if not _pool:
        return []

    return await _pool.fetch(
        """
        SELECT
            id,
            moderator_id,
            reason,
            evidence,
            created_at,
            'AC-W' || LPAD(id::text,4,'0') AS case_code
        FROM warnings
        WHERE guild_id=$1
        AND user_id=$2
        ORDER BY created_at DESC
        LIMIT 25
        """,
        guild_id,
        user_id
    )


# =========================================================
# TICKET DATABASE
# =========================================================

async def init_ticket_db():
    if not _pool:
        return

    async with _pool.acquire() as conn:

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_config(
                guild_id BIGINT PRIMARY KEY,
                enabled BOOLEAN DEFAULT TRUE,
                max_open_tickets INTEGER DEFAULT 1,
                ticket_naming TEXT DEFAULT 'ticket-{number}-{user}',
                category_id BIGINT,
                support_role_ids JSONB DEFAULT '[]'::jsonb,
                admin_role_ids JSONB DEFAULT '[]'::jsonb,
                log_channel_id BIGINT,
                transcript_channel_id BIGINT
            );

            CREATE TABLE IF NOT EXISTS ticket_templates(
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                category_id BIGINT,
                support_role_ids JSONB DEFAULT '[]'::jsonb,
                welcome_message TEXT DEFAULT '',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS ticket_panels(
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                channel_id BIGINT,
                template_ids JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS tickets(
                id BIGSERIAL PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                channel_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                template_id BIGINT,
                ticket_number INTEGER,
                status TEXT DEFAULT 'open',
                claimed_by BIGINT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                closed_at TIMESTAMPTZ
            );

            CREATE TABLE IF NOT EXISTS ticket_events(
                id BIGSERIAL PRIMARY KEY,
                ticket_id BIGINT NOT NULL,
                guild_id BIGINT NOT NULL,
                actor_id BIGINT,
                event TEXT NOT NULL,
                data JSONB DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );

            CREATE TABLE IF NOT EXISTS ticket_counters(
                guild_id BIGINT PRIMARY KEY,
                counter INTEGER DEFAULT 0
            );
        """)


# =========================================================
# TICKET ADVANCED SETTINGS
# =========================================================

async def init_ticket_advanced_db():
    if not _pool:
        return

    async with _pool.acquire() as conn:

        await conn.execute("""
            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS auto_close_minutes INTEGER DEFAULT 0;

            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS auto_delete_minutes INTEGER DEFAULT 0;

            ALTER TABLE ticket_config
            ADD COLUMN IF NOT EXISTS user_can_close BOOLEAN DEFAULT TRUE;
        """)


# =========================================================
# TICKET CONFIG
# =========================================================

async def get_ticket_config(guild_id):
    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM ticket_config
        WHERE guild_id=$1
        """,
        guild_id
    )

    return dict(row) if row else None


async def create_ticket_config(guild_id):
    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        INSERT INTO ticket_config(guild_id)
        VALUES($1)
        ON CONFLICT(guild_id)
        DO UPDATE SET guild_id=EXCLUDED.guild_id
        RETURNING *
        """,
        guild_id
    )

    return dict(row)


async def update_ticket_config(guild_id, **updates):
    if not _pool or not updates:
        return

    allowed = {
        "enabled",
        "max_open_tickets",
        "ticket_naming",
        "category_id",
        "support_role_ids",
        "admin_role_ids",
        "log_channel_id",
        "transcript_channel_id",
        "auto_close_minutes",
        "auto_delete_minutes",
        "user_can_close"
    }

    updates = {
        key: value
        for key, value in updates.items()
        if key in allowed
    }

    if not updates:
        return

    values = []
    sets = []

    for index, (key, value) in enumerate(updates.items(), start=2):
        if key in {
            "support_role_ids",
            "admin_role_ids"
        }:
            value = json.dumps(value)

        values.append(value)
        sets.append(f"{key}=${index}")

    values.insert(0, guild_id)

    await _pool.execute(
        f"""
        UPDATE ticket_config
        SET {", ".join(sets)}
        WHERE guild_id=$1
        """,
        *values
    )


# =========================================================
# TICKET COUNTER
# =========================================================

async def next_ticket_number(guild_id):
    if not _pool:
        return 1

    return await _pool.fetchval(
        """
        INSERT INTO ticket_counters(guild_id,counter)
        VALUES($1,1)
        ON CONFLICT(guild_id)
        DO UPDATE SET counter=ticket_counters.counter+1
        RETURNING counter
        """,
        guild_id
    )


# =========================================================
# TICKET TEMPLATES
# =========================================================

async def create_ticket_template(
    guild_id,
    name,
    description="",
    category_id=None,
    support_role_ids=None,
    welcome_message=""
):
    if not _pool:
        return None

    return await _pool.fetchval(
        """
        INSERT INTO ticket_templates(
            guild_id,
            name,
            description,
            category_id,
            support_role_ids,
            welcome_message
        )
        VALUES($1,$2,$3,$4,$5::jsonb,$6)
        RETURNING id
        """,
        guild_id,
        name,
        description,
        category_id,
        json.dumps(support_role_ids or []),
        welcome_message
    )


async def get_ticket_templates(guild_id):
    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM ticket_templates
        WHERE guild_id=$1
        ORDER BY id
        """,
        guild_id
    )

    return [dict(row) for row in rows]


async def get_ticket_template(guild_id, template_id):
    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM ticket_templates
        WHERE guild_id=$1 AND id=$2
        """,
        guild_id,
        template_id
    )

    return dict(row) if row else None


async def delete_ticket_template(guild_id, template_id):
    if not _pool:
        return False

    result = await _pool.execute(
        """
        DELETE FROM ticket_templates
        WHERE guild_id=$1 AND id=$2
        """,
        guild_id,
        template_id
    )

    return result.endswith("1")


# =========================================================
# TICKET PANELS
# =========================================================

async def create_ticket_panel(
    guild_id,
    name,
    description="",
    channel_id=None,
    template_ids=None
):
    if not _pool:
        return None

    return await _pool.fetchval(
        """
        INSERT INTO ticket_panels(
            guild_id,
            name,
            description,
            channel_id,
            template_ids
        )
        VALUES($1,$2,$3,$4,$5::jsonb)
        RETURNING id
        """,
        guild_id,
        name,
        description,
        channel_id,
        json.dumps(template_ids or [])
    )


async def get_ticket_panels(guild_id):
    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM ticket_panels
        WHERE guild_id=$1
        ORDER BY id
        """,
        guild_id
    )

    return [dict(row) for row in rows]


async def get_ticket_panel(guild_id, panel_id):
    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM ticket_panels
        WHERE guild_id=$1 AND id=$2
        """,
        guild_id,
        panel_id
    )

    return dict(row) if row else None


async def update_ticket_panel(guild_id, panel_id, **updates):
    if not _pool or not updates:
        return

    allowed = {
        "name",
        "description",
        "channel_id",
        "template_ids"
    }

    updates = {
        key: value
        for key, value in updates.items()
        if key in allowed
    }

    if not updates:
        return

    values = [guild_id, panel_id]
    sets = []

    for index, (key, value) in enumerate(
        updates.items(),
        start=3
    ):
        if key == "template_ids":
            value = json.dumps(value)

        values.append(value)
        sets.append(f"{key}=${index}")

    await _pool.execute(
        f"""
        UPDATE ticket_panels
        SET {", ".join(sets)}
        WHERE guild_id=$1 AND id=$2
        """,
        *values
    )


async def delete_ticket_panel(guild_id, panel_id):
    if not _pool:
        return False

    result = await _pool.execute(
        """
        DELETE FROM ticket_panels
        WHERE guild_id=$1 AND id=$2
        """,
        guild_id,
        panel_id
    )

    return result.endswith("1")


# =========================================================
# TICKETS
# =========================================================

async def create_ticket(
    guild_id,
    channel_id,
    user_id,
    template_id,
    ticket_number
):
    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        INSERT INTO tickets(
            guild_id,
            channel_id,
            user_id,
            template_id,
            ticket_number
        )
        VALUES($1,$2,$3,$4,$5)
        RETURNING *
        """,
        guild_id,
        channel_id,
        user_id,
        template_id,
        ticket_number
    )

    return dict(row)


async def get_ticket_by_channel(channel_id):
    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM tickets
        WHERE channel_id=$1
        """,
        channel_id
    )

    return dict(row) if row else None


async def get_user_open_tickets(guild_id, user_id):
    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM tickets
        WHERE guild_id=$1
        AND user_id=$2
        AND status='open'
        ORDER BY created_at
        """,
        guild_id,
        user_id
    )

    return [dict(row) for row in rows]


async def get_open_tickets(guild_id):
    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM tickets
        WHERE guild_id=$1
        AND status='open'
        ORDER BY created_at
        """,
        guild_id
    )

    return [dict(row) for row in rows]


async def close_ticket(ticket_id):
    if not _pool:
        return False

    result = await _pool.execute(
        """
        UPDATE tickets
        SET status='closed',
            closed_at=NOW()
        WHERE id=$1
        AND status='open'
        """,
        ticket_id
    )

    return result.endswith("1")


async def reopen_ticket(ticket_id):
    if not _pool:
        return False

    result = await _pool.execute(
        """
        UPDATE tickets
        SET status='open',
            closed_at=NULL
        WHERE id=$1
        AND status='closed'
        """,
        ticket_id
    )

    return result.endswith("1")


async def claim_ticket(ticket_id, user_id):
    if not _pool:
        return False

    result = await _pool.execute(
        """
        UPDATE tickets
        SET claimed_by=$2
        WHERE id=$1
        AND status='open'
        """,
        ticket_id,
        user_id
    )

    return result.endswith("1")


# =========================================================
# TICKET EVENTS / LOGS
# =========================================================

async def log_ticket_event(
    ticket_id,
    guild_id,
    actor_id,
    event,
    data=None
):
    if not _pool:
        return

    await _pool.execute(
        """
        INSERT INTO ticket_events(
            ticket_id,
            guild_id,
            actor_id,
            event,
            data
        )
        VALUES($1,$2,$3,$4,$5::jsonb)
        """,
        ticket_id,
        guild_id,
        actor_id,
        event,
        json.dumps(data or {})
    )


# =========================================================
# BOT HOOK
# =========================================================

try:
    from discord.ext import commands as _commands

    _original_bot_init = _commands.Bot.__init__

    def _air_bot_init(self, *args, **kwargs):
        _original_bot_init(self, *args, **kwargs)

        try:
            import moderation_extra
            moderation_extra.setup(self)

        except Exception as exc:
            print(
                f"Moderation module setup error: "
                f"{type(exc).__name__}: {exc}"
            )

    _commands.Bot.__init__ = _air_bot_init

except Exception as exc:
    print(
        f"Bot hook setup error: "
        f"{type(exc).__name__}: {exc}"
    )
