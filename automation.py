# ============================================================
# AIR COMMANDER
# AUTOMODE + ADVANCED ANTI-NUKE
# ============================================================
#
# Prefix:
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
# ,automode badword add word1, word2
# ,automode badword remove word1, word2
#
# ,antinuke
#
# Slash:
# /automode enable
# /automode disable
# /automode status
# /automode config
# /automode whitelist user
# /automode whitelist role
# /automode badword add
# /automode badword remove
#
# /antinuke config
# /antinuke whitelist
# /antinuke unwhitelist
#
# ============================================================

import os
import json
import time
import re
import copy
import asyncio

from pathlib import Path
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands


# ============================================================
# FILES
# ============================================================

AUTOMODE_CONFIG_FILE = "automode_config.json"
ANTINUKE_CONFIG_FILE = "antinuke_config.json"


# ============================================================
# ============================================================
#                         AUTOMODE
# ============================================================
# ============================================================


AUTOMODE_DEFAULT_CONFIG = {
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

    # Duplicate protection
    "duplicate_protection": True,
    "duplicate_limit": 3,

    # Bad words
    "badword_protection": True,
    "badwords": [],

    # Whitelist
    "whitelist_users": [],
    "whitelist_roles": [],

    # Warnings
    "warnings": {}
}


# ============================================================
# AUTOMODE STORAGE
# ============================================================

def automode_load_all():
    if not os.path.exists(AUTOMODE_CONFIG_FILE):
        return {}

    try:
        with open(
            AUTOMODE_CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


def automode_save_all(data):
    try:
        with open(
            AUTOMODE_CONFIG_FILE,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

    except Exception as e:
        print(f"[AutoMode] Config save error: {e}")


def get_automode_config(guild_id: int):

    data = automode_load_all()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = copy.deepcopy(
            AUTOMODE_DEFAULT_CONFIG
        )

        automode_save_all(data)
        return data[gid]

    config = data[gid]

    if not isinstance(config, dict):
        config = copy.deepcopy(
            AUTOMODE_DEFAULT_CONFIG
        )

    changed = False

    # Add new settings
    for key, value in AUTOMODE_DEFAULT_CONFIG.items():

        if key not in config:
            config[key] = copy.deepcopy(value)
            changed = True

    # Validate containers
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
        automode_save_all(data)

    return config


def update_automode_config(
    guild_id: int,
    config
):
    data = automode_load_all()
    data[str(guild_id)] = config
    automode_save_all(data)


# ============================================================
# AUTOMODE HELPERS
# ============================================================

def automode_is_whitelisted(
    member: discord.Member,
    config
):

    if member.id in config.get(
        "whitelist_users",
        []
    ):
        return True

    role_ids = {
        role.id
        for role in member.roles
    }

    whitelist_roles = set(
        config.get(
            "whitelist_roles",
            []
        )
    )

    return bool(
        role_ids.intersection(
            whitelist_roles
        )
    )


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

    if not content or not badwords:
        return None

    text = content.casefold()

    cleaned = []

    for word in badwords:

        word = str(
            word
        ).strip().casefold()

        if word:
            cleaned.append(word)

    cleaned = sorted(
        set(cleaned),
        key=len,
        reverse=True
    )

    for word in cleaned:

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


def parse_word_list(value: str):

    if not value:
        return []

    parts = re.split(
        r"[\n,]+",
        value
    )

    result = []

    for item in parts:

        item = (
            item
            .strip()
            .casefold()
        )

        if item and item not in result:
            result.append(item)

    return result


# ============================================================
# ============================================================
#                    ANTI-NUKE CONFIG
# ============================================================
# ============================================================


ANTINUKE_DEFAULT_CONFIG = {

    "enabled": False,

    # Default punishment
    "action": "ban",

    # Logs
    "log_channel_id": None,

    # Trusted users/roles
    "whitelist_users": [],
    "whitelist_roles": [],

    # Detection thresholds
    "thresholds": {

        "ban": 3,
        "kick": 3,

        "channel_delete": 2,
        "channel_create": 5,

        "role_delete": 2,
        "role_create": 5,

        "webhook_delete": 3,

        "bot_add": 2,

        "guild_update": 2,

        "emoji_delete": 5,
        "emoji_create": 5,

        "sticker_delete": 5,
        "sticker_create": 5,

        "overwrite_update": 3,
    },

    # Detection window
    "window": 10,

    # Protection modules
    "modules": {

        "ban": True,
        "kick": True,

        "channel_delete": True,
        "channel_create": True,

        "role_delete": True,
        "role_create": True,

        "webhook_delete": True,

        "bot_add": True,

        "guild_update": True,

        "emoji_delete": True,
        "emoji_create": True,

        "sticker_delete": True,
        "sticker_create": True,

        "overwrite_update": True,
    }
}


# ============================================================
# ANTI-NUKE STORAGE
# ============================================================

def antinuke_load_all():

    if not os.path.exists(
        ANTINUKE_CONFIG_FILE
    ):
        return {}

    try:

        with open(
            ANTINUKE_CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


ANTINUKE_CONFIGS = antinuke_load_all()


def antinuke_save_all():

    temp = (
        Path(ANTINUKE_CONFIG_FILE)
        .with_suffix(".tmp")
    )

    try:

        with open(
            temp,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                ANTINUKE_CONFIGS,
                f,
                indent=4,
                ensure_ascii=False
            )

        temp.replace(
            ANTINUKE_CONFIG_FILE
        )

    except Exception as e:

        print(
            f"[AntiNuke] Config save error: {e}"
        )


def get_antinuke_config(
    guild_id: int
):

    gid = str(guild_id)

    if gid not in ANTINUKE_CONFIGS:

        ANTINUKE_CONFIGS[gid] = (
            json.loads(
                json.dumps(
                    ANTINUKE_DEFAULT_CONFIG
                )
            )
        )

        antinuke_save_all()

    cfg = ANTINUKE_CONFIGS[gid]

    if not isinstance(cfg, dict):
        cfg = json.loads(
            json.dumps(
                ANTINUKE_DEFAULT_CONFIG
            )
        )

    cfg.setdefault(
        "enabled",
        False
    )

    cfg.setdefault(
        "action",
        "ban"
    )

    cfg.setdefault(
        "log_channel_id",
        None
    )

    cfg.setdefault(
        "whitelist_users",
        []
    )

    cfg.setdefault(
        "whitelist_roles",
        []
    )

    cfg.setdefault(
        "thresholds",
        {}
    )

    cfg.setdefault(
        "window",
        10
    )

    cfg.setdefault(
        "modules",
        {}
    )

    for key, value in (
        ANTINUKE_DEFAULT_CONFIG[
            "thresholds"
        ].items()
    ):

        cfg["thresholds"].setdefault(
            key,
            value
        )

    for key, value in (
        ANTINUKE_DEFAULT_CONFIG[
            "modules"
        ].items()
    ):

        cfg["modules"].setdefault(
            key,
            value
        )

    ANTINUKE_CONFIGS[gid] = cfg

    return cfg


# ============================================================
# ANTI-NUKE HELPERS
# ============================================================

def status_text(value: bool):

    return (
        "🟢 Enabled"
        if value
        else "🔴 Disabled"
    )


def action_text(action: str):

    return {

        "ban": "🔨 Ban",
        "kick": "👢 Kick",
        "timeout": "⏱️ Timeout",
        "strip": "🧹 Strip Roles"

    }.get(
        action,
        str(action).title()
    )


def make_embed(
    title,
    description="",
    success=True
):

    embed = discord.Embed(
        title=title,
        description=description,
        colour=(
            discord.Colour.orange()
            if success
            else discord.Colour.red()
        ),
        timestamp=discord.utils.utcnow()
    )

    embed.set_footer(
        text="Air Commander • Security System"
    )

    return embed


async def public_send(
    interaction: discord.Interaction,
    *,
    embed=None,
    view=None
):

    if interaction.response.is_done():

        await interaction.followup.send(
            embed=embed,
            view=view
        )

    else:

        await interaction.response.send_message(
            embed=embed,
            view=view
        )


def is_admin(
    member: discord.Member
):

    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


def is_owner(
    member: discord.Member
):

    try:
        return (
            member.guild.owner_id
            == member.id
        )

    except Exception:
        return False


def antinuke_is_whitelisted(
    member: discord.Member,
    cfg
):

    if member.id in cfg.get(
        "whitelist_users",
        []
    ):
        return True

    if member.guild.owner_id == member.id:
        return True

    if (
        member.guild.me
        and member.id
        == member.guild.me.id
    ):
        return True

    role_ids = {
        role.id
        for role in member.roles
    }

    whitelist_roles = set(
        cfg.get(
            "whitelist_roles",
            []
        )
    )

    return bool(
        role_ids.intersection(
            whitelist_roles
        )
    )


# ============================================================
# SHARED SECURITY LOG
# ============================================================

async def ensure_antinuke_log_channel(
    guild: discord.Guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    existing_id = cfg.get(
        "log_channel_id"
    )

    if existing_id:

        channel = guild.get_channel(
            existing_id
        )

        if channel:
            return channel

    # Existing channel
    for channel in guild.text_channels:

        if channel.name.lower() in (
            "commander-antinuke-logs",
            "commander-security-logs"
        ):

            cfg["log_channel_id"] = (
                channel.id
            )

            antinuke_save_all()

            return channel

    me = guild.me

    overwrites = {

        guild.default_role:
        discord.PermissionOverwrite(
            view_channel=False
        )

    }

    if me:

        overwrites[me] = (
            discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                embed_links=True,
                read_message_history=True
            )
        )

    try:

        channel = await guild.create_text_channel(

            "commander-antinuke-logs",

            topic=(
                "Air Commander "
                "Anti-Nuke Security Logs"
            ),

            overwrites=overwrites,

            reason=(
                "Air Commander "
                "Anti-Nuke enabled"
            )
        )

        cfg["log_channel_id"] = (
            channel.id
        )

        antinuke_save_all()

        return channel

    except (
        discord.Forbidden,
        discord.HTTPException
    ):

        return None


async def send_antinuke_log(
    guild,
    title,
    description,
    colour=None
):

    if colour is None:
        colour = discord.Colour.orange()

    cfg = get_antinuke_config(
        guild.id
    )

    channel_id = cfg.get(
        "log_channel_id"
    )

    if not channel_id:
        return

    channel = guild.get_channel(
        channel_id
    )

    if not channel:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        colour=colour,
        timestamp=discord.utils.utcnow()
    )

    embed.set_footer(
        text="Air Commander • Anti-Nuke"
    )

    try:

        await channel.send(
            embed=embed
        )

    except (
        discord.Forbidden,
        discord.HTTPException
    ):
        pass


# ============================================================
# ANTI-NUKE ACTION HISTORY
# ============================================================

ANTI_NUKE_HISTORY = defaultdict(
    lambda: defaultdict(
        lambda: defaultdict(deque)
    )
)


def register_antinuke_action(
    guild_id,
    actor_id,
    action
):

    history = (
        ANTI_NUKE_HISTORY[
            guild_id
        ][actor_id][action]
    )

    now = time.monotonic()

    history.append(now)

    return history


def cleanup_antinuke_history(
    guild_id,
    actor_id,
    action,
    window
):

    history = (
        ANTI_NUKE_HISTORY[
            guild_id
        ][actor_id][action]
    )

    now = time.monotonic()

    while (
        history
        and now - history[0] > window
    ):

        history.popleft()

    return len(history)


# ============================================================
# ANTI-NUKE PUNISHMENT
# ============================================================

async def punish_member(
    guild: discord.Guild,
    member: discord.Member,
    cfg
):

    action = cfg.get(
        "action",
        "ban"
    )

    try:

        if action == "ban":

            await guild.ban(
                member,
                reason=(
                    "Air Commander "
                    "Anti-Nuke protection"
                )
            )

            return "Banned"

        if action == "kick":

            await guild.kick(
                member,
                reason=(
                    "Air Commander "
                    "Anti-Nuke protection"
                )
            )

            return "Kicked"

        if action == "timeout":

            await member.timeout(

                timedelta(
                    minutes=30
                ),

                reason=(
                    "Air Commander "
                    "Anti-Nuke protection"
                )
            )

            return "Timed out"

        if action == "strip":

            removable = []

            if not guild.me:
                return "Failed: bot member unavailable"

            for role in member.roles:

                if role.is_default():
                    continue

                if role >= guild.me.top_role:
                    continue

                removable.append(role)

            if removable:

                await member.remove_roles(
                    *removable,
                    reason=(
                        "Air Commander "
                        "Anti-Nuke protection"
                    )
                )

            return "Roles removed"

    except discord.Forbidden:

        return (
            "Failed: missing permissions "
            "or role hierarchy"
        )

    except discord.HTTPException:

        return (
            "Failed: Discord API error"
        )

    except Exception as e:

        print(
            f"[AntiNuke] Punishment error: {e}"
        )

        return "Failed: internal error"

    return "No action"


# ============================================================
# AUDIT LOG MAP
# ============================================================

AUDIT_ACTION_MAP = {

    discord.AuditLogAction.ban:
        "ban",

    discord.AuditLogAction.kick:
        "kick",

    discord.AuditLogAction.channel_delete:
        "channel_delete",

    discord.AuditLogAction.channel_create:
        "channel_create",

    discord.AuditLogAction.role_delete:
        "role_delete",

    discord.AuditLogAction.role_create:
        "role_create",

    discord.AuditLogAction.webhook_delete:
        "webhook_delete",

    discord.AuditLogAction.bot_add:
        "bot_add",

    discord.AuditLogAction.guild_update:
        "guild_update",

    discord.AuditLogAction.emoji_delete:
        "emoji_delete",

    discord.AuditLogAction.emoji_create:
        "emoji_create",

    discord.AuditLogAction.sticker_delete:
        "sticker_delete",

    discord.AuditLogAction.sticker_create:
        "sticker_create",

    discord.AuditLogAction.overwrite_update:
        "overwrite_update",
}


# ============================================================
# ANTI-NUKE AUDIT PROCESSOR
# ============================================================

async def process_audit_entry(
    bot,
    entry
):

    guild = entry.guild

    if guild is None:
        return

    cfg = get_antinuke_config(
        guild.id
    )

    if not cfg.get("enabled"):
        return

    action_type = AUDIT_ACTION_MAP.get(
        entry.action
    )

    if not action_type:
        return

    if not cfg["modules"].get(
        action_type,
        True
    ):
        return

    actor = entry.user

    if actor is None:
        return

    if not isinstance(
        actor,
        discord.Member
    ):

        actor = guild.get_member(
            actor.id
        )

    if actor is None:
        return

    # Trusted users are ignored
    if antinuke_is_whitelisted(
        actor,
        cfg
    ):
        return

    # Register action for THIS actor
    register_antinuke_action(
        guild.id,
        actor.id,
        action_type
    )

    count = cleanup_antinuke_history(
        guild.id,
        actor.id,
        action_type,
        int(
            cfg.get(
                "window",
                10
            )
        )
    )

    threshold = int(
        cfg["thresholds"].get(
            action_type,
            3
        )
    )

    # Detection log
    await send_antinuke_log(

        guild,

        "🚨 Anti-Nuke Detection",

        (
            f"**Executor:** {actor.mention}\n"
            f"**Action:** `{action_type}`\n"
            f"**Count:** `{count}/{threshold}`\n"
            f"**Window:** "
            f"`{cfg.get('window', 10)} seconds`"
        ),

        discord.Colour.red()
    )

    if count < threshold:
        return

    # Reset this actor/action
    ANTI_NUKE_HISTORY[
        guild.id
    ][actor.id][action_type].clear()

    result = await punish_member(
        guild,
        actor,
        cfg
    )

    await send_antinuke_log(

        guild,

        "🛡️ Anti-Nuke Punishment",

        (
            f"**User:** {actor.mention}\n"
            f"**Detected:** `{action_type}`\n"
            f"**Threshold:** `{threshold}`\n"
            f"**Punishment:** `{result}`"
        ),

        discord.Colour.dark_red()
    )


# ============================================================
# ============================================================
#                    AUTOMODE COG
# ============================================================
# ============================================================


class AutoMode(commands.Cog):

    def __init__(
        self,
        bot
    ):

        self.bot = bot

        # guild -> user -> timestamps
        self.message_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

        # guild -> user -> messages
        self.duplicate_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

    # ========================================================
    # AUTOMODE LOG CHANNEL
    # ========================================================

    async def get_log_channel(
        self,
        guild
    ):

        config = get_automode_config(
            guild.id
        )

        channel_id = config.get(
            "log_channel_id"
        )

        if not channel_id:
            return None

        return guild.get_channel(
            channel_id
        )

    # ========================================================
    # AUTOMODE LOG
    # ========================================================

    async def send_log(
        self,
        guild,
        title,
        description,
        user=None,
        action=None
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
    # AUTOMODE DM
    # ========================================================

    async def send_dm(
        self,
        member,
        title,
        description
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

            return False

    # ========================================================
    # AUTOMODE ENABLE
    # ========================================================

    async def enable_automode(
        self,
        guild
    ):

        config = get_automode_config(
            guild.id
        )

        if config.get("enabled"):

            return (
                None,
                "⚠️ **AutoMode is already enabled.**"
            )

        channel = discord.utils.get(
            guild.text_channels,
            name="commander-logs"
        )

        if channel is None:

            try:

                channel = (
                    await guild.create_text_channel(
                        "commander-logs",
                        reason=(
                            "Air Commander "
                            "AutoMode enabled"
                        )
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
        config["log_channel_id"] = (
            channel.id
        )

        update_automode_config(
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
    # AUTOMODE DISABLE
    # ========================================================

    async def disable_automode(
        self,
        guild
    ):

        config = get_automode_config(
            guild.id
        )

        if not config.get("enabled"):

            return (
                "⚠️ **AutoMode is already disabled.**"
            )

        config["enabled"] = False

        update_automode_config(
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
        member,
        reason
    ):

        guild = member.guild

        config = get_automode_config(
            guild.id
        )

        warnings = config.setdefault(
            "warnings",
            {}
        )

        uid = str(
            member.id
        )

        warnings[uid] = (
            int(
                warnings.get(
                    uid,
                    0
                )
            )
            + 1
        )

        count = warnings[uid]

        update_automode_config(
            guild.id,
            config
        )

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
        member,
        reason
    ):

        config = get_automode_config(
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

            await self.send_dm(

                member,

                "You have been timed out",

                (
                    f"You have been timed out "
                    f"in **{member.guild.name}**.\n\n"
                    f"**Reason:** {reason}\n"
                    f"**Duration:** "
                    f"`{minutes} minutes`"
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
                    "I could not timeout this "
                    "member because of permissions "
                    "or role hierarchy."
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
        member,
        warning_count,
        reason
    ):

        config = get_automode_config(
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

        # Timeout first
        if (
            config.get(
                "timeout_enabled",
                True
            )
            and warning_count
            >= timeout_after
        ):

            await self.timeout_member(
                member,
                (
                    f"{reason} | "
                    f"{warning_count} warnings"
                )
            )

            return

        if (
            config.get(
                "warn_enabled",
                True
            )
            and warning_count
            >= warn_after
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
    # AUTOMODE MESSAGE PROTECTION
    # ========================================================

    @commands.Cog.listener()
    async def on_message(
        self,
        message
    ):

        if message.author.bot:
            return

        if not message.guild:
            return

        config = get_automode_config(
            message.guild.id
        )

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
        if automode_is_whitelisted(
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
            and now - user_messages[0]
            > window
        ):

            user_messages.popleft()

        user_messages.append(now)

        # ====================================================
        # BAD WORD
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
        # DUPLICATE PROTECTION
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

            normalized = (
                message.content
                .lower()
                .strip()
            )

            recent.append(
                normalized
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
                normalized
                and list(recent).count(
                    normalized
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
    # SLASH ENABLE
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
        interaction
    ):

        _, result = (
            await self.enable_automode(
                interaction.guild
            )
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

    # ========================================================
    # SLASH DISABLE
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
        interaction
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
    # SLASH STATUS
    # ========================================================

    @automode_group.command(
        name="status",
        description="View AutoMode status"
    )
    async def automode_status(
        self,
        interaction
    ):

        config = get_automode_config(
            interaction.guild.id
        )

        log_channel = (
            interaction.guild.get_channel(
                config.get(
                    "log_channel_id"
                )
            )
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
    # SLASH CONFIG
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
        interaction
    ):

        config = get_automode_config(
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

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # AUTOMODE SLASH WHITELIST
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
        interaction,
        user: discord.Member
    ):

        config = get_automode_config(
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

        update_automode_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(

            f"✅ {user.mention} has been "
            "added to the AutoMode whitelist.",

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
        interaction,
        role: discord.Role
    ):

        config = get_automode_config(
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

        update_automode_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(

            f"✅ {role.mention} has been "
            "added to the AutoMode whitelist.",

            ephemeral=True
        )

    # ========================================================
    # AUTOMODE BADWORD SLASH
    # ========================================================

    badword_group = app_commands.Group(

        name="badword",

        description="Manage AutoMode blocked words",

        parent=automode_group
    )

    @badword_group.command(
        name="add",
        description="Add blocked words or phrases"
    )
    @app_commands.describe(
        words="Words separated by commas"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def badword_add(
        self,
        interaction,
        words: str
    ):

        config = get_automode_config(
            interaction.guild.id
        )

        new_words = parse_word_list(
            words
        )

        if not new_words:

            return await interaction.response.send_message(

                "❌ Please provide at least "
                "one word or phrase.",

                ephemeral=True
            )

        if len(new_words) > 100:

            return await interaction.response.send_message(

                "❌ Maximum 100 words/phrases at once.",

                ephemeral=True
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
                badwords.append(word)
                added += 1

        update_automode_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(

            "✅ **Bad Words Updated**\n\n"
            f"Added: **{added}**\n"
            f"Already existed: **{existing}**\n"
            f"Total blocked: **{len(badwords)}**",

            ephemeral=True
        )

    @badword_group.command(
        name="remove",
        description="Remove blocked words or phrases"
    )
    @app_commands.describe(
        words="Words separated by commas"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def badword_remove(
        self,
        interaction,
        words: str
    ):

        config = get_automode_config(
            interaction.guild.id
        )

        remove_words = parse_word_list(
            words
        )

        if not remove_words:

            return await interaction.response.send_message(

                "❌ Please provide at least "
                "one word or phrase.",

                ephemeral=True
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

        update_automode_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(

            "✅ **Bad Words Updated**\n\n"
            f"Removed: **{removed}**\n"
            f"Not found: **{not_found}**\n"
            f"Total blocked: **{len(badwords)}**",

            ephemeral=True
        )

    # ========================================================
    # AUTOMODE PREFIX GROUP
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
        ctx
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

    @automode_prefix.command(
        name="enable"
    )
    async def automode_prefix_enable(
        self,
        ctx
    ):

        _, result = await self.enable_automode(
            ctx.guild
        )

        await ctx.send(
            result
        )

    @automode_prefix.command(
        name="disable"
    )
    async def automode_prefix_disable(
        self,
        ctx
    ):

        result = await self.disable_automode(
            ctx.guild
        )

        await ctx.send(
            result
        )

    @automode_prefix.command(
        name="status"
    )
    async def automode_prefix_status(
        self,
        ctx
    ):

        config = get_automode_config(
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

    @automode_prefix.command(
        name="config"
    )
    async def automode_prefix_config(
        self,
        ctx
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

    @automode_prefix.command(
        name="spam"
    )
    async def automode_spam(
        self,
        ctx,
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

        config = get_automode_config(
            ctx.guild.id
        )

        config["spam_messages"] = messages
        config["spam_window"] = seconds

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(

            f"✅ Spam protection set to "
            f"**{messages} messages / "
            f"{seconds} seconds**."
        )

    @automode_prefix.command(
        name="warn"
    )
    async def automode_warn(
        self,
        ctx,
        warnings: int
    ):

        if warnings < 1:

            return await ctx.send(
                "❌ Warning threshold must be at least `1`."
            )

        config = get_automode_config(
            ctx.guild.id
        )

        config["warn_after"] = warnings

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ Warning threshold set to **{warnings}**."
        )

    @automode_prefix.command(
        name="timeout"
    )
    async def automode_timeout(
        self,
        ctx,
        warnings: int,
        minutes: int
    ):

        if warnings < 1:

            return await ctx.send(
                "❌ Timeout warning threshold must be at least `1`."
            )

        if minutes < 1:

            return await ctx.send(
                "❌ Timeout duration must be at least `1` minute."
            )

        config = get_automode_config(
            ctx.guild.id
        )

        config["timeout_after"] = warnings
        config["timeout_minutes"] = minutes

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(

            f"✅ Timeout will trigger at "
            f"**{warnings} warnings** "
            f"for **{minutes} minutes**."
        )

    @automode_prefix.command(
        name="links"
    )
    async def automode_links(
        self,
        ctx,
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

        config = get_automode_config(
            ctx.guild.id
        )

        config["link_protection"] = (
            state == "on"
        )

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"🔗 Link protection: **{state.upper()}**"
        )

    @automode_prefix.command(
        name="mentions"
    )
    async def automode_mentions(
        self,
        ctx,
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

        config = get_automode_config(
            ctx.guild.id
        )

        config["mention_protection"] = (
            state == "on"
        )

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"📢 Mention protection: **{state.upper()}**"
        )

    @automode_prefix.command(
        name="duplicates"
    )
    async def automode_duplicates(
        self,
        ctx,
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

        config = get_automode_config(
            ctx.guild.id
        )

        config["duplicate_protection"] = (
            state == "on"
        )

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"♻️ Duplicate protection: **{state.upper()}**"
        )

    # ========================================================
    # PREFIX WHITELIST
    # ========================================================

    @automode_prefix.group(
        name="whitelist",
        invoke_without_command=True
    )
    async def whitelist_prefix(
        self,
        ctx
    ):

        await ctx.send(

            "🛡️ **AutoMode Whitelist**\n\n"

            "`,automode whitelist user @User`\n"
            "`,automode whitelist role @Role`"
        )

    @whitelist_prefix.command(
        name="user"
    )
    async def whitelist_prefix_user(
        self,
        ctx,
        member: discord.Member
    ):

        config = get_automode_config(
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

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ {member.mention} is now whitelisted."
        )

    @whitelist_prefix.command(
        name="role"
    )
    async def whitelist_prefix_role(
        self,
        ctx,
        role: discord.Role
    ):

        config = get_automode_config(
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

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ {role.mention} is now whitelisted."
        )

    # ========================================================
    # PREFIX BADWORD
    # ========================================================

    @automode_prefix.group(
        name="badword",
        invoke_without_command=True
    )
    async def badword_prefix(
        self,
        ctx
    ):

        await ctx.send(

            "🚫 **Bad Word Protection**\n\n"

            "`,automode badword add word1, word2`\n"
            "`,automode badword remove word1, word2`"
        )

    @badword_prefix.command(
        name="add"
    )
    async def badword_prefix_add(
        self,
        ctx,
        *,
        words: str
    ):

        config = get_automode_config(
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
                "❌ You can add a maximum of 100 words/phrases at once."
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

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(

            "✅ **Bad Words Updated**\n\n"

            f"Added: **{added}**\n"
            f"Already existed: **{existing}**\n"
            f"Total blocked: **{len(badwords)}**"
        )

    @badword_prefix.command(
        name="remove"
    )
    async def badword_prefix_remove(
        self,
        ctx,
        *,
        words: str
    ):

        config = get_automode_config(
            ctx.guild.id
        )

        remove_words = parse_word_list(
            words
        )

        if not remove_words:

            return await ctx.send(
                "❌ Please provide at least one word or phrase."
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

        update_automode_config(
            ctx.guild.id,
            config
        )

        await ctx.send(

            "✅ **Bad Words Updated**\n\n"

            f"Removed: **{removed}**\n"
            f"Not found: **{not_found}**\n"
            f"Total blocked: **{len(badwords)}**"
        )


# ============================================================
# ============================================================
#                    ANTI-NUKE UI
# ============================================================
# ============================================================


class AntiNukeMainView(
    discord.ui.View
):

    def __init__(self, bot):

        super().__init__(
            timeout=None
        )

        self.bot = bot

    @discord.ui.select(

        placeholder=(
            "Choose an Anti-Nuke option..."
        ),

        min_values=1,
        max_values=1,

        options=[

            discord.SelectOption(
                label="Enable / Disable",
                description="Enable or disable Anti-Nuke",
                emoji="⚡",
                value="toggle"
            ),

            discord.SelectOption(
                label="Modify",
                description="Modify Anti-Nuke settings",
                emoji="⚙️",
                value="modify"
            ),

            discord.SelectOption(
                label="View",
                description="View current Anti-Nuke settings",
                emoji="👁️",
                value="view"
            ),

            discord.SelectOption(
                label="Whitelist",
                description="Manage trusted users and roles",
                emoji="👤",
                value="whitelist"
            ),

            discord.SelectOption(
                label="Thresholds",
                description="Configure action thresholds",
                emoji="📊",
                value="thresholds"
            ),

            discord.SelectOption(
                label="Logs",
                description="Configure Anti-Nuke logs",
                emoji="📋",
                value="logs"
            )
        ]
    )
    async def select(
        self,
        interaction,
        select
    ):

        if not interaction.guild:

            await public_send(

                interaction,

                embed=make_embed(

                    "❌ Server Only",

                    "This configuration can only be used inside a server.",

                    False
                )
            )

            return

        if not isinstance(
            interaction.user,
            discord.Member
        ):
            return

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Only server administrators can configure Anti-Nuke.",

                    False
                )
            )

            return

        value = select.values[0]

        if value == "toggle":

            await public_send(

                interaction,

                embed=toggle_embed(
                    interaction.guild
                ),

                view=ToggleView()
            )

        elif value == "modify":

            await public_send(

                interaction,

                embed=modify_embed(
                    interaction.guild
                ),

                view=ModifyView()
            )

        elif value == "view":

            await public_send(

                interaction,

                embed=view_config_embed(
                    interaction.guild
                )
            )

        elif value == "whitelist":

            await public_send(

                interaction,

                embed=make_embed(

                    "👤 Anti-Nuke | Whitelist",

                    (
                        "Manage users and roles "
                        "that Anti-Nuke will trust automatically."
                    )
                ),

                view=WhitelistView()
            )

        elif value == "thresholds":

            await public_send(

                interaction,

                embed=threshold_embed(
                    interaction.guild
                ),

                view=ThresholdView()
            )

        elif value == "logs":

            await public_send(

                interaction,

                embed=logs_embed(
                    interaction.guild
                ),

                view=LogsView()
            )


# ============================================================
# TOGGLE
# ============================================================

def toggle_embed(
    guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    return make_embed(

        "⚡ Anti-Nuke | Enable / Disable",

        (
            f"**Current Status:** "
            f"{status_text(cfg['enabled'])}\n\n"
            "Choose an option below."
        )
    )


class ToggleView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=180
        )

    @discord.ui.button(

        label="Enable",
        emoji="🟢",
        style=discord.ButtonStyle.success
    )
    async def enable(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Only administrators can enable Anti-Nuke.",

                    False
                )
            )

            return

        guild = interaction.guild

        cfg = get_antinuke_config(
            guild.id
        )

        cfg["enabled"] = True

        # Trust owner
        if (
            guild.owner_id
            not in cfg["whitelist_users"]
        ):

            cfg["whitelist_users"].append(
                guild.owner_id
            )

        # Trust bot
        if (
            guild.me
            and guild.me.id
            not in cfg["whitelist_users"]
        ):

            cfg["whitelist_users"].append(
                guild.me.id
            )

        antinuke_save_all()

        channel = (
            await ensure_antinuke_log_channel(
                guild
            )
        )

        description = (

            "🛡️ **Anti-Nuke has been enabled.**\n\n"

            "Server owner and bot have been "
            "automatically trusted."
        )

        if channel:

            description += (
                f"\n\n📋 Logs: "
                f"{channel.mention}"
            )

        else:

            description += (
                "\n\n⚠️ I could not create "
                "the security log channel."
            )

        await public_send(

            interaction,

            embed=make_embed(

                "🟢 Anti-Nuke Enabled",

                description
            )
        )

    @discord.ui.button(

        label="Disable",
        emoji="🔴",
        style=discord.ButtonStyle.danger
    )
    async def disable(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Only administrators can disable Anti-Nuke.",

                    False
                )
            )

            return

        guild = interaction.guild

        cfg = get_antinuke_config(
            guild.id
        )

        cfg["enabled"] = False

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "🔴 Anti-Nuke Disabled",

                "Anti-Nuke protection is now disabled."
            )
        )


# ============================================================
# MODIFY
# ============================================================

def modify_embed(
    guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    enabled_count = sum(
        1
        for value in cfg["modules"].values()
        if value
    )

    return make_embed(

        "⚙️ Anti-Nuke | Modify",

        (
            f"**Protection:** "
            f"{status_text(cfg['enabled'])}\n"

            f"**Active Modules:** "
            f"`{enabled_count}`\n"

            f"**Punishment:** "
            f"{action_text(cfg['action'])}\n"

            f"**Time Window:** "
            f"`{cfg['window']} seconds`\n\n"

            "Choose the protection you want to configure."
        )
    )


class ModifyView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=180
        )

    @discord.ui.select(

        placeholder="Select a protection...",

        options=[

            discord.SelectOption(
                label="Mass Ban",
                emoji="🔨",
                value="ban"
            ),

            discord.SelectOption(
                label="Mass Kick",
                emoji="👢",
                value="kick"
            ),

            discord.SelectOption(
                label="Channel Delete",
                emoji="🗑️",
                value="channel_delete"
            ),

            discord.SelectOption(
                label="Channel Create",
                emoji="📁",
                value="channel_create"
            ),

            discord.SelectOption(
                label="Role Delete",
                emoji="🎭",
                value="role_delete"
            ),

            discord.SelectOption(
                label="Role Create",
                emoji="➕",
                value="role_create"
            ),

            discord.SelectOption(
                label="Webhook Delete",
                emoji="🔗",
                value="webhook_delete"
            ),

            discord.SelectOption(
                label="Bot Add",
                emoji="🤖",
                value="bot_add"
            ),

            discord.SelectOption(
                label="Server Update",
                emoji="🌐",
                value="guild_update"
            ),

            discord.SelectOption(
                label="Permission Changes",
                emoji="🔐",
                value="overwrite_update"
            ),

            discord.SelectOption(
                label="Emoji Delete",
                emoji="😀",
                value="emoji_delete"
            ),

            discord.SelectOption(
                label="Emoji Create",
                emoji="😎",
                value="emoji_create"
            ),

            discord.SelectOption(
                label="Sticker Delete",
                emoji="🏷️",
                value="sticker_delete"
            ),

            discord.SelectOption(
                label="Sticker Create",
                emoji="✨",
                value="sticker_create"
            )
        ]
    )
    async def modify_select(
        self,
        interaction,
        select
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Only administrators can modify Anti-Nuke.",

                    False
                )
            )

            return

        action_type = (
            select.values[0]
        )

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        enabled = cfg["modules"].get(
            action_type,
            True
        )

        threshold = cfg["thresholds"].get(
            action_type,
            3
        )

        embed = make_embed(

            "⚙️ Anti-Nuke | "
            + action_type.replace(
                "_",
                " "
            ).title(),

            (
                f"**Status:** "
                f"{status_text(enabled)}\n"

                f"**Threshold:** "
                f"`{threshold}` actions\n"

                f"**Window:** "
                f"`{cfg['window']} seconds`\n\n"

                "Use the buttons below "
                "to change this protection."
            )
        )

        await public_send(

            interaction,

            embed=embed,

            view=ModuleControlView(
                action_type
            )
        )


# ============================================================
# MODULE CONTROL
# ============================================================

class ModuleControlView(
    discord.ui.View
):

    def __init__(
        self,
        action_type
    ):

        super().__init__(
            timeout=180
        )

        self.action_type = action_type

    @discord.ui.button(

        label="Enable",
        emoji="🟢",
        style=discord.ButtonStyle.success
    )
    async def enable(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Administrator permissions are required.",

                    False
                )
            )

            return

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        cfg["modules"][
            self.action_type
        ] = True

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "🟢 Protection Enabled",

                (
                    f"`{self.action_type}` "
                    "protection has been enabled."
                )
            )
        )

    @discord.ui.button(

        label="Disable",
        emoji="🔴",
        style=discord.ButtonStyle.danger
    )
    async def disable(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Administrator permissions are required.",

                    False
                )
            )

            return

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        cfg["modules"][
            self.action_type
        ] = False

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "🔴 Protection Disabled",

                (
                    f"`{self.action_type}` "
                    "protection has been disabled."
                )
            )
        )


# ============================================================
# VIEW CONFIG
# ============================================================

def view_config_embed(
    guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    lines = []

    for key, value in (
        cfg["modules"].items()
    ):

        lines.append(

            f"{status_text(value)} "
            f"`{key.replace('_', ' ').title()}`"
        )

    log_channel = guild.get_channel(
        cfg.get(
            "log_channel_id"
        )
    )

    return make_embed(

        "👁️ Anti-Nuke | Current Configuration",

        (
            f"**Overall Status:** "
            f"{status_text(cfg['enabled'])}\n"

            f"**Punishment:** "
            f"{action_text(cfg['action'])}\n"

            f"**Window:** "
            f"`{cfg['window']} seconds`\n"

            f"**Log Channel:** "
            f"{log_channel.mention if log_channel else 'Not configured'}\n\n"

            "**Protection Modules**\n"

            + "\n".join(lines)

            + "\n\n"

            f"**Whitelisted Users:** "
            f"`{len(cfg['whitelist_users'])}`\n"

            f"**Whitelisted Roles:** "
            f"`{len(cfg['whitelist_roles'])}`"
        )
    )


# ============================================================
# WHITELIST VIEW
# ============================================================

class WhitelistView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=180
        )

    @discord.ui.button(

        label="Add User",
        emoji="➕",
        style=discord.ButtonStyle.success
    )
    async def add_user(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Administrator permissions are required.",

                    False
                )
            )

            return

        await public_send(

            interaction,

            embed=make_embed(

                "👤 Add Whitelisted User",

                (
                    "Use:\n"
                    "`,antinuke whitelist @user`\n\n"
                    "The selected member will become trusted."
                )
            )
        )

    @discord.ui.button(

        label="View",
        emoji="👁️",
        style=discord.ButtonStyle.secondary
    )
    async def view(
        self,
        interaction,
        button
    ):

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        users = []

        for user_id in (
            cfg["whitelist_users"]
        ):

            member = (
                interaction.guild
                .get_member(user_id)
            )

            if member:
                users.append(
                    member.mention
                )

        roles = []

        for role_id in (
            cfg["whitelist_roles"]
        ):

            role = (
                interaction.guild
                .get_role(role_id)
            )

            if role:
                roles.append(
                    role.mention
                )

        description = (

            "**Trusted Users**\n"

            + (
                "\n".join(users)
                if users
                else "None"
            )

            + "\n\n"

            "**Trusted Roles**\n"

            + (
                "\n".join(roles)
                if roles
                else "None"
            )
        )

        await public_send(

            interaction,

            embed=make_embed(

                "👤 Anti-Nuke | Whitelist",

                description
            )
        )


# ============================================================
# THRESHOLDS
# ============================================================

def threshold_embed(
    guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    rows = []

    for key, value in (
        cfg["thresholds"].items()
    ):

        rows.append(

            f"• **{key.replace('_', ' ').title()}:** "
            f"`{value}`"
        )

    return make_embed(

        "📊 Anti-Nuke | Thresholds",

        (
            "\n".join(rows)

            + f"\n\n**Time Window:** "
            f"`{cfg['window']} seconds`"

            + "\n\n"
            "Use the prefix commands to modify thresholds."
        )
    )


class ThresholdView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=180
        )

    @discord.ui.button(

        label="5 Seconds",
        emoji="⏱️",
        style=discord.ButtonStyle.secondary
    )
    async def five(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):
            return

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        cfg["window"] = 5

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "⏱️ Threshold Window Updated",

                "Anti-Nuke detection window is now **5 seconds**."
            )
        )

    @discord.ui.button(

        label="10 Seconds",
        emoji="⏱️",
        style=discord.ButtonStyle.primary
    )
    async def ten(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):
            return

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        cfg["window"] = 10

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "⏱️ Threshold Window Updated",

                "Anti-Nuke detection window is now **10 seconds**."
            )
        )


# ============================================================
# LOGS VIEW
# ============================================================

def logs_embed(
    guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    channel = guild.get_channel(
        cfg.get(
            "log_channel_id"
        )
    )

    return make_embed(

        "📋 Anti-Nuke | Logs",

        (
            f"**Log Channel:** "
            f"{channel.mention if channel else 'Not configured'}\n\n"

            "Anti-Nuke detections and punishments "
            "are sent to this channel."
        )
    )


class LogsView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=180
        )

    @discord.ui.button(

        label="Create / Fix Log Channel",
        emoji="📋",
        style=discord.ButtonStyle.primary
    )
    async def create_logs(
        self,
        interaction,
        button
    ):

        if not is_admin(
            interaction.user
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Administrator Required",

                    "Administrator permissions are required.",

                    False
                )
            )

            return

        channel = (
            await ensure_antinuke_log_channel(
                interaction.guild
            )
        )

        if not channel:

            await public_send(

                interaction,

                embed=make_embed(

                    "❌ Log Channel Failed",

                    (
                        "I couldn't create/find "
                        "the security log channel. "
                        "Check my **Manage Channels** permission."
                    ),

                    False
                )
            )

            return

        await public_send(

            interaction,

            embed=make_embed(

                "📋 Security Logs Ready",

                (
                    "Anti-Nuke logs will be sent to "
                    f"{channel.mention}."
                )
            )
        )


# ============================================================
# ANTI-NUKE DASHBOARD
# ============================================================

def dashboard_embed(
    guild
):

    cfg = get_antinuke_config(
        guild.id
    )

    log_channel = guild.get_channel(
        cfg.get(
            "log_channel_id"
        )
    )

    return make_embed(

        "🛡️ Anti-Nuke | Configuration",

        (
            "This system protects your server against "
            "unauthorized destructive actions.\n\n"

            "**Available features:**\n"

            "• Mass ban protection\n"
            "• Mass kick protection\n"
            "• Channel protection\n"
            "• Role protection\n"
            "• Webhook protection\n"
            "• Bot-add protection\n"
            "• Permission protection\n"
            "• Server update protection\n"
            "• Emoji & sticker protection\n\n"

            "**Current Status:** "
            f"{status_text(cfg['enabled'])}\n"

            f"**Punishment:** "
            f"{action_text(cfg['action'])}\n"

            f"**Detection Window:** "
            f"`{cfg['window']} seconds`\n"

            f"**Logs:** "
            f"{log_channel.mention if log_channel else 'Not configured'}\n\n"

            "Use the menu below to configure "
            "Air Commander's Anti-Nuke system."
        )
    )


# ============================================================
# PREFIX ANTINUKE
# ============================================================

@commands.command(
    name="antinuke"
)
@commands.guild_only()
async def antinuke_prefix_command(
    ctx
):

    if not isinstance(
        ctx.author,
        discord.Member
    ):
        return

    if not is_admin(
        ctx.author
    ):

        await ctx.send(

            embed=make_embed(

                "🔒 Administrator Required",

                "Only server administrators can configure Anti-Nuke.",

                False
            )
        )

        return

    await ctx.send(

        embed=dashboard_embed(
            ctx.guild
        ),

        view=AntiNukeMainView(
            ctx.bot
        )
    )


# ============================================================
# ANTI-NUKE SLASH GROUP
# ============================================================

class AntiNukeGroup(
    app_commands.Group
):

    def __init__(self):

        super().__init__(

            name="antinuke",

            description=(
                "Configure Air Commander Anti-Nuke protection"
            )
        )

    # ========================================================
    # CONFIG
    # ========================================================

    @app_commands.command(
        name="config",
        description=(
            "Open the public Anti-Nuke configuration panel"
        )
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def config(
        self,
        interaction
    ):

        await public_send(

            interaction,

            embed=dashboard_embed(
                interaction.guild
            ),

            view=AntiNukeMainView(
                interaction.client
            )
        )

    # ========================================================
    # WHITELIST
    # ========================================================

    @app_commands.command(
        name="whitelist",
        description="Whitelist a member from Anti-Nuke"
    )
    @app_commands.describe(
        member="Member to whitelist"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def whitelist(
        self,
        interaction,
        member: discord.Member
    ):

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        if member.id not in (
            cfg["whitelist_users"]
        ):

            cfg["whitelist_users"].append(
                member.id
            )

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "👤 Anti-Nuke Whitelist Updated",

                f"{member.mention} is now trusted by Anti-Nuke."
            )
        )

    # ========================================================
    # UNWHITELIST
    # ========================================================

    @app_commands.command(
        name="unwhitelist",
        description="Remove a member from Anti-Nuke whitelist"
    )
    @app_commands.describe(
        member="Member to remove"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def unwhitelist(
        self,
        interaction,
        member: discord.Member
    ):

        if (
            member.id
            == interaction.guild.owner_id
        ):

            await public_send(

                interaction,

                embed=make_embed(

                    "🔒 Protected Owner",

                    "The server owner cannot be removed from trusted users.",

                    False
                )
            )

            return

        cfg = get_antinuke_config(
            interaction.guild.id
        )

        if member.id in (
            cfg["whitelist_users"]
        ):

            cfg["whitelist_users"].remove(
                member.id
            )

        antinuke_save_all()

        await public_send(

            interaction,

            embed=make_embed(

                "👤 Whitelist Updated",

                f"{member.mention} is no longer whitelisted."
            )
        )


# ============================================================
# ANTI-NUKE ERROR HANDLER
# ============================================================

async def antinuke_error(
    interaction,
    error
):

    if isinstance(
        error,
        app_commands.errors.MissingPermissions
    ):

        await public_send(

            interaction,

            embed=make_embed(

                "🔒 Administrator Required",

                "You need administrator permission to use this command.",

                False
            )
        )

        return

    print(
        f"[AntiNuke] Slash error: {error}"
    )

    if interaction.response.is_done():

        await interaction.followup.send(

            embed=make_embed(

                "❌ Anti-Nuke Error",

                f"An error occurred: `{error}`",

                False
            )
        )

    else:

        await interaction.response.send_message(

            embed=make_embed(

                "❌ Anti-Nuke Error",

                f"An error occurred: `{error}`",

                False
            )
        )


# ============================================================
# ============================================================
#                     COMBINED SETUP
# ============================================================
# ============================================================

async def setup(
    bot
):

    # ========================================================
    # PREVENT DUPLICATE COG
    # ========================================================

    if getattr(
        bot,
        "_air_security_combined_setup",
        False
    ):

        print(
            "⚠️ Air Commander Security already loaded."
        )

        return

    bot._air_security_combined_setup = True

    # ========================================================
    # ADD AUTOMODE COG
    # ========================================================

    try:

        if bot.get_cog(
            "AutoMode"
        ) is None:

            await bot.add_cog(
                AutoMode(bot)
            )

            print(
                "🛡️ AutoMode loaded."
            )

        else:

            print(
                "⚠️ AutoMode Cog already exists."
            )

    except Exception as e:

        print(
            f"❌ AutoMode setup error: {e}"
        )

    # ========================================================
    # ADD ANTI-NUKE SLASH GROUP
    # ========================================================

    try:

        existing = bot.tree.get_command(
            "antinuke"
        )

        if existing is None:

            antinuke_group = (
                AntiNukeGroup()
            )

            bot.tree.add_command(
                antinuke_group
            )

            # Register error handlers
            for command in (
                antinuke_group.walk_commands()
            ):

                try:

                    command.on_error = (
                        antinuke_error
                    )

                except Exception:
                    pass

            print(
                "🛡️ Anti-Nuke slash group loaded."
            )

        else:

            print(
                "⚠️ /antinuke already registered."
            )

    except discord.app_commands.errors.CommandAlreadyRegistered:

        print(
            "⚠️ /antinuke was already registered."
        )

    except Exception as e:

        print(
            f"❌ Anti-Nuke slash setup error: {e}"
        )

    # ========================================================
    # PREFIX ANTINUKE
    # ========================================================

    try:

        if bot.get_command(
            "antinuke"
        ) is None:

            bot.add_command(
                antinuke_prefix_command
            )

            print(
                "🛡️ ,antinuke prefix loaded."
            )

        else:

            print(
                "⚠️ ,antinuke already registered."
            )

    except commands.CommandRegistrationError:

        print(
            "⚠️ ,antinuke was already registered."
        )

    except Exception as e:

        print(
            f"❌ Anti-Nuke prefix setup error: {e}"
        )

    # ========================================================
    # AUDIT LOG EVENT
    # ========================================================

    if not getattr(
        bot,
        "_air_security_audit_registered",
        False
    ):

        @bot.event
        async def on_audit_log_entry_create(
            entry
        ):

            try:

                await process_audit_entry(
                    bot,
                    entry
                )

            except Exception as e:

                print(
                    f"[AntiNuke] Audit error: {e}"
                )

        bot._air_security_audit_registered = True

    print(
        "🛡️ Air Commander Security System loaded."
    )
    print(
        "   ├─ AutoMode / Silent Protect"
    )
    print(
        "   └─ Advanced Anti-Nuke"
    )
