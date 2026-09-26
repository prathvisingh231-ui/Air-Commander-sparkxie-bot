import discord
from discord.ext import commands
from discord import app_commands

import json
import os
import time
from collections import defaultdict, deque
from datetime import timedelta


CONFIG_FILE = "antinuke_config.json"


DEFAULT_CONFIG = {
    "enabled": False,
    "log_channel_id": None,

    # Punishment
    "punishment": "ban",

    # Protection switches
    "channel_delete": True,
    "channel_create": True,
    "role_delete": True,
    "role_create": True,
    "mass_ban": True,
    "mass_kick": True,
    "webhook": True,
    "bot_add": True,
    "dangerous_role": True,

    # Thresholds
    "channel_delete_limit": 3,
    "channel_create_limit": 5,
    "role_delete_limit": 3,
    "role_create_limit": 5,
    "ban_limit": 3,
    "kick_limit": 3,
    "webhook_limit": 3,

    # Time window
    "threshold_window": 10,

    # Trusted users/roles
    "whitelist_users": [],
    "whitelist_roles": [],

    # Extra owners
    "extra_owners": {},

    # Warning/action tracking
    "actions": {}
}


# ============================================================
# DATABASE
# ============================================================

def load_database():
    if not os.path.exists(CONFIG_FILE):
        return {}

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_database(data):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_config(guild_id: int):
    data = load_database()
    gid = str(guild_id)

    if gid not in data:
        data[gid] = json.loads(
            json.dumps(DEFAULT_CONFIG)
        )
        save_database(data)

    config = data[gid]

    for key, value in DEFAULT_CONFIG.items():
        if key not in config:
            config[key] = json.loads(
                json.dumps(value)
            )

    save_database(data)

    return config


def update_config(guild_id: int, config):
    data = load_database()
    data[str(guild_id)] = config
    save_database(data)


# ============================================================
# ANTINUKE COG
# ============================================================

class AntiNuke(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        # guild -> action -> deque[timestamps]
        self.action_tracker = defaultdict(
            lambda: defaultdict(deque)
        )

    # ========================================================
    # TRUST SYSTEM
    # ========================================================

    async def is_trusted(
        self,
        member: discord.Member,
        config=None
    ):
        if not member:
            return True

        guild = member.guild

        # Discord's actual server owner
        if member.id == guild.owner_id:
            return True

        config = config or get_config(guild.id)

        # Extra owners
        if member.id in [
            int(x)
            for x in config.get(
                "extra_owners",
                {}
            ).keys()
        ]:
            return True

        # Whitelisted users
        if member.id in config.get(
            "whitelist_users",
            []
        ):
            return True

        # Whitelisted roles
        member_role_ids = {
            role.id
            for role in member.roles
        }

        if member_role_ids.intersection(
            set(config.get(
                "whitelist_roles",
                []
            ))
        ):
            return True

        return False

    # ========================================================
    # LOG CHANNEL
    # ========================================================

    async def get_log_channel(
        self,
        guild: discord.Guild
    ):
        config = get_config(guild.id)

        channel_id = config.get(
            "log_channel_id"
        )

        if not channel_id:
            return None

        return guild.get_channel(
            channel_id
        )

    async def log(
        self,
        guild,
        title,
        description,
        member=None,
        action=None
    ):

        channel = await self.get_log_channel(
            guild
        )

        if not channel:
            return

        embed = discord.Embed(
            title=f"🛡️ {title}",
            description=description,
            timestamp=discord.utils.utcnow()
        )

        if member:
            embed.add_field(
                name="Executor",
                value=(
                    f"{member.mention}\n"
                    f"`{member}`\n"
                    f"ID: `{member.id}`"
                ),
                inline=False
            )

        if action:
            embed.add_field(
                name="Action",
                value=f"`{action}`",
                inline=True
            )

        try:
            await channel.send(
                embed=embed
            )
        except discord.HTTPException:
            pass

    # ========================================================
    # CREATE LOG CHANNEL
    # ========================================================

    async def create_log_channel(
        self,
        guild: discord.Guild
    ):

        existing = discord.utils.get(
            guild.text_channels,
            name="commander-antinuke-logs"
        )

        if existing:
            return existing

        try:

            overwrites = {
                guild.default_role:
                    discord.PermissionOverwrite(
                        view_channel=False
                    )
            }

            if guild.me:
                overwrites[guild.me] = (
                    discord.PermissionOverwrite(
                        view_channel=True,
                        send_messages=True,
                        embed_links=True,
                        read_message_history=True
                    )
                )

            channel = await guild.create_text_channel(
                "commander-antinuke-logs",
                overwrites=overwrites,
                reason="Air Commander AntiNuke"
            )

            return channel

        except discord.Forbidden:
            return None

        except discord.HTTPException:
            return None

    # ========================================================
    # ENABLE
    # ========================================================

    async def enable(
        self,
        guild: discord.Guild
    ):

        config = get_config(guild.id)

        if config["enabled"]:
            return None, "⚠️ AntiNuke is already enabled."

        channel = await self.create_log_channel(
            guild
        )

        if channel is None:
            return None, (
                "❌ I couldn't create "
                "`commander-antinuke-logs`.\n"
                "Give me **Manage Channels** permission."
            )

        config["enabled"] = True
        config["log_channel_id"] = channel.id

        update_config(
            guild.id,
            config
        )

        await self.log(
            guild,
            "AntiNuke Enabled",
            (
                "🛡️ Air Commander AntiNuke "
                "has been enabled."
            ),
            action="ENABLE"
        )

        return channel, (
            "🛡️ **AntiNuke Enabled**\n"
            f"📋 Logs: {channel.mention}\n\n"
            "Use `/antinuke config` to customize protection."
        )

    # ========================================================
    # DISABLE
    # ========================================================

    async def disable(
        self,
        guild: discord.Guild
    ):

        config = get_config(guild.id)

        if not config["enabled"]:
            return "⚠️ AntiNuke is already disabled."

        config["enabled"] = False

        update_config(
            guild.id,
            config
        )

        await self.log(
            guild,
            "AntiNuke Disabled",
            "AntiNuke protection has been disabled.",
            action="DISABLE"
        )

        return "🔴 **AntiNuke Disabled.**"

    # ========================================================
    # ACTION TRACKER
    # ========================================================

    def register_action(
        self,
        guild_id,
        user_id,
        action,
        window
    ):

        key = f"{user_id}:{action}"

        queue = self.action_tracker[
            guild_id
        ][key]

        now = time.monotonic()

        while queue and (
            now - queue[0] > window
        ):
            queue.popleft()

        queue.append(now)

        return len(queue)

    # ========================================================
    # FIND AUDIT LOG EXECUTOR
    # ========================================================

    async def get_executor(
        self,
        guild,
        action,
        target_id=None
    ):

        try:

            async for entry in guild.audit_logs(
                limit=8,
                action=action
            ):

                if target_id is not None:

                    if getattr(
                        entry.target,
                        "id",
                        None
                    ) != target_id:
                        continue

                # Small delay can sometimes be needed
                # for Discord audit logs.
                if entry.user:
                    return entry.user

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            return None

        return None

    # ========================================================
    # PUNISH
    # ========================================================

    async def punish(
        self,
        guild,
        member,
        reason
    ):

        if not member:
            return

        config = get_config(guild.id)

        if await self.is_trusted(
            member,
            config
        ):
            return

        # Never punish bot itself
        if member.id == self.bot.user.id:
            return

        punishment = config.get(
            "punishment",
            "ban"
        )

        success = False

        try:

            if punishment == "ban":

                await guild.ban(
                    member,
                    reason=f"AntiNuke: {reason}",
                    delete_message_seconds=0
                )

                success = True

            elif punishment == "kick":

                await guild.kick(
                    member,
                    reason=f"AntiNuke: {reason}"
                )

                success = True

            elif punishment == "timeout":

                await member.timeout(
                    timedelta(
                        minutes=60
                    ),
                    reason=f"AntiNuke: {reason}"
                )

                success = True

        except (
            discord.Forbidden,
            discord.HTTPException
        ):
            success = False

        await self.log(
            guild,
            "🚨 AntiNuke Action",
            (
                f"Reason: **{reason}**\n"
                f"Punishment: **{punishment}**\n"
                f"Successful: **{success}**"
            ),
            member=member,
            action=punishment.upper()
        )

    # ========================================================
    # THRESHOLD CHECK
    # ========================================================

    async def check_action(
        self,
        guild,
        member,
        action_name,
        limit,
        reason
    ):

        if not member:
            return

        config = get_config(guild.id)

        if await self.is_trusted(
            member,
            config
        ):
            return

        count = self.register_action(
            guild.id,
            member.id,
            action_name,
            config.get(
                "threshold_window",
                10
            )
        )

        await self.log(
            guild,
            "⚠️ Protected Action Detected",
            (
                f"Action: **{action_name}**\n"
                f"Count: **{count}/{limit}**"
            ),
            member=member,
            action="DETECTED"
        )

        if count >= limit:

            await self.punish(
                guild,
                member,
                reason
            )

            self.action_tracker[
                guild.id
            ][
                f"{member.id}:{action_name}"
            ].clear()

    # ========================================================
    # CHANNEL DELETE
    # ========================================================

    @commands.Cog.listener()
    async def on_guild_channel_delete(
        self,
        channel
    ):

        guild = channel.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["channel_delete"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.channel_delete,
            channel.id
        )

        await self.check_action(
            guild,
            executor,
            "channel_delete",
            config["channel_delete_limit"],
            "Mass channel deletion"
        )

    # ========================================================
    # CHANNEL CREATE
    # ========================================================

    @commands.Cog.listener()
    async def on_guild_channel_create(
        self,
        channel
    ):

        guild = channel.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["channel_create"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.channel_create,
            channel.id
        )

        await self.check_action(
            guild,
            executor,
            "channel_create",
            config["channel_create_limit"],
            "Mass channel creation"
        )

    # ========================================================
    # ROLE DELETE
    # ========================================================

    @commands.Cog.listener()
    async def on_guild_role_delete(
        self,
        role
    ):

        guild = role.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["role_delete"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.role_delete,
            role.id
        )

        await self.check_action(
            guild,
            executor,
            "role_delete",
            config["role_delete_limit"],
            "Mass role deletion"
        )

    # ========================================================
    # ROLE CREATE
    # ========================================================

    @commands.Cog.listener()
    async def on_guild_role_create(
        self,
        role
    ):

        guild = role.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["role_create"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.role_create,
            role.id
        )

        await self.check_action(
            guild,
            executor,
            "role_create",
            config["role_create_limit"],
            "Mass role creation"
        )

    # ========================================================
    # MEMBER BAN
    # ========================================================

    @commands.Cog.listener()
    async def on_member_ban(
        self,
        guild,
        user
    ):

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["mass_ban"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.ban,
            user.id
        )

        await self.check_action(
            guild,
            executor,
            "mass_ban",
            config["ban_limit"],
            "Mass member banning"
        )

    # ========================================================
    # MEMBER KICK
    # ========================================================

    @commands.Cog.listener()
    async def on_member_remove(
        self,
        member
    ):

        guild = member.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["mass_kick"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.kick,
            member.id
        )

        if executor:

            await self.check_action(
                guild,
                executor,
                "mass_kick",
                config["kick_limit"],
                "Mass member kicking"
            )

    # ========================================================
    # WEBHOOK
    # ========================================================

    @commands.Cog.listener()
    async def on_webhooks_update(
        self,
        channel
    ):

        guild = channel.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["webhook"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.webhook_create
        )

        await self.check_action(
            guild,
            executor,
            "webhook",
            config["webhook_limit"],
            "Suspicious webhook activity"
        )

    # ========================================================
    # BOT ADD
    # ========================================================

    @commands.Cog.listener()
    async def on_member_join(
        self,
        member
    ):

        if not member.bot:
            return

        guild = member.guild

        config = get_config(
            guild.id
        )

        if not config["enabled"]:
            return

        if not config["bot_add"]:
            return

        executor = await self.get_executor(
            guild,
            discord.AuditLogAction.bot_add,
            member.id
        )

        if executor:

            await self.log(
                guild,
                "🤖 Bot Added",
                (
                    f"Bot added: {member.mention}\n"
                    f"Added by: {executor.mention}"
                ),
                member=executor,
                action="BOT ADD"
            )

            # If executor isn't trusted,
            # punish the executor.
            if not await self.is_trusted(
                executor,
                config
            ):

                await self.punish(
                    guild,
                    executor,
                    "Unauthorized bot addition"
                )

                try:
                    await guild.kick(
                        member,
                        reason="AntiNuke: Unauthorized bot"
                    )
                except (
                    discord.Forbidden,
                    discord.HTTPException
                ):
                    pass

    # ========================================================
    # SLASH GROUP
    # ========================================================

    antinuke_group = app_commands.Group(
        name="antinuke",
        description="Configure Air Commander AntiNuke"
    )

    # ========================================================
    # ENABLE
    # ========================================================

    @antinuke_group.command(
        name="enable",
        description="Enable AntiNuke"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def antinuke_enable(
        self,
        interaction: discord.Interaction
    ):

        _, result = await self.enable(
            interaction.guild
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

    # ========================================================
    # DISABLE
    # ========================================================

    @antinuke_group.command(
        name="disable",
        description="Disable AntiNuke"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def antinuke_disable(
        self,
        interaction: discord.Interaction
    ):

        result = await self.disable(
            interaction.guild
        )

        await interaction.response.send_message(
            result,
            ephemeral=True
        )

    # ========================================================
    # STATUS
    # ========================================================

    @antinuke_group.command(
        name="status",
        description="View AntiNuke status"
    )
    async def antinuke_status(
        self,
        interaction: discord.Interaction
    ):

        config = get_config(
            interaction.guild.id
        )

        channel = interaction.guild.get_channel(
            config.get("log_channel_id")
        )

        embed = discord.Embed(
            title="🛡️ Air Commander AntiNuke",
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="Status",
            value=(
                "🟢 Enabled"
                if config["enabled"]
                else "🔴 Disabled"
            ),
            inline=True
        )

        embed.add_field(
            name="Punishment",
            value=f"`{config['punishment']}`",
            inline=True
        )

        embed.add_field(
            name="Logs",
            value=(
                channel.mention
                if channel
                else "Not configured"
            ),
            inline=True
        )

        embed.add_field(
            name="Threshold Window",
            value=f"`{config['threshold_window']} seconds`",
            inline=False
        )

        embed.add_field(
            name="Protection",
            value=(
                f"Channels: `{config['channel_delete']}`\n"
                f"Roles: `{config['role_delete']}`\n"
                f"Mass Ban: `{config['mass_ban']}`\n"
                f"Mass Kick: `{config['mass_kick']}`\n"
                f"Webhooks: `{config['webhook']}`\n"
                f"Bot Add: `{config['bot_add']}`"
            ),
            inline=False
        )

        embed.add_field(
            name="Whitelist",
            value=(
                f"Users: `{len(config['whitelist_users'])}`\n"
                f"Roles: `{len(config['whitelist_roles'])}`\n"
                f"Extra Owners: `{len(config['extra_owners'])}`"
            ),
            inline=False
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # WHITELIST USER
    # ========================================================

    @antinuke_group.command(
        name="whitelist",
        description="Whitelist a user or role"
    )
    @app_commands.describe(
        user="User to whitelist",
        role="Role to whitelist"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def antinuke_whitelist(
        self,
        interaction: discord.Interaction,
        user: discord.Member = None,
        role: discord.Role = None
    ):

        if not user and not role:

            return await interaction.response.send_message(
                "❌ Mention a user or select a role.",
                ephemeral=True
            )

        config = get_config(
            interaction.guild.id
        )

        if user:

            if user.id not in config["whitelist_users"]:
                config["whitelist_users"].append(
                    user.id
                )

            update_config(
                interaction.guild.id,
                config
            )

            return await interaction.response.send_message(
                f"✅ {user.mention} is now whitelisted.",
                ephemeral=True
            )

        if role:

            if role.id not in config["whitelist_roles"]:
                config["whitelist_roles"].append(
                    role.id
                )

            update_config(
                interaction.guild.id,
                config
            )

            return await interaction.response.send_message(
                f"✅ {role.mention} is now whitelisted.",
                ephemeral=True
            )

    # ========================================================
    # EXTRA OWNER GROUP
    # ========================================================

    extraowner_group = app_commands.Group(
        name="extraowner",
        description="Manage AntiNuke extra owners"
    )

    @extraowner_group.command(
        name="add",
        description="Add an extra trusted owner"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def extraowner_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):

        # Only actual server owner can manage
        # extra owners.
        if interaction.user.id != interaction.guild.owner_id:

            return await interaction.response.send_message(
                "❌ Only the actual server owner can manage Extra Owners.",
                ephemeral=True
            )

        config = get_config(
            interaction.guild.id
        )

        config["extra_owners"][
            str(user.id)
        ] = user.name

        update_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            f"👑 {user.mention} has been added as an **Extra Owner**.",
            ephemeral=True
        )

    @extraowner_group.command(
        name="remove",
        description="Remove an extra owner"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def extraowner_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):

        if interaction.user.id != interaction.guild.owner_id:

            return await interaction.response.send_message(
                "❌ Only the actual server owner can manage Extra Owners.",
                ephemeral=True
            )

        config = get_config(
            interaction.guild.id
        )

        config["extra_owners"].pop(
            str(user.id),
            None
        )

        update_config(
            interaction.guild.id,
            config
        )

        await interaction.response.send_message(
            f"✅ {user.mention} removed from Extra Owners.",
            ephemeral=True
        )

    @extraowner_group.command(
        name="list",
        description="Show Extra Owners"
    )
    async def extraowner_list(
        self,
        interaction: discord.Interaction
    ):

        config = get_config(
            interaction.guild.id
        )

        owners = config.get(
            "extra_owners",
            {}
        )

        if not owners:

            return await interaction.response.send_message(
                "👑 No Extra Owners configured.",
                ephemeral=True
            )

        text = []

        for uid in owners:

            member = interaction.guild.get_member(
                int(uid)
            )

            if member:
                text.append(
                    f"• {member.mention} (`{uid}`)"
                )
            else:
                text.append(
                    f"• `<@{uid}>` (`{uid}`)"
                )

        await interaction.response.send_message(
            "👑 **AntiNuke Extra Owners**\n\n"
            + "\n".join(text),
            ephemeral=True
        )

    # ========================================================
    # CONFIG
    # ========================================================

    @antinuke_group.command(
        name="config",
        description="View AntiNuke configuration"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def antinuke_config(
        self,
        interaction: discord.Interaction
    ):

        config = get_config(
            interaction.guild.id
        )

        embed = discord.Embed(
            title="⚙️ AntiNuke Configuration"
        )

        embed.add_field(
            name="Punishment",
            value=f"`{config['punishment']}`",
            inline=True
        )

        embed.add_field(
            name="Window",
            value=f"`{config['threshold_window']} sec`",
            inline=True
        )

        embed.add_field(
            name="Channel Delete",
            value=f"`{config['channel_delete_limit']}` actions",
            inline=True
        )

        embed.add_field(
            name="Channel Create",
            value=f"`{config['channel_create_limit']}` actions",
            inline=True
        )

        embed.add_field(
            name="Role Delete",
            value=f"`{config['role_delete_limit']}` actions",
            inline=True
        )

        embed.add_field(
            name="Mass Ban",
            value=f"`{config['ban_limit']}` bans",
            inline=True
        )

        embed.add_field(
            name="Mass Kick",
            value=f"`{config['kick_limit']}` kicks",
            inline=True
        )

        embed.add_field(
            name="Webhook",
            value=f"`{config['webhook_limit']}` actions",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(
        AntiNuke(bot)
    )
