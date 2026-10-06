# ============================================================
# Air Commander — PRO GIVEAWAY SYSTEM
# Persistent PostgreSQL • Buttons • Winners • Reroll • Restart-safe
# ============================================================

import asyncio
import random
from datetime import timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks
import db


_SETUP_LOCK = asyncio.Lock()
_GIVEAWAY_TASK = None


def _embed(title, description="", color=discord.Color.blurple()):
    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    e.set_footer(text="Air Commander • Giveaway System")
    return e


async def _ensure_tables():
    if not db._pool:
        return False

    await db._pool.execute("""
        CREATE TABLE IF NOT EXISTS giveaways (
            giveaway_id BIGSERIAL PRIMARY KEY,
            guild_id BIGINT NOT NULL,
            channel_id BIGINT NOT NULL,
            message_id BIGINT UNIQUE,
            host_id BIGINT NOT NULL,
            prize TEXT NOT NULL,
            winners INT NOT NULL DEFAULT 1,
            ends_at TIMESTAMPTZ NOT NULL,
            ended BOOLEAN NOT NULL DEFAULT FALSE,
            winner_ids BIGINT[] NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    await db._pool.execute("""
        CREATE TABLE IF NOT EXISTS giveaway_entries (
            giveaway_id BIGINT NOT NULL REFERENCES giveaways(giveaway_id) ON DELETE CASCADE,
            user_id BIGINT NOT NULL,
            joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY(giveaway_id,user_id)
        )
    """)

    await db._pool.execute("""
        CREATE INDEX IF NOT EXISTS idx_giveaways_active
        ON giveaways(ended, ends_at)
    """)
    return True


def _duration(seconds: int) -> str:
    seconds = max(1, seconds)
    parts = []
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            value, seconds = divmod(seconds, size)
            parts.append(f"{value}{unit}")
        if len(parts) >= 2:
            break
    return " ".join(parts) or "1s"


async def _get_entries(giveaway_id: int):
    if not db._pool:
        return []
    rows = await db._pool.fetch(
        "SELECT user_id FROM giveaway_entries WHERE giveaway_id=$1",
        giveaway_id,
    )
    return [int(r["user_id"]) for r in rows]


async def _choose_winners(giveaway_id: int, count: int):
    entries = await _get_entries(giveaway_id)
    if not entries:
        return []
    return random.sample(entries, min(max(1, count), len(entries)))


async def _end_giveaway(bot, giveaway_id: int, reroll=False):
    if not db._pool:
        return False

    row = await db._pool.fetchrow(
        "SELECT * FROM giveaways WHERE giveaway_id=$1",
        giveaway_id,
    )
    if not row:
        return False

    if row["ended"] and not reroll:
        return False

    winners = await _choose_winners(giveaway_id, int(row["winners"]))
    if not reroll:
        await db._pool.execute(
            """UPDATE giveaways SET ended=TRUE,winner_ids=$2
               WHERE giveaway_id=$1""",
            giveaway_id,
            winners,
        )

    channel = bot.get_channel(row["channel_id"])
    if not isinstance(channel, discord.TextChannel):
        return True

    try:
        message = await channel.fetch_message(row["message_id"])
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        message = None

    mentions = ", ".join(f"<@{uid}>" for uid in winners) if winners else "No valid entries."

    e = _embed(
        "🎉 Giveaway Ended" if not reroll else "🎲 Giveaway Reroll",
        f"**Prize:** {row['prize']}\n"
        f"**Winners:** {mentions}\n"
        f"**Entries:** {len(await _get_entries(giveaway_id))}",
        discord.Color.green() if winners else discord.Color.red(),
    )

    if message:
        try:
            await message.edit(view=None)
        except (discord.HTTPException, discord.Forbidden):
            pass

    await channel.send(
        content=mentions if winners else None,
        embed=e,
        allowed_mentions=discord.AllowedMentions(users=True),
    )
    return True


class GiveawayView(discord.ui.View):
    def __init__(self, giveaway_id: int, ended=False):
        super().__init__(timeout=None)
        self.giveaway_id = giveaway_id

        button = discord.ui.Button(
            label="🎉 Enter Giveaway",
            style=discord.ButtonStyle.success,
            custom_id=f"air:gaw:enter:{giveaway_id}",
            disabled=ended,
        )
        button.callback = self.enter
        self.add_item(button)

    async def enter(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Server only.", ephemeral=True)
        if not db._pool:
            return await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)

        row = await db._pool.fetchrow(
            "SELECT ended,ends_at,prize FROM giveaways WHERE giveaway_id=$1",
            self.giveaway_id,
        )
        if not row or row["ended"] or row["ends_at"] <= discord.utils.utcnow():
            return await interaction.response.send_message("❌ This giveaway has ended.", ephemeral=True)

        result = await db._pool.execute(
            """INSERT INTO giveaway_entries(giveaway_id,user_id)
               VALUES($1,$2) ON CONFLICT DO NOTHING""",
            self.giveaway_id,
            interaction.user.id,
        )

        if result == "INSERT 0 0":
            return await interaction.response.send_message(
                "ℹ️ You are already entered in this giveaway.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"🎉 You entered **{row['prize']}**. Good luck!",
            ephemeral=True,
        )


class GiveawayGroup(app_commands.Group):
    def __init__(self, bot):
        super().__init__(name="giveaway", description="Manage persistent giveaways")
        self.bot = bot

    @app_commands.command(name="create", description="Create a giveaway")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.describe(
        prize="What users can win",
        duration="Duration such as 10m, 2h, 1d",
        winners="Number of winners",
        channel="Where to post the giveaway",
    )
    async def create(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration: str,
        winners: app_commands.Range[int, 1, 20] = 1,
        channel: discord.TextChannel | None = None,
    ):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Server only.", ephemeral=True)

        seconds = self._parse_duration(duration)
        if seconds is None:
            return await interaction.response.send_message(
                "❌ Invalid duration. Use examples: `10m`, `2h`, `1d`.",
                ephemeral=True,
            )

        target = channel or interaction.channel
        if not isinstance(target, discord.TextChannel):
            return await interaction.response.send_message("❌ Invalid channel.", ephemeral=True)

        ends_at = discord.utils.utcnow() + timedelta(seconds=seconds)

        if not db._pool:
            return await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)

        giveaway_id = await db._pool.fetchval(
            """INSERT INTO giveaways
               (guild_id,channel_id,host_id,prize,winners,ends_at)
               VALUES($1,$2,$3,$4,$5,$6)
               RETURNING giveaway_id""",
            interaction.guild.id,
            target.id,
            interaction.user.id,
            prize[:500],
            winners,
            ends_at,
        )

        e = _embed(
            "🎉 GIVEAWAY",
            f"### {prize[:500]}\n\n"
            f"🏆 **Winners:** {winners}\n"
            f"⏰ **Ends:** {discord.utils.format_dt(ends_at, 'R')}\n"
            f"👤 **Hosted by:** {interaction.user.mention}\n\n"
            f"Click **Enter Giveaway** below to participate!",
            discord.Color.gold(),
        )
        e.add_field(name="Giveaway ID", value=f"`{giveaway_id}`", inline=True)
        e.set_footer(text="Air Commander • Giveaway System • Persistent")

        await interaction.response.send_message(
            f"✅ Giveaway created in {target.mention}.",
            ephemeral=True,
        )

        try:
            message = await target.send(embed=e, view=GiveawayView(giveaway_id))
            await db._pool.execute(
                "UPDATE giveaways SET message_id=$2 WHERE giveaway_id=$1",
                giveaway_id,
                message.id,
            )
        except discord.HTTPException:
            await db._pool.execute(
                "DELETE FROM giveaways WHERE giveaway_id=$1",
                giveaway_id,
            )
            await interaction.followup.send(
                "❌ I could not post the giveaway. Check Send Messages and Embed Links.",
                ephemeral=True,
            )

    @app_commands.command(name="end", description="End a giveaway immediately")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def end(self, interaction: discord.Interaction, giveaway_id: int):
        if not await _end_giveaway(self.bot, giveaway_id):
            return await interaction.response.send_message(
                "❌ Giveaway not found or already ended.",
                ephemeral=True,
            )
        await interaction.response.send_message("✅ Giveaway ended.", ephemeral=True)

    @app_commands.command(name="reroll", description="Reroll winners")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def reroll(self, interaction: discord.Interaction, giveaway_id: int):
        if not db._pool:
            return await interaction.response.send_message("❌ Database unavailable.", ephemeral=True)
        row = await db._pool.fetchrow(
            "SELECT ended FROM giveaways WHERE giveaway_id=$1",
            giveaway_id,
        )
        if not row or not row["ended"]:
            return await interaction.response.send_message(
                "❌ That giveaway has not ended yet.",
                ephemeral=True,
            )
        await _end_giveaway(self.bot, giveaway_id, reroll=True)
        await interaction.response.send_message("🎲 Winner rerolled.", ephemeral=True)

    @app_commands.command(name="list", description="List active giveaways")
    async def list(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Server only.", ephemeral=True)
        rows = await db._pool.fetch(
            """SELECT giveaway_id,channel_id,prize,winners,ends_at
               FROM giveaways WHERE guild_id=$1 AND ended=FALSE
               ORDER BY ends_at ASC LIMIT 20""",
            interaction.guild.id,
        ) if db._pool else []

        if not rows:
            return await interaction.response.send_message(
                embed=_embed("Active Giveaways", "No active giveaways."),
                ephemeral=True,
            )

        lines = [
            f"`#{r['giveaway_id']}` **{r['prize'][:80]}** • "
            f"{r['winners']} winner(s) • {discord.utils.format_dt(r['ends_at'], 'R')}"
            for r in rows
        ]
        await interaction.response.send_message(
            embed=_embed("🎉 Active Giveaways", "\n".join(lines))
        )

    @staticmethod
    def _parse_duration(value):
        value = value.strip().lower()
        if not value or len(value) > 10:
            return None
        try:
            number = int(value[:-1])
            unit = value[-1]
            multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}[unit]
            seconds = number * multiplier
            if seconds < 10 or seconds > 365 * 86400:
                return None
            return seconds
        except (ValueError, KeyError):
            return None


async def _giveaway_worker(bot):
    await bot.wait_until_ready()
    while not bot.is_closed():
        try:
            if db._pool:
                rows = await db._pool.fetch(
                    """SELECT giveaway_id FROM giveaways
                       WHERE ended=FALSE AND ends_at <= NOW()
                       ORDER BY ends_at ASC LIMIT 25"""
                )
                for row in rows:
                    try:
                        await _end_giveaway(bot, int(row["giveaway_id"]))
                    except Exception as exc:
                        print(f"❌ Giveaway #{row['giveaway_id']} end error: {type(exc).__name__}: {exc}")
        except Exception as exc:
            print(f"⚠️ Giveaway worker error: {type(exc).__name__}: {exc}")
        await asyncio.sleep(10)


async def setup(bot):
    global _GIVEAWAY_TASK

    async with _SETUP_LOCK:
        if getattr(bot, "_air_giveaways_setup", False):
            return
        if not db._pool:
            print("⚠️ giveaways: database unavailable; setup skipped.")
            return

        await _ensure_tables()

        if not getattr(bot, "_air_giveaway_slash", False):
            group = GiveawayGroup(bot)
            bot.tree.add_command(group)
            bot._air_giveaway_slash = True

        # Restore persistent views for active giveaways.
        rows = await db._pool.fetch(
            "SELECT giveaway_id,message_id,ended FROM giveaways WHERE ended=FALSE AND message_id IS NOT NULL"
        )
        for row in rows:
            try:
                bot.add_view(GiveawayView(int(row["giveaway_id"]), bool(row["ended"])))
            except Exception:
                pass

        if _GIVEAWAY_TASK is None or _GIVEAWAY_TASK.done():
            _GIVEAWAY_TASK = asyncio.create_task(_giveaway_worker(bot))

        bot._air_giveaways_setup = True
        print("🎉 giveaways: persistent giveaway system ready.")
