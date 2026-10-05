# ============================================================
# AIR COMMANDER — SAFE NEW LEVELING ADDON
# This file does NOT overwrite the existing leveling.py commands.
# It adds a new namespaced system: /airlevel ... and ,airrank ...
# ============================================================

import json
import os
import time
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands

DATA_FILE = "airleveling_data.json"

DEFAULT_XP_PER_MESSAGE = 15
DEFAULT_COOLDOWN = 60

EMBED_COLOR = discord.Color.blurple()
SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
GOLD_COLOR = discord.Color.gold()
ORANGE_COLOR = discord.Color.orange()
PURPLE_COLOR = discord.Color.purple()


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_data(data):
    temp_file = DATA_FILE + ".tmp"
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(temp_file, DATA_FILE)

DATA = load_data()


def guild_config(guild_id: int):
    gid = str(guild_id)
    if gid not in DATA:
        DATA[gid] = {
            "enabled": True,
            "xp_per_message": DEFAULT_XP_PER_MESSAGE,
            "cooldown": DEFAULT_COOLDOWN,
            "announce": True,
            "announce_channel": None,
            "ignored_channels": [],
            "ignored_roles": [],
            "role_rewards": {},
            "role_boosters": {},
            "channel_boosters": {},
            "users": {},
            "season": {"number": 1, "xp": 0, "started": time.time()},
            "quests": {
                "name": "Chat Storm",
                "description": "Send 500 messages this week",
                "target": 500,
                "reward": 1000,
                "progress": {}
            }
        }
        save_data(DATA)

    config = DATA[gid]
    config.setdefault("enabled", True)
    config.setdefault("xp_per_message", DEFAULT_XP_PER_MESSAGE)
    config.setdefault("cooldown", DEFAULT_COOLDOWN)
    config.setdefault("announce", True)
    config.setdefault("announce_channel", None)
    config.setdefault("ignored_channels", [])
    config.setdefault("ignored_roles", [])
    config.setdefault("role_rewards", {})
    config.setdefault("role_boosters", {})
    config.setdefault("channel_boosters", {})
    config.setdefault("users", {})
    config.setdefault("season", {"number": 1, "xp": 0, "started": time.time()})
    config.setdefault("quests", {
        "name": "Chat Storm",
        "description": "Send 500 messages this week",
        "target": 500,
        "reward": 1000,
        "progress": {}
    })
    return config


def xp_required(level: int) -> int:
    return 100 + (level * 55) + int((level ** 2) * 5)


def calculate_level(total_xp: int):
    level = 0
    remaining = max(0, total_xp)
    while remaining >= xp_required(level):
        remaining -= xp_required(level)
        level += 1
    return level, remaining, xp_required(level)


def progress_bar(current: int, required: int, length: int = 14):
    if required <= 0:
        return "━━━━━━━━━━━━━━"
    ratio = max(0, min(1, current / required))
    filled = int(ratio * length)
    return "▰" * filled + "▱" * (length - filled)


def user_data(config, user_id: int):
    uid = str(user_id)
    if uid not in config["users"]:
        config["users"][uid] = {
            "xp": 0,
            "messages": 0,
            "last_xp": 0,
            "streak": 0,
            "best_streak": 0,
            "daily_claim": 0,
            "badges": []
        }

    user = config["users"][uid]
    user.setdefault("xp", 0)
    user.setdefault("messages", 0)
    user.setdefault("last_xp", 0)
    user.setdefault("streak", 0)
    user.setdefault("best_streak", 0)
    user.setdefault("daily_claim", 0)
    user.setdefault("badges", [])
    return user


def success_embed(title, description):
    e = discord.Embed(title=f"✅ {title}", description=description, color=SUCCESS_COLOR)
    e.set_footer(text="Air Commander • Air Leveling")
    return e


def error_embed(description):
    e = discord.Embed(title="❌ Air Leveling", description=description, color=ERROR_COLOR)
    e.set_footer(text="Air Commander")
    return e


def info_embed(title, description):
    e = discord.Embed(title=title, description=description, color=EMBED_COLOR)
    e.set_footer(text="Air Commander • Air Leveling")
    return e


class AirLeveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}

    airlevel = app_commands.Group(name="airlevel", description="Air Commander level system")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        config = guild_config(message.guild.id)
        if not config.get("enabled", True):
            return

        if message.channel.id in config.get("ignored_channels", []):
            return

        member_role_ids = {role.id for role in message.author.roles}
        if member_role_ids.intersection(set(config.get("ignored_roles", []))):
            return

        user = user_data(config, message.author.id)
        now = time.time()
        cooldown_key = (message.guild.id, message.author.id)
        last_xp = self.cooldowns.get(cooldown_key, 0)

        if now - last_xp < config["cooldown"]:
            user["messages"] += 1
            save_data(DATA)
            return

        self.cooldowns[cooldown_key] = now

        old_xp = user["xp"]
        old_level, _, _ = calculate_level(old_xp)

        gained = config["xp_per_message"]
        multiplier = 1.0

        for role in message.author.roles:
            boost = config.get("role_boosters", {}).get(str(role.id))
            if boost:
                try:
                    multiplier = max(multiplier, float(boost))
                except (TypeError, ValueError):
                    pass

        channel_boost = config.get("channel_boosters", {}).get(str(message.channel.id))
        if channel_boost:
            try:
                multiplier = max(multiplier, float(channel_boost))
            except (TypeError, ValueError):
                pass

        gained = max(1, int(gained * multiplier))
        user["xp"] += gained
        user["messages"] += 1
        save_data(DATA)

        new_level, _, _ = calculate_level(user["xp"])
        if new_level > old_level:
            for level in range(old_level + 1, new_level + 1):
                await self.handle_level_up(message.guild, message.author, level)

    async def handle_level_up(self, guild, member, level):
        config = guild_config(guild.id)
        reward_role_id = config["role_rewards"].get(str(level))
        reward_role = None

        if reward_role_id:
            reward_role = guild.get_role(int(reward_role_id))
            if reward_role and reward_role not in member.roles:
                try:
                    await member.add_roles(reward_role, reason=f"Level {level} reward")
                except discord.Forbidden:
                    reward_role = None

        if not config["announce"]:
            return

        total_xp = user_data(config, member.id)["xp"]
        text = f"🎉 {member.mention} reached **Level {level}**!"

        channel = None
        if config["announce_channel"]:
            channel = guild.get_channel(int(config["announce_channel"]))
        if channel is None:
            channel = guild.system_channel
        if channel is None:
            return

        embed = discord.Embed(
            title="✦ LEVEL UP!",
            description=(f"## 🎉 Congratulations {member.mention}!\n\n{text}\n\n**✨ New Level:** `{level}`"),
            color=discord.Color.from_rgb(88, 101, 242)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="📈 Progress", value=f"**Level {level} unlocked**\n`{progress_bar(0, 1)}`", inline=True)
        if reward_role:
            embed.add_field(name="🎖️ Reward", value=reward_role.mention, inline=True)
        embed.set_footer(text=f"{guild.name} • Air Commander Leveling")
        try:
            await channel.send(embed=embed)
        except discord.Forbidden:
            pass

    def build_rank_embed(self, guild, member):
        config = guild_config(guild.id)
        user = user_data(config, member.id)
        total_xp = user["xp"]
        level, current_xp, needed = calculate_level(total_xp)

        ranking = sorted(config["users"].items(), key=lambda item: item[1].get("xp", 0), reverse=True)
        position = 1
        for index, (uid, _) in enumerate(ranking, start=1):
            if uid == str(member.id):
                position = index
                break

        percentage = ((current_xp / needed) * 100) if needed else 0
        embed = discord.Embed(
            title=f"✦ {member.display_name}'s Profile",
            description=f"{member.mention}\n**Keep chatting and climb the ranks!**",
            color=EMBED_COLOR
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="⭐ LEVEL", value=f"**{level}**", inline=True)
        embed.add_field(name="🏆 SERVER RANK", value=f"**#{position}**", inline=True)
        embed.add_field(name="💬 MESSAGES", value=f"**{user['messages']:,}**", inline=True)
        embed.add_field(
            name="✨ XP",
            value=f"**{current_xp:,} / {needed:,} XP**\n`{progress_bar(current_xp, needed)}`\n**{percentage:.1f}%**",
            inline=False
        )
        embed.add_field(name="📊 TOTAL XP", value=f"**{total_xp:,}**", inline=True)
        embed.add_field(name="🚀 NEXT LEVEL", value=f"**Level {level + 1}**", inline=True)
        embed.set_footer(text="Air Commander • Air Leveling")
        return embed

    def build_leaderboard_embed(self, guild):
        config = guild_config(guild.id)
        ranking = sorted(config["users"].items(), key=lambda item: item[1].get("xp", 0), reverse=True)
        if not ranking:
            return None

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for index, (uid, data) in enumerate(ranking[:10], start=1):
            member = guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            level, _, _ = calculate_level(data.get("xp", 0))
            prefix = medals[index - 1] if index <= 3 else f"**#{index}**"
            lines.append(f"{prefix}  **{name}**\n      └─ Level `{level}` • `{data.get('xp', 0):,} XP`")

        embed = discord.Embed(
            title="🏆 AIR XP LEADERBOARD",
            description="```ansi\n     AIR COMMANDER • TOP 10\n```\n" + "\n\n".join(lines),
            color=GOLD_COLOR
        )
        embed.set_footer(text=f"{guild.name} • Air Leveling Leaderboard")
        return embed

    @airlevel.command(name="rank", description="View your or another member's rank")
    @app_commands.describe(member="Member whose rank you want to see")
    async def airlevel_rank(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        member = member or interaction.user
        await interaction.response.send_message(embed=self.build_rank_embed(interaction.guild, member))

    @airlevel.command(name="leaderboard", description="Show the server XP leaderboard")
    async def airlevel_leaderboard(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        embed = self.build_leaderboard_embed(interaction.guild)
        if embed is None:
            await interaction.response.send_message(embed=info_embed("📊 No XP Data", "No XP data exists in this server yet."))
            return
        await interaction.response.send_message(embed=embed)

    @airlevel.command(name="streak", description="View your streak")
    @app_commands.describe(member="Member to inspect")
    async def airlevel_streak(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        member = member or interaction.user
        config = guild_config(interaction.guild.id)
        user = user_data(config, member.id)
        embed = discord.Embed(
            title=f"🔥 {member.display_name}'s Streak",
            description=f"Current streak: **{user.get('streak', 0)}** days\nBest streak: **{user.get('best_streak', 0)}** days",
            color=ORANGE_COLOR
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @airlevel.command(name="daily", description="Claim a daily XP reward")
    async def airlevel_daily(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return

        config = guild_config(interaction.guild.id)
        user = user_data(config, interaction.user.id)
        now = time.time()
        last_claim = user.get("daily_claim", 0)
        if now - last_claim < 86400:
            remain = max(0, int(86400 - (now - last_claim)))
            hours = remain // 3600
            minutes = (remain % 3600) // 60
            await interaction.response.send_message(embed=info_embed("⏳ Daily Reward", f"You already claimed today. Come back in **{hours}h {minutes}m**."), ephemeral=True)
            return

        user["daily_claim"] = now
        user["xp"] += 250
        save_data(DATA)
        await interaction.response.send_message(embed=success_embed("🎁 Daily Reward Claimed", "You received **250 XP** for your daily reward."))

    @airlevel.command(name="badges", description="Show your earned badges")
    @app_commands.describe(member="Member to inspect")
    async def airlevel_badges(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        member = member or interaction.user
        config = guild_config(interaction.guild.id)
        user = user_data(config, member.id)
        badges = user.get("badges", [])
        if not badges:
            await interaction.response.send_message(embed=info_embed(f"🎖️ {member.display_name}'s Badges", "No badges earned yet."))
            return
        label = "\n".join(f"• {badge}" for badge in badges)
        await interaction.response.send_message(embed=discord.Embed(title=f"🎖️ {member.display_name}'s Badges", description=label, color=GOLD_COLOR))

    @airlevel.command(name="season", description="Show current season progress")
    async def airlevel_season(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        config = guild_config(interaction.guild.id)
        season = config.get("season", {"number": 1, "xp": 0})
        embed = discord.Embed(
            title=f"🏆 Season {season.get('number', 1)}",
            description=f"Season XP: **{season.get('xp', 0):,}**",
            color=PURPLE_COLOR
        )
        await interaction.response.send_message(embed=embed)

    @airlevel.command(name="quest", description="Show the current weekly quest")
    async def airlevel_quest(self, interaction: discord.Interaction):
        embed = discord.Embed(title="⚔️ Weekly Quest", description="Complete **500 messages** this week for **1000 XP**.", color=discord.Color.orange())
        await interaction.response.send_message(embed=embed)

    @airlevel.command(name="battlepass", description="Show progression battle pass")
    async def airlevel_battlepass(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🎮 Air Battle Pass", description="Tier 1: 100 XP\nTier 2: Level 5\nTier 3: 500 XP\nTier 4: Special role reward", color=discord.Color.dark_magenta())
        await interaction.response.send_message(embed=embed)

    @airlevel.command(name="rewards", description="Show reward milestones")
    async def airlevel_rewards(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        config = guild_config(interaction.guild.id)
        rewards = config.get("role_rewards", {})
        if not rewards:
            await interaction.response.send_message(embed=info_embed("🎖️ Reward Milestones", "No reward roles are set yet."))
            return
        lines = [f"**Level {level}** → <@&{role_id}>" for level, role_id in sorted(rewards.items(), key=lambda x: int(x[0]))]
        await interaction.response.send_message(embed=discord.Embed(title="🎖️ Reward Milestones", description="\n".join(lines), color=GOLD_COLOR))

    @airlevel.command(name="boost", description="View active XP boosters")
    async def airlevel_boost(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        config = guild_config(interaction.guild.id)
        roles = config.get("role_boosters", {})
        channels = config.get("channel_boosters", {})
        text = "\n".join([f"Role boost: **{k}** = {v}x" for k, v in roles.items()]) or "No role boosts enabled."
        if channels:
            text += "\n" + "\n".join([f"Channel boost: **{k}** = {v}x" for k, v in channels.items()])
        await interaction.response.send_message(embed=discord.Embed(title="⚡ XP Boosts", description=text, color=discord.Color.from_rgb(255, 153, 51)))

    @airlevel.command(name="profile", description="Show your full profile card")
    @app_commands.describe(member="Member to inspect")
    async def airlevel_profile(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if not interaction.guild:
            await interaction.response.send_message(embed=error_embed("This command can only be used inside a server."), ephemeral=True)
            return
        member = member or interaction.user
        await interaction.response.send_message(embed=self.build_rank_embed(interaction.guild, member))

    @airlevel.command(name="help", description="Show Air Leveling commands")
    async def airlevel_help(self, interaction: discord.Interaction):
        help_text = (
            "```text\n"
            "/airlevel rank\n"
            "/airlevel leaderboard\n"
            "/airlevel streak\n"
            "/airlevel daily\n"
            "/airlevel badges\n"
            "/airlevel season\n"
            "/airlevel quest\n"
            "/airlevel battlepass\n"
            "/airlevel rewards\n"
            "/airlevel boost\n"
            "/airlevel profile\n"
            "```"
        )
        await interaction.response.send_message(embed=info_embed("📖 Air Leveling Help", help_text))

    @commands.group(name="airlevel", invoke_without_command=True)
    async def prefix_airlevel(self, ctx):
        await ctx.send(embed=info_embed("📖 Air Leveling Help", "Use `,airlevel rank`, `,airlevel leaderboard`, `,airlevel daily`, `,airlevel quest`"))

    @prefix_airlevel.command(name="rank")
    async def prefix_airlevel_rank(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        await ctx.send(embed=self.build_rank_embed(ctx.guild, member))

    @prefix_airlevel.command(name="leaderboard")
    async def prefix_airlevel_leaderboard(self, ctx):
        embed = self.build_leaderboard_embed(ctx.guild)
        if embed is None:
            await ctx.send(embed=info_embed("📊 No XP Data", "No XP data exists in this server yet."))
            return
        await ctx.send(embed=embed)

    @prefix_airlevel.command(name="daily")
    async def prefix_airlevel_daily(self, ctx):
        config = guild_config(ctx.guild.id)
        user = user_data(config, ctx.author.id)
        now = time.time()
        last_claim = user.get("daily_claim", 0)
        if now - last_claim < 86400:
            remain = max(0, int(86400 - (now - last_claim)))
            hours = remain // 3600
            minutes = (remain % 3600) // 60
            await ctx.send(embed=info_embed("⏳ Daily Reward", f"You already claimed today. Come back in **{hours}h {minutes}m**."))
            return
        user["daily_claim"] = now
        user["xp"] += 250
        save_data(DATA)
        await ctx.send(embed=success_embed("🎁 Daily Reward Claimed", "You received **250 XP** for your daily reward."))

    @prefix_airlevel.command(name="streak")
    async def prefix_airlevel_streak(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        config = guild_config(ctx.guild.id)
        user = user_data(config, member.id)
        embed = discord.Embed(
            title=f"🔥 {member.display_name}'s Streak",
            description=f"Current streak: **{user.get('streak', 0)}** days\nBest streak: **{user.get('best_streak', 0)}** days",
            color=ORANGE_COLOR
        )
        await ctx.send(embed=embed)

    @prefix_airlevel.command(name="help")
    async def prefix_airlevel_help(self, ctx):
        await ctx.send(embed=info_embed("📖 Air Leveling Help", "Use `,airlevel rank`, `,airlevel leaderboard`, `,airlevel daily`, `,airlevel quest`"))

    @commands.command(name="airrank", aliases=["airlevelrank"])
    async def prefix_airrank(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        await ctx.send(embed=self.build_rank_embed(ctx.guild, member))

    @commands.command(name="airleaderboard", aliases=["airlb"])
    async def prefix_airleaderboard(self, ctx):
        embed = self.build_leaderboard_embed(ctx.guild)
        if embed is None:
            await ctx.send(embed=info_embed("📊 No XP Data", "No XP data exists in this server yet."))
            return
        await ctx.send(embed=embed)

    @commands.command(name="airstreak")
    async def prefix_airstreak(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        config = guild_config(ctx.guild.id)
        user = user_data(config, member.id)
        embed = discord.Embed(
            title=f"🔥 {member.display_name}'s Streak",
            description=f"Current streak: **{user.get('streak', 0)}** days\nBest streak: **{user.get('best_streak', 0)}** days",
            color=ORANGE_COLOR
        )
        await ctx.send(embed=embed)

    @commands.command(name="airdaily")
    async def prefix_airdaily(self, ctx):
        config = guild_config(ctx.guild.id)
        user = user_data(config, ctx.author.id)
        now = time.time()
        last_claim = user.get("daily_claim", 0)
        if now - last_claim < 86400:
            remain = max(0, int(86400 - (now - last_claim)))
            hours = remain // 3600
            minutes = (remain % 3600) // 60
            await ctx.send(embed=info_embed("⏳ Daily Reward", f"You already claimed today. Come back in **{hours}h {minutes}m**."))
            return
        user["daily_claim"] = now
        user["xp"] += 250
        save_data(DATA)
        await ctx.send(embed=success_embed("🎁 Daily Reward Claimed", "You received **250 XP** for your daily reward."))


async def setup(bot):
    await bot.add_cog(AirLeveling(bot))
    print("✅ Air Leveling loaded")
