# ============================================================
# AIR COMMANDER — ADVANCED LEVELING SYSTEM
# PREFIX + SLASH VERSION
# AESTHETIC EMBED EDITION
# ============================================================

import json
import os
import time
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

DATA_FILE = "leveling_data.json"

DEFAULT_XP_PER_MESSAGE = 15
DEFAULT_COOLDOWN = 60
DEFAULT_ANNOUNCE = True

EMBED_COLOR = discord.Color.blurple()
SUCCESS_COLOR = discord.Color.green()
ERROR_COLOR = discord.Color.red()
GOLD_COLOR = discord.Color.gold()


# ============================================================
# DATABASE
# ============================================================

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
            "announce": DEFAULT_ANNOUNCE,
            "announce_channel": None,
            "level_message": "🎉 {user} reached **Level {level}**!",
            "ignored_channels": [],
            "ignored_roles": [],
            "role_rewards": {},
            "role_boosters": {},
            "channel_boosters": {},
            "users": {}
        }

        save_data(DATA)

    config = DATA[gid]

    config.setdefault("enabled", True)
    config.setdefault("xp_per_message", DEFAULT_XP_PER_MESSAGE)
    config.setdefault("cooldown", DEFAULT_COOLDOWN)
    config.setdefault("announce", DEFAULT_ANNOUNCE)
    config.setdefault("announce_channel", None)

    config.setdefault(
        "level_message",
        "🎉 {user} reached **Level {level}**!"
    )

    config.setdefault("ignored_channels", [])
    config.setdefault("ignored_roles", [])
    config.setdefault("role_rewards", {})
    config.setdefault("role_boosters", {})
    config.setdefault("channel_boosters", {})
    config.setdefault("users", {})

    return config


# ============================================================
# XP / LEVEL CALCULATIONS
# ============================================================

def xp_required(level: int) -> int:
    return 100 + (level * 55) + int((level ** 2) * 5)


def calculate_level(total_xp: int):
    level = 0
    remaining = max(0, total_xp)

    while remaining >= xp_required(level):
        remaining -= xp_required(level)
        level += 1

    return level, remaining, xp_required(level)


def progress_bar(
    current: int,
    required: int,
    length: int = 14
):
    if required <= 0:
        return "━━━━━━━━━━━━━━"

    ratio = max(0, min(1, current / required))
    filled = int(ratio * length)

    return "▰" * filled + "▱" * (length - filled)


# ============================================================
# USER DATA
# ============================================================

def user_data(config, user_id: int):
    uid = str(user_id)

    if uid not in config["users"]:
        config["users"][uid] = {
            "xp": 0,
            "messages": 0,
            "last_xp": 0
        }

    user = config["users"][uid]

    user.setdefault("xp", 0)
    user.setdefault("messages", 0)
    user.setdefault("last_xp", 0)

    return user


# ============================================================
# VARIABLES
# ============================================================

def replace_variables(
    text,
    member,
    level,
    xp,
    server
):
    return (
        text
        .replace("{user}", member.mention)
        .replace("{username}", member.name)
        .replace("{displayname}", member.display_name)
        .replace("{level}", str(level))
        .replace("{xp}", str(xp))
        .replace("{server}", server.name)
        .replace("{membercount}", str(server.member_count))
    )


# ============================================================
# PERMISSION
# ============================================================

def is_manager():
    async def predicate(ctx):
        return (
            ctx.author.guild_permissions.manage_guild
            or ctx.author.guild_permissions.administrator
        )

    return commands.check(predicate)


# ============================================================
# EMBED HELPERS
# ============================================================

def success_embed(title, description):
    embed = discord.Embed(
        title=f"✅ {title}",
        description=description,
        color=SUCCESS_COLOR
    )
    embed.set_footer(text="Air Commander • Leveling System")
    return embed


def error_embed(description):
    embed = discord.Embed(
        title="❌ Leveling System",
        description=description,
        color=ERROR_COLOR
    )
    embed.set_footer(text="Air Commander")
    return embed


def info_embed(title, description):
    embed = discord.Embed(
        title=title,
        description=description,
        color=EMBED_COLOR
    )
    embed.set_footer(text="Air Commander • Leveling System")
    return embed


# ============================================================
# LEVELING COG
# ============================================================

class Leveling(commands.Cog):

    # ========================================================
    # SLASH GROUPS
    # ========================================================

    leveling = app_commands.Group(
        name="leveling",
        description="Configure the Air Commander leveling system"
    )

    levelrole = app_commands.Group(
        name="levelrole",
        description="Manage level reward roles"
    )

    def __init__(self, bot):
        self.bot = bot
        self.cooldowns = {}

    # ========================================================
    # MESSAGE XP
    # ========================================================

    @commands.Cog.listener()
    async def on_message(self, message):

        if message.author.bot:
            return

        if not message.guild:
            return

        config = guild_config(message.guild.id)

        if not config["enabled"]:
            return

        if message.channel.id in config["ignored_channels"]:
            return

        member_role_ids = {
            role.id for role in message.author.roles
        }

        if member_role_ids.intersection(
            set(config["ignored_roles"])
        ):
            return

        user = user_data(
            config,
            message.author.id
        )

        now = time.time()

        cooldown_key = (
            message.guild.id,
            message.author.id
        )

        last_xp = self.cooldowns.get(
            cooldown_key,
            0
        )

        if now - last_xp < config["cooldown"]:
            user["messages"] += 1
            save_data(DATA)
            return

        self.cooldowns[cooldown_key] = now

        old_xp = user["xp"]

        old_level, _, _ = calculate_level(old_xp)

        gained = config["xp_per_message"]

        multiplier = 1.0

        # ----------------------------------------------------
        # ROLE BOOSTERS
        # ----------------------------------------------------

        for role in message.author.roles:

            boost = config["role_boosters"].get(
                str(role.id)
            )

            if boost:
                try:
                    multiplier = max(
                        multiplier,
                        float(boost)
                    )
                except (ValueError, TypeError):
                    pass

        # ----------------------------------------------------
        # CHANNEL BOOSTER
        # ----------------------------------------------------

        channel_boost = config[
            "channel_boosters"
        ].get(
            str(message.channel.id)
        )

        if channel_boost:
            try:
                multiplier = max(
                    multiplier,
                    float(channel_boost)
                )
            except (ValueError, TypeError):
                pass

        gained = max(
            1,
            int(gained * multiplier)
        )

        user["xp"] += gained
        user["messages"] += 1

        new_level, _, _ = calculate_level(
            user["xp"]
        )

        save_data(DATA)

        if new_level > old_level:

            for level in range(
                old_level + 1,
                new_level + 1
            ):
                await self.handle_level_up(
                    message.guild,
                    message.author,
                    level
                )

    # ========================================================
    # LEVEL UP
    # ========================================================

    async def handle_level_up(
        self,
        guild,
        member,
        level
    ):

        config = guild_config(guild.id)

        reward_role_id = config[
            "role_rewards"
        ].get(
            str(level)
        )

        reward_role = None

        if reward_role_id:

            reward_role = guild.get_role(
                int(reward_role_id)
            )

            if (
                reward_role
                and reward_role not in member.roles
            ):
                try:
                    await member.add_roles(
                        reward_role,
                        reason=f"Level {level} reward"
                    )
                except discord.Forbidden:
                    reward_role = None

        if not config["announce"]:
            return

        total_xp = user_data(
            config,
            member.id
        )["xp"]

        text = replace_variables(
            config["level_message"],
            member,
            level,
            total_xp,
            guild
        )

        channel = None

        if config["announce_channel"]:

            channel = guild.get_channel(
                int(config["announce_channel"])
            )

        if channel is None:
            channel = guild.system_channel

        if channel is None:
            return

        # ----------------------------------------------------
        # AESTHETIC LEVEL-UP EMBED
        # ----------------------------------------------------

        embed = discord.Embed(
            title="✦ LEVEL UP!",
            description=(
                f"## 🎉 Congratulations {member.mention}!\n\n"
                f"{text}\n\n"
                f"**✨ New Level:** `{level}`"
            ),
            color=discord.Color.from_rgb(
                88,
                101,
                242
            )
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="📈 Progress",
            value=(
                f"**Level {level} unlocked**\n"
                f"`{progress_bar(0, 1)}`"
            ),
            inline=True
        )

        if reward_role:
            embed.add_field(
                name="🎖️ Reward",
                value=reward_role.mention,
                inline=True
            )

        embed.set_footer(
            text=f"{guild.name} • Air Commander Leveling"
        )

        try:
            await channel.send(
                embed=embed
            )
        except discord.Forbidden:
            pass

    # ========================================================
    # RANK EMBED BUILDER
    # ========================================================

    def build_rank_embed(
        self,
        guild,
        member
    ):

        config = guild_config(guild.id)

        user = user_data(
            config,
            member.id
        )

        total_xp = user["xp"]

        level, current_xp, needed = calculate_level(
            total_xp
        )

        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get(
                "xp",
                0
            ),
            reverse=True
        )

        position = 1

        for index, (uid, _) in enumerate(
            ranking,
            start=1
        ):
            if uid == str(member.id):
                position = index
                break

        percentage = (
            (current_xp / needed) * 100
            if needed
            else 0
        )

        embed = discord.Embed(
            title=f"✦ {member.display_name}'s Profile",
            description=(
                f"{member.mention}\n"
                f"**Keep chatting and climb the ranks!**"
            ),
            color=EMBED_COLOR
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="⭐ LEVEL",
            value=f"**{level}**",
            inline=True
        )

        embed.add_field(
            name="🏆 SERVER RANK",
            value=f"**#{position}**",
            inline=True
        )

        embed.add_field(
            name="💬 MESSAGES",
            value=f"**{user['messages']:,}**",
            inline=True
        )

        embed.add_field(
            name="✨ XP",
            value=(
                f"**{current_xp:,} / {needed:,} XP**\n"
                f"`{progress_bar(current_xp, needed)}`\n"
                f"**{percentage:.1f}%**"
            ),
            inline=False
        )

        embed.add_field(
            name="📊 TOTAL XP",
            value=f"**{total_xp:,}**",
            inline=True
        )

        embed.add_field(
            name="🚀 NEXT LEVEL",
            value=f"**Level {level + 1}**",
            inline=True
        )

        embed.set_footer(
            text="Air Commander • Leveling System"
        )

        return embed

    # ========================================================
    # SLASH /rank
    # ========================================================

    @app_commands.command(
        name="rank",
        description="View your or another member's rank"
    )
    @app_commands.describe(
        member="Member whose rank you want to see"
    )
    async def rank(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):

        if not interaction.guild:
            await interaction.response.send_message(
                embed=error_embed(
                    "This command can only be used inside a server."
                ),
                ephemeral=True
            )
            return

        member = member or interaction.user

        embed = self.build_rank_embed(
            interaction.guild,
            member
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # PREFIX ,rank / ,level / ,lvl
    # ========================================================

    @commands.command(
        name="rank",
        aliases=["level", "lvl"]
    )
    async def prefix_rank(
        self,
        ctx,
        member: Optional[discord.Member] = None
    ):

        member = member or ctx.author

        embed = self.build_rank_embed(
            ctx.guild,
            member
        )

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # LEADERBOARD EMBED BUILDER
    # ========================================================

    def build_leaderboard_embed(
        self,
        guild
    ):

        config = guild_config(guild.id)

        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get(
                "xp",
                0
            ),
            reverse=True
        )

        if not ranking:
            return None

        lines = []

        medals = [
            "🥇",
            "🥈",
            "🥉"
        ]

        for index, (uid, data) in enumerate(
            ranking[:10],
            start=1
        ):

            member = guild.get_member(
                int(uid)
            )

            name = (
                member.display_name
                if member
                else f"User {uid}"
            )

            level, _, _ = calculate_level(
                data.get("xp", 0)
            )

            prefix = (
                medals[index - 1]
                if index <= 3
                else f"**#{index}**"
            )

            lines.append(
                f"{prefix}  **{name}**\n"
                f"      └─ Level `{level}` • "
                f"`{data.get('xp', 0):,} XP`"
            )

        embed = discord.Embed(
            title="🏆 SERVER XP LEADERBOARD",
            description=(
                "```ansi\n"
                "     AIR COMMANDER • TOP 10\n"
                "```\n"
                + "\n\n".join(lines)
            ),
            color=GOLD_COLOR
        )

        embed.set_footer(
            text=f"{guild.name} • Leveling Leaderboard"
        )

        return embed

    # ========================================================
    # SLASH /leaderboard
    # ========================================================

    @app_commands.command(
        name="leaderboard",
        description="Show the server XP leaderboard"
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:
            await interaction.response.send_message(
                embed=error_embed(
                    "This command can only be used inside a server."
                ),
                ephemeral=True
            )
            return

        embed = self.build_leaderboard_embed(
            interaction.guild
        )

        if embed is None:
            await interaction.response.send_message(
                embed=info_embed(
                    "📊 No XP Data",
                    "No XP data exists in this server yet."
                )
            )
            return

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # PREFIX ,leaderboard / ,lb / ,levels
    # ========================================================

    @commands.command(
        name="leaderboard",
        aliases=["lb", "levels"]
    )
    async def prefix_leaderboard(
        self,
        ctx
    ):

        embed = self.build_leaderboard_embed(
            ctx.guild
        )

        if embed is None:
            await ctx.send(
                embed=info_embed(
                    "📊 No XP Data",
                    "No XP data exists in this server yet."
                )
            )
            return

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # SLASH /leveling enable
    # ========================================================

    @leveling.command(
        name="enable",
        description="Enable server leveling"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_enable(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["enabled"] = True
        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "Leveling Enabled",
                "The server leveling system is now **enabled**."
            )
        )

    # ========================================================
    # SLASH /leveling disable
    # ========================================================

    @leveling.command(
        name="disable",
        description="Disable server leveling"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_disable(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["enabled"] = False
        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "Leveling Disabled",
                "The server leveling system is now **disabled**."
            )
        )

    # ========================================================
    # SLASH /leveling xp
    # ========================================================

    @leveling.command(
        name="xp",
        description="Set XP gained per message"
    )
    @app_commands.describe(
        amount="XP amount per message"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_xp(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 1000]
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["xp_per_message"] = amount
        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "XP Updated",
                f"Members will now receive **{amount} XP** per eligible message."
            )
        )

    # ========================================================
    # SLASH /leveling cooldown
    # ========================================================

    @leveling.command(
        name="cooldown",
        description="Set XP cooldown in seconds"
    )
    @app_commands.describe(
        seconds="Cooldown between XP gains"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_cooldown(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 3600]
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["cooldown"] = seconds
        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "XP Cooldown Updated",
                f"XP cooldown is now **{seconds} seconds**."
            )
        )

    # ========================================================
    # SLASH /leveling announce
    # ========================================================

    @leveling.command(
        name="announce",
        description="Enable or disable level-up announcements"
    )
    @app_commands.describe(
        enabled="Whether announcements should be enabled"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_announce(
        self,
        interaction: discord.Interaction,
        enabled: bool
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["announce"] = enabled
        save_data(DATA)

        status = (
            "enabled"
            if enabled
            else "disabled"
        )

        await interaction.response.send_message(
            embed=success_embed(
                "Announcements Updated",
                f"Level-up announcements are now **{status}**."
            )
        )

    # ========================================================
    # SLASH /leveling channel
    # ========================================================

    @leveling.command(
        name="channel",
        description="Set the level-up announcement channel"
    )
    @app_commands.describe(
        channel="Channel where level-ups should be announced"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["announce_channel"] = channel.id
        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "Announcement Channel Updated",
                f"Level-up announcements will now be sent to {channel.mention}."
            )
        )

    # ========================================================
    # SLASH /leveling channelreset
    # ========================================================

    @leveling.command(
        name="channelreset",
        description="Reset the level-up announcement channel"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_channelreset(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["announce_channel"] = None
        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "Announcement Channel Reset",
                "Level-up announcements will use the server system channel."
            )
        )

    # ========================================================
    # PREFIX ,leveling
    # ========================================================

    @commands.group(
        name="leveling",
        invoke_without_command=True
    )
    async def leveling_prefix(
        self,
        ctx
    ):

        embed = info_embed(
            "📊 LEVELING CONFIGURATION",
            (
                "```text\n"
                ",leveling enable\n"
                ",leveling disable\n"
                ",leveling xp <amount>\n"
                ",leveling cooldown <seconds>\n"
                ",leveling announce <on/off>\n"
                ",leveling channel #channel\n"
                ",leveling channelreset\n"
                "```"
            )
        )

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # PREFIX ,leveling enable
    # ========================================================

    @leveling_prefix.command(
        name="enable"
    )
    @is_manager()
    async def prefix_leveling_enable(
        self,
        ctx
    ):

        config = guild_config(
            ctx.guild.id
        )

        config["enabled"] = True
        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "Leveling Enabled",
                "The server leveling system is now **enabled**."
            )
        )

    # ========================================================
    # PREFIX ,leveling disable
    # ========================================================

    @leveling_prefix.command(
        name="disable"
    )
    @is_manager()
    async def prefix_leveling_disable(
        self,
        ctx
    ):

        config = guild_config(
            ctx.guild.id
        )

        config["enabled"] = False
        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "Leveling Disabled",
                "The server leveling system is now **disabled**."
            )
        )

    # ========================================================
    # PREFIX ,leveling xp
    # ========================================================

    @leveling_prefix.command(
        name="xp"
    )
    @is_manager()
    async def prefix_leveling_xp(
        self,
        ctx,
        amount: int
    ):

        if amount < 1 or amount > 1000:
            await ctx.send(
                embed=error_embed(
                    "XP must be between **1 and 1000**."
                )
            )
            return

        config = guild_config(
            ctx.guild.id
        )

        config["xp_per_message"] = amount
        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "XP Updated",
                f"XP per message is now **{amount} XP**."
            )
        )

    # ========================================================
    # PREFIX ,leveling cooldown
    # ========================================================

    @leveling_prefix.command(
        name="cooldown"
    )
    @is_manager()
    async def prefix_leveling_cooldown(
        self,
        ctx,
        seconds: int
    ):

        if seconds < 0 or seconds > 3600:
            await ctx.send(
                embed=error_embed(
                    "Cooldown must be between **0 and 3600 seconds**."
                )
            )
            return

        config = guild_config(
            ctx.guild.id
        )

        config["cooldown"] = seconds
        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "XP Cooldown Updated",
                f"XP cooldown is now **{seconds}s**."
            )
        )

    # ========================================================
    # PREFIX ,leveling announce
    # ========================================================

    @leveling_prefix.command(
        name="announce"
    )
    @is_manager()
    async def prefix_leveling_announce(
        self,
        ctx,
        value: str
    ):

        value = value.lower()

        if value not in {
            "on",
            "off",
            "enable",
            "disable"
        }:
            await ctx.send(
                embed=error_embed(
                    "Use `on` or `off`.\n"
                    "Example: `,leveling announce on`"
                )
            )
            return

        enabled = value in {
            "on",
            "enable"
        }

        config = guild_config(
            ctx.guild.id
        )

        config["announce"] = enabled
        save_data(DATA)

        status = (
            "enabled"
            if enabled
            else "disabled"
        )

        await ctx.send(
            embed=success_embed(
                "Announcements Updated",
                f"Level-up announcements are now **{status}**."
            )
        )

    # ========================================================
    # PREFIX ,leveling channel
    # ========================================================

    @leveling_prefix.command(
        name="channel"
    )
    @is_manager()
    async def prefix_leveling_channel(
        self,
        ctx,
        channel: discord.TextChannel
    ):

        config = guild_config(
            ctx.guild.id
        )

        config["announce_channel"] = channel.id
        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "Announcement Channel Updated",
                f"Level-ups will now be announced in {channel.mention}."
            )
        )

    # ========================================================
    # PREFIX ,leveling channelreset
    # ========================================================

    @leveling_prefix.command(
        name="channelreset"
    )
    @is_manager()
    async def prefix_leveling_channelreset(
        self,
        ctx
    ):

        config = guild_config(
            ctx.guild.id
        )

        config["announce_channel"] = None
        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "Announcement Channel Reset",
                "Level-up announcements will use the server system channel."
            )
        )

    # ========================================================
    # SLASH /levelrole add
    # ========================================================

    @levelrole.command(
        name="add",
        description="Give a role when a member reaches a level"
    )
    @app_commands.describe(
        level="Level required",
        role="Reward role"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def levelrole_add(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 1, 1000],
        role: discord.Role
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["role_rewards"][
            str(level)
        ] = role.id

        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "Level Reward Added",
                f"{role.mention} will be awarded at **Level {level}**."
            )
        )

    # ========================================================
    # SLASH /levelrole remove
    # ========================================================

    @levelrole.command(
        name="remove",
        description="Remove a level reward role"
    )
    @app_commands.describe(
        level="Level whose reward should be removed"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def levelrole_remove(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 1, 1000]
    ):

        config = guild_config(
            interaction.guild.id
        )

        removed = config[
            "role_rewards"
        ].pop(
            str(level),
            None
        )

        if removed is None:
            await interaction.response.send_message(
                embed=error_embed(
                    f"No reward role is configured for **Level {level}**."
                ),
                ephemeral=True
            )
            return

        save_data(DATA)

        await interaction.response.send_message(
            embed=success_embed(
                "Level Reward Removed",
                f"Reward role for **Level {level}** has been removed."
            )
        )

    # ========================================================
    # SLASH /levelrole list
    # ========================================================

    @levelrole.command(
        name="list",
        description="List all level reward roles"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def levelrole_list(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        rewards = config[
            "role_rewards"
        ]

        if not rewards:
            await interaction.response.send_message(
                embed=info_embed(
                    "🎖️ Level Rewards",
                    "No level reward roles are configured."
                )
            )
            return

        lines = []

        for level, role_id in sorted(
            rewards.items(),
            key=lambda x: int(x[0])
        ):

            role = interaction.guild.get_role(
                int(role_id)
            )

            role_name = (
                role.mention
                if role
                else f"`Deleted Role ({role_id})`"
            )

            lines.append(
                f"**Level {level}**  →  {role_name}"
            )

        embed = discord.Embed(
            title="🎖️ LEVEL REWARD ROLES",
            description="\n".join(lines),
            color=GOLD_COLOR
        )

        embed.set_footer(
            text="Air Commander • Level Rewards"
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # PREFIX ,levelrole
    # ========================================================

    @commands.group(
        name="levelrole",
        invoke_without_command=True
    )
    async def levelrole_prefix(
        self,
        ctx
    ):

        embed = info_embed(
            "🎖️ LEVEL ROLE COMMANDS",
            (
                "```text\n"
                ",levelrole add <level> @role\n"
                ",levelrole remove <level>\n"
                ",levelrole list\n"
                "```"
            )
        )

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # PREFIX ,levelrole add
    # ========================================================

    @levelrole_prefix.command(
        name="add"
    )
    @is_manager()
    async def prefix_levelrole_add(
        self,
        ctx,
        level: int,
        role: discord.Role
    ):

        if level < 1:
            await ctx.send(
                embed=error_embed(
                    "Level must be **1 or higher**."
                )
            )
            return

        config = guild_config(
            ctx.guild.id
        )

        config["role_rewards"][
            str(level)
        ] = role.id

        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "Level Reward Added",
                f"{role.mention} will be awarded at **Level {level}**."
            )
        )

    # ========================================================
    # PREFIX ,levelrole remove
    # ========================================================

    @levelrole_prefix.command(
        name="remove"
    )
    @is_manager()
    async def prefix_levelrole_remove(
        self,
        ctx,
        level: int
    ):

        config = guild_config(
            ctx.guild.id
        )

        removed = config[
            "role_rewards"
        ].pop(
            str(level),
            None
        )

        if removed is None:
            await ctx.send(
                embed=error_embed(
                    f"No reward role is configured for **Level {level}**."
                )
            )
            return

        save_data(DATA)

        await ctx.send(
            embed=success_embed(
                "Level Reward Removed",
                f"Reward role for **Level {level}** has been removed."
            )
        )

    # ========================================================
    # PREFIX ,levelrole list
    # ========================================================

    @levelrole_prefix.command(
        name="list"
    )
    @is_manager()
    async def prefix_levelrole_list(
        self,
        ctx
    ):

        config = guild_config(
            ctx.guild.id
        )

        rewards = config[
            "role_rewards"
        ]

        if not rewards:
            await ctx.send(
                embed=info_embed(
                    "🎖️ Level Rewards",
                    "No level reward roles are configured."
                )
            )
            return

        lines = []

        for level, role_id in sorted(
            rewards.items(),
            key=lambda x: int(x[0])
        ):

            role = ctx.guild.get_role(
                int(role_id)
            )

            role_name = (
                role.mention
                if role
                else f"`Deleted Role ({role_id})`"
            )

            lines.append(
                f"**Level {level}**  →  {role_name}"
            )

        embed = discord.Embed(
            title="🎖️ LEVEL REWARD ROLES",
            description="\n".join(lines),
            color=GOLD_COLOR
        )

        embed.set_footer(
            text="Air Commander • Level Rewards"
        )

        await ctx.send(
            embed=embed
        )


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(
        Leveling(bot)
    )

