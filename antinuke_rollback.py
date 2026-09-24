import asyncio
import discord
from discord.ext import commands

import security


class AntiNukeRollback(commands.Cog):
    """Reverts identifiable destructive changes made by non-whitelisted users."""

    def __init__(self, bot):
        self.bot = bot
        self._handled = set()

    async def _actor(self, guild, action, target_id=None):
        try:
            async for entry in guild.audit_logs(limit=10, action=action):
                if entry.id in self._handled:
                    continue
                if target_id is not None and getattr(entry.target, "id", None) != target_id:
                    continue
                self._handled.add(entry.id)
                return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    async def _enabled_and_unauthorized(self, guild, entry):
        if not (await security.cfg(guild.id)).get("antinuke_enabled"):
            return False
        return not await security.is_whitelisted(guild.id, entry.user.id)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        await asyncio.sleep(0.8)
        entry = await self._actor(role.guild, discord.AuditLogAction.role_create, role.id)
        if not entry or not await self._enabled_and_unauthorized(role.guild, entry):
            return
        try:
            await role.delete(reason="Anti-nuke rollback: unauthorized role creation")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        await asyncio.sleep(0.8)
        entry = await self._actor(channel.guild, discord.AuditLogAction.channel_create, channel.id)
        if not entry or not await self._enabled_and_unauthorized(channel.guild, entry):
            return
        try:
            await channel.delete(reason="Anti-nuke rollback: unauthorized channel creation")
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        await asyncio.sleep(0.8)
        entry = await self._actor(after.guild, discord.AuditLogAction.role_update, after.id)
        if not entry or not await self._enabled_and_unauthorized(after.guild, entry):
            return
        try:
            # Restore the properties Discord exposes safely through Role.edit.
            kwargs = {
                "name": before.name,
                "permissions": before.permissions,
                "colour": before.colour,
                "hoist": before.hoist,
                "mentionable": before.mentionable,
            }
            await after.edit(reason="Anti-nuke rollback: unauthorized role change", **kwargs)
        except (discord.Forbidden, discord.HTTPException):
            pass

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.roles == after.roles:
            return
        await asyncio.sleep(0.8)
        entry = await self._actor(after.guild, discord.AuditLogAction.member_role_update, after.id)
        if not entry or not await self._enabled_and_unauthorized(after.guild, entry):
            return

        before_ids = {r.id for r in before.roles}
        after_ids = {r.id for r in after.roles}
        added = after_ids - before_ids
        removed = before_ids - after_ids

        # Undo only the roles implicated by the unauthorized audit-log change.
        # Discord may report multiple role changes in one audit entry, so restoring
        # the complete previous role set is the most reliable rollback.
        try:
            await after.edit(roles=before.roles, reason="Anti-nuke rollback: unauthorized member role change")
        except (discord.Forbidden, discord.HTTPException):
            # Fallback: remove newly-added roles when full role restoration is not allowed.
            for role in after.roles:
                if role.id in added and role.is_assignable():
                    try:
                        await after.remove_roles(role, reason="Anti-nuke rollback: unauthorized role addition")
                    except (discord.Forbidden, discord.HTTPException):
                        pass

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        # If a non-whitelisted actor deletes a role, we cannot recreate it perfectly
        # from the audit event alone. The existing anti-nuke handler still bans the
        # actor; this cog intentionally avoids a lossy reconstruction.
        return


async def setup(bot):
    await bot.add_cog(AntiNukeRollback(bot))
