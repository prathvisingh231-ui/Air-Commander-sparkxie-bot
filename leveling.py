# ============================================================
# AIR COMMANDER — ADVANCED LEVELING SYSTEM
# PREFIX + SLASH VERSION
# ============================================================

import json
import os
import time
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

    # --------------------------------------------------------
    # SLASH GROUPS
    # --------------------------------------------------------

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

        old_level, _, _ = calculate_level(
            old_xp
        )

        gained = config["xp_per_message"]

        multiplier = 1.0

        # Role boosters
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

        # Channel booster
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

        config = guild_config(
            ctx.guild.id
        )

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

        config = guild_config(
            interaction.guild.id
        )

        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get(
                "xp",
                0
            ),
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

        config = guild_config(
            ctx.guild.id
        )

        ranking = sorted(
            config["users"].items(),
            key=lambda item: item[1].get(
                "xp",
                0
            ),
            reverse=True
        )

        if not ranking:
            await ctx.send(
                "📊 No XP data yet."
            )
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
            "✅ Leveling system enabled."
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
            "🔴 Leveling system disabled."
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
            f"✅ XP per message set to **{amount} XP**."
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
            f"✅ XP cooldown set to **{seconds}s**."
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
            f"✅ Level-up announcements **{status}**."
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

        await ctx.send(
            "📊 **Leveling Configuration**\n\n"
            "`,leveling enable`\n"
            "`,leveling disable`\n"
            "`,leveling xp <amount>`\n"
            "`,leveling cooldown <seconds>`\n"
            "`,leveling announce <on/off>`\n"
            "`,leveling channel #channel`\n"
            "`,leveling channelreset`"
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
            "✅ **Leveling system enabled.**"
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
            "🔴 **Leveling system disabled.**"
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
                "❌ XP must be between **1 and 1000**."
            )
            return

        config = guild_config(
            ctx.guild.id
        )

        config["xp_per_message"] = amount
        save_data(DATA)

        await ctx.send(
            f"✅ XP per message set to **{amount} XP**."
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
                "❌ Cooldown must be between **0 and 3600 seconds**."
            )
            return

        config = guild_config(
            ctx.guild.id
        )

        config["cooldown"] = seconds
        save_data(DATA)

        await ctx.send(
            f"✅ XP cooldown set to **{seconds}s**."
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
                "❌ Use `on` or `off`.\n"
                "Example: `,leveling announce on`"
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
            f"✅ Level-up announcements **{status}**."
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
            f"✅ Level-up announcement channel set to "
            f"{channel.mention}."
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
            "✅ Level-up announcement channel reset."
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

        await ctx.send(
            "🏆 **Level Role Commands**\n\n"
            "`,levelrole add <level> @role`\n"
            "`,levelrole remove <level>`\n"
            "`,levelrole list`"
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
                "❌ Level must be **1 or higher**."
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
            f"✅ {role.mention} will be awarded "
            f"at **Level {level}**."
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
                f"❌ No reward role is configured "
                f"for Level **{level}**."
            )
            return

        save_data(DATA)

        await ctx.send(
            f"✅ Reward role for Level "
            f"**{level}** removed."
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
                "📋 No level reward roles configured."
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
                f"**Level {level}** → {role_name}"
            )

        embed = discord.Embed(
            title="🏆 Level Reward Roles",
            description="\n".join(lines),
            color=discord.Color.gold()
        )

        await ctx.send(
            embed=embed
        )


# ============================================================
# EXTENSION SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(Leveling(bot))
