# automode.py
# Air Commander - AutoMode / Silent Protect
#
# Prefix:
# ,automode enable
# ,automode disable
# ,automode status
# ,automode config
# ,automode whitelist user @User
# ,automode whitelist role @Role
#
# Slash:
# /automode enable
# /automode disable
# /automode status
# /automode config
# /automode whitelist user
# /automode whitelist role

import os
import json
import time
import re
from collections import defaultdict, deque
from datetime import timedelta

import discord
from discord.ext import commands
from discord import app_commands


CONFIG_FILE = "automode_config.json"

DEFAULT_CONFIG = {
    "enabled": False,
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

    # Whitelists
    "whitelist_users": [],
    "whitelist_roles": [],

    # Per-user warning count
    "warnings": {}
}


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_guild_config(guild_id: int):
    data = load_config()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = DEFAULT_CONFIG.copy()
        save_config(data)

    config = data[gid]

    # Make sure newly-added options exist
    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = value

    save_config(data)
    return config


def update_guild_config(guild_id: int, config):
    data = load_config()
    data[str(guild_id)] = config
    save_config(data)


def is_whitelisted(member: discord.Member, config):
    if member.id in config.get("whitelist_users", []):
        return True

    member_roles = {role.id for role in member.roles}

    if member_roles.intersection(
        set(config.get("whitelist_roles", []))
    ):
        return True

    return False


def contains_link(content: str):
    pattern = r"(https?://|www\.|discord\.gg/|discord\.com/invite/)"
    return re.search(pattern, content.lower()) is not None


class AutoMode(commands.Cog):
    """Air Commander AutoMode / Silent Protect."""

    def __init__(self, bot):
        self.bot = bot

        # guild_id -> user_id -> timestamps
        self.message_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

        # guild_id -> user_id -> recent messages
        self.duplicate_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

        # guild_id -> user_id -> warning count
        self.warning_cache = defaultdict(
            lambda: defaultdict(int)
        )

    # =========================================================
    # LOGGING
    # =========================================================

    async def get_log_channel(self, guild: discord.Guild):
        config = get_guild_config(guild.id)

        channel_id = config.get("log_channel_id")

        if channel_id:
            channel = guild.get_channel(channel_id)

            if channel:
                return channel

        return None

    async def send_log(
        self,
        guild: discord.Guild,
        title: str,
        description: str,
        user: discord.Member = None,
        action: str = None
    ):
        channel = await self.get_log_channel(guild)

        if not channel:
            return

        embed = discord.Embed(
            title=f"🛡️ {title}",
            description=description,
            timestamp=discord.utils.utcnow()
        )

        if user:
            embed.add_field(
                name="User",
                value=f"{user.mention}\n`{user}`\nID: `{user.id}`",
                inline=False
            )

        if action:
            embed.add_field(
                name="Action",
                value=f"`{action}`",
                inline=False
            )

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

    # =========================================================
    # ENABLE
    # =========================================================

    async def enable_automode(self, guild: discord.Guild):
        config = get_guild_config(guild.id)

        if config.get("enabled"):
            return None, "⚠️ AutoMode is already enabled."

        # Try to find an existing channel first
        channel = discord.utils.get(
            guild.text_channels,
            name="commander-logs"
        )

        if channel is None:
            try:
                channel = await guild.create_text_channel(
                    "commander-logs",
                    reason="Air Commander AutoMode enabled"
                )
            except discord.Forbidden:
                return None, (
                    "❌ I don't have permission to create channels."
                )
            except discord.HTTPException:
                return None, (
                    "❌ Discord rejected the channel creation request."
                )

        config["enabled"] = True
        config["log_channel_id"] = channel.id

        update_guild_config(guild.id, config)

        await self.send_log(
            guild,
            "AutoMode Enabled",
            "Air Commander AutoMode has been enabled.",
            action="AUTOMODE ENABLE"
        )

        return channel, (
            f"🛡️ **AutoMode enabled!**\n"
            f"📋 Logs: {channel.mention}\n\n"
            f"Use `/automode config` to configure protection."
        )

    async def disable_automode(self, guild: discord.Guild):
        config = get_guild_config(guild.id)

        if not config.get("enabled"):
            return "⚠️ AutoMode is already disabled."

        config["enabled"] = False
        update_guild_config(guild.id, config)

        await self.send_log(
            guild,
            "AutoMode Disabled",
            "AutoMode protection has been disabled.",
            action="AUTOMODE DISABLE"
        )

        return "🔴 **AutoMode disabled.**"

    # =========================================================
    # MODERATION
    # =========================================================

    async def warn_member(
        self,
        member: discord.Member,
        reason: str
    ):
        guild = member.guild
        config = get_guild_config(guild.id)

        warnings = config.setdefault("warnings", {})
        uid = str(member.id)

        warnings[uid] = int(warnings.get(uid, 0)) + 1

        count = warnings[uid]

        update_guild_config(guild.id, config)

        await self.send_log(
            guild,
            "Member Warned",
            f"Reason: **{reason}**\n"
            f"Warning count: **{count}**",
            user=member,
            action="WARN"
        )

        return count

    async def timeout_member(
        self,
        member: discord.Member,
        reason: str
    ):
        config = get_guild_config(member.guild.id)

        minutes = int(config.get("timeout_minutes", 10))

        try:
            await member.timeout(
                timedelta(minutes=minutes),
                reason=f"AutoMode: {reason}"
            )

            await self.send_log(
                member.guild,
                "Member Timed Out",
                f"Reason: **{reason}**\n"
                f"Duration: **{minutes} minutes**",
                user=member,
                action="TIMEOUT"
            )

            return True

        except discord.Forbidden:
            await self.send_log(
                member.guild,
                "Moderation Failed",
                "I could not timeout this member because of permissions/role hierarchy.",
                user=member,
                action="TIMEOUT FAILED"
            )
            return False

        except discord.HTTPException:
            return False

    # =========================================================
    # MESSAGE PROTECTION
    # =========================================================

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):

        if message.author.bot:
            return

        if not message.guild:
            return

        config = get_guild_config(message.guild.id)

        if not config.get("enabled"):
            return

        member = message.author

        if not isinstance(member, discord.Member):
            return

        # Don't moderate server administrators
        if member.guild_permissions.administrator:
            return

        # Whitelist
        if is_whitelisted(member, config):
            return

        now = time.monotonic()

        user_messages = self.message_tracker[
            message.guild.id
        ][member.id]

        # Remove old timestamps
        window = int(config.get("spam_window", 7))

        while user_messages and now - user_messages[0] > window:
            user_messages.popleft()

        user_messages.append(now)

        # =====================================================
        # LINK PROTECTION
        # =====================================================

        if config.get("link_protection"):

            if contains_link(message.content):

                try:
                    await message.delete()
                except discord.HTTPException:
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

        # =====================================================
        # MENTION SPAM
        # =====================================================

        if config.get("mention_protection"):

            mention_count = (
                len(message.mentions)
                + len(message.role_mentions)
            )

            limit = int(
                config.get("mention_limit", 5)
            )

            if mention_count >= limit:

                try:
                    await message.delete()
                except discord.HTTPException:
                    pass

                count = await self.warn_member(
                    member,
                    f"Mention spam ({mention_count} mentions)"
                )

                await self.handle_escalation(
                    member,
                    count,
                    "Mention spam"
                )

                return

        # =====================================================
        # DUPLICATE MESSAGE PROTECTION
        # =====================================================

        if config.get("duplicate_protection"):

            recent = self.duplicate_tracker[
                message.guild.id
            ][member.id]

            recent.append(message.content.lower().strip())

            while len(recent) > 5:
                recent.popleft()

            duplicate_limit = int(
                config.get("duplicate_limit", 3)
            )

            if (
                message.content.strip()
                and list(recent).count(
                    message.content.lower().strip()
                ) >= duplicate_limit
            ):

                try:
                    await message.delete()
                except discord.HTTPException:
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

        # =====================================================
        # GENERAL SPAM
        # =====================================================

        spam_limit = int(
            config.get("spam_messages", 5)
        )

        if len(user_messages) >= spam_limit:

            # Clear tracker so one spam burst doesn't
            # trigger the system continuously.
            user_messages.clear()

            try:
                await message.delete()
            except discord.HTTPException:
                pass

            count = await self.warn_member(
                member,
                f"Spam detected ({spam_limit} messages)"
            )

            await self.handle_escalation(
                member,
                count,
                "Message spam"
            )

    # =========================================================
    # ESCALATION
    # =========================================================

    async def handle_escalation(
        self,
        member: discord.Member,
        warning_count: int,
        reason: str
    ):

        config = get_guild_config(member.guild.id)

        # Warning threshold
        warn_after = int(
            config.get("warn_after", 3)
        )

        # Timeout threshold
        timeout_after = int(
            config.get("timeout_after", 5)
        )

        # Timeout
        if (
            config.get("timeout_enabled")
            and warning_count >= timeout_after
        ):

            await self.timeout_member(
                member,
                f"{reason} | {warning_count} warnings"
            )

            return

        # Warn only
        if (
            config.get("warn_enabled")
            and warning_count >= warn_after
        ):

            await self.send_log(
                member.guild,
                "Warning Threshold Reached",
                f"{member.mention} reached "
                f"**{warning_count} warnings**.",
                user=member,
                action="WARNING THRESHOLD"
            )

    # =========================================================
    # SLASH COMMAND GROUP
    # =========================================================

    automode_group = app_commands.Group(
        name="automode",
        description="Configure Air Commander AutoMode"
    )

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

        channel, result = await self.enable_automode(
            interaction.guild
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

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

        result = await self.disable_automode(
            interaction.guild
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

    # =========================================================
    # STATUS
    # =========================================================

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

        log_channel = interaction.guild.get_channel(
            config.get("log_channel_id")
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
                f"`{config.get('spam_messages')}` messages / "
                f"`{config.get('spam_window')}s`"
            ),
            inline=True
        )

        embed.add_field(
            name="Warning",
            value=(
                f"`{config.get('warn_after')}` warnings"
            ),
            inline=True
        )

        embed.add_field(
            name="Timeout",
            value=(
                f"`{config.get('timeout_after')}` warnings\n"
                f"`{config.get('timeout_minutes')}` minutes"
            ),
            inline=True
        )

        embed.add_field(
            name="Protection",
            value=(
                f"Links: {'ON' if config.get('link_protection') else 'OFF'}\n"
                f"Mentions: {'ON' if config.get('mention_protection') else 'OFF'}\n"
                f"Duplicates: {'ON' if config.get('duplicate_protection') else 'OFF'}"
            ),
            inline=False
        )

        embed.add_field(
            name="Whitelist",
            value=(
                f"Users: `{len(config.get('whitelist_users', []))}`\n"
                f"Roles: `{len(config.get('whitelist_roles', []))}`"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =========================================================
    # CONFIG
    # =========================================================

    @automode_group.command(
        name="config",
        description="Configure AutoMode settings"
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
                f"Messages: `{config['spam_messages']}`\n"
                f"Window: `{config['spam_window']} seconds`"
            ),
            inline=False
        )

        embed.add_field(
            name="Warnings",
            value=(
                f"Enabled: `{config['warn_enabled']}`\n"
                f"Warn threshold: `{config['warn_after']}`"
            ),
            inline=False
        )

        embed.add_field(
            name="Timeout",
            value=(
                f"Enabled: `{config['timeout_enabled']}`\n"
                f"Threshold: `{config['timeout_after']}` warnings\n"
                f"Duration: `{config['timeout_minutes']} minutes`"
            ),
            inline=False
        )

        embed.add_field(
            name="Protection",
            value=(
                f"Links: `{config['link_protection']}`\n"
                f"Mentions: `{config['mention_protection']}`\n"
                f"Duplicates: `{config['duplicate_protection']}`"
            ),
            inline=False
        )

        embed.set_footer(
            text="Use the prefix config commands to change values."
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # =========================================================
    # WHITELIST - SLASH
    # =========================================================

    whitelist_group = app_commands.Group(
        name="whitelist",
        description="Manage AutoMode whitelist"
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
            "whitelist_users", []
        )

        if user.id not in users:
            users.append(user.id)

        update_guild_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            f"✅ {user.mention} has been added to the AutoMode whitelist.",
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
            "whitelist_roles", []
        )

        if role.id not in roles:
            roles.append(role.id)

        update_guild_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            f"✅ {role.mention} has been added to the AutoMode whitelist.",
            ephemeral=True
        )

    # =========================================================
    # PREFIX COMMANDS
    # =========================================================

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
            "`,automode whitelist user @User`\n"
            "`,automode whitelist role @Role`"
        )

    @automode_prefix.command(name="enable")
    async def automode_prefix_enable(
        self,
        ctx: commands.Context
    ):

        _, result = await self.enable_automode(
            ctx.guild
        )

        await ctx.send(result)

    @automode_prefix.command(name="disable")
    async def automode_prefix_disable(
        self,
        ctx: commands.Context
    ):

        result = await self.disable_automode(
            ctx.guild
        )

        await ctx.send(result)

    @automode_prefix.command(name="status")
    async def automode_prefix_status(
        self,
        ctx: commands.Context
    ):

        config = get_guild_config(
            ctx.guild.id
        )

        log_channel = ctx.guild.get_channel(
            config.get("log_channel_id")
        )

        await ctx.send(
            "🛡️ **AutoMode Status**\n\n"
            f"Status: {'🟢 Enabled' if config['enabled'] else '🔴 Disabled'}\n"
            f"Logs: {log_channel.mention if log_channel else 'Not configured'}\n"
            f"Spam: `{config['spam_messages']}` messages / `{config['spam_window']}s`\n"
            f"Warn after: `{config['warn_after']}`\n"
            f"Timeout after: `{config['timeout_after']}` warnings\n"
            f"Timeout duration: `{config['timeout_minutes']} min`\n"
            f"Link protection: `{config['link_protection']}`\n"
            f"Mention protection: `{config['mention_protection']}`"
        )

    @automode_prefix.command(name="config")
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

    # =========================================================
    # PREFIX CONFIG SETTINGS
    # =========================================================

    @automode_prefix.command(name="spam")
    async def automode_spam(
        self,
        ctx: commands.Context,
        messages: int,
        seconds: int
    ):

        if messages < 2 or seconds < 1:
            return await ctx.send(
                "❌ Invalid spam configuration."
            )

        config = get_guild_config(ctx.guild.id)

        config["spam_messages"] = messages
        config["spam_window"] = seconds

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ Spam protection set to "
            f"**{messages} messages / {seconds} seconds**."
        )

    @automode_prefix.command(name="warn")
    async def automode_warn(
        self,
        ctx: commands.Context,
        warnings: int
    ):

        if warnings < 1:
            return await ctx.send(
                "❌ Warning threshold must be at least 1."
            )

        config = get_guild_config(ctx.guild.id)

        config["warn_after"] = warnings

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ Warning threshold set to **{warnings}**."
        )

    @automode_prefix.command(name="timeout")
    async def automode_timeout(
        self,
        ctx: commands.Context,
        warnings: int,
        minutes: int
    ):

        if warnings < 1 or minutes < 1:
            return await ctx.send(
                "❌ Invalid timeout configuration."
            )

        config = get_guild_config(ctx.guild.id)

        config["timeout_after"] = warnings
        config["timeout_minutes"] = minutes

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ Timeout will trigger at **{warnings} warnings** "
            f"for **{minutes} minutes**."
        )

    @automode_prefix.command(name="links")
    async def automode_links(
        self,
        ctx: commands.Context,
        state: str
    ):

        state = state.lower()

        if state not in ("on", "off"):
            return await ctx.send(
                "Use `on` or `off`."
            )

        config = get_guild_config(ctx.guild.id)

        config["link_protection"] = state == "on"

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"🔗 Link protection: **{state.upper()}**"
        )

    @automode_prefix.command(name="mentions")
    async def automode_mentions(
        self,
        ctx: commands.Context,
        state: str
    ):

        state = state.lower()

        if state not in ("on", "off"):
            return await ctx.send(
                "Use `on` or `off`."
            )

        config = get_guild_config(ctx.guild.id)

        config["mention_protection"] = state == "on"

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"📢 Mention protection: **{state.upper()}**"
        )

    @automode_prefix.command(name="duplicates")
    async def automode_duplicates(
        self,
        ctx: commands.Context,
        state: str
    ):

        state = state.lower()

        if state not in ("on", "off"):
            return await ctx.send(
                "Use `on` or `off`."
            )

        config = get_guild_config(ctx.guild.id)

        config["duplicate_protection"] = state == "on"

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"♻️ Duplicate protection: **{state.upper()}**"
        )

    # =========================================================
    # WHITELIST PREFIX GROUP
    # =========================================================

    @automode_prefix.group(
        name="whitelist",
        invoke_without_command=True
    )
    async def whitelist_prefix(
        self,
        ctx: commands.Context
    ):

        await ctx.send(
            "Whitelist commands:\n"
            "`,automode whitelist user @User`\n"
            "`,automode whitelist role @Role`"
        )

    @whitelist_prefix.command(name="user")
    async def whitelist_prefix_user(
        self,
        ctx: commands.Context,
        member: discord.Member
    ):

        config = get_guild_config(ctx.guild.id)

        users = config.setdefault(
            "whitelist_users",
            []
        )

        if member.id not in users:
            users.append(member.id)

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ {member.mention} is now whitelisted."
        )

    @whitelist_prefix.command(name="role")
    async def whitelist_prefix_role(
        self,
        ctx: commands.Context,
        role: discord.Role
    ):

        config = get_guild_config(ctx.guild.id)

        roles = config.setdefault(
            "whitelist_roles",
            []
        )

        if role.id not in roles:
            roles.append(role.id)

        update_guild_config(
            ctx.guild.id,
            config
        )

        await ctx.send(
            f"✅ {role.mention} is now whitelisted."
        )


async def setup(bot):
    await bot.add_cog(AutoMode(bot))
