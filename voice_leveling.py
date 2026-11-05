import json
import math
import os
import time
import asyncio
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

DATA_FILE = Path("data/voice_leveling.json")
MAX_LEVEL = 200
DEFAULT_XP_PER_MINUTE = 10
ACTIVE = {}


def load_data():
    try:
        if DATA_FILE.exists():
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError) as exc:
        print(f"[VoiceLeveling] Load failed: {type(exc).__name__}: {exc}", flush=True)
    return {}


DATA = load_data()


def save_data():
    try:
        DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = DATA_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(DATA, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, DATA_FILE)
    except (OSError, TypeError, ValueError) as exc:
        print(f"[VoiceLeveling] Save failed: {type(exc).__name__}: {exc}", flush=True)


def level_for_xp(xp):
    return min(MAX_LEVEL, int(math.sqrt(max(0, int(xp)) / 100)))


def config(guild_id):
    value = DATA.setdefault(str(guild_id), {})
    value.setdefault("enabled", True)
    value.setdefault("xp_per_minute", DEFAULT_XP_PER_MINUTE)
    value.setdefault("announce_channel_id", None)
    value.setdefault("users", {})
    return value


def user_data(cfg, user_id):
    value = cfg["users"].setdefault(str(user_id), {"xp": 0, "minutes": 0, "level": 0})
    value.setdefault("xp", 0)
    value.setdefault("minutes", 0)
    value.setdefault("level", level_for_xp(value["xp"]))
    return value


async def award_minute(guild, member):
    cfg = config(guild.id)
    if not cfg["enabled"]:
        return
    user = user_data(cfg, member.id)
    old_level = level_for_xp(user["xp"])
    user["xp"] = int(user["xp"]) + max(1, min(100, int(cfg["xp_per_minute"])))
    user["minutes"] = int(user["minutes"]) + 1
    new_level = level_for_xp(user["xp"])
    user["level"] = new_level
    save_data()
    if new_level > old_level:
        channel_id = cfg.get("announce_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            embed = discord.Embed(
                title="🎙️ Voice Level Up!",
                description=f"Congratulations {member.mention}! You reached Voice Level **{new_level}**.",
                color=discord.Color.blurple(),
                timestamp=discord.utils.utcnow(),
            )
            embed.add_field(name="Voice XP", value=f"{user['xp']:,}", inline=True)
            embed.add_field(name="Voice time", value=f"{user['minutes']:,} minutes", inline=True)
            embed.set_footer(text="Air Commander • Voice Leveling")
            try:
                await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False))
            except discord.HTTPException as exc:
                print(f"[VoiceLeveling] Announcement failed: {type(exc).__name__}", flush=True)


def setup(bot: commands.Bot):
    if getattr(bot, "_air_voice_leveling_setup", False):
        return
    bot._air_voice_leveling_setup = True

    async def on_voice_state_update(member, before, after):
        if member.bot or member.guild is None:
            return
        key = (member.guild.id, member.id)
        if after.channel is None:
            ACTIVE.pop(key, None)
        elif before.channel is None or before.channel != after.channel:
            ACTIVE[key] = time.monotonic()

    bot.add_listener(on_voice_state_update, "on_voice_state_update")

    @tasks.loop(seconds=10)
    async def voice_tick():
        now = time.monotonic()
        for guild in list(bot.guilds):
            cfg = config(guild.id)
            if not cfg["enabled"]:
                continue
            for channel in guild.voice_channels:
                for member in channel.members:
                    if member.bot:
                        continue
                    key = (guild.id, member.id)
                    last = ACTIVE.setdefault(key, now)
                    if now - last >= 60:
                        ACTIVE[key] = now
                        try:
                            await award_minute(guild, member)
                        except Exception as exc:
                            print(f"[VoiceLeveling] XP award failed: {type(exc).__name__}: {exc}", flush=True)

    @voice_tick.before_loop
    async def before_voice_tick():
        await bot.wait_until_ready()

    voice_tick.start()

    group = app_commands.Group(name="voicelevel", description="Voice XP and leveling")

    @group.command(name="rank", description="View your or another member's voice rank")
    async def rank(interaction: discord.Interaction, member: discord.Member = None):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        target = member or interaction.user
        cfg = config(interaction.guild.id)
        user = user_data(cfg, target.id)
        level = level_for_xp(user["xp"])
        next_xp = (level + 1) ** 2 * 100
        embed = discord.Embed(title=f"🎙️ {target.display_name} • Voice Rank", color=discord.Color.blurple())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=str(level), inline=True)
        embed.add_field(name="Voice XP", value=f"{user['xp']:,} / {next_xp:,}", inline=True)
        embed.add_field(name="Voice time", value=f"{user['minutes']:,} minutes", inline=True)
        await interaction.response.send_message(embed=embed)

    @group.command(name="leaderboard", description="Top voice XP members")
    async def leaderboard(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        cfg = config(interaction.guild.id)
        ranked = sorted(cfg["users"].items(), key=lambda pair: int(pair[1].get("xp", 0)), reverse=True)[:10]
        rows = []
        for i, (uid, data) in enumerate(ranked, 1):
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            rows.append(f"**{i}.** {name} — Level {level_for_xp(data['xp'])} · {int(data['xp']):,} XP")
        embed = discord.Embed(title="🎙️ Voice Leaderboard", description="\n".join(rows) or "No voice XP earned yet.", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed)

    @group.command(name="enable", description="Enable voice leveling")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def enable(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        config(interaction.guild.id)["enabled"] = True
        save_data()
        await interaction.response.send_message("✅ Voice leveling enabled.", ephemeral=True)

    @group.command(name="disable", description="Disable voice leveling")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def disable(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        config(interaction.guild.id)["enabled"] = False
        save_data()
        await interaction.response.send_message("⏸️ Voice leveling disabled.", ephemeral=True)

    @group.command(name="channel", description="Set voice level-up announcement text channel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def channel(interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        config(interaction.guild.id)["announce_channel_id"] = channel.id
        save_data()
        await interaction.response.send_message(f"✅ Voice level-ups will be announced in {channel.mention}.", ephemeral=True)

    @group.command(name="xp", description="Set XP earned per voice minute")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def xp(interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        config(interaction.guild.id)["xp_per_minute"] = int(amount)
        save_data()
        await interaction.response.send_message(f"✅ Voice XP set to {amount} per minute.", ephemeral=True)

    @group.command(name="status", description="Show voice leveling settings")
    async def status(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        cfg = config(interaction.guild.id)
        ch_id = cfg.get("announce_channel_id")
        ch = interaction.guild.get_channel(int(ch_id)) if ch_id else None
        embed = discord.Embed(title="🎙️ Voice Leveling Status", color=discord.Color.blurple())
        embed.add_field(name="Status", value="Enabled" if cfg["enabled"] else "Disabled", inline=True)
        embed.add_field(name="XP/minute", value=str(cfg["xp_per_minute"]), inline=True)
        embed.add_field(name="Announcement channel", value=ch.mention if ch else "Not configured", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    if bot.tree.get_command("voicelevel") is None:
        bot.tree.add_command(group)
    else:
        existing = bot.tree.get_command("voicelevel")
        if isinstance(existing, app_commands.Group):
            for child in group.commands:
                if existing.get_command(child.name) is None:
                    existing.add_command(child)
        else:
            raise TypeError("A non-group slash command named voicelevel already exists")

    @bot.group(name="voicelevel", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_voicelevel(ctx):
        await ctx.send("🎙️ Voice Leveling: ,voicelevel rank [@member] · ,voicelevel leaderboard · ,voicelevel status\nAdmin: ,voicelevel enable/disable · ,voicelevel channel #channel · ,voicelevel xp 10")

    @prefix_voicelevel.command(name="rank")
    async def prefix_rank(ctx, member: discord.Member = None):
        target = member or ctx.author
        user = user_data(config(ctx.guild.id), target.id)
        await ctx.send(f"🎙️ **{target.display_name}** — Level {level_for_xp(user['xp'])} · {user['xp']:,} XP · {user['minutes']:,} minutes in VC")

    @prefix_voicelevel.command(name="leaderboard", aliases=["lb", "top"])
    async def prefix_leaderboard(ctx):
        ranked = sorted(config(ctx.guild.id)["users"].items(), key=lambda pair: int(pair[1].get("xp", 0)), reverse=True)[:10]
        rows = []
        for i, (uid, data) in enumerate(ranked, 1):
            member = ctx.guild.get_member(int(uid))
            rows.append(f"**{i}.** {member.display_name if member else uid} — Level {level_for_xp(data['xp'])} · {data['xp']:,} XP")
        await ctx.send("🎙️ **Voice Leaderboard**\n" + ("\n".join(rows) if rows else "No voice XP earned yet."))

    @prefix_voicelevel.command(name="status")
    async def prefix_status(ctx):
        cfg = config(ctx.guild.id)
        ch_id = cfg.get("announce_channel_id")
        ch = ctx.guild.get_channel(int(ch_id)) if ch_id else None
        await ctx.send(f"🎙️ Voice leveling: {'Enabled' if cfg['enabled'] else 'Disabled'} · XP/minute: {cfg['xp_per_minute']} · Announcement channel: {ch.mention if ch else 'Not configured'}")

    @prefix_voicelevel.command(name="enable")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_enable(ctx):
        config(ctx.guild.id)["enabled"] = True
        save_data()
        await ctx.send("✅ Voice leveling enabled.")

    @prefix_voicelevel.command(name="disable")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_disable(ctx):
        config(ctx.guild.id)["enabled"] = False
        save_data()
        await ctx.send("⏸️ Voice leveling disabled.")

    @prefix_voicelevel.command(name="channel")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_channel(ctx, channel: discord.TextChannel):
        config(ctx.guild.id)["announce_channel_id"] = channel.id
        save_data()
        await ctx.send(f"✅ Voice level-up announcements set to {channel.mention}.")

    @prefix_voicelevel.command(name="xp")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_xp(ctx, amount: commands.Range[int, 1, 100]):
        config(ctx.guild.id)["xp_per_minute"] = int(amount)
        save_data()
        await ctx.send(f"✅ Voice XP set to {amount} per minute.")

    print("🎙️ Voice XP and leveling module registered.", flush=True)
