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
