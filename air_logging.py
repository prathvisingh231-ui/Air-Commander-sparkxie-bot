"""
Air Commander - Unified Logging & Configuration
-----------------------------------------------
Adds configurable log channels for:
- Message logs
- Moderation logs
- Anti-nuke logs
- AutoMod logs
- Anti-link logs
- Member logs
- Role logs
- Channel logs
- Server/security logs
- Ticket logs

Integration:
    import air_logging
    air_logging.setup(bot)

Commands:
    /logs setup
    /logs set <type> <channel>
    /logs remove <type>
    /logs view
    /logs test
    /logs all <channel>
    Prefix:
    ,logs ...
"""

from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands


LOG_TYPES = (
    "message",
    "moderation",
    "antinuke",
    "automod",
    "antilink",
    "member",
    "role",
    "channel",
    "server",
    "ticket",
)

# Temporary storage; replace these helpers with your db.py later.
_LOG_CHANNELS: dict[int, dict[str, int]] = defaultdict(dict)
_DELETED_MESSAGES: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))


def _cfg(guild_id: int) -> dict[str, int]:
    return _LOG_CHANNELS[guild_id]


def _channel(guild: discord.Guild, kind: str):
    cid = _cfg(guild.id).get(kind)
    return guild.get_channel(cid) if cid else None


async def send_log(guild: discord.Guild, kind: str, title: str, description: str,
                   color: discord.Color | None = None, **fields):
    """Public helper. Other modules can call:
       await bot._air_log(guild, "moderation", "Ban", "...")
    """
    if kind not in LOG_TYPES:
        kind = "server"
    channel = _channel(guild, kind)
    if not isinstance(channel, discord.TextChannel):
        return False

    embed = discord.Embed(
        title=f"✈️ {title}",
        description=description[:4096],
        color=color or discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc),
    )
    for name, value in fields.items():
        embed.add_field(name=str(name)[:256], value=str(value)[:1024], inline=True)
    embed.set_footer(text=f"Air Commander • {kind.title()} Logs")
    try:
        await channel.send(embed=embed)
        return True
    except discord.HTTPException:
        return False


class LoggingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot._air_log = send_log

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.guild and not message.author.bot:
            _DELETED_MESSAGES[(message.guild.id, message.channel.id)].append({
                "author": message.author,
                "content": message.content,
                "created_at": message.created_at,
                "attachments": [a.url for a in message.attachments],
            })

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        content = message.content or "*No text content*"
        await send_log(
            message.guild, "message", "🗑️ Message Deleted",
            f"**Author:** {message.author.mention}\n**Channel:** {message.channel.mention}\n\n{content}",
            discord.Color.red(),
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        await send_log(
            before.guild, "message", "✏️ Message Edited",
            f"**Author:** {before.author.mention}\n**Channel:** {before.channel.mention}",
            discord.Color.orange(),
            Before=before.content or "*empty*",
            After=after.content or "*empty*",
        )

    @commands.Cog.listener()
    async def on_member_join(self, member):
        await send_log(
            member.guild, "member", "📥 Member Joined",
            f"{member.mention} joined the server.",
            discord.Color.green(), User=str(member), ID=member.id,
        )

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        await send_log(
            member.guild, "member", "📤 Member Left",
            f"**User:** {member.mention}\n**ID:** `{member.id}`",
            discord.Color.orange(),
        )

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await send_log(role.guild, "role", "🎭 Role Created", f"Created {role.mention} (`{role.id}`).")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await send_log(role.guild, "role", "🗑️ Role Deleted", f"Deleted **{role.name}** (`{role.id}`).", discord.Color.red())

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await send_log(channel.guild, "channel", "📁 Channel Created", f"Created **{channel.name}** (`{channel.id}`).", discord.Color.green())

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await send_log(channel.guild, "channel", "🗑️ Channel Deleted", f"Deleted **{channel.name}** (`{channel.id}`).", discord.Color.red())

    # ---------------- slash /logs ----------------

    logs = app_commands.Group(name="logs", description="Configure Air Commander logging channels")

    @logs.command(name="set", description="Set one logging category to a channel")
    @app_commands.describe(kind="Logging category", channel="Destination channel")
    @app_commands.choices(kind=[app_commands.Choice(name=x.title(), value=x) for x in LOG_TYPES])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_set(self, interaction, kind: app_commands.Choice[str], channel: discord.TextChannel):
        _cfg(interaction.guild.id)[kind.value] = channel.id
        await interaction.response.send_message(
            f"✅ **{kind.name} logs** will now be sent to {channel.mention}.", ephemeral=True
        )

    @logs.command(name="remove", description="Disable a logging category")
    @app_commands.describe(kind="Logging category")
    @app_commands.choices(kind=[app_commands.Choice(name=x.title(), value=x) for x in LOG_TYPES])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_remove(self, interaction, kind: app_commands.Choice[str]):
        _cfg(interaction.guild.id).pop(kind.value, None)
        await interaction.response.send_message(f"✅ {kind.name} logging disabled.", ephemeral=True)

    @logs.command(name="all", description="Send all supported logs to one channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_all(self, interaction, channel: discord.TextChannel):
        _cfg(interaction.guild.id).update({x: channel.id for x in LOG_TYPES})
        await interaction.response.send_message(
            f"✅ All Air Commander log categories now use {channel.mention}.", ephemeral=True
        )

    @logs.command(name="view", description="View configured logging channels")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_view(self, interaction):
        lines = []
        for kind in LOG_TYPES:
            ch = _channel(interaction.guild, kind)
            lines.append(f"**{kind.title()}** → {ch.mention if ch else 'Not configured'}")
        e = discord.Embed(title="📋 Air Commander • Logging Configuration",
                          description="\n".join(lines), color=discord.Color.blurple())
        await interaction.response.send_message(embed=e, ephemeral=True)

    @logs.command(name="test", description="Test one logging category")
    @app_commands.choices(kind=[app_commands.Choice(name=x.title(), value=x) for x in LOG_TYPES])
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_test(self, interaction, kind: app_commands.Choice[str]):
        ok = await send_log(interaction.guild, kind.value, "🧪 Log Test",
                            f"This is a test for **{kind.name} logs**.\nTriggered by {interaction.user.mention}.",
                            discord.Color.blurple())
        await interaction.response.send_message(
            "✅ Test sent." if ok else "❌ That log category has no valid configured channel.",
            ephemeral=True,
        )

    # Prefix compatibility
    @commands.group(name="logs", invoke_without_command=True)
    @commands.has_guild_permissions(manage_guild=True)
    async def logs_prefix(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("📋 Use `,logs set <type> #channel`, `,logs all #channel`, `,logs view`, or `,logs test <type>`.")

    @logs_prefix.command(name="set")
    async def logs_p_set(self, ctx, kind: str, channel: discord.TextChannel):
        kind = kind.lower()
        if kind not in LOG_TYPES:
            return await ctx.send("❌ Invalid log type: " + ", ".join(LOG_TYPES))
        _cfg(ctx.guild.id)[kind] = channel.id
        await ctx.send(f"✅ {kind.title()} logs → {channel.mention}")

    @logs_prefix.command(name="remove")
    async def logs_p_remove(self, ctx, kind: str):
        _cfg(ctx.guild.id).pop(kind.lower(), None)
        await ctx.send(f"✅ {kind.title()} logs disabled.")

    @logs_prefix.command(name="all")
    async def logs_p_all(self, ctx, channel: discord.TextChannel):
        _cfg(ctx.guild.id).update({x: channel.id for x in LOG_TYPES})
        await ctx.send(f"✅ All logs → {channel.mention}")

    @logs_prefix.command(name="view")
    async def logs_p_view(self, ctx):
        lines = []
        for kind in LOG_TYPES:
            ch = _channel(ctx.guild, kind)
            lines.append(f"**{kind.title()}** → {ch.mention if ch else 'Not configured'}")
        await ctx.send(embed=discord.Embed(title="📋 Logging Configuration", description="\n".join(lines)))

    @logs_prefix.command(name="test")
    async def logs_p_test(self, ctx, kind: str):
        kind = kind.lower()
        if kind not in LOG_TYPES:
            return await ctx.send("❌ Invalid log type.")
        ok = await send_log(ctx.guild, kind, "🧪 Log Test", f"Triggered by {ctx.author.mention}")
        await ctx.send("✅ Test sent." if ok else "❌ Configure that log channel first.")


def setup(bot):
    bot.loop.create_task(bot.add_cog(LoggingCog(bot)))
