# ============================================================
# AIR COMMANDER - ADVANCED ANTI-NUKE
# Public Configuration Dashboard
# discord.py 2.5+
# ============================================================

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands


# ============================================================
# CONFIG
# ============================================================

DATA_FILE = Path("antinuke_config.json")

DEFAULT_CONFIG = {
    "enabled": False,
    "action": "ban",

    "log_channel_id": None,

    "whitelist_users": [],
    "whitelist_roles": [],

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

    "window": 10,

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
    },
}


# ============================================================
# STORAGE
# ============================================================

def load_all():
    if not DATA_FILE.exists():
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


def save_all(data):
    temp = DATA_FILE.with_suffix(".tmp")

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    temp.replace(DATA_FILE)


CONFIGS = load_all()


def get_config(guild_id: int):
    gid = str(guild_id)

    if gid not in CONFIGS:
        CONFIGS[gid] = json.loads(json.dumps(DEFAULT_CONFIG))
        save_all(CONFIGS)

    cfg = CONFIGS[gid]

    # Safety defaults for old configs
    cfg.setdefault("enabled", False)
    cfg.setdefault("action", "ban")
    cfg.setdefault("log_channel_id", None)
    cfg.setdefault("whitelist_users", [])
    cfg.setdefault("whitelist_roles", [])
    cfg.setdefault("thresholds", {})
    cfg.setdefault("window", 10)
    cfg.setdefault("modules", {})

    for key, value in DEFAULT_CONFIG["thresholds"].items():
        cfg["thresholds"].setdefault(key, value)

    for key, value in DEFAULT_CONFIG["modules"].items():
        cfg["modules"].setdefault(key, value)

    return cfg


# ============================================================
# HELPERS
# ============================================================

def status_text(value: bool):
    return "🟢 Enabled" if value else "🔴 Disabled"


def action_text(action: str):
    return {
        "ban": "🔨 Ban",
        "kick": "👢 Kick",
        "timeout": "⏱️ Timeout",
        "strip": "🧹 Strip Roles",
    }.get(action, action.title())


def make_embed(title, description="", success=True):
    embed = discord.Embed(
        title=title,
        description=description,
        colour=discord.Colour.orange()
        if success
        else discord.Colour.red()
    )

    embed.set_footer(text="Air Commander • Anti-Nuke Security")

    return embed


async def public_send(interaction: discord.Interaction, *, embed=None, view=None):
    """
    IMPORTANT:
    Everything is public.
    No ephemeral=True anywhere.
    """

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


def is_admin(member: discord.Member):
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


def is_owner(member: discord.Member):
    try:
        return member.guild.owner_id == member.id
    except Exception:
        return False


def is_whitelisted(member: discord.Member, cfg):
    if member.id in cfg["whitelist_users"]:
        return True

    if member.guild.owner_id == member.id:
        return True

    if member.id == member.guild.me.id:
        return True

    member_role_ids = {role.id for role in member.roles}

    if member_role_ids.intersection(
        set(cfg["whitelist_roles"])
    ):
        return True

    return False


async def ensure_log_channel(guild: discord.Guild):
    cfg = get_config(guild.id)

    existing_id = cfg.get("log_channel_id")

    if existing_id:
        channel = guild.get_channel(existing_id)

        if channel:
            return channel

    # Search existing channel first
    for channel in guild.text_channels:
        if channel.name.lower() == "commander-antinuke-logs":
            cfg["log_channel_id"] = channel.id
            save_all(CONFIGS)
            return channel

    me = guild.me

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        )
    }

    if me:
        overwrites[me] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            embed_links=True,
            read_message_history=True
        )

    try:
        channel = await guild.create_text_channel(
            "commander-antinuke-logs",
            topic="Air Commander Anti-Nuke Security Logs",
            overwrites=overwrites,
            reason="Air Commander Anti-Nuke enabled"
        )

        cfg["log_channel_id"] = channel.id
        save_all(CONFIGS)

        return channel

    except discord.Forbidden:
        return None

    except discord.HTTPException:
        return None


async def send_log(guild, title, description, colour=discord.Colour.orange()):
    cfg = get_config(guild.id)

    channel_id = cfg.get("log_channel_id")

    if not channel_id:
        return

    channel = guild.get_channel(channel_id)

    if not channel:
        return

    embed = discord.Embed(
        title=title,
        description=description,
        colour=colour,
        timestamp=discord.utils.utcnow()
    )

    embed.set_footer(text="Air Commander • Anti-Nuke")

    try:
        await channel.send(embed=embed)
    except Exception:
        pass


# ============================================================
# ACTION TRACKING
# ============================================================

ACTION_HISTORY = defaultdict(
    lambda: defaultdict(deque)
)

# guild -> action -> deque(timestamp)


def register_action(guild_id, action):
    history = ACTION_HISTORY[guild_id][action]

    now = time.monotonic()

    history.append(now)

    return list(history)


def cleanup_history(guild_id, action, window):
    history = ACTION_HISTORY[guild_id][action]

    now = time.monotonic()

    while history and now - history[0] > window:
        history.popleft()

    return len(history)


# ============================================================
# PUNISHMENT
# ============================================================

async def punish_member(guild: discord.Guild, member: discord.Member, cfg):
    action = cfg.get("action", "ban")

    try:
        if action == "ban":
            await guild.ban(
                member,
                reason="Air Commander Anti-Nuke protection"
            )
            return "Banned"

        if action == "kick":
            await guild.kick(
                member,
                reason="Air Commander Anti-Nuke protection"
            )
            return "Kicked"

        if action == "timeout":
            await member.timeout(
                discord.utils.utcnow() + discord.timedelta(minutes=30),
                reason="Air Commander Anti-Nuke protection"
            )
            return "Timed out"

        if action == "strip":
            removable = []

            for role in member.roles:
                if role.is_default():
                    continue

                if role >= guild.me.top_role:
                    continue

                removable.append(role)

            if removable:
                await member.remove_roles(
                    *removable,
                    reason="Air Commander Anti-Nuke protection"
                )

            return "Roles removed"

    except discord.Forbidden:
        return "Failed: missing permissions"

    except discord.HTTPException:
        return "Failed: Discord API error"

    return "No action"


# ============================================================
# ANTI-NUKE AUDIT LOG PROCESSOR
# ============================================================

AUDIT_ACTION_MAP = {
    discord.AuditLogAction.ban: "ban",
    discord.AuditLogAction.kick: "kick",

    discord.AuditLogAction.channel_delete: "channel_delete",
    discord.AuditLogAction.channel_create: "channel_create",

    discord.AuditLogAction.role_delete: "role_delete",
    discord.AuditLogAction.role_create: "role_create",

    discord.AuditLogAction.webhook_delete: "webhook_delete",

    discord.AuditLogAction.bot_add: "bot_add",

    discord.AuditLogAction.guild_update: "guild_update",

    discord.AuditLogAction.emoji_delete: "emoji_delete",
    discord.AuditLogAction.emoji_create: "emoji_create",

    discord.AuditLogAction.sticker_delete: "sticker_delete",
    discord.AuditLogAction.sticker_create: "sticker_create",

    discord.AuditLogAction.overwrite_update: "overwrite_update",
}


async def process_audit_entry(bot, entry):
    guild = entry.guild

    if guild is None:
        return

    cfg = get_config(guild.id)

    if not cfg.get("enabled"):
        return

    action_type = AUDIT_ACTION_MAP.get(entry.action)

    if not action_type:
        return

    if not cfg["modules"].get(action_type, True):
        return

    actor = entry.user

    if actor is None:
        return

    if not isinstance(actor, discord.Member):
        try:
            actor = guild.get_member(actor.id)
        except Exception:
            return

    if actor is None:
        return

    if is_whitelisted(actor, cfg):
        return

    # Register action
    register_action(
        guild.id,
        action_type
    )

    count = cleanup_history(
        guild.id,
        action_type,
        cfg.get("window", 10)
    )

    threshold = cfg["thresholds"].get(
        action_type,
        3
    )

    # Log every suspicious action
    await send_log(
        guild,
        "🚨 Anti-Nuke Detection",
        (
            f"**Executor:** {actor.mention}\n"
            f"**Action:** `{action_type}`\n"
            f"**Count:** `{count}/{threshold}`\n"
            f"**Window:** `{cfg.get('window', 10)} seconds`"
        ),
        discord.Colour.red()
    )

    if count < threshold:
        return

    # Reset after triggering
    ACTION_HISTORY[guild.id][action_type].clear()

    result = await punish_member(
        guild,
        actor,
        cfg
    )

    await send_log(
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
# MAIN DASHBOARD VIEW
# ============================================================

class AntiNukeMainView(discord.ui.View):

    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.select(
        placeholder="Choose an Anti-Nuke option...",
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
            ),
        ]
    )
    async def select(self, interaction: discord.Interaction, select: discord.ui.Select):

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

        if not isinstance(interaction.user, discord.Member):
            return

        if not is_admin(interaction.user):
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
                embed=toggle_embed(interaction.guild),
                view=ToggleView()
            )

        elif value == "modify":
            await public_send(
                interaction,
                embed=modify_embed(interaction.guild),
                view=ModifyView()
            )

        elif value == "view":
            await public_send(
                interaction,
                embed=view_config_embed(interaction.guild)
            )

        elif value == "whitelist":
            await public_send(
                interaction,
                embed=make_embed(
                    "👤 Anti-Nuke | Whitelist",
                    (
                        "Manage users and roles that Anti-Nuke "
                        "will trust automatically."
                    )
                ),
                view=WhitelistView()
            )

        elif value == "thresholds":
            await public_send(
                interaction,
                embed=threshold_embed(interaction.guild),
                view=ThresholdView()
            )

        elif value == "logs":
            await public_send(
                interaction,
                embed=logs_embed(interaction.guild),
                view=LogsView()
            )


# ============================================================
# TOGGLE VIEW
# ============================================================

def toggle_embed(guild):
    cfg = get_config(guild.id)

    return make_embed(
        "⚡ Anti-Nuke | Enable / Disable",
        (
            f"**Current Status:** {status_text(cfg['enabled'])}\n\n"
            "Choose an option below."
        )
    )


class ToggleView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Enable",
        emoji="🟢",
        style=discord.ButtonStyle.success
    )
    async def enable(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
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
        cfg = get_config(guild.id)

        cfg["enabled"] = True

        # Automatically trust owner and bot
        if guild.owner_id not in cfg["whitelist_users"]:
            cfg["whitelist_users"].append(guild.owner_id)

        if guild.me and guild.me.id not in cfg["whitelist_users"]:
            cfg["whitelist_users"].append(guild.me.id)

        save_all(CONFIGS)

        channel = await ensure_log_channel(guild)

        description = (
            "🛡️ **Anti-Nuke has been enabled.**\n\n"
            "Server owner and bot have been automatically trusted."
        )

        if channel:
            description += (
                f"\n\n📋 Logs: {channel.mention}"
            )
        else:
            description += (
                "\n\n⚠️ I could not create the security log channel."
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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
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
        cfg = get_config(guild.id)

        cfg["enabled"] = False
        save_all(CONFIGS)

        await public_send(
            interaction,
            embed=make_embed(
                "🔴 Anti-Nuke Disabled",
                "Anti-Nuke protection is now disabled."
            )
        )


# ============================================================
# MODIFY VIEW
# ============================================================

def modify_embed(guild):
    cfg = get_config(guild.id)

    enabled_count = sum(
        1 for value in cfg["modules"].values()
        if value
    )

    return make_embed(
        "⚙️ Anti-Nuke | Modify",
        (
            f"**Protection:** {status_text(cfg['enabled'])}\n"
            f"**Active Modules:** `{enabled_count}`\n"
            f"**Punishment:** {action_text(cfg['action'])}\n"
            f"**Time Window:** `{cfg['window']} seconds`\n\n"
            "Choose the protection you want to configure."
        )
    )


class ModifyView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

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
        ]
    )
    async def modify_select(
        self,
        interaction: discord.Interaction,
        select: discord.ui.Select
    ):
        if not is_admin(interaction.user):
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Administrator Required",
                    "Only administrators can modify Anti-Nuke.",
                    False
                )
            )
            return

        action_type = select.values[0]

        cfg = get_config(interaction.guild.id)

        enabled = cfg["modules"].get(
            action_type,
            True
        )

        threshold = cfg["thresholds"].get(
            action_type,
            3
        )

        embed = make_embed(
            f"⚙️ Anti-Nuke | {action_type.replace('_', ' ').title()}",
            (
                f"**Status:** {status_text(enabled)}\n"
                f"**Threshold:** `{threshold}` actions\n"
                f"**Window:** `{cfg['window']} seconds`\n\n"
                "Use the buttons below to change this protection."
            )
        )

        await public_send(
            interaction,
            embed=embed,
            view=ModuleControlView(action_type)
        )


# ============================================================
# MODULE CONTROL
# ============================================================

class ModuleControlView(discord.ui.View):

    def __init__(self, action_type):
        super().__init__(timeout=180)
        self.action_type = action_type

    @discord.ui.button(
        label="Enable",
        emoji="🟢",
        style=discord.ButtonStyle.success
    )
    async def enable(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Administrator Required",
                    "Administrator permissions are required.",
                    False
                )
            )
            return

        cfg = get_config(interaction.guild.id)

        cfg["modules"][self.action_type] = True
        save_all(CONFIGS)

        await public_send(
            interaction,
            embed=make_embed(
                "🟢 Protection Enabled",
                (
                    f"`{self.action_type}` protection has been enabled."
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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Administrator Required",
                    "Administrator permissions are required.",
                    False
                )
            )
            return

        cfg = get_config(interaction.guild.id)

        cfg["modules"][self.action_type] = False
        save_all(CONFIGS)

        await public_send(
            interaction,
            embed=make_embed(
                "🔴 Protection Disabled",
                (
                    f"`{self.action_type}` protection has been disabled."
                )
            )
        )


# ============================================================
# VIEW CONFIGURATION
# ============================================================

def view_config_embed(guild):
    cfg = get_config(guild.id)

    lines = []

    for key, value in cfg["modules"].items():
        lines.append(
            f"{status_text(value)} `{key.replace('_', ' ').title()}`"
        )

    log_channel = guild.get_channel(
        cfg.get("log_channel_id")
    )

    return make_embed(
        "👁️ Anti-Nuke | Current Configuration",
        (
            f"**Overall Status:** {status_text(cfg['enabled'])}\n"
            f"**Punishment:** {action_text(cfg['action'])}\n"
            f"**Window:** `{cfg['window']} seconds`\n"
            f"**Log Channel:** "
            f"{log_channel.mention if log_channel else 'Not configured'}\n\n"
            "**Protection Modules**\n"
            + "\n".join(lines)
            + "\n\n"
            f"**Whitelisted Users:** `{len(cfg['whitelist_users'])}`\n"
            f"**Whitelisted Roles:** `{len(cfg['whitelist_roles'])}`"
        )
    )


# ============================================================
# WHITELIST VIEW
# ============================================================

class WhitelistView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Add User",
        emoji="➕",
        style=discord.ButtonStyle.success
    )
    async def add_user(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
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
                    "` ,antinuke whitelist @user `\n\n"
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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        cfg = get_config(interaction.guild.id)

        users = []

        for user_id in cfg["whitelist_users"]:
            member = interaction.guild.get_member(user_id)

            if member:
                users.append(member.mention)

        roles = []

        for role_id in cfg["whitelist_roles"]:
            role = interaction.guild.get_role(role_id)

            if role:
                roles.append(role.mention)

        description = (
            "**Trusted Users**\n"
            + (
                "\n".join(users)
                if users
                else "None"
            )
            + "\n\n**Trusted Roles**\n"
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
# THRESHOLD VIEW
# ============================================================

def threshold_embed(guild):
    cfg = get_config(guild.id)

    rows = []

    for key, value in cfg["thresholds"].items():
        rows.append(
            f"• **{key.replace('_', ' ').title()}:** `{value}`"
        )

    return make_embed(
        "📊 Anti-Nuke | Thresholds",
        (
            "\n".join(rows)
            + f"\n\n**Time Window:** `{cfg['window']} seconds`"
            "\n\nUse the prefix commands to modify thresholds."
        )
    )


class ThresholdView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="5 Seconds",
        emoji="⏱️",
        style=discord.ButtonStyle.secondary
    )
    async def five(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Administrator Required",
                    "Administrator permissions are required.",
                    False
                )
            )
            return

        cfg = get_config(interaction.guild.id)
        cfg["window"] = 5
        save_all(CONFIGS)

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
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Administrator Required",
                    "Administrator permissions are required.",
                    False
                )
            )
            return

        cfg = get_config(interaction.guild.id)
        cfg["window"] = 10
        save_all(CONFIGS)

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

def logs_embed(guild):
    cfg = get_config(guild.id)

    channel = guild.get_channel(
        cfg.get("log_channel_id")
    )

    return make_embed(
        "📋 Anti-Nuke | Logs",
        (
            f"**Log Channel:** "
            f"{channel.mention if channel else 'Not configured'}\n\n"
            "Anti-Nuke detections and punishments are "
            "sent to this channel."
        )
    )


class LogsView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(
        label="Create / Fix Log Channel",
        emoji="📋",
        style=discord.ButtonStyle.primary
    )
    async def create_logs(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if not is_admin(interaction.user):
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Administrator Required",
                    "Administrator permissions are required.",
                    False
                )
            )
            return

        channel = await ensure_log_channel(
            interaction.guild
        )

        if not channel:
            await public_send(
                interaction,
                embed=make_embed(
                    "❌ Log Channel Failed",
                    (
                        "I couldn't create/find the security log channel. "
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
                f"Anti-Nuke logs will be sent to {channel.mention}."
            )
        )


# ============================================================
# PREFIX COMMANDS
# ============================================================

async def prefix_antinuke(ctx: commands.Context):
    if not ctx.guild:
        return

    if not isinstance(ctx.author, discord.Member):
        return

    if not is_admin(ctx.author):
        await ctx.send(
            embed=make_embed(
                "🔒 Administrator Required",
                "Only server administrators can configure Anti-Nuke.",
                False
            )
        )
        return

    await ctx.send(
        embed=dashboard_embed(ctx.guild),
        view=AntiNukeMainView(ctx.bot)
    )


def dashboard_embed(guild):
    cfg = get_config(guild.id)

    log_channel = guild.get_channel(
        cfg.get("log_channel_id")
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
            f"**Punishment:** {action_text(cfg['action'])}\n"
            f"**Detection Window:** `{cfg['window']} seconds`\n"
            f"**Logs:** "
            f"{log_channel.mention if log_channel else 'Not configured'}\n\n"

            "Use the menu below to configure "
            "Air Commander's Anti-Nuke system."
        )
    )


# ============================================================
# SLASH GROUP
# ============================================================

class AntiNukeGroup(app_commands.Group):

    def __init__(self):
        super().__init__(
            name="antinuke",
            description="Configure Air Commander Anti-Nuke protection"
        )

    @app_commands.command(
        name="config",
        description="Open the public Anti-Nuke configuration panel"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def config(self, interaction: discord.Interaction):

        await public_send(
            interaction,
            embed=dashboard_embed(interaction.guild),
            view=AntiNukeMainView(interaction.client)
        )

    @app_commands.command(
        name="whitelist",
        description="Whitelist a member from Anti-Nuke"
    )
    @app_commands.describe(
        member="Member to whitelist"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def whitelist(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        cfg = get_config(interaction.guild.id)

        if member.id not in cfg["whitelist_users"]:
            cfg["whitelist_users"].append(member.id)

        save_all(CONFIGS)

        await public_send(
            interaction,
            embed=make_embed(
                "👤 Anti-Nuke Whitelist Updated",
                f"{member.mention} is now trusted by Anti-Nuke."
            )
        )

    @app_commands.command(
        name="unwhitelist",
        description="Remove a member from Anti-Nuke whitelist"
    )
    @app_commands.describe(
        member="Member to remove"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def unwhitelist(
        self,
        interaction: discord.Interaction,
        member: discord.Member
    ):
        if member.id == interaction.guild.owner_id:
            await public_send(
                interaction,
                embed=make_embed(
                    "🔒 Protected Owner",
                    "The server owner cannot be removed from trusted users.",
                    False
                )
            )
            return

        cfg = get_config(interaction.guild.id)

        if member.id in cfg["whitelist_users"]:
            cfg["whitelist_users"].remove(member.id)

        save_all(CONFIGS)

        await public_send(
            interaction,
            embed=make_embed(
                "👤 Whitelist Updated",
                f"{member.mention} is no longer whitelisted."
            )
        )


# ============================================================
# ERROR HANDLER
# ============================================================

async def antinuke_error(
    interaction: discord.Interaction,
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

    await public_send(
        interaction,
        embed=make_embed(
            "❌ Anti-Nuke Error",
            f"An error occurred: `{error}`",
            False
        )
    )


# ============================================================
# SETUP
# ============================================================

def setup(bot: commands.Bot):

    # Prevent duplicate registration
    if getattr(bot, "_air_antinuke_setup", False):
        return

    bot._air_antinuke_setup = True

    # Slash group
    try:
        bot.tree.add_command(
            AntiNukeGroup()
        )
    except discord.app_commands.errors.CommandAlreadyRegistered:
        pass

    # Prefix dashboard
    @bot.command(
        name="antinuke"
    )
    @commands.guild_only()
    async def antinuke_prefix(ctx):
        await prefix_antinuke(ctx)

    # Audit-log event
    if not getattr(
        bot,
        "_air_antinuke_audit_registered",
        False
    ):

        @bot.event
        async def on_audit_log_entry_create(entry):
            try:
                await process_audit_entry(
                    bot,
                    entry
                )
            except Exception as e:
                print(
                    f"[AntiNuke] Audit error: {e}"
                )

        bot._air_antinuke_audit_registered = True

    print("🛡️ Air Commander Anti-Nuke loaded.")
