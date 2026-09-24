import asyncio
import os
import re
from collections import defaultdict, deque
from datetime import timedelta

import asyncpg
import discord
from discord import app_commands
from discord.ext import commands

OWNER_ID = 1504354088538869892
DB_URL = os.getenv("DATABASE_URL")
_pool = None

LINK_RE = re.compile(r"(?:https?://|www\.)\S+", re.I)
SPAM = defaultdict(lambda: deque(maxlen=20))
CONFIG_CACHE = {}


def clean_color(value: str) -> discord.Colour:
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        raise ValueError("Use a 6-digit hex color such as #5865F2.")
    return discord.Colour(int(value, 16))


async def init_security_db():
    global _pool
    if _pool or not DB_URL:
        return
    try:
        _pool = await asyncpg.create_pool(DB_URL, min_size=1, max_size=4, command_timeout=15)
        async with _pool.acquire() as c:
            await c.execute("""
                CREATE TABLE IF NOT EXISTS security_config(
                    guild_id BIGINT PRIMARY KEY,
                    automod_enabled BOOLEAN DEFAULT FALSE,
                    automod_spam_limit INT DEFAULT 5,
                    automod_spam_seconds INT DEFAULT 3,
                    automod_action TEXT DEFAULT 'warn',
                    automod_mention_limit INT DEFAULT 5,
                    automod_emoji_limit INT DEFAULT 10,
                    automod_lines_limit INT DEFAULT 12,
                    automod_chars_limit INT DEFAULT 2000,
                    antilink_enabled BOOLEAN DEFAULT FALSE,
                    antilink_action TEXT DEFAULT 'delete',
                    antinuke_enabled BOOLEAN DEFAULT FALSE,
                    antinuke_action TEXT DEFAULT 'ban'
                );
                CREATE TABLE IF NOT EXISTS security_whitelist(
                    guild_id BIGINT,
                    user_id BIGINT,
                    kind TEXT DEFAULT 'user',
                    PRIMARY KEY(guild_id,user_id)
                );
                CREATE TABLE IF NOT EXISTS security_warnings(
                    id BIGSERIAL PRIMARY KEY,
                    guild_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    moderator_id BIGINT NOT NULL,
                    reason TEXT NOT NULL,
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
            """)
        print("🛡️ Security database ready")
    except Exception as e:
        _pool = None
        print(f"⚠️ Security database unavailable: {type(e).__name__}: {e}")


async def cfg(guild_id):
    if guild_id in CONFIG_CACHE:
        return CONFIG_CACHE[guild_id]
    defaults = {
        "automod_enabled": False, "automod_spam_limit": 5, "automod_spam_seconds": 3,
        "automod_action": "warn", "automod_mention_limit": 5, "automod_emoji_limit": 10,
        "automod_lines_limit": 12, "automod_chars_limit": 2000,
        "antilink_enabled": False, "antilink_action": "delete",
        "antinuke_enabled": False, "antinuke_action": "ban"
    }
    if not _pool:
        return defaults.copy()
    row = await _pool.fetchrow("SELECT * FROM security_config WHERE guild_id=$1", guild_id)
    if not row:
        await _pool.execute("INSERT INTO security_config(guild_id) VALUES($1) ON CONFLICT DO NOTHING", guild_id)
        CONFIG_CACHE[guild_id] = defaults.copy()
        return CONFIG_CACHE[guild_id]
    data = dict(row)
    CONFIG_CACHE[guild_id] = data
    return data


async def set_cfg(guild_id, **values):
    data = await cfg(guild_id)
    data.update(values)
    CONFIG_CACHE[guild_id] = data
    if _pool:
        cols = [k for k in values if k in data and k != "guild_id"]
        if cols:
            sets = ",".join(f"{k}=${i+2}" for i,k in enumerate(cols))
            await _pool.execute(
                f"INSERT INTO security_config(guild_id,{','.join(cols)}) VALUES($1,{','.join(f'${i+2}' for i in range(len(cols)))}) ON CONFLICT(guild_id) DO UPDATE SET {sets}",
                guild_id, *[values[k] for k in cols]
            )


async def is_whitelisted(guild_id, user_id):
    if user_id == OWNER_ID:
        return True
    if not _pool:
        return False
    return bool(await _pool.fetchval("SELECT 1 FROM security_whitelist WHERE guild_id=$1 AND user_id=$2", guild_id, user_id))


async def whitelist_user(guild_id, user_id):
    if _pool:
        await _pool.execute("INSERT INTO security_whitelist(guild_id,user_id) VALUES($1,$2) ON CONFLICT DO NOTHING", guild_id, user_id)


async def unwhitelist_user(guild_id, user_id):
    if _pool:
        await _pool.execute("DELETE FROM security_whitelist WHERE guild_id=$1 AND user_id=$2", guild_id, user_id)


async def add_warning(guild_id, user_id, moderator_id, reason):
    if not _pool:
        return 0
    return await _pool.fetchval(
        "INSERT INTO security_warnings(guild_id,user_id,moderator_id,reason) VALUES($1,$2,$3,$4) RETURNING id",
        guild_id, user_id, moderator_id, reason
    )


async def remove_warning(guild_id, case_id):
    if not _pool:
        return False
    return bool(await _pool.execute("DELETE FROM security_warnings WHERE guild_id=$1 AND id=$2", guild_id, case_id) == "DELETE 1")


async def warning_count(guild_id, user_id):
    if not _pool:
        return 0
    return int(await _pool.fetchval("SELECT COUNT(*) FROM security_warnings WHERE guild_id=$1 AND user_id=$2", guild_id, user_id))


async def punish(member: discord.Member, action: str, reason: str, duration: int = 10):
    try:
        if action == "warn":
            await add_warning(member.guild.id, member.id, member.guild.me.id, reason)
        elif action == "mute":
            await member.timeout(timedelta(minutes=duration), reason=reason)
        elif action == "kick":
            await member.kick(reason=reason)
        elif action == "ban":
            await member.ban(reason=reason, delete_message_seconds=0)
    except (discord.Forbidden, discord.HTTPException) as e:
        print(f"⚠️ Security punishment failed for {member.id}: {e}")


def admin_check(interaction: discord.Interaction) -> bool:
    return bool(interaction.guild and (interaction.user.id == OWNER_ID or interaction.user.guild_permissions.manage_guild))


def embed(title, description, success=True):
    e = discord.Embed(title=("✅ " if success else "⚠️ ") + title, description=description, colour=discord.Colour.blurple() if success else discord.Colour.orange())
    e.set_footer(text="Air Commander • Security")
    return e


class Security(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._audit_seen = set()

    async def security_action(self, guild: discord.Guild, actor_id: int, reason: str):
        if actor_id == guild.me.id or await is_whitelisted(guild.id, actor_id):
            return False
        member = guild.get_member(actor_id)
        if not member:
            try:
                member = await guild.fetch_member(actor_id)
            except discord.HTTPException:
                return False
        if not member or not member.bannable:
            owner = guild.owner
            if owner:
                try: await owner.send(f"🚨 Anti-nuke detected `{actor_id}` in **{guild.name}**, but I could not ban them. Move my role above their role and ensure I have Ban Members.")
                except discord.HTTPException: pass
            return False
        await member.ban(reason=f"Anti-nuke: {reason}", delete_message_seconds=0)
        try:
            await guild.owner.send(f"🚨 Anti-nuke triggered in **{guild.name}**. Banned <@{actor_id}> for: {reason}")
        except discord.HTTPException: pass
        return True

    async def audit_trigger(self, guild, action, reason):
        if not (await cfg(guild.id)).get("antinuke_enabled"):
            return
        await asyncio.sleep(0.8)
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                if entry.id in self._audit_seen:
                    continue
                self._audit_seen.add(entry.id)
                await self.security_action(guild, entry.user.id, reason)
                return
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await self.audit_trigger(channel.guild, discord.AuditLogAction.channel_create, "created a channel")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        await self.audit_trigger(channel.guild, discord.AuditLogAction.channel_delete, "deleted a channel")

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await self.audit_trigger(role.guild, discord.AuditLogAction.role_create, "created a role")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        await self.audit_trigger(role.guild, discord.AuditLogAction.role_delete, "deleted a role")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        await self.audit_trigger(after.guild, discord.AuditLogAction.role_update, "changed a role")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        await self.audit_trigger(guild, discord.AuditLogAction.ban, "banned a member")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        if member.bot:
            await self.audit_trigger(member.guild, discord.AuditLogAction.bot_add, "removed a bot/member")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        if member.bot and (await cfg(member.guild.id)).get("antinuke_enabled"):
            await asyncio.sleep(1)
            try:
                async for entry in member.guild.audit_logs(limit=5, action=discord.AuditLogAction.bot_add):
                    if entry.target and entry.target.id == member.id:
                        await self.security_action(member.guild, entry.user.id, "added an unauthorized bot")
                        return
            except (discord.Forbidden, discord.HTTPException):
                pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if not message.guild or message.author.bot:
            return
        c = await cfg(message.guild.id)
        if c.get("antilink_enabled") and LINK_RE.search(message.content) and not await is_whitelisted(message.guild.id, message.author.id):
            try: await message.delete()
            except discord.HTTPException: pass
            if c.get("antilink_action") in {"warn", "mute", "kick", "ban"} and isinstance(message.author, discord.Member):
                await punish(message.author, c["antilink_action"], "Anti-link: unauthorized link")
            return
        if not c.get("automod_enabled") or await is_whitelisted(message.guild.id, message.author.id):
            return
        now = message.created_at.timestamp()
        key = (message.guild.id, message.author.id)
        q = SPAM[key]
        q.append(now)
        while q and now - q[0] > c.get("automod_spam_seconds", 3): q.popleft()
        reasons = []
        if len(q) >= c.get("automod_spam_limit", 5): reasons.append("spam")
        if len(message.mentions) >= c.get("automod_mention_limit", 5): reasons.append("mention spam")
        emoji_count = len(re.findall(r"<a?:\w+:\d+>|[\U0001F300-\U0001FAFF]", message.content))
        if emoji_count >= c.get("automod_emoji_limit", 10): reasons.append("emoji spam")
        if message.mention_everyone: reasons.append("@everyone/@here spam")
        if len(message.content.splitlines()) > c.get("automod_lines_limit", 12) or len(message.content) > c.get("automod_chars_limit", 2000): reasons.append("line/character spam")
        if reasons:
            try: await message.delete()
            except discord.HTTPException: pass
            if isinstance(message.author, discord.Member):
                await punish(message.author, c.get("automod_action", "warn"), "Automod: " + ", ".join(reasons))


def setup(bot):
    bot.add_cog(Security(bot))
    bot.tree.add_command(WarningGroup())
    bot.tree.add_command(AutoModGroup())
    bot.tree.add_command(AntiNukeGroup())
    bot.tree.add_command(AntiLinkGroup())


class WarningGroup(app_commands.Group):
    def __init__(self): super().__init__(name="warning", description="Manage member warnings")

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.check(admin_check)
    async def warn(self, interaction, member: discord.Member, reason: str = "No reason provided"):
        case = await add_warning(interaction.guild.id, member.id, interaction.user.id, reason)
        count = await warning_count(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed("Warning issued", f"**Member:** {member.mention}\n**Case:** `AC-W{case:04d}`\n**Warnings:** `{count}`\n**Reason:** {reason}"))

    @app_commands.command(name="unwarn", description="Remove a warning by case ID")
    @app_commands.check(admin_check)
    async def unwarn(self, interaction, case: str):
        try: case_id = int(case.upper().replace("AC-W", ""))
        except ValueError:
            await interaction.response.send_message(embed=embed("Invalid case", "Use a case such as `AC-W0001`.", False), ephemeral=True); return
        ok = await remove_warning(interaction.guild.id, case_id)
        await interaction.response.send_message(embed=embed("Warning removed" if ok else "Warning not found", f"Case `AC-W{case_id:04d}` was {'removed' if ok else 'not found'}. ", ok))

    @app_commands.command(name="warnings", description="Show a member's warnings")
    @app_commands.check(admin_check)
    async def warnings(self, interaction, member: discord.Member):
        if not _pool:
            await interaction.response.send_message(embed=embed("Warnings", "Database is unavailable.", False), ephemeral=True); return
        rows = await _pool.fetch("SELECT id,moderator_id,reason,created_at FROM security_warnings WHERE guild_id=$1 AND user_id=$2 ORDER BY id DESC LIMIT 10", interaction.guild.id, member.id)
        desc = "\n".join(f"`AC-W{r['id']:04d}` • <@{r['moderator_id']}> • {r['reason']}" for r in rows) or "No warnings."
        await interaction.response.send_message(embed=embed(f"Warnings • {member}", desc))


class AutoModGroup(app_commands.Group):
    def __init__(self): super().__init__(name="automod", description="Configure message protection")

    @app_commands.command(name="enable", description="Enable automod")
    @app_commands.check(admin_check)
    @app_commands.describe(action="warn, mute, kick or ban")
    async def enable(self, interaction, action: str = "warn", spam_limit: int = 5, seconds: int = 3):
        action = action.lower()
        if action not in {"warn","mute","kick","ban"}:
            await interaction.response.send_message("Action must be warn, mute, kick or ban.", ephemeral=True); return
        await set_cfg(interaction.guild.id, automod_enabled=True, automod_action=action, automod_spam_limit=max(2,spam_limit), automod_spam_seconds=max(1,seconds))
        await interaction.response.send_message(embed=embed("Automod enabled", f"Spam: **{spam_limit} messages / {seconds}s**\nPunishment: **{action}**\nMention/emoji/@everyone/line checks are active."))

    @app_commands.command(name="disable", description="Disable automod")
    @app_commands.check(admin_check)
    async def disable(self, interaction):
        await set_cfg(interaction.guild.id, automod_enabled=False)
        await interaction.response.send_message(embed=embed("Automod disabled", "Message automod is now off."))


class AntiNukeGroup(app_commands.Group):
    def __init__(self): super().__init__(name="antinuke", description="Protect the server from destructive actions")

    @app_commands.command(name="enable", description="Enable anti-nuke protection")
    @app_commands.check(admin_check)
    async def enable(self, interaction):
        me = interaction.guild.me
        if not me or not me.top_role:
            await interaction.response.send_message(embed=embed("Cannot enable anti-nuke", "I cannot see my role hierarchy.", False), ephemeral=True); return
        higher_admins = [m for m in interaction.guild.members if m.id != me.id and m.guild_permissions.administrator and not m.bot and m.top_role >= me.top_role]
        if higher_admins:
            names = ", ".join(m.mention for m in higher_admins[:5])
            await interaction.response.send_message(embed=embed("Move my role to the top first", f"Before enabling Anti-nuke, move my bot role **above every administrator role**.\n\nCurrently at/above my role: {names}", False), ephemeral=True); return
        await whitelist_user(interaction.guild.id, OWNER_ID)
        await whitelist_user(interaction.guild.id, me.id)
        await set_cfg(interaction.guild.id, antinuke_enabled=True, antinuke_action="ban")
        await interaction.response.send_message(embed=embed("Anti-nuke enabled", "🛡️ Non-whitelisted users who perform protected destructive server actions are immediately banned when Discord's audit log identifies the actor.\n\nOwner and bot are automatically whitelisted."))

    @app_commands.command(name="disable", description="Disable anti-nuke")
    @app_commands.check(admin_check)
    async def disable(self, interaction):
        await set_cfg(interaction.guild.id, antinuke_enabled=False)
        await interaction.response.send_message(embed=embed("Anti-nuke disabled", "Protection is now off."))

    @app_commands.command(name="whitelist", description="Whitelist a trusted member")
    @app_commands.check(admin_check)
    async def whitelist(self, interaction, member: discord.Member):
        await whitelist_user(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed("Anti-nuke whitelist updated", f"{member.mention} is now trusted."))

    @app_commands.command(name="unwhitelist", description="Remove a member from the anti-nuke whitelist")
    @app_commands.check(admin_check)
    async def unwhitelist(self, interaction, member: discord.Member):
        if member.id == OWNER_ID:
            await interaction.response.send_message(embed=embed("Protected owner", "The configured owner cannot be removed from the whitelist.", False), ephemeral=True); return
        await unwhitelist_user(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed("Anti-nuke whitelist updated", f"{member.mention} is no longer trusted."))


class AntiLinkGroup(app_commands.Group):
    def __init__(self): super().__init__(name="antilink", description="Block unauthorized links")

    @app_commands.command(name="enable", description="Enable anti-link")
    @app_commands.check(admin_check)
    async def enable(self, interaction):
        await set_cfg(interaction.guild.id, antilink_enabled=True)
        await interaction.response.send_message(embed=embed("Anti-link enabled", "Unauthorized links will be deleted. Anti-link whitelist members are bypassed."))

    @app_commands.command(name="disable", description="Disable anti-link")
    @app_commands.check(admin_check)
    async def disable(self, interaction):
        await set_cfg(interaction.guild.id, antilink_enabled=False)
        await interaction.response.send_message(embed=embed("Anti-link disabled", "Link filtering is now off."))

    @app_commands.command(name="whitelist", description="Whitelist a member for links")
    @app_commands.check(admin_check)
    async def whitelist(self, interaction, member: discord.Member):
        await whitelist_user(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed("Anti-link whitelist updated", f"{member.mention} can now post links."))

    @app_commands.command(name="unwhitelist", description="Remove a member from the anti-link whitelist")
    @app_commands.check(admin_check)
    async def unwhitelist(self, interaction, member: discord.Member):
        await unwhitelist_user(interaction.guild.id, member.id)
        await interaction.response.send_message(embed=embed("Anti-link whitelist updated", f"{member.mention} can no longer bypass anti-link."))
