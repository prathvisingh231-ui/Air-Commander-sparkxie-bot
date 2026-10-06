```python
# ============================================================
# AIR COMMANDER — CENTRAL POSTGRESQL DATABASE
# ============================================================
#
# Persistent storage for:
#   • Players / Coins / XP / Levels
#   • Game statistics
#   • Inventories
#   • Game sessions
#   • Achievements / Missions / Bounties
#   • Market / Territories
#   • Guild prefix
#   • Warnings
#   • Command logs / Analytics
#
#   • Welcome
#   • Autorole
#   • Selfrole
#   • Reaction roles
#   • Tickets
#   • YouTube Alerts
#   • Giveaways
#   • Leveling configuration
#   • Level rewards
#   • XP boosters
#   • Automation / AutoMode
#   • AntiNuke
#   • Security
#   • Snipe
#   • Custom Commands
#   • Automations
#
# PostgreSQL / asyncpg
# ============================================================

import os
import json
import asyncio
import time
from urllib.parse import urlparse
from functools import wraps

import asyncpg
import discord
from discord.ext import commands


DATABASE_URL = os.getenv("DATABASE_URL")
_pool = None


# ============================================================
# HELPERS
# ============================================================

async def db_execute(query, *args):
    if not _pool:
        return None

    try:
        return await _pool.execute(query, *args)
    except Exception as exc:
        print(f"❌ DB execute error: {type(exc).__name__}: {exc}")
        return None


async def db_fetch(query, *args):
    if not _pool:
        return []

    try:
        return await _pool.fetch(query, *args)
    except Exception as exc:
        print(f"❌ DB fetch error: {type(exc).__name__}: {exc}")
        return []


async def db_fetchrow(query, *args):
    if not _pool:
        return None

    try:
        return await _pool.fetchrow(query, *args)
    except Exception as exc:
        print(f"❌ DB fetchrow error: {type(exc).__name__}: {exc}")
        return None


async def db_fetchval(query, *args):
    if not _pool:
        return None

    try:
        return await _pool.fetchval(query, *args)
    except Exception as exc:
        print(f"❌ DB fetchval error: {type(exc).__name__}: {exc}")
        return None


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

async def init_db():
    global _pool

    if _pool:
        return True

    if not DATABASE_URL:
        print("⚠️ DATABASE_URL is not set; database features are disabled.")
        return False

    parsed = urlparse(DATABASE_URL)
    host = (parsed.hostname or "").lower()

    if host.startswith("db.") and host.endswith(".supabase.co"):
        print(
            "❌ Supabase direct database URL detected. "
            "Use the Session Pooler connection string."
        )
        return False

    for attempt in range(1, 4):
        try:
            _pool = await asyncpg.create_pool(
                DATABASE_URL,
                min_size=1,
                max_size=8,
                command_timeout=30,
                timeout=15,
            )

            async with _pool.acquire() as conn:

                # ====================================================
                # CORE PLAYER SYSTEM
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS players(
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        coins BIGINT DEFAULT 100,
                        xp BIGINT DEFAULT 0,
                        level INT DEFAULT 1,
                        total_messages BIGINT DEFAULT 0,
                        last_xp_at TIMESTAMPTZ,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        updated_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY(guild_id, user_id)
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
                        session_id BIGINT REFERENCES game_sessions(id)
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
                """)

                # ====================================================
                # GUILD SETTINGS
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS guild_settings(
                        guild_id BIGINT PRIMARY KEY,
                        prefix TEXT NOT NULL DEFAULT ',',
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

                # ====================================================
                # WARNINGS
                # ====================================================

                await conn.execute("""
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

                # ====================================================
                # COMMAND LOGS
                # ====================================================

                await conn.execute("""
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
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_guild_logs
                        ON command_logs(guild_id);

                    CREATE INDEX IF NOT EXISTS idx_user_logs
                        ON command_logs(user_id);

                    CREATE INDEX IF NOT EXISTS idx_command_logs
                        ON command_logs(command_name);

                    CREATE INDEX IF NOT EXISTS idx_created_at
                        ON command_logs(created_at);
                """)

                # ====================================================
                # WELCOME / AUTOROLE
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS welcome_config(
                        guild_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        channel_id BIGINT,
                        message TEXT,
                        embed_enabled BOOLEAN DEFAULT TRUE,
                        embed_title TEXT,
                        embed_description TEXT,
                        embed_color BIGINT DEFAULT 5793266,
                        image_url TEXT,
                        thumbnail_url TEXT,
                        footer TEXT,
                        dm_enabled BOOLEAN DEFAULT FALSE,
                        dm_message TEXT,
                        autorole_id BIGINT,
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

                # ====================================================
                # SELFROLE / REACTION ROLE
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS selfrole_panels(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        message_id BIGINT,
                        title TEXT,
                        description TEXT,
                        panel_type TEXT DEFAULT 'button',
                        data JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS selfrole_entries(
                        id BIGSERIAL PRIMARY KEY,
                        panel_id BIGINT REFERENCES selfrole_panels(id)
                            ON DELETE CASCADE,
                        guild_id BIGINT NOT NULL,
                        role_id BIGINT NOT NULL,
                        label TEXT,
                        emoji TEXT,
                        description TEXT,
                        custom_id TEXT,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_selfrole_guild
                        ON selfrole_panels(guild_id);

                    CREATE INDEX IF NOT EXISTS idx_selfrole_entries_panel
                        ON selfrole_entries(panel_id);
                """)

                # ====================================================
                # TICKETS
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS ticket_config(
                        guild_id BIGINT PRIMARY KEY,
                        support_role_id BIGINT,
                        log_channel_id BIGINT,
                        ticket_category_id BIGINT,
                        transcript_enabled BOOLEAN DEFAULT TRUE,
                        naming_format TEXT DEFAULT 'ticket-{username}',
                        panel_channel_id BIGINT,
                        panel_message_id BIGINT,
                        enabled BOOLEAN DEFAULT TRUE,
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS ticket_categories(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        category_key TEXT NOT NULL,
                        name TEXT NOT NULL,
                        emoji TEXT,
                        description TEXT,
                        support_role_id BIGINT,
                        channel_category_id BIGINT,
                        enabled BOOLEAN DEFAULT TRUE,
                        data JSONB DEFAULT '{}'::jsonb,
                        UNIQUE(guild_id, category_key)
                    );

                    CREATE TABLE IF NOT EXISTS tickets(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        user_id BIGINT NOT NULL,
                        category_key TEXT,
                        claimed_by BIGINT,
                        status TEXT DEFAULT 'open',
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        closed_at TIMESTAMPTZ,
                        data JSONB DEFAULT '{}'::jsonb
                    );

                    CREATE INDEX IF NOT EXISTS idx_tickets_guild
                        ON tickets(guild_id);

                    CREATE INDEX IF NOT EXISTS idx_tickets_user
                        ON tickets(guild_id,user_id);

                    CREATE INDEX IF NOT EXISTS idx_tickets_channel
                        ON tickets(channel_id);
                """)

                # ====================================================
                # YOUTUBE ALERTS
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS youtube_config(
                        guild_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        alert_channel_id BIGINT,
                        role_id BIGINT,
                        message_template TEXT,
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS youtube_channels(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_key TEXT NOT NULL,
                        channel_name TEXT,
                        channel_url TEXT,
                        channel_id TEXT,
                        last_video_id TEXT,
                        enabled BOOLEAN DEFAULT TRUE,
                        data JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        UNIQUE(guild_id,channel_key)
                    );

                    CREATE INDEX IF NOT EXISTS idx_youtube_guild
                        ON youtube_channels(guild_id);
                """)

                # ====================================================
                # GIVEAWAYS
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS giveaways(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT,
                        message_id BIGINT,
                        host_id BIGINT,
                        prize TEXT NOT NULL,
                        winner_count INT DEFAULT 1,
                        ends_at TIMESTAMPTZ,
                        status TEXT DEFAULT 'active',
                        winners JSONB DEFAULT '[]'::jsonb,
                        requirements JSONB DEFAULT '{}'::jsonb,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS giveaway_entries(
                        giveaway_id BIGINT REFERENCES giveaways(id)
                            ON DELETE CASCADE,
                        user_id BIGINT NOT NULL,
                        joined_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY(giveaway_id,user_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_giveaway_guild
                        ON giveaways(guild_id);
                """)

                # ====================================================
                # LEVELING CONFIG
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS leveling_config(
                        guild_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT TRUE,
                        xp_min INT DEFAULT 15,
                        xp_max INT DEFAULT 30,
                        cooldown_seconds INT DEFAULT 60,
                        levelup_channel_id BIGINT,
                        levelup_message TEXT,
                        announce_levelup BOOLEAN DEFAULT TRUE,
                        stack_rewards BOOLEAN DEFAULT FALSE,
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS level_rewards(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        level INT NOT NULL,
                        role_id BIGINT NOT NULL,
                        remove_previous BOOLEAN DEFAULT FALSE,
                        data JSONB DEFAULT '{}'::jsonb,
                        UNIQUE(guild_id,level,role_id)
                    );

                    CREATE TABLE IF NOT EXISTS xp_boosters(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id BIGINT NOT NULL,
                        multiplier DOUBLE PRECISION DEFAULT 1.0,
                        enabled BOOLEAN DEFAULT TRUE,
                        data JSONB DEFAULT '{}'::jsonb,
                        UNIQUE(guild_id,target_type,target_id)
                    );

                    CREATE TABLE IF NOT EXISTS leveling_seasons(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        name TEXT NOT NULL,
                        started_at TIMESTAMPTZ DEFAULT NOW(),
                        ended_at TIMESTAMPTZ,
                        active BOOLEAN DEFAULT TRUE,
                        data JSONB DEFAULT '{}'::jsonb
                    );

                    CREATE TABLE IF NOT EXISTS leveling_quests(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        user_id BIGINT NOT NULL,
                        quest_key TEXT NOT NULL,
                        progress INT DEFAULT 0,
                        target INT DEFAULT 1,
                        reward_xp BIGINT DEFAULT 0,
                        reward_coins BIGINT DEFAULT 0,
                        completed BOOLEAN DEFAULT FALSE,
                        expires_at TIMESTAMPTZ,
                        data JSONB DEFAULT '{}'::jsonb
                    );
                """)

                # ====================================================
                # AUTOMATION / AUTOMODE
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS automation_config(
                        guild_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        log_channel_id BIGINT,
                        spam_enabled BOOLEAN DEFAULT TRUE,
                        spam_limit INT DEFAULT 5,
                        spam_window_seconds INT DEFAULT 7,
                        warning_limit INT DEFAULT 3,
                        timeout_limit INT DEFAULT 5,
                        timeout_minutes INT DEFAULT 10,
                        mention_limit INT DEFAULT 5,
                        duplicate_limit INT DEFAULT 3,
                        link_protection BOOLEAN DEFAULT TRUE,
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS automation_whitelist(
                        guild_id BIGINT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id BIGINT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY(guild_id,target_type,target_id)
                    );

                    CREATE TABLE IF NOT EXISTS automations(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        name TEXT NOT NULL,
                        trigger_type TEXT NOT NULL,
                        trigger_data JSONB DEFAULT '{}'::jsonb,
                        action_data JSONB DEFAULT '{}'::jsonb,
                        enabled BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT NOW()
                    );
                """)

                # ====================================================
                # ANTINUKE / SECURITY
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS antinuke_config(
                        guild_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        log_channel_id BIGINT,
                        punishment TEXT DEFAULT 'ban',
                        extra_owners JSONB DEFAULT '[]'::jsonb,
                        whitelist JSONB DEFAULT '[]'::jsonb,
                        thresholds JSONB DEFAULT '{}'::jsonb,
                        animation_enabled BOOLEAN DEFAULT FALSE,
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS security_config(
                        guild_id BIGINT PRIMARY KEY,
                        enabled BOOLEAN DEFAULT FALSE,
                        log_channel_id BIGINT,
                        anti_link BOOLEAN DEFAULT FALSE,
                        anti_invite BOOLEAN DEFAULT FALSE,
                        anti_gif BOOLEAN DEFAULT FALSE,
                        anti_youtube BOOLEAN DEFAULT FALSE,
                        anti_mass_mention BOOLEAN DEFAULT FALSE,
                        punishment TEXT DEFAULT 'delete',
                        data JSONB DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS security_whitelist(
                        guild_id BIGINT NOT NULL,
                        target_type TEXT NOT NULL,
                        target_id BIGINT NOT NULL,
                        created_at TIMESTAMPTZ DEFAULT NOW(),
                        PRIMARY KEY(guild_id,target_type,target_id)
                    );
                """)

                # ====================================================
                # SNIPE
                # ====================================================

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS snipe_messages(
                        id BIGSERIAL PRIMARY KEY,
                        guild_id BIGINT NOT NULL,
                        channel_id BIGINT NOT NULL,
                        message_id BIGINT,
                        author_id BIGINT,
                        author_name TEXT,
                        content TEXT,
                        attachments JSONB DEFAULT '[]'::jsonb,
                        deleted_at TIMESTAMPTZ DEFAULT NOW()
```
