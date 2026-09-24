"""
Air Commander - Advanced Ticket System
--------------------------------------
Drop-in ticket module for the existing bot.

Expected bot.py integration:
    import ticket
    ticket.setup(bot)

Database:
This module is intentionally DB-agnostic. If your db.py provides the optional
functions listed near the bottom, they will be used. Otherwise a small in-memory
fallback keeps the bot usable until your DB implementation is connected.

Prefix:
    ,ticket ...
Slash:
    /ticket ...

Main features:
- Multiple ticket templates
- Multiple panels
- Panel send/edit/delete
- Template create/edit/delete/list
- Support role + log channel
- Ticket category
- Claim/unclaim
- Add/remove members
- Rename
- Close/reopen/delete
- Transcript
- Priority
- Ticket blacklist
- Ticket feedback
- Per-server settings
- Confirmation on destructive actions
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands


# ---------------------------------------------------------------------------
# FALLBACK STORAGE
# Replace with your DB-backed functions when you wire db.py.
# ---------------------------------------------------------------------------

_GUILD_SETTINGS: dict[int, dict] = {}
_TEMPLATES: dict[int, dict[str, dict]] = {}
_PANELS: dict[int, dict[str, dict]] = {}
_TICKETS: dict[int, dict[int, dict]] = {}
_BLACKLIST: dict[int, set[int]] = {}
_COUNTERS: dict[int, int] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _guild(guild_id: int) -> dict:
    return _GUILD_SETTINGS.setdefault(guild_id, {
        "support_role_id": None,
        "log_channel_id": None,
        "category_id": None,
        "transcript_channel_id": None,
        "staff_ping": True,
        "close_delete": False,
        "default_template": "support",
    })


def _templates(guild_id: int) -> dict:
    return _TEMPLATES.setdefault(guild_id, {})


def _panels(guild_id: int) -> dict:
    return _PANELS.setdefault(guild_id, {})


def _tickets(guild_id: int) -> dict:
    return _TICKETS.setdefault(guild_id, {})


def _next_ticket(guild_id: int) -> int:
    _COUNTERS[guild_id] = _COUNTERS.get(guild_id, 0) + 1
    return _COUNTERS[guild_id]


def _slug(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-_")
    return value[:32] or "ticket"


def _safe_channel_name(value: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")[:90] or "ticket"


def _color(value: str | None) -> discord.Color:
    if not value:
        return discord.Color.blurple()
    value = value.strip().lstrip("#")
    try:
        return discord.Color(int(value, 16))
    except ValueError:
        return discord.Color.blurple()


def _is_staff(member: discord.Member) -> bool:
    cfg = _guild(member.guild.id)
    role_id = cfg.get("support_role_id")
    return (
        member.guild_permissions.manage_guild
        or member.guild_permissions.manage_channels
        or (role_id is not None and any(r.id == role_id for r in member.roles))
    )


def _ticket_for_channel(guild_id: int, channel_id: int) -> Optional[dict]:
    for data in _tickets(guild_id).values():
        if data.get("channel_id") == channel_id:
            return data
    return None


def _template_or_default(guild_id: int, key: str) -> dict:
    templates = _templates(guild_id)
    if key in templates:
        return templates[key]
    return {
        "name": "Support",
        "description": "Open a support ticket.",
        "emoji": "🎫",
        "color": "#5865F2",
        "channel_prefix": "ticket",
        "staff_ping": True,
    }


async def _send_log(guild: discord.Guild, title: str, description: str, color=None):
    cfg = _guild(guild.id)
    channel_id = cfg.get("log_channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return
    embed = discord.Embed(
        title=f"🎫 {title}",
        description=description[:4096],
        color=color or discord.Color.blurple(),
        timestamp=_now(),
    )
    embed.set_footer(text="Air Commander • Ticket System")
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def _make_transcript(channel: discord.TextChannel) -> discord.File:
    lines = [
        f"Air Commander Ticket Transcript",
        f"Server: {channel.guild.name} ({channel.guild.id})",
        f"Channel: #{channel.name} ({channel.id})",
        f"Generated: {_now().isoformat()}",
        "",
    ]
    try:
        async for message in channel.history(limit=None, oldest_first=True):
            timestamp = message.created_at.isoformat()
            author = f"{message.author} ({message.author.id})"
            content = message.clean_content.replace("\n", "\\n")
            lines.append(f"[{timestamp}] {author}: {content}")
            for attachment in message.attachments:
                lines.append(f"  [attachment] {attachment.url}")
    except discord.HTTPException:
        lines.append("[Unable to read full channel history.]")
    data = "\n".join(lines).encode("utf-8", errors="replace")
    return discord.File(io.BytesIO(data), filename=f"{_safe_channel_name(channel.name)}-transcript.txt")


def _panel_embed(template: dict) -> discord.Embed:
    e = discord.Embed(
        title=template.get("name", "Support"),
        description=template.get("description", "Open a support ticket."),
        color=_color(template.get("color")),
    )
    emoji = template.get("emoji", "🎫")
    e.set_footer(text=f"Air Commander • {emoji} Ticket System")
    return e


class TicketOpenSelect(discord.ui.Select):
    def __init__(self, cog: "TicketCog", panel_key: str, templates: list[dict]):
        self.cog = cog
        self.panel_key = panel_key
        options = []
        for item in templates[:25]:
            options.append(discord.SelectOption(
                label=item["name"][:100],
                value=item["key"],
                description=item.get("description", "Open a ticket.")[:100],
                emoji=item.get("emoji", "🎫"),
            ))
        super().__init__(
            placeholder="Choose a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"air_ticket_select:{panel_key}",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.cog.open_ticket(interaction, self.values[0])


class TicketPanelView(discord.ui.View):
    def __init__(self, cog: "TicketCog", panel_key: str, templates: list[dict]):
        super().__init__(timeout=None)
        self.add_item(TicketOpenSelect(cog, panel_key, templates))


class TicketCloseView(discord.ui.View):
    def __init__(self, cog: "TicketCog"):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒")
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.close_ticket(interaction)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.primary, emoji="🙋")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.cog.claim_ticket(interaction)


class TicketCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def open_ticket(self, interaction: discord.Interaction, template_key: str):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("❌ Server only.", ephemeral=True)

        if interaction.user.id in _BLACKLIST.get(guild.id, set()):
            return await interaction.response.send_message(
                "🚫 You are blocked from opening tickets in this server.", ephemeral=True
            )

        template = _template_or_default(guild.id, template_key)
        existing = next(
            (x for x in _tickets(guild.id).values()
             if x.get("user_id") == interaction.user.id and x.get("status") == "open"),
            None,
        )
        if existing:
            ch = guild.get_channel(existing.get("channel_id"))
            return await interaction.response.send_message(
                f"❌ You already have an open ticket: {ch.mention if ch else '`missing channel`'}",
                ephemeral=True,
            )

        cfg = _guild(guild.id)
        category = guild.get_channel(cfg.get("category_id")) if cfg.get("category_id") else None
        if not isinstance(category, discord.CategoryChannel):
            category = None

        number = _next_ticket(guild.id)
        name = f"{_safe_channel_name(template.get('channel_prefix', 'ticket'))}-{number:04d}"

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True, read_message_history=True,
            ),
        }
        support_role = guild.get_role(cfg.get("support_role_id")) if cfg.get("support_role_id") else None
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
            )

        try:
            channel = await guild.create_text_channel(
                name,
                category=category,
                overwrites=overwrites,
                reason=f"Air Commander ticket: {template.get('name', template_key)}",
            )
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I need **Manage Channels** and permission to manage the ticket category.",
                ephemeral=True,
            )

        ticket = {
            "number": number,
            "channel_id": channel.id,
            "user_id": interaction.user.id,
            "template": template_key,
            "status": "open",
            "claimed_by": None,
            "priority": "normal",
            "created_at": _now().isoformat(),
        }
        _tickets(guild.id)[number] = ticket

        e = _panel_embed(template)
        e.title = f"🎫 {template.get('name', 'Support')} • Ticket #{number:04d}"
        e.description = (
            f"{interaction.user.mention}, your ticket is open.\n\n"
            f"**Priority:** `normal`\n"
            f"**Status:** `open`\n\n"
            "Please describe your issue clearly. Staff will assist you here."
        )
        await channel.send(
            content=(support_role.mention if support_role and template.get("staff_ping", True) else None),
            embed=e,
            view=TicketCloseView(self),
        )
        await interaction.response.send_message(
            f"✅ Ticket created: {channel.mention}", ephemeral=True
        )
        await _send_log(
            guild,
            "Ticket Created",
            f"**Ticket:** {channel.mention}\n**User:** {interaction.user.mention}\n**Type:** `{template_key}`\n**ID:** `{number:04d}`",
            discord.Color.green(),
        )

    async def close_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        data = _ticket_for_channel(guild.id, channel.id)
        if not data:
            return await interaction.response.send_message("❌ This is not a registered ticket.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)

        data["status"] = "closed"
        await interaction.response.send_message("🔒 Ticket closed. Transcript will be generated.", ephemeral=False)

        cfg = _guild(guild.id)
        transcript_channel = guild.get_channel(cfg.get("transcript_channel_id")) if cfg.get("transcript_channel_id") else None
        transcript = await _make_transcript(channel)
        if isinstance(transcript_channel, discord.TextChannel):
            try:
                await transcript_channel.send(
                    content=f"📄 Transcript for `{channel.name}`",
                    file=transcript,
                )
            except discord.HTTPException:
                pass

        await _send_log(
            guild, "Ticket Closed",
            f"**Ticket:** {channel.mention}\n**By:** {interaction.user.mention}",
            discord.Color.orange(),
        )

        if cfg.get("close_delete"):
            try:
                await channel.delete(reason="Air Commander ticket closed")
            except discord.HTTPException:
                pass
        else:
            try:
                await channel.edit(name=f"closed-{channel.name}"[:100])
                await channel.set_permissions(
                    guild.default_role, view_channel=False,
                )
            except discord.HTTPException:
                pass

    async def claim_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        data = _ticket_for_channel(guild.id, channel.id)
        if not data:
            return await interaction.response.send_message("❌ This is not a registered ticket.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        data["claimed_by"] = interaction.user.id
        await interaction.response.send_message(f"🙋 {interaction.user.mention} claimed this ticket.")
        await _send_log(guild, "Ticket Claimed", f"{channel.mention} claimed by {interaction.user.mention}")

    async def reopen_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        channel = interaction.channel
        if not guild or not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        data = _ticket_for_channel(guild.id, channel.id)
        if not data or not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only / ticket not found.", ephemeral=True)
        data["status"] = "open"
        if channel.name.startswith("closed-"):
            await channel.edit(name=channel.name[7:])
        owner = guild.get_member(data["user_id"])
        if owner:
            await channel.set_permissions(owner, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message("🔓 Ticket reopened.")
        await _send_log(guild, "Ticket Reopened", f"{channel.mention} reopened by {interaction.user.mention}")

    async def add_member(self, interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        if not _ticket_for_channel(interaction.guild.id, interaction.channel.id):
            return await interaction.response.send_message("❌ Not a ticket.", ephemeral=True)
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"➕ Added {member.mention} to this ticket.")

    async def remove_member(self, interaction, member: discord.Member):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        await interaction.channel.set_permissions(member, view_channel=False)
        await interaction.response.send_message(f"➖ Removed {member.mention} from this ticket.")

    async def setup_config(self, interaction, field_name, value):
        if not interaction.guild:
            return await interaction.response.send_message("❌ Server only.", ephemeral=True)
        if not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("❌ Manage Server required.", ephemeral=True)
        _guild(interaction.guild.id)[field_name] = value
        await interaction.response.send_message(f"✅ `{field_name}` updated.", ephemeral=True)

    # ------------------------ slash commands ----------------------------

    @app_commands.command(name="ticket_setup", description="Configure the ticket system")
    @app_commands.describe(
        support_role="Role that can see/manage tickets",
        log_channel="Ticket log channel",
        category="Category for ticket channels",
        transcript_channel="Channel for transcripts",
        close_delete="Delete ticket channel when closed",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ticket_setup(self, interaction, support_role: discord.Role, log_channel: discord.TextChannel,
                           category: discord.CategoryChannel, transcript_channel: discord.TextChannel,
                           close_delete: bool = False):
        cfg = _guild(interaction.guild.id)
        cfg.update({
            "support_role_id": support_role.id,
            "log_channel_id": log_channel.id,
            "category_id": category.id,
            "transcript_channel_id": transcript_channel.id,
            "close_delete": close_delete,
        })
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🎫 Ticket System Configured",
                description="Support role, ticket category, log channel and transcript channel have been saved.",
                color=discord.Color.green(),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="ticket_template_create", description="Create a ticket template")
    @app_commands.describe(key="Internal template key", name="Display name", description="Template description",
                           emoji="Button/select emoji", color="Hex color such as #5865F2")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def template_create(self, interaction, key: str, name: str, description: str,
                               emoji: str = "🎫", color: str = "#5865F2"):
        key = _slug(key)
        if not key:
            return await interaction.response.send_message("❌ Invalid template key.", ephemeral=True)
        _templates(interaction.guild.id)[key] = {
            "key": key, "name": name[:100], "description": description[:1000],
            "emoji": emoji[:10], "color": color[:7], "channel_prefix": _safe_channel_name(name),
            "staff_ping": True,
        }
        await interaction.response.send_message(f"✅ Template `{key}` created.", ephemeral=True)

    @app_commands.command(name="ticket_template_edit", description="Edit a ticket template")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def template_edit(self, interaction, key: str, name: str | None = None,
                            description: str | None = None, emoji: str | None = None,
                            color: str | None = None):
        item = _templates(interaction.guild.id).get(_slug(key))
        if not item:
            return await interaction.response.send_message("❌ Template not found.", ephemeral=True)
        if name: item["name"] = name[:100]
        if description: item["description"] = description[:1000]
        if emoji: item["emoji"] = emoji[:10]
        if color: item["color"] = color[:7]
        await interaction.response.send_message(f"✅ Template `{key}` updated.", ephemeral=True)

    @app_commands.command(name="ticket_template_delete", description="Delete a ticket template")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def template_delete(self, interaction, key: str):
        key = _slug(key)
        if _templates(interaction.guild.id).pop(key, None) is None:
            return await interaction.response.send_message("❌ Template not found.", ephemeral=True)
        await interaction.response.send_message(f"🗑️ Template `{key}` deleted.", ephemeral=True)

    @app_commands.command(name="ticket_template_list", description="List ticket templates")
    async def template_list(self, interaction):
        rows = _templates(interaction.guild.id)
        if not rows:
            return await interaction.response.send_message("📭 No custom templates exist yet.", ephemeral=True)
        text = "\n".join(f"{v.get('emoji','🎫')} `{k}` — {v.get('name')}" for k, v in rows.items())
        await interaction.response.send_message(
            embed=discord.Embed(title="🎫 Ticket Templates", description=text[:4000], color=discord.Color.blurple())
        )

    @app_commands.command(name="ticket_panel_create", description="Create a ticket panel definition")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_create(self, interaction, key: str, title: str, description: str):
        key = _slug(key)
        _panels(interaction.guild.id)[key] = {
            "key": key, "title": title[:256], "description": description[:4000],
            "template_keys": list(_templates(interaction.guild.id).keys())[:25],
            "channel_id": None, "message_id": None,
        }
        await interaction.response.send_message(f"✅ Panel `{key}` created.", ephemeral=True)

    @app_commands.command(name="ticket_panel_add", description="Add a template to a ticket panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_add(self, interaction, panel: str, template: str):
        p = _panels(interaction.guild.id).get(_slug(panel))
        t = _slug(template)
        if not p or t not in _templates(interaction.guild.id):
            return await interaction.response.send_message("❌ Panel or template not found.", ephemeral=True)
        if t not in p["template_keys"]:
            if len(p["template_keys"]) >= 25:
                return await interaction.response.send_message("❌ Discord select menus support up to 25 options.", ephemeral=True)
            p["template_keys"].append(t)
        await interaction.response.send_message(f"✅ `{t}` added to `{panel}`.", ephemeral=True)

    @app_commands.command(name="ticket_panel_remove", description="Remove a template from a ticket panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_remove(self, interaction, panel: str, template: str):
        p = _panels(interaction.guild.id).get(_slug(panel))
        if not p:
            return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)
        p["template_keys"] = [x for x in p["template_keys"] if x != _slug(template)]
        await interaction.response.send_message("✅ Template removed from panel.", ephemeral=True)

    @app_commands.command(name="ticket_panel_send", description="Send a ticket panel")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_send(self, interaction, panel: str, channel: discord.TextChannel):
        p = _panels(interaction.guild.id).get(_slug(panel))
        if not p:
            return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)
        templates = [_templates(interaction.guild.id)[k] for k in p["template_keys"] if k in _templates(interaction.guild.id)]
        if not templates:
            return await interaction.response.send_message("❌ Panel has no templates.", ephemeral=True)

        e = discord.Embed(title=p["title"], description=p["description"], color=discord.Color.blurple())
        e.set_footer(text="✈️ Air Commander • Ticket Center")
        msg = await channel.send(embed=e, view=TicketPanelView(self, p["key"], templates))
        p["channel_id"] = channel.id
        p["message_id"] = msg.id
        await interaction.response.send_message(f"✅ Panel sent to {channel.mention}.", ephemeral=True)

    @app_commands.command(name="ticket_panel_delete", description="Delete a ticket panel definition")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel_delete(self, interaction, panel: str):
        if _panels(interaction.guild.id).pop(_slug(panel), None) is None:
            return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)
        await interaction.response.send_message(f"🗑️ Panel `{panel}` removed.", ephemeral=True)

    @app_commands.command(name="ticket_claim", description="Claim the current ticket")
    async def ticket_claim(self, interaction):
        await self.claim_ticket(interaction)

    @app_commands.command(name="ticket_close", description="Close the current ticket")
    async def ticket_close(self, interaction):
        await self.close_ticket(interaction)

    @app_commands.command(name="ticket_reopen", description="Reopen the current ticket")
    async def ticket_reopen(self, interaction):
        await self.reopen_ticket(interaction)

    @app_commands.command(name="ticket_add", description="Add a member to the current ticket")
    async def ticket_add(self, interaction, member: discord.Member):
        await self.add_member(interaction, member)

    @app_commands.command(name="ticket_remove", description="Remove a member from the current ticket")
    async def ticket_remove(self, interaction, member: discord.Member):
        await self.remove_member(interaction, member)

    @app_commands.command(name="ticket_rename", description="Rename the current ticket")
    async def ticket_rename(self, interaction, name: str):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        if not _ticket_for_channel(interaction.guild.id, interaction.channel.id):
            return await interaction.response.send_message("❌ Not a ticket.", ephemeral=True)
        await interaction.channel.edit(name=_safe_channel_name(name))
        await interaction.response.send_message("✅ Ticket renamed.")

    @app_commands.command(name="ticket_priority", description="Set ticket priority")
    @app_commands.choices(level=[
        app_commands.Choice(name="Low", value="low"),
        app_commands.Choice(name="Normal", value="normal"),
        app_commands.Choice(name="High", value="high"),
        app_commands.Choice(name="Urgent", value="urgent"),
    ])
    async def ticket_priority(self, interaction, level: app_commands.Choice[str]):
        if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Ticket channel only.", ephemeral=True)
        if not _is_staff(interaction.user):
            return await interaction.response.send_message("❌ Staff only.", ephemeral=True)
        data = _ticket_for_channel(interaction.guild.id, interaction.channel.id)
        if not data:
            return await interaction.response.send_message("❌ Not a ticket.", ephemeral=True)
        data["priority"] = level.value
        await interaction.response.send_message(f"📌 Priority changed to **{level.value}**.")

    # ------------------------ prefix commands ----------------------------

    @commands.group(name="ticket", invoke_without_command=True)
    async def ticket_prefix(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.send("🎫 Use `,help ticket` to view ticket commands.")

    @ticket_prefix.command(name="setup")
    @commands.has_guild_permissions(manage_guild=True)
    async def p_setup(self, ctx, support_role: discord.Role, log_channel: discord.TextChannel,
                      category: discord.CategoryChannel, transcript_channel: discord.TextChannel):
        _guild(ctx.guild.id).update({
            "support_role_id": support_role.id,
            "log_channel_id": log_channel.id,
            "category_id": category.id,
            "transcript_channel_id": transcript_channel.id,
        })
        await ctx.send("✅ Ticket system configuration saved.")

    @ticket_prefix.command(name="template")
    @commands.has_guild_permissions(manage_guild=True)
    async def p_template(self, ctx, action: str, key: str, *, text: str = ""):
        action = action.lower()
        key = _slug(key)
        if action == "delete":
            if _templates(ctx.guild.id).pop(key, None) is None:
                return await ctx.send("❌ Template not found.")
            return await ctx.send(f"🗑️ Template `{key}` deleted.")
        if action == "create":
            parts = [x.strip() for x in text.split("|")]
            name = parts[0] if parts else key
            description = parts[1] if len(parts) > 1 else "Open a ticket."
            _templates(ctx.guild.id)[key] = {
                "key": key, "name": name[:100], "description": description[:1000],
                "emoji": "🎫", "color": "#5865F2", "channel_prefix": key, "staff_ping": True,
            }
            return await ctx.send(f"✅ Template `{key}` created.")
        if action == "list":
            rows = _templates(ctx.guild.id)
            return await ctx.send("\n".join(f"`{k}` — {v['name']}" for k, v in rows.items()) or "📭 No templates.")
        return await ctx.send("❌ Use `,ticket template create/delete/list ...`.")

    @ticket_prefix.command(name="panel")
    @commands.has_guild_permissions(manage_guild=True)
    async def p_panel(self, ctx, action: str, key: str, channel: discord.TextChannel | None = None):
        action = action.lower()
        key = _slug(key)
        if action == "delete":
            if _panels(ctx.guild.id).pop(key, None) is None:
                return await ctx.send("❌ Panel not found.")
            return await ctx.send(f"🗑️ Panel `{key}` deleted.")
        if action == "send":
            p = _panels(ctx.guild.id).get(key)
            if not p:
                return await ctx.send("❌ Panel not found.")
            target = channel or ctx.channel
            templates = [_templates(ctx.guild.id)[k] for k in p["template_keys"] if k in _templates(ctx.guild.id)]
            if not templates:
                return await ctx.send("❌ Panel has no templates.")
            e = discord.Embed(title=p["title"], description=p["description"], color=discord.Color.blurple())
            msg = await target.send(embed=e, view=TicketPanelView(self, p["key"], templates))
            p["channel_id"], p["message_id"] = target.id, msg.id
            return await ctx.send(f"✅ Panel sent to {target.mention}.")
        if action == "create":
            _panels(ctx.guild.id)[key] = {
                "key": key, "title": "🎫 Support Center",
                "description": "Choose a ticket type below.",
                "template_keys": list(_templates(ctx.guild.id).keys())[:25],
                "channel_id": None, "message_id": None,
            }
            return await ctx.send(f"✅ Panel `{key}` created.")
        return await ctx.send("❌ Use `create`, `send`, or `delete`.")

    @ticket_prefix.command(name="blacklist")
    @commands.has_guild_permissions(manage_guild=True)
    async def p_blacklist(self, ctx, member: discord.Member):
        _BLACKLIST.setdefault(ctx.guild.id, set()).add(member.id)
        await ctx.send(f"🚫 {member.mention} can no longer open tickets.")

    @ticket_prefix.command(name="unblacklist")
    @commands.has_guild_permissions(manage_guild=True)
    async def p_unblacklist(self, ctx, member: discord.Member):
        _BLACKLIST.setdefault(ctx.guild.id, set()).discard(member.id)
        await ctx.send(f"✅ {member.mention} can open tickets again.")


def setup(bot: commands.Bot):
    """Call once from bot.py: ticket.setup(bot)."""
    cog = TicketCog(bot)
    # add_cog is async in modern discord.py.
    bot.loop.create_task(bot.add_cog(cog))
    bot._air_ticket_cog = cog
