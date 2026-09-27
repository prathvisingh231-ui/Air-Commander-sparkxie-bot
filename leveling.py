# ============================================================
# AIR COMMANDER — ADVANCED LEVELING SYSTEM
# ============================================================

import json
import os
import time
import math
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands


DATA_FILE = "leveling_data.json"

DEFAULT_XP_PER_MESSAGE = 15
DEFAULT_COOLDOWN = 60
DEFAULT_ANNOUNCE = True


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

    # Migration protection for older databases
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
    """
    XP needed to reach the next level.

    Example:
    Level 0 -> 100 XP
    Level 1 -> 155 XP
    Level 2 -> 220 XP
    """
    return 100 + (level * 55) + int((level ** 2) * 5)


def calculate_level(total_xp: int):
    level = 0
    remaining = max(0, total_xp)

    while remaining >= xp_required(level):
        remaining -= xp_required(level)
        level += 1

    return level, remaining, xp_required(level)


def progress_bar(current: int, required: int, length: int = 12):
    if required <= 0:
        return "━━━━━━━━━━━━"

    ratio = max(0, min(1, current / required))
    filled = int(ratio * length)

    return "█" * filled + "░" * (length - filled)


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

def replace_variables(text, member, level, xp, server):
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
# LEVELING COG
# ============================================================

class Leveling(commands.Cog):

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

        # Ignored channel
        if message.channel.id in config["ignored_channels"]:
            return

        # Ignored roles
        member_role_ids = {role.id for role in message.author.roles}

        if member_role_ids.intersection(
            set(config["ignored_roles"])
        ):
            return

        user = user_data(config, message.author.id)

        now = time.time()

        cooldown_key = (
            message.guild.id,
            message.author.id
        )

        last_xp = self.cooldowns.get(cooldown_key, 0)

        if now - last_xp < config["cooldown"]:
            user["messages"] += 1
            save_data(DATA)
            return

        self.cooldowns[cooldown_key] = now

        old_xp = user["xp"]
        old_level, _, _ = calculate_level(old_xp)

        # Base XP
        gained = config["xp_per_message"]

        # Role boosters
        multiplier = 1.0

        for role in message.author.roles:

            boost = config["role_boosters"].get(str(role.id))

            if boost:
                try:
                    multiplier = max(
                        multiplier,
                        float(boost)
                    )
                except ValueError:
                    pass

        # Channel booster
        channel_boost = config["channel_boosters"].get(
            str(message.channel.id)
        )

        if channel_boost:
            try:
                multiplier = max(
                    multiplier,
                    float(channel_boost)
                )
            except ValueError:
                pass

        gained = max(1, int(gained * multiplier))

        user["xp"] += gained
        user["messages"] += 1

        new_level, _, _ = calculate_level(user["xp"])

        save_data(DATA)

        # Level up
        if new_level > old_level:

            for level in range(old_level + 1, new_level + 1):
                await self.handle_level_up(
                    message.guild,
                    message.author,
                    level
                )

    # ========================================================
    # LEVEL UP
    # ========================================================

    async def handle_level_up(self, guild, member, level):

        config = guild_config(guild.id)

        # Give reward role
        reward_role_id = config["role_rewards"].get(
            str(level)
        )

        if reward_role_id:

            role = guild.get_role(
                int(reward_role_id)
            )

            if role and role not in member.roles:

                try:
                    await member.add_roles(
                        role,
                        reason=f"Level {level} reward"
                    )
                except discord.Forbidden:
                    pass

        if not config["announce"]:
            return

        text = replace_variables(
            config["level_message"],
            member,
            level,
            user_data(
                config,
                member.id
            )["xp"],
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

        try:
            await channel.send(text)
        except discord.Forbidden:
            pass

    # ========================================================
    # /rank
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

        member = member or interaction.user

        config = guild_config(
            interaction.guild.id
        )

        user = user_data(
            config,
            member.id
        )

        total_xp = user["xp"]

        level, current_xp, needed = calculate_level(
            total_xp
        )

        # Server rank
        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get("xp", 0),
            reverse=True
        )

        position = 1

        for index, (uid, _) in enumerate(ranking, start=1):
            if uid == str(member.id):
                position = index
                break

        embed = discord.Embed(
            title=f"🏆 {member.display_name}'s Rank",
            color=discord.Color.blurple()
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="⭐ Level",
            value=f"**{level}**",
            inline=True
        )

        embed.add_field(
            name="📊 Server Rank",
            value=f"**#{position}**",
            inline=True
        )

        embed.add_field(
            name="💬 Messages",
            value=f"**{user['messages']:,}**",
            inline=True
        )

        embed.add_field(
            name="✨ XP",
            value=f"**{current_xp:,} / {needed:,}**",
            inline=False
        )

        embed.add_field(
            name="Progress",
            value=(
                f"`{progress_bar(current_xp, needed)}`\n"
                f"**{current_xp / needed * 100:.1f}%**"
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Total XP: {total_xp:,}"
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # PREFIX ,rank
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

        config = guild_config(ctx.guild.id)

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
            key=lambda item: item[1].get("xp", 0),
            reverse=True
        )

        position = 1

        for index, (uid, _) in enumerate(ranking, start=1):
            if uid == str(member.id):
                position = index
                break

        embed = discord.Embed(
            title=f"🏆 {member.display_name}'s Rank",
            color=discord.Color.blurple()
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.add_field(
            name="⭐ Level",
            value=f"**{level}**",
            inline=True
        )

        embed.add_field(
            name="📊 Rank",
            value=f"**#{position}**",
            inline=True
        )

        embed.add_field(
            name="💬 Messages",
            value=f"**{user['messages']:,}**",
            inline=True
        )

        embed.add_field(
            name="✨ XP",
            value=f"**{current_xp:,} / {needed:,}**",
            inline=False
        )

        embed.add_field(
            name="Progress",
            value=(
                f"`{progress_bar(current_xp, needed)}`\n"
                f"**{current_xp / needed * 100:.1f}%**"
            ),
            inline=False
        )

        embed.set_footer(
            text=f"Total XP: {total_xp:,}"
        )

        await ctx.send(embed=embed)

    # ========================================================
    # /leaderboard
    # ========================================================

    @app_commands.command(
        name="leaderboard",
        description="Show the server XP leaderboard"
    )
    async def leaderboard(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get("xp", 0),
            reverse=True
        )

        if not ranking:
            await interaction.response.send_message(
                "📊 No XP data yet."
            )
            return

        lines = []

        medals = ["🥇", "🥈", "🥉"]

        for index, (uid, data) in enumerate(
            ranking[:10],
            start=1
        ):

            member = interaction.guild.get_member(
                int(uid)
            )

            if member:
                name = member.display_name
            else:
                name = f"User {uid}"

            level, _, _ = calculate_level(
                data.get("xp", 0)
            )

            prefix = (
                medals[index - 1]
                if index <= 3
                else f"**#{index}**"
            )

            lines.append(
                f"{prefix} {name} — "
                f"Level **{level}** • "
                f"**{data.get('xp', 0):,} XP**"
            )

        embed = discord.Embed(
            title="🏆 Server XP Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold()
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # PREFIX ,leaderboard
    # ========================================================

    @commands.command(
        name="leaderboard",
        aliases=["lb", "levels"]
    )
    async def prefix_leaderboard(self, ctx):

        config = guild_config(ctx.guild.id)

        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get("xp", 0),
            reverse=True
        )

        if not ranking:
            await ctx.send("📊 No XP data yet.")
            return

        lines = []

        medals = ["🥇", "🥈", "🥉"]

        for index, (uid, data) in enumerate(
            ranking[:10],
            start=1
        ):

            member = ctx.guild.get_member(
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
                f"{prefix} {name} — "
                f"Level **{level}** • "
                f"**{data.get('xp', 0):,} XP**"
            )

        embed = discord.Embed(
            title="🏆 Server XP Leaderboard",
            description="\n".join(lines),
            color=discord.Color.gold()
        )

        await ctx.send(embed=embed)

    # ========================================================
    # /leveling enable
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
            "✅ Leveling system enabled."
        )

    # ========================================================
    # /leveling disable
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
            "🔴 Leveling system disabled."
        )

    # ========================================================
    # /leveling xp
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
            f"✅ XP per message set to **{amount} XP**."
        )

    # ========================================================
    # /leveling cooldown
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
            f"✅ XP cooldown set to **{seconds}s**."
        )

    # ========================================================
    # /leveling announce
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

        status = "enabled" if enabled else "disabled"

        await interaction.response.send_message(
            f"✅ Level-up announcements **{status}**."
        )

    # ========================================================
    # /leveling channel
    # ========================================================

    @leveling.command(
        name="channel",
        description="Set level-up announcement channel"
    )
    @app_commands.describe(
        channel="Announcement channel"
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
            f"✅ Level announcements will be sent in {channel.mention}."
        )

    # ========================================================
    # /leveling message
    # ========================================================

    @leveling.command(
        name="message",
        description="Set custom level-up message"
    )
    @app_commands.describe(
        message="Custom message"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def leveling_message(
        self,
        interaction: discord.Interaction,
        message: str
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["level_message"] = message

        save_data(DATA)

        await interaction.response.send_message(
            "✅ Level-up message updated.\n\n"
            "**Variables:** "
            "`{user}` `{username}` `{level}` `{xp}` `{server}` `{membercount}`"
        )

    # ========================================================
    # /levelrole add
    # ========================================================

    @levelrole.command(
        name="add",
        description="Give a role when a member reaches a level"
    )
    @app_commands.describe(
        level="Required level",
        role="Reward role"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def levelrole_add(
        self,
        interaction: discord.Interaction,
        level: app_commands.Range[int, 1, 10000],
        role: discord.Role
    ):

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ I cannot manage that role. "
                "Move my bot role above the reward role.",
                ephemeral=True
            )
            return

        config = guild_config(
            interaction.guild.id
        )

        config["role_rewards"][str(level)] = role.id

        save_data(DATA)

        await interaction.response.send_message(
            f"✅ **Level {level}** reward set to {role.mention}."
        )

    # ========================================================
    # /levelrole remove
    # ========================================================

    @levelrole.command(
        name="remove",
        description="Remove a level reward"
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
        level: app_commands.Range[int, 1, 10000]
    ):

        config = guild_config(
            interaction.guild.id
        )

        removed = config["role_rewards"].pop(
            str(level),
            None
        )

        save_data(DATA)

        if removed:
            await interaction.response.send_message(
                f"✅ Level **{level}** reward removed."
            )
        else:
            await interaction.response.send_message(
                f"ℹ️ No reward was configured for level **{level}**."
            )

    # ========================================================
    # /levelrole list
    # ========================================================

    @levelrole.command(
        name="list",
        description="List level reward roles"
    )
    async def levelrole_list(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        rewards = config["role_rewards"]

        if not rewards:
            await interaction.response.send_message(
                "📋 No level reward roles configured."
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

            role_text = (
                role.mention
                if role
                else f"`Deleted role ({role_id})`"
            )

            lines.append(
                f"**Level {level}** → {role_text}"
            )

        embed = discord.Embed(
            title="🎁 Level Rewards",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # /leveling ignore-channel
    # ========================================================

    @leveling.command(
        name="ignore-channel",
        description="Ignore a channel for XP"
    )
    @app_commands.describe(
        channel="Channel to ignore"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def ignore_channel(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        config = guild_config(
            interaction.guild.id
        )

        if channel.id not in config["ignored_channels"]:
            config["ignored_channels"].append(
                channel.id
            )

        save_data(DATA)

        await interaction.response.send_message(
            f"🚫 {channel.mention} is now ignored for XP."
        )

    # ========================================================
    # /leveling ignore-role
    # ========================================================

    @leveling.command(
        name="ignore-role",
        description="Ignore a role for XP"
    )
    @app_commands.describe(
        role="Role to ignore"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def ignore_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role
    ):

        config = guild_config(
            interaction.guild.id
        )

        if role.id not in config["ignored_roles"]:
            config["ignored_roles"].append(
                role.id
            )

        save_data(DATA)

        await interaction.response.send_message(
            f"🚫 {role.mention} is now ignored for XP."
        )

    # ========================================================
    # /leveling add-xp
    # ========================================================

    @leveling.command(
        name="add-xp",
        description="Give XP to a member"
    )
    @app_commands.describe(
        member="Member",
        amount="XP amount"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def add_xp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1000000]
    ):

        config = guild_config(
            interaction.guild.id
        )

        user = user_data(
            config,
            member.id
        )

        old_level, _, _ = calculate_level(
            user["xp"]
        )

        user["xp"] += amount

        new_level, _, _ = calculate_level(
            user["xp"]
        )

        save_data(DATA)

        await interaction.response.send_message(
            f"✅ Added **{amount:,} XP** to {member.mention}.\n"
            f"⭐ Level: **{new_level}**"
        )

        if new_level > old_level:
            for level in range(
                old_level + 1,
                new_level + 1
            ):
                await self.handle_level_up(
                    interaction.guild,
                    member,
                    level
                )

    # ========================================================
    # /leveling remove-xp
    # ========================================================

    @leveling.command(
        name="remove-xp",
        description="Remove XP from a member"
    )
    @app_commands.describe(
        member="Member",
        amount="XP amount"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def remove_xp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1000000]
    ):

        config = guild_config(
            interaction.guild.id
        )

        user = user_data(
            config,
            member.id
        )

        user["xp"] = max(
            0,
            user["xp"] - amount
        )

        save_data(DATA)

        level, _, _ = calculate_level(
            user["xp"]
        )

        await interaction.response.send_message(
            f"✅ Removed **{amount:,} XP** from {member.mention}.\n"
            f"⭐ Current level: **{level}**"
        )

    # ========================================================
    # /leveling reset-user
    # ========================================================

    @leveling.command(
        name="reset-user",
        description="Reset a member's XP"
    )
    @app_commands.describe(
        member="Member to reset"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def reset_user(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):

        config = guild_config(
            interaction.guild.id
        )

        config["users"].pop(
            str(member.id),
            None
        )

        save_data(DATA)

        await interaction.response.send_message(
            f"♻️ Reset XP for {member.mention}."
        )

    # ========================================================
    # /leveling stats
    # ========================================================

    @leveling.command(
        name="stats",
        description="View leveling system statistics"
    )
    async def leveling_stats(
        self,
        interaction: discord.Interaction
    ):

        config = guild_config(
            interaction.guild.id
        )

        total_users = len(config["users"])

        total_xp = sum(
            user.get("xp", 0)
            for user in config["users"].values()
        )

        total_messages = sum(
            user.get("messages", 0)
            for user in config["users"].values()
        )

        embed = discord.Embed(
            title="📊 Leveling Statistics",
            color=discord.Color.blurple()
        )

        embed.add_field(
            name="👥 Users",
            value=f"**{total_users:,}**"
        )

        embed.add_field(
            name="✨ Total XP",
            value=f"**{total_xp:,}**"
        )

        embed.add_field(
            name="💬 Messages",
            value=f"**{total_messages:,}**"
        )

        embed.add_field(
            name="⚙️ Status",
            value=(
                "🟢 Enabled"
                if config["enabled"]
                else "🔴 Disabled"
            )
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # ERROR HANDLER
    # ========================================================

    async def cog_app_command_error(
        self,
        interaction,
        error
    ):

        if isinstance(
            error,
            app_commands.errors.MissingPermissions
        ):
            message = (
                "❌ You need **Manage Server** permission "
                "to use this command."
            )
        else:
            message = (
                f"❌ Leveling command error:\n"
                f"`{error}`"
            )

        if interaction.response.is_done():
            await interaction.followup.send(
                message,
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                message,
                ephemeral=True
            )


# ============================================================
# SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(Leveling(bot))
