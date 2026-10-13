import json
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
import db

def _load_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}

def _enabled(value):
    return "ON" if value else "OFF / not configured"

async def _status_embed(bot, guild):
    gid = str(guild.id)
    db_status = await db.database_status()
    ai_channel = None
    if getattr(db, "_pool", None):
        try:
            value = await db._pool.fetchval("SELECT data->>'ai_channel_id' FROM guild_settings WHERE guild_id=$1", guild.id)
            ai_channel = int(value) if value else None
        except Exception:
            pass

    welcome = _load_json("welcome_config.json").get(gid, {})
    youtube = _load_json("data/youtube_alerts.json").get("guilds", {}).get(gid, {})
    ticket = _load_json("data/tickets.json").get(gid, {})
    level = _load_json("airleveling_data.json").get(gid, {})
    automode = _load_json("automode_config.json").get(gid, {})
    antinuke = _load_json("antinuke_config.json").get(gid, {})
    antilink = _load_json("antilink_config.json").get(gid, {})
    autoresponder = _load_json("data/autoresponder.json").get("guilds", {}).get(gid, {})
    modlog = _load_json("data/modlog.json").get(gid, {})
    panel = ticket.get("panel", {})
    ticket_cfg = ticket.get("config", {})

    e = discord.Embed(
        title="Air Commander • Server Setup Dashboard",
        description=f"Configuration overview for {guild.name}.",
        colour=discord.Colour.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    e.add_field(name="PostgreSQL", value="CONNECTED" if db_status.get("connected") else "DISCONNECTED", inline=True)
    e.add_field(name="Feature modules", value=f"{len(getattr(bot, '_air_loaded_feature_modules', set()))} loaded", inline=True)
    e.add_field(name="Slash roots", value=str(len(bot.tree.get_commands())), inline=True)
    e.add_field(name="AI channel", value=f"<#{ai_channel}>" if ai_channel else "Not configured / DB unavailable", inline=True)
    e.add_field(name="Welcome", value=f"<#{welcome.get('channel_id')}>" if welcome.get("channel_id") else "Not configured", inline=True)
    e.add_field(name="Self-role panels", value=str(len(welcome.get("selfroles", {}))), inline=True)
    yt_status = "Enabled" if youtube.get("enabled", False) else "Disabled / not configured"
    yt_channel = f"<#{youtube.get('default_channel')}>" if youtube.get("default_channel") else "not set"
    e.add_field(name="YouTube alerts", value=f"{yt_status}; tracked: {len(youtube.get('channels', {}))}; alert channel: {yt_channel}", inline=False)
    e.add_field(name="Tickets", value=f"Panel: {'set' if panel.get('channel_id') else 'not set'}; categories: {len(ticket.get('categories', {}))}; log channel: {'set' if ticket_cfg.get('log_channel_id') else 'not set'}", inline=False)
    e.add_field(name="Leveling", value=f"{_enabled(level.get('enabled', False))}; XP/message: {level.get('xp_per_message', 'default')}", inline=True)
    e.add_field(name="AutoMode / AntiNuke / AntiLink", value=f"AutoMode: {_enabled(automode.get('enabled', False))}\nAntiNuke: {_enabled(antinuke.get('enabled', False))}\nAntiLink: {_enabled(antilink.get('enabled', False))}", inline=True)
    e.add_field(name="Autoresponder / Modlog", value=f"Autoresponder: {_enabled(autoresponder.get('enabled', False))}; rules: {len(autoresponder.get('rules', {}))}\nModlog channel: <#{modlog.get('channel_id')}>" if modlog.get("channel_id") else f"Autoresponder: {_enabled(autoresponder.get('enabled', False))}; rules: {len(autoresponder.get('rules', {}))}\nModlog: not configured", inline=False)
    e.add_field(name="Persistence", value="JSON-backed settings survive redeploy only when PostgreSQL snapshot restore is working. The owner can run /backup create and save the ZIP outside Render.", inline=False)
    e.set_footer(text="Air Commander • Config Status")
    return e

def setup(bot):
    group = app_commands.Group(name="config", description="Air Commander server configuration dashboard")
    @group.command(name="status", description="Show setup status for this server")
    async def config_status(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        await interaction.response.send_message(embed=await _status_embed(bot, interaction.guild), ephemeral=True)

    @bot.group(name="config", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_config(ctx):
        await ctx.send(embed=await _status_embed(bot, ctx.guild))
    @prefix_config.command(name="status")
    async def prefix_config_status(ctx):
        await ctx.send(embed=await _status_embed(bot, ctx.guild))

    existing = bot.tree.get_command("config")
    if existing is None:
        bot.tree.add_command(group)
    elif isinstance(existing, app_commands.Group):
        for child in group.commands:
            if existing.get_command(child.name) is None:
                existing.add_command(child)
    print("Config dashboard registered.", flush=True)
