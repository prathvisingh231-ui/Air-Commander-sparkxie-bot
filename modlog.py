import json
from pathlib import Path
from datetime import datetime, timezone
import discord
from discord import app_commands
from discord.ext import commands

DATA_FILE = Path("data/modlog.json")
DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
RECENT = {}

def _load():
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def _save(data):
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(DATA_FILE)

def _record(guild_id, text):
    entries = RECENT.setdefault(str(guild_id), [])
    entries.append({"at": datetime.now(timezone.utc).isoformat(), "text": text[:1500]})
    del entries[:-25]

async def _send_log(bot, guild, text):
    _record(guild.id, text)
    cfg = _load().get(str(guild.id), {})
    channel_id = cfg.get("channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await bot.fetch_channel(int(channel_id))
        except Exception:
            return
    embed = discord.Embed(description=text[:4000], colour=discord.Colour.orange(), timestamp=discord.utils.utcnow())
    embed.set_footer(text="Air Commander • Moderation Log")
    try:
        await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
    except discord.HTTPException as exc:
        print(f"[Modlog] Send failed: {type(exc).__name__}: {exc}", flush=True)

def setup(bot):
    group = app_commands.Group(name="modlog", description="Configure moderation event logs")
    @group.command(name="setup", description="Set the moderation log channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_setup(interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        data = _load()
        data[str(interaction.guild.id)] = {"channel_id": channel.id}
        _save(data)
        await interaction.response.send_message(f"Moderation logs will be sent to {channel.mention}.", ephemeral=True)

    @group.command(name="status", description="Show the current moderation log channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_status(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        channel_id = _load().get(str(interaction.guild.id), {}).get("channel_id")
        channel = interaction.guild.get_channel(int(channel_id)) if channel_id else None
        await interaction.response.send_message(f"Moderation log channel: {channel.mention if channel else 'Not configured'}", ephemeral=True)

    @group.command(name="recent", description="Show recent moderation events observed by this bot")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def modlog_recent(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        entries = RECENT.get(str(interaction.guild.id), [])
        text = "\n".join(f"• {item['at'][:19]} — {item['text']}" for item in entries[-10:])
        await interaction.response.send_message(text[:1900] or "No moderation events observed since this process started.", ephemeral=True)

    @bot.group(name="modlog", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_modlog(ctx):
        if not ctx.author.guild_permissions.manage_guild:
            return await ctx.send("Manage Server permission required.")
        channel_id = _load().get(str(ctx.guild.id), {}).get("channel_id")
        channel = ctx.guild.get_channel(int(channel_id)) if channel_id else None
        await ctx.send(f"Moderation log channel: {channel.mention if channel else 'Not configured'}. Use ,modlog setup #channel.")

    @prefix_modlog.command(name="setup")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_modlog_setup(ctx, channel: discord.TextChannel):
        data = _load()
        data[str(ctx.guild.id)] = {"channel_id": channel.id}
        _save(data)
        await ctx.send(f"Moderation logs will be sent to {channel.mention}.")
    @prefix_modlog.command(name="recent")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_modlog_recent(ctx):
        entries = RECENT.get(str(ctx.guild.id), [])
        text = "\n".join(f"• {item['at'][:19]} — {item['text']}" for item in entries[-10:])
        await ctx.send(text[:1900] or "No moderation events observed since this process started.")

    async def on_ban(guild, user):
        await _send_log(bot, guild, f"Member banned\nUser: {user} ({user.id})")
    async def on_unban(guild, user):
        await _send_log(bot, guild, f"Member unbanned\nUser: {user} ({user.id})")
    async def on_member_update(before, after):
        old = before.timed_out_until
        new = after.timed_out_until
        if old != new:
            action = "timeout applied" if new and new > discord.utils.utcnow() else "timeout removed/expired"
            await _send_log(bot, after.guild, f"Member timeout change\nUser: {after} ({after.id})\nAction: {action}")
    async def on_member_remove(member):
        try:
            async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.kick):
                if entry.target and entry.target.id == member.id and (discord.utils.utcnow() - entry.created_at).total_seconds() < 12:
                    await _send_log(bot, member.guild, f"Member kicked\nUser: {member} ({member.id})\nModerator: {entry.user}")
                    return
        except (discord.Forbidden, discord.HTTPException):
            pass

    bot.add_listener(on_ban, "on_member_ban")
    bot.add_listener(on_unban, "on_member_unban")
    bot.add_listener(on_member_update, "on_member_update")
    bot.add_listener(on_member_remove, "on_member_remove")

    existing = bot.tree.get_command("modlog")
    if existing is None:
        bot.tree.add_command(group)
    elif isinstance(existing, app_commands.Group):
        for child in group.commands:
            if existing.get_command(child.name) is None:
                existing.add_command(child)
    print("Moderation log registered.", flush=True)
