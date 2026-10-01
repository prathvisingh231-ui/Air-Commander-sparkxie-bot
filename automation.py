# automode.py
# ============================================================
# Air Commander - AutoMode / Silent Protect
#
# PREFIX:
# ,automode enable
# ,automode disable
# ,automode status
# ,automode config
# ,automode spam 5 7
# ,automode warn 3
# ,automode timeout 5 10
# ,automode links on
# ,automode mentions on
# ,automode duplicates on
# ,automode whitelist user @User
# ,automode whitelist role @Role
# ,automode badword add word1 word2
# ,automode badword remove word1 word2
#
# SLASH:
# /automode enable
# /automode disable
# /automode status
# /automode config
# /automode whitelist user
# /automode whitelist role
# /automode badword add
# /automode badword remove
#
# ============================================================

import os
import json
import time
import re
import copy

from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

CONFIG_FILE = "automode_config.json"


DEFAULT_CONFIG = {
    "enabled": False,

    # Logs
    "log_channel_id": None,

    # Spam
    "spam_messages": 5,
    "spam_window": 7,

    # Warnings
    "warn_enabled": True,
    "warn_after": 3,

    # Timeout
    "timeout_enabled": True,
    "timeout_after": 5,
    "timeout_minutes": 10,

    # Link protection
    "link_protection": True,

    # Mention protection
    "mention_protection": True,
    "mention_limit": 5,

    # Duplicate message protection
    "duplicate_protection": True,
    "duplicate_limit": 3,

    # Bad word protection
    "badword_protection": True,
    "badwords": [],

    # Whitelist
    "whitelist_users": [],
    "whitelist_roles": [],

    # Per-user warning count
    "warnings": {}
}


# ============================================================
# CONFIG FUNCTIONS
# ============================================================

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


def save_config(data):
    try:
        with open(
            CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )
    except Exception:
        pass


def get_guild_config(guild_id: int):

    data = load_config()
    gid = str(guild_id)

    if gid not in data:

        data[gid] = copy.deepcopy(
            DEFAULT_CONFIG
        )

        save_config(data)

        return data[gid]

    config = data[gid]

    if not isinstance(config, dict):
        config = copy.deepcopy(
            DEFAULT_CONFIG
        )

    # Add missing settings from newer versions
    changed = False

    for key, value in DEFAULT_CONFIG.items():

        if key not in config:

            config[key] = copy.deepcopy(
                value
            )

            changed = True

    # Make sure lists/dicts have correct types
    if not isinstance(
        config.get("badwords"),
        list
    ):
        config["badwords"] = []

        changed = True

    if not isinstance(
        config.get("whitelist_users"),
        list
    ):
        config["whitelist_users"] = []

        changed = True

    if not isinstance(
        config.get("whitelist_roles"),
        list
    ):
        config["whitelist_roles"] = []

        changed = True

    if not isinstance(
        config.get("warnings"),
        dict
    ):
        config["warnings"] = {}

        changed = True

    if changed:

        data[gid] = config
        save_config(data)

    return config


def update_guild_config(
    guild_id: int,
    config
):
    data = load_config()

    data[str(guild_id)] = config

    save_config(data)


# ============================================================
# HELPERS
# ============================================================

def is_whitelisted(
    member: discord.Member,
    config
):

    if member.id in config.get(
        "whitelist_users",
        []
    ):
        return True

    member_roles = {
        role.id
        for role in member.roles
    }

    whitelist_roles = set(
        config.get(
            "whitelist_roles",
            []
        )
    )

    if member_roles.intersection(
        whitelist_roles
    ):
        return True

    return False


def contains_link(content: str):

    pattern = (
        r"(https?://"
        r"|www\."
        r"|discord\.gg/"
        r"|discord\.com/invite/)"
    )

    return (
        re.search(
            pattern,
            content.lower()
        )
        is not None
    )


def find_badword(
    content: str,
    badwords
):

    if not content:
        return None

    if not badwords:
        return None

    text = content.casefold()

    cleaned_words = []

    for word in badwords:

        word = str(word).strip().casefold()

        if word:
            cleaned_words.append(word)

    # Longest words/phrases first
    cleaned_words = sorted(
        set(cleaned_words),
        key=len,
        reverse=True
    )

    for word in cleaned_words:

        pattern = (
            rf"(?<!\w)"
            rf"{re.escape(word)}"
            rf"(?!\w)"
        )

        if re.search(
            pattern,
            text,
            flags=re.IGNORECASE
        ):
            return word

    return None


def parse_word_list(
    value: str
):

    if not value:
        return []

    # Supports:
    # word1
    # word2
    #
    # OR:
    # word1, word2, word3
    #
    # OR:
    # word1 word2
    #
    # Newline and comma are preferred
    # so phrases containing spaces work.

    parts = re.split(
        r"[\n,]+",
        value
    )

    result = []

    for item in parts:

        item = item.strip().casefold()

        if item and item not in result:
            result.append(item)

    return result


# ============================================================
# COG
# ============================================================

class AutoMode(commands.Cog):
    """
    Air Commander AutoMode / Silent Protect.
    """

    def __init__(
        self,
        bot
    ):

        self.bot = bot

        # guild_id -> user_id -> timestamps
        self.message_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

        # guild_id -> user_id -> recent messages
        self.duplicate_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

    # ========================================================
    # LOG CHANNEL
    # ========================================================

    async def get_log_channel(
        self,
        guild: discord.Guild
    ):

        config = get_guild_config(
            guild.id
        )

        channel_id = config.get(
            "log_channel_id"
        )

        if not channel_id:
            return None

        channel = guild.get_channel(
            channel_id
        )

        if channel:
            return channel

        return None

    # ========================================================
    # SERVER LOG
    # ========================================================

    async def send_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        user: discord.Member = None,
        action: str = None
    ):

        channel = await self.get_log_channel(
            guild
        )

        if not channel:
            return False

        embed = discord.Embed(
            title=f"🛡️ {title}",
            description=description,
            timestamp=discord.utils.utcnow()
        )

        if user:

            embed.add_field(
                name="User",
                value=(
                    f"{user.mention}\n"
                    f"`{user}`\n"
                    f"ID: `{user.id}`"
                ),
                inline=False
            )

        if action:

            embed.add_field(
                name="Action",
                value=f"`{action}`",
                inline=False
            )

        try:

            await channel.send(
                embed=embed
            )

            return True

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            return False

    # ========================================================
    # USER DM
    # ========================================================

    async def send_dm(
        self,
        member: discord.Member,
        title: str,
        description: str
    ):

        embed = discord.Embed(
            title=f"🛡️ {title}",
            description=description,
            timestamp=discord.utils.utcnow()
        )

        embed.set_footer(
            text=(
                f"Air Commander • "
                f"{member.guild.name}"
            )
        )

        try:

            await member.send(
                embed=embed
            )

            return True

        except (
            discord.Forbidden,
            discord.HTTPException,
            discord.NotFound
        ):
            # DM closed / blocked.
            # Never stop moderation.
            return False

    # ========================================================
    # ENABLE
    # ========================================================

    async def enable_automode(
        self,
        guild: discord.Guild
    ):

        config = get_guild_config(
            guild.id
        )

        if config.get("enabled"):

            return (
                None,
                "⚠️ **AutoMode is already enabled.**"
            )

        # Find existing commander logs
        channel = discord.utils.get(
            guild.text_channels,
            name="commander-logs"
        )

        # Create if missing
        if channel is None:

            try:

                channel = await guild.create_text_channel(
                    "commander-logs",
                    reason=(
                        "Air Commander "
                        "AutoMode enabled"
                    )
                )

            except discord.Forbidden:

                return (
                    None,
                    "❌ I don't have permission "
                    "to create channels."
                )

            except discord.HTTPException:

                return (
                    None,
                    "❌ Discord rejected the "
                    "channel creation request."
                )

        config["enabled"] = True
        config["log_channel_id"] = channel.id

        update_guild_config(
            guild.id,
            config
        )

        await self.send_log(
            guild,
            "AutoMode Enabled",
            (
                "Air Commander AutoMode "
                "has been enabled."
            ),
            action="AUTOMODE ENABLE"
        )

        return (
            channel,
            (
                "🛡️ **AutoMode enabled!**\n"
                f"📋 Logs: {channel.mention}\n\n"
                "Use `/automode config` "
                "to view protection settings."
            )
        )

    # ========================================================
    # DISABLE
    # ========================================================

    async def disable_automode(
        self,
        guild: discord.Guild
    ):

        config = get_guild_config(
            guild.id
        )

        if not config.get("enabled"):

            return (
                "⚠️ **AutoMode is already disabled.**"
            )

        config["enabled"] = False

        update_guild_config(
            guild.id,
            config
        )

        await self.send_log(
            guild,
            "AutoMode Disabled",
            (
                "AutoMode protection "
                "has been disabled."
            ),
            action="AUTOMODE DISABLE"
        )

        return (
            "🔴 **AutoMode disabled.**"
        )

    # ========================================================
    # WARNING
    # ========================================================

    async def warn_member(
        self,
        member: discord.Member,
        reason: str
    ):

        guild = member.guild

        config = get_guild_config(
            guild.id
        )

        warnings = config.setdefault(
            "warnings",
            {}
        )

        uid = str(member.id)

        warnings[uid] = (
            int(
                warnings.get(uid, 0)
            )
            + 1
        )

        count = warnings[uid]

        update_guild_config(
            guild.id,
            config
        )

        # Server log
        await self.send_log(
            guild,
            "Member Warned",
            (
                f"Reason: **{reason}**\n"
                f"Warning count: **{count}**"
            ),
            user=member,
            action="WARN"
        )

        # DM
        await self.send_dm(
            member,
            "You received a warning",
            (
                f"You have received a warning "
                f"in **{guild.name}**.\n\n"
                f"**Reason:** {reason}\n"
                f"**Warning count:** `{count}`"
            )
        )

        return count

    # ========================================================
    # TIMEOUT
    # ========================================================

    async def timeout_member(
        self,
        member: discord.Member,
        reason: str
    ):

        config = get_guild_config(
            member.guild.id
        )

        minutes = int(
            config.get(
                "timeout_minutes",
                10
            )
        )

        try:

            await member.timeout(
                timedelta(
                    minutes=minutes
                ),
                reason=(
                    f"AutoMode: {reason}"
                )
            )

            # DM after successful timeout
            await self.send_dm(
                member,
                "You have been timed out",
                (
                    f"You have been timed out "
                    f"in **{member.guild.name}**.\n\n"
                    f"**Reason:** {reason}\n"
                    f"**Duration:** `{minutes} minutes`"
                )
            )

            await self.send_log(
                member.guild,
                "Member Timed Out",
                (
                    f"Reason: **{reason}**\n"
                    f"Duration: "
                    f"**{minutes} minutes**"
                ),
                user=member,
                action="TIMEOUT"
            )

            return True

        except discord.Forbidden:

            await self.send_log(
                member.guild,
                "Moderation Failed",
                (
                    "I could not timeout this member "
                    "because of permissions or "
                    "role hierarchy."
                ),
                user=member,
                action="TIMEOUT FAILED"
            )

            return False

        except discord.HTTPException:

            return False

    # ========================================================
    # ESCALATION
    # ========================================================

    async def handle_escalation(
        self,
        member: discord.Member,
        warning_count: int,
        reason: str
    ):

        config = get_guild_config(
            member.guild.id
        )

        warn_after = int(
            config.get(
                "warn_after",
                3
            )
        )

        timeout_after = int(
            config.get(
                "timeout_after",
                5
            )
        )

        # Timeout
        if (
            config.get(
                "timeout_enabled",
                True
            )
            and warning_count >= timeout_after
        ):

            await self.timeout_member(
                member,
                (
                    f"{reason} | "
                    f"{warning_count} warnings"
                )
            )

            return

        # Warning threshold log
        if (
            config.get(
                "warn_enabled",
                True
            )
            and warning_count >= warn_after
        ):

            await self.send_log(
                member.guild,
                "Warning Threshold Reached",
                (
                    f"{member.mention} reached "
                    f"**{warning_count} warnings**."
                ),
                user=member,
                action="WARNING THRESHOLD"
            )

    # ========================================================
    # MESSAGE PROTECTION
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message: discord.Message
    ):

        # Ignore bots
        if message.author.bot:
            return

        # Ignore DMs
        if not message.guild:
            return

        config = get_guild_config(
            message.guild.id
        )

        # AutoMode disabled
        if not config.get("enabled"):
            return

        member = message.author

        if not isinstance(
            member,
            discord.Member
        ):
            return

        # Administrators bypass AutoMode
        if member.guild_permissions.administrator:
            return

        # Whitelisted users/roles bypass
        if is_whitelisted(
            member,
            config
        ):
            return

        now = time.monotonic()

        # ====================================================
        # MESSAGE TRACKER
        # ====================================================

        user_messages = (
            self.message_tracker[
                message.guild.id
            ][member.id]
        )

        window = int(
            config.get(
                "spam_window",
                7
            )
        )

        while (
            user_messages
            and now - user_messages[0] > window
        ):
            user_messages.popleft()

        user_messages.append(now)

        # ====================================================
        # BAD WORD PROTECTION
        # ====================================================

        if config.get(
            "badword_protection",
            True
        ):

            badword = find_badword(
                message.content,
                config.get(
                    "badwords",
                    []
                )
            )

            if badword:

                try:

                    await message.delete()

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

                count = await self.warn_member(
                    member,
                    "Blocked word detected"
                )

                # Log without displaying
                # the actual offensive word
                await self.send_log(
                    message.guild,
                    "Bad Word Detected",
                    (
                        "A blocked word/phrase "
                        "was detected and "
                        "the message was removed."
                    ),
                    user=member,
                    action="BADWORD"
                )

                await self.handle_escalation(
                    member,
                    count,
                    "Blocked word detected"
                )

                return

        # ====================================================
        # LINK PROTECTION
        # ====================================================

        if config.get(
            "link_protection",
            True
        ):

            if contains_link(
                message.content
            ):

                try:

                    await message.delete()

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

                count = await self.warn_member(
                    member,
                    "Unauthorized link"
                )

                await self.handle_escalation(
                    member,
                    count,
                    "Unauthorized link"
                )

                return

        # ====================================================
        # MENTION SPAM
        # ====================================================

        if config.get(
            "mention_protection",
            True
        ):

            mention_count = (
                len(message.mentions)
                + len(message.role_mentions)
            )

            limit = int(
                config.get(
                    "mention_limit",
                    5
                )
            )

            if mention_count >= limit:

                try:

                    await message.delete()

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

                count = await self.warn_member(
                    member,
                    (
                        f"Mention spam "
                        f"({mention_count} mentions)"
                    )
                )

                await self.handle_escalation(
                    member,
                    count,
                    "Mention spam"
                )

                return

        # ====================================================
        # DUPLICATE MESSAGE PROTECTION
        # ====================================================

        if config.get(
            "duplicate_protection",
            True
        ):

            recent = (
                self.duplicate_tracker[
                    message.guild.id
                ][member.id]
            )

            normalized_message = (
                message.content
                .lower()
                .strip()
            )

            recent.append(
                normalized_message
            )

            while len(recent) > 5:
                recent.popleft()

            duplicate_limit = int(
                config.get(
                    "duplicate_limit",
                    3
                )
            )

            if (
                normalized_message
                and list(recent).count(
                    normalized_message
                ) >= duplicate_limit
            ):

                try:

                    await message.delete()

                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

                count = await self.warn_member(
                    member,
                    "Repeated duplicate messages"
                )

                await self.handle_escalation(
                    member,
                    count,
                    "Duplicate spam"
                )

                return

        # ====================================================
        # GENERAL SPAM
        # ====================================================

        spam_limit = int(
            config.get(
                "spam_messages",
                5
            )
        )

        if len(user_messages) >= spam_limit:

            # Reset tracker
            user_messages.clear()

            try:

                await message.delete()

            except (
                discord.Forbidden,
                discord.HTTPException
            ):
                pass

            count = await self.warn_member(
                member,
                (
                    f"Spam detected "
                    f"({spam_limit} messages)"
                )
            )

            await self.handle_escalation(
                member,
                count,
                "Message spam"
            )

    # ========================================================
    # AUTOMODE SLASH GROUP
    # ========================================================

    automode_group = app_commands.Group(
        name="automode",
        description=(
            "Configure Air Commander AutoMode"
        )
    )

    # ========================================================
    # ENABLE
    # ========================================================

    @automode_group.command(
        name="enable",
        description="Enable AutoMode"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def automode_enable(
        self,
        interaction: discord.Interaction
    ):

        channel, result = (
            await self.enable_automode(
                interaction.guild
            )
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

    # ========================================================
    # DISABLE
    # ========================================================

    @automode_group.command(
        name="disable",
        description="Disable AutoMode"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def automode_disable(
        self,
        interaction: discord.Interaction
    ):

        result = (
            await self.disable_automode(
                interaction.guild
            )
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

    # ========================================================
    # STATUS
    # ========================================================

    @automode_group.command(
        name="status",
        description="View AutoMode status"
    )
    async def automode_status(
        self,
        interaction: discord.Interaction
    ):

        config = get_guild_config(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="🛡️ Air Commander AutoMode",
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="Status",
            value=(
                "🟢 Enabled"
                if config.get("enabled")
                else "🔴 Disabled"
            ),
            inline=False
        )

        log_channel = (
            interaction.guild.get_channel(
                config.get(
                    "log_channel_id"
                )
            )
        )

        embed.add_field(
            name="Commander Logs",
            value=(
                log_channel.mention
                if log_channel
                else "Not configured"
            ),
            inline=False
        )

        embed.add_field(
            name="Spam",
            value=(
                f"`{config.get('spam_messages')}` "
                f"messages / "
                f"`{config.get('spam_window')}s`"
            ),
            inline=True
        )

        embed.add_field(
            name="Warning",
            value=(
                f"`{config.get('warn_after')}` "
                f"warnings"
            ),
            inline=True
        )

        embed.add_field(
            name="Timeout",
            value=(
                f"`{config.get('timeout_after')}` "
                f"warnings\n"
                f"`{config.get('timeout_minutes')}` "
                f"minutes"
            ),
            inline=True
        )

        embed.add_field(
            name="Protection",
            value=(
                f"Links: "
                f"{'ON' if config.get('link_protection') else 'OFF'}\n"
                f"Mentions: "
                f"{'ON' if config.get('mention_protection') else 'OFF'}\n"
                f"Duplicates: "
                f"{'ON' if config.get('duplicate_protection') else 'OFF'}\n"
                f"Bad Words: "
                f"{'ON' if config.get('badword_protection') else 'OFF'}"
            ),
            inline=False
        )

        embed.add_field(
            name="Bad Words",
            value=(
                f"`{len(config.get('badwords', []))}` "
                "blocked"
            ),
            inline=True
        )

        embed.add_field(
            name="Whitelist",
            value=(
                f"Users: "
                f"`{len(config.get('whitelist_users', []))}`\n"
                f"Roles: "
                f"`{len(config.get('whitelist_roles', []))}`"
            ),
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # CONFIG
    # ========================================================

    @automode_group.command(
        name="config",
        description="View AutoMode configuration"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def automode_config(
        self,
        interaction: discord.Interaction
    ):

        config = get_guild_config(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="⚙️ AutoMode Configuration",
            description=(
                "Current AutoMode protection settings."
            )
        )

        embed.add_field(
            name="Spam",
            value=(
                f"Messages: "
                f"`{config['spam_messages']}`\n"
                f"Window: "
                f"`{config['spam_window']} seconds`"
            ),
            inline=False
        )

        embed.add_field(
            name="Warnings",
            value=(
                f"Enabled: "
                f"`{config['warn_enabled']}`\n"
                f"Threshold: "
                f"`{config['warn_after']}`"
            ),
            inline=False
        )

        embed.add_field(
            name="Timeout",
            value=(
                f"Enabled: "
                f"`{config['timeout_enabled']}`\n"
                f"Threshold: "
                f"`{config['timeout_after']} warnings`\n"
                f"Duration: "
                f"`{config['timeout_minutes']} minutes`"
            ),
            inline=False
        )

        embed.add_field(
            name="Protection",
            value=(
                f"Links: "
                f"`{config['link_protection']}`\n"
                f"Mentions: "
                f"`{config['mention_protection']}`\n"
                f"Duplicates: "
                f"`{config['duplicate_protection']}`\n"
                f"Bad Words: "
                f"`{config['badword_protection']}`"
            ),
            inline=False
        )

        embed.add_field(
            name="Bad Word Database",
            value=(
                f"Blocked words/phrases: "
                f"`{len(config.get('badwords', []))}`"
            ),
            inline=False
        )

        embed.set_footer(
            text=(
                "Use prefix config commands "
                "to change values."
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # WHITELIST SLASH GROUP
    # ========================================================

    whitelist_group = app_commands.Group(
        name="whitelist",
        description="Manage AutoMode whitelist",
        parent=automode_group
    )

    @whitelist_group.command(
        name="user",
        description="Whitelist a user"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def whitelist_user(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):

        config = get_guild_config(
            interaction.guild.id
        )

        users = config.setdefault(
            "whitelist_users",
            []
        )

        if user.id in users:

            return await interaction.response.send_message(
                f"ℹ️ {user.mention} is already whitelisted.",
                ephemeral=True
            )

        users.append(
            user.id
        )

        update_guild_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            (
                f"✅ {user.mention} has been "
                "added to the AutoMode whitelist."
            ),
            ephemeral=True
        )

    @whitelist_group.command(
        name="role",
        description="Whitelist a role"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def whitelist_role(
        self,
        interaction: discord.Interaction,
        role: discord.Role
    ):

        config = get_guild_config(
            interaction.guild.id
        )

        roles = config.setdefault(
            "whitelist_roles",
            []
        )

        if role.id in roles:

            return await interaction.response.send_message(
                f"ℹ️ {role.mention} is already whitelisted.",
                ephemeral=True
            )

        roles.append(
            role.id
        )

        update_guild_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            (
                f"✅ {role.mention} has been "
                "added to the AutoMode whitelist."
            ),
            ephemeral=True
        )

    # ========================================================
    # BADWORD SLASH GROUP
    # ========================================================

    badword_group = app_commands.Group(
        name="badword",
        description="Manage AutoMode blocked words",
        parent=automode_group
    )

    # ========================================================
    # BADWORD ADD
    # ========================================================

    @badword_group.command(
        name="add",
        description=(
            "Add up to 100 blocked words or phrases"
        )
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def badword_add(
        self,
        interaction: discord.Interaction,
        words: str
    ):

        config = get_guild_config(
            interaction.guild.id
        )

        new_words = parse_word_list(
            words
        )

        if not new_words:

            return await interaction.response.send_message(
                (
                    "❌ Please provide at least "
                    "one word or phrase."
                ),
                ephemeral=True
            )

        if len(new_words) > 100:

            return await interaction.response.send_message(
                (
                    "❌ You can add a maximum "
                    "of **100 words/phrases** "
                    "at once."
                ),
                ephemeral=True
            )

        badwords = config.setdefault(
            "badwords",
            []
        )

        added = []
        existing = []

        for word in new_words:

            if word in badwords:

                existing.append(
                    word
                )

            else:

                badwords.append(
                    word
                )

                added.append(
                    word
                )

        update_guild_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            (
                "✅ **Bad Words Updated**\n\n"
                f"Added: **{len(added)}**\n"
                f"Already existed: **{len(existing)}**\n"
                f"Total blocked: "
                f"**{len(badwords)}**"
            ),
            ephemeral=True
        )

    # ========================================================
    # BADWORD REMOVE
    # ========================================================

    @badword_group.command(
        name="remove",
        description=(
            "Remove up to 100 blocked words or phrases"
        )
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def badword_remove(
        self,
        interaction: discord.Interaction,
        words: str
    ):

        config = get_guild_config(
            interaction.guild.id
        )

        remove_words = parse_word_list(
            words
        )

        if not remove_words:

            return await interaction.response.send_message(
                (
                    "❌ Please provide at least "
                    "one word or phrase."
                ),
                ephemeral=True
            )

        if len(remove_words) > 100:

            return await interaction.response.send_message(
                (
                    "❌ You can remove a maximum "
                    "of **100 words/phrases** "
                    "at once."
                ),
                ephemeral=True
            )

        badwords = config.setdefault(
            "badwords",
            []
        )

        removed = []
        not_found = []

        for word in remove_words:

            if word in badwords:

                badwords.remove(
                    word
                )

                removed.append(
                    word
                )

            else:

                not_found.append(
                    word
                )

        update_guild_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            (
                "✅ **Bad Words Updated**\n\n"
                f"Removed: **{len(removed)}**\n"
                f"Not found: **{len(not_found)}**\n"
                f"Total blocked: "
                f"**{len(badwords)}**"
            ),
            ephemeral=True
        )

    # ========================================================
    # PREFIX AUTOMODE GROUP
    # ========================================================

    @commands.group(
        name="automode",
        invoke_without_command=True
    )
    @commands.has_guild_permissions(
        manage_guild=True
    )
    async def automode_prefix(
        self,
        ctx: commands.Context
    ):

        await ctx.send(
            "🛡️ **Air Commander AutoMode**\n\n"
            "`,automode enable`\n"
            "`,automode disable`\n"
            "`,automode status`\n"
            "`,automode config`\n"
            "`,automode spam <messages> <seconds>`\n"
            "`,automode warn <warnings>`\n"
            "`,automode timeout <warnings> <minutes>`\n"
            "`,automode links on/off`\n"
            "`,automode mentions on/off`\n"
            "`,automode duplicates on/off`\n"
            "`,automode whitelist user @User`\n"
            "`,automode whitelist role @Role`\n"
            "`,automode badword add <words>`\n"
            "`,automode badword remove <words>`"
        )

    # ========================================================
    # PREFIX ENABLE
    # ========================================================

    @automode_prefix.command(
        name="enable"
    )
    async def automode_prefix_enable(
        self,
        ctx: commands.Context
    ):

        _, result = await self.enable_automode(
            ctx.guild
        )

        await ctx.send(
            result
        )

    # ========================================================
    # PREFIX DISABLE
    # ========================================================

    @automode_prefix.command(
        name="disable"
    )
    async def automode_prefix_disable(
        self,
        ctx: commands.Context
    ):

        result = await self.disable_automode(
            ctx.guild
        )

        await ctx.send(
            result
        )

    # ========================================================
    # PREFIX STATUS
    # ========================================================

    @automode_prefix.command(
        name="status"
    )
    async def automode_prefix_status(
        self,
        ctx: commands.Context
    ):

        config = get_guild_config(
            ctx.guild.id
        )

        log_channel = (
            ctx.guild.get_channel(
                config.get(
                    "log_channel_id"
                )
            )
        )

        await ctx.send(
            "🛡️ **AutoMode Status**\n\n"
            f"Status: "
            f"{'🟢 Enabled' if config['enabled'] else '🔴 Disabled'}\n"
            f"Logs: "
            f"{log_channel.mention if log_channel else 'Not configured'}\n"
            f"Spam: "
            f"`{config['spam_messages']}` messages / "
            f"`{config['spam_window']}s`\n"
            f"Warn after: "
            f"`{config['warn_after']}`\n"
            f"Timeout after: "
            f"`{config['timeout_after']}` warnings\n"
            f"Timeout duration: "
            f"`{config['timeout_minutes']} min`\n"
            f"Links: "
            f"`{config['link_protection']}`\n"
            f"Mentions: "
            f"`{config['mention_protection']}`\n"
            f"Duplicates: "
            f"`{config['duplicate_protection']}`\n"
            f"Bad Words: "
            f"`{config['badword_protection']}`\n"
            f"Blocked Words: "
            f"`{len(config.get('badwords', []))}`"
        )

    # ========================================================
    # PREFIX CONFIG
    # ========================================================

    @automode_prefix.command(
        name="config"
    )
    async def automode_prefix_config(
        self,
        ctx: commands.Context
    ):

        await ctx.send(
            "⚙️ **AutoMode Config**\n\n"
            "`,automode spam <messages> <seconds>`\n"
            "`,automode warn <warnings>`\n"
            "`,automode timeout <warnings> <minutes>`\n"
            "`,automode links on/off`\n"
            "`,automode mentions on/off`\n"
            "`,automode duplicates on/off`"
        )

    # ========================================================
    # PREFIX SPAM
    # ========================================================

    @automode_prefix.command(
        name="spam"
    )
    async def automode_spam(
        self,
        ctx: commands.Context,
        messages: int,
        seconds: int
    ):

        if messages < 2:

            return await ctx.send(
                "❌ Spam message count must be at least `2`."
            )

        if seconds < 1:

            return await ctx.send(
                "❌ Spam window must be at least `1` second."
            )

        config = get_guild_config(
            ctx.guild.id
        )

        config["spam_messages"] = messages
        config["spam_window"] = seconds

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            (
                f"✅ Spam protection set to "
                f"**{messages} messages / "
                f"{seconds} seconds**."
            )
        )

    # ========================================================
    # PREFIX WARN
    # ========================================================

    @automode_prefix.command(
        name="warn"
    )
    async def automode_warn(
        self,
        ctx: commands.Context,
        warnings: int
    ):

        if warnings < 1:

            return await ctx.send(
                "❌ Warning threshold must be at least `1`."
            )

        config = get_guild_config(
            ctx.guild.id
        )

        config["warn_after"] = warnings

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            (
                f"✅ Warning threshold set to "
                f"**{warnings}**."
            )
        )

    # ========================================================
    # PREFIX TIMEOUT
    # ========================================================

    @automode_prefix.command(
        name="timeout"
    )
    async def automode_timeout(
        self,
        ctx: commands.Context,
        warnings: int,
        minutes: int
    ):

        if warnings < 1:

            return await ctx.send(
                "❌ Timeout warning threshold "
                "must be at least `1`."
            )

        if minutes < 1:

            return await ctx.send(
                "❌ Timeout duration must be at least `1` minute."
            )

        config = get_guild_config(
            ctx.guild.id
        )

        config["timeout_after"] = warnings
        config["timeout_minutes"] = minutes

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            (
                f"✅ Timeout will trigger at "
                f"**{warnings} warnings** "
                f"for **{minutes} minutes**."
            )
        )

    # ========================================================
    # PREFIX LINKS
    # ========================================================

    @automode_prefix.command(
        name="links"
    )
    async def automode_links(
        self,
        ctx: commands.Context,
        state: str
    ):

        state = state.lower()

        if state not in (
            "on",
            "off"
        ):

            return await ctx.send(
                "Use `on` or `off`."
            )

        config = get_guild_config(
            ctx.guild.id
        )

        config["link_protection"] = (
            state == "on"
        )

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"🔗 Link protection: **{state.upper()}**"
        )

    # ========================================================
    # PREFIX MENTIONS
    # ========================================================

    @automode_prefix.command(
        name="mentions"
    )
    async def automode_mentions(
        self,
        ctx: commands.Context,
        state: str
    ):

        state = state.lower()

        if state not in (
            "on",
            "off"
        ):

            return await ctx.send(
                "Use `on` or `off`."
            )

        config = get_guild_config(
            ctx.guild.id
        )

        config["mention_protection"] = (
            state == "on"
        )

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"📢 Mention protection: **{state.upper()}**"
        )

    # ========================================================
    # PREFIX DUPLICATES
    # ========================================================

    @automode_prefix.command(
        name="duplicates"
    )
    async def automode_duplicates(
        self,
        ctx: commands.Context,
        state: str
    ):

        state = state.lower()

        if state not in (
            "on",
            "off"
        ):

            return await ctx.send(
                "Use `on` or `off`."
            )

        config = get_guild_config(
            ctx.guild.id
        )

        config["duplicate_protection"] = (
            state == "on"
        )

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"♻️ Duplicate protection: **{state.upper()}**"
        )

    # ========================================================
    # PREFIX WHITELIST GROUP
    # ========================================================

    @automode_prefix.group(
        name="whitelist",
        invoke_without_command=True
    )
    async def whitelist_prefix(
        self,
        ctx: commands.Context
    ):

        await ctx.send(
            "🛡️ **AutoMode Whitelist**\n\n"
            "`,automode whitelist user @User`\n"
            "`,automode whitelist role @Role`"
        )

    # ========================================================
    # PREFIX WHITELIST USER
    # ========================================================

    @whitelist_prefix.command(
        name="user"
    )
    async def whitelist_prefix_user(
        self,
        ctx: commands.Context,
        member: discord.Member
    ):

        config = get_guild_config(
            ctx.guild.id
        )

        users = config.setdefault(
            "whitelist_users",
            []
        )

        if member.id in users:

            return await ctx.send(
                f"ℹ️ {member.mention} is already whitelisted."
            )

        users.append(
            member.id
        )

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ {member.mention} is now whitelisted."
        )

    # ========================================================
    # PREFIX WHITELIST ROLE
    # ========================================================

    @whitelist_prefix.command(
        name="role"
    )
    async def whitelist_prefix_role(
        self,
        ctx: commands.Context,
        role: discord.Role
    ):

        config = get_guild_config(
            ctx.guild.id
        )

        roles = config.setdefault(
            "whitelist_roles",
            []
        )

        if role.id in roles:

            return await ctx.send(
                f"ℹ️ {role.mention} is already whitelisted."
            )

        roles.append(
            role.id
        )

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ {role.mention} is now whitelisted."
        )

    # ========================================================
    # PREFIX BADWORD GROUP
    # ========================================================

    @automode_prefix.group(
        name="badword",
        invoke_without_command=True
    )
    async def badword_prefix(
        self,
        ctx: commands.Context
    ):

        await ctx.send(
            "🚫 **Bad Word Protection**\n\n"
            "`,automode badword add word1, word2`\n"
            "`,automode badword remove word1, word2`"
        )

    # ========================================================
    # PREFIX BADWORD ADD
    # ========================================================

    @badword_prefix.command(
        name="add"
    )
    async def badword_prefix_add(
        self,
        ctx: commands.Context,
        *,
        words: str
    ):

        config = get_guild_config(
            ctx.guild.id
        )

        new_words = parse_word_list(
            words
        )

        if not new_words:

            return await ctx.send(
                "❌ Please provide at least one word or phrase."
            )

        if len(new_words) > 100:

            return await ctx.send(
                (
                    "❌ You can add a maximum "
                    "of **100 words/phrases** at once."
                )
            )

        badwords = config.setdefault(
            "badwords",
            []
        )

        added = 0
        existing = 0

        for word in new_words:

            if word in badwords:

                existing += 1

            else:

                badwords.append(
                    word
                )

                added += 1

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            (
                "✅ **Bad Words Updated**\n\n"
                f"Added: **{added}**\n"
                f"Already existed: **{existing}**\n"
                f"Total blocked: "
                f"**{len(badwords)}**"
            )
        )

    # ========================================================
    # PREFIX BADWORD REMOVE
    # ========================================================

    @badword_prefix.command(
        name="remove"
    )
    async def badword_prefix_remove(
        self,
        ctx: commands.Context,
        *,
        words: str
    ):

        config = get_guild_config(
            ctx.guild.id
        )

        remove_words = parse_word_list(
            words
        )

        if not remove_words:

            return await ctx.send(
                "❌ Please provide at least one word or phrase."
            )

        if len(remove_words) > 100:

            return await ctx.send(
                (
                    "❌ You can remove a maximum "
                    "of **100 words/phrases** at once."
                )
            )

        badwords = config.setdefault(
            "badwords",
            []
        )

        removed = 0
        not_found = 0

        for word in remove_words:

            if word in badwords:

                badwords.remove(
                    word
                )

                removed += 1

            else:

                not_found += 1

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            (
                "✅ **Bad Words Updated**\n\n"
                f"Removed: **{removed}**\n"
                f"Not found: **{not_found}**\n"
                f"Total blocked: "
                f"**{len(badwords)}**"
            )
        )


# ============================================================
# SETUP
# ============================================================

async def setup(bot):

    await bot.add_cog(
        AutoMode(bot)
    )
