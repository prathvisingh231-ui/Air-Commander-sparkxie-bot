"""Air Commander standalone advanced ticket system.

Add to bot.py:
    import ticket
    # after creating bot:
    # ticket.setup(bot)   # if your bot already has an async setup pattern, await it there
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATA_FILE = DATA_DIR / "tickets.json"

DEFAULT = {
    "support_role_id": None,
    "category_id": None,
    "log_channel_id": None,
    "transcript_channel_id": None,
    "panel_channel_id": None,
    "panel_message_id": None,
    "panel_title": "🎫 Support Center",
    "panel_description": "Select a ticket type below to open a private support ticket.",
    "panel_color": 0x5865F2,
    "panel_footer": "Air Commander Tickets",
    "templates": {
        "support": {
            "label": "Support", "emoji": "🎫",
            "description": "Open a general support ticket.",
            "color": 0x5865F2,
            "welcome_title": "🎫 Support Ticket",
            "welcome_description": "Please explain your issue clearly."
        },
        "purchase": {
            "label": "Purchase", "emoji": "🛒",
            "description": "Questions about purchases or orders.",
            "color": 0x57F287,
            "welcome_title": "🛒 Purchase Ticket",
            "welcome_description": "Please provide your order details."
        },
        "report": {
            "label": "Report", "emoji": "🚨",
            "description": "Report a user or server issue.",
            "color": 0xED4245,
            "welcome_title": "🚨 Report Ticket",
            "welcome_description": "Please provide the relevant details."
        },
    },
}

def load_all():
    if not DATA_FILE.exists():
        return {}
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_all(data):
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(DATA_FILE)

def get_config(guild_id):
    data = load_all()
    key = str(guild_id)
    if key not in data:
        data[key] = json.loads(json.dumps(DEFAULT))
        save_all(data)
    else:
        changed = False
        for k, v in DEFAULT.items():
            if k not in data[key]:
                data[key][k] = json.loads(json.dumps(v))
                changed = True
        if changed:
            save_all(data)
    return data[key]

def save_config(guild_id, config):
    data = load_all()
    data[str(guild_id)] = config
    save_all(data)

def slug(text):
    text = re.sub(r"[^a-z0-9-]+", "-", text.lower().strip())
    return text.strip("-")[:35] or "ticket"

def ticket_owner(channel):
    if not channel.topic:
        return None
    m = re.search(r"owner=(\d+)", channel.topic)
    return int(m.group(1)) if m else None

def is_ticket(channel):
    return isinstance(channel, discord.TextChannel) and (
        channel.name.startswith("ticket-") or channel.name.startswith("closed-")
    )

def is_support(member, config):
    role_id = config.get("support_role_id")
    return member.guild_permissions.manage_channels or (
        role_id is not None and any(r.id == int(role_id) for r in member.roles)
    )

async def log_event(guild, config, embed):
    channel_id = config.get("log_channel_id")
    if not channel_id:
        return
    channel = guild.get_channel(int(channel_id))
    if channel:
        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            pass

async def transcript(channel):
    lines = [
        f"Ticket: #{channel.name}",
        f"Created: {channel.created_at.isoformat()}",
        "",
    ]
    try:
        messages = [m async for m in channel.history(limit=None, oldest_first=True)]
        for m in messages:
            stamp = m.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = m.content or ""
            if m.attachments:
                content += " " + " ".join(a.url for a in m.attachments)
            lines.append(f"[{stamp}] {m.author} ({m.author.id}): {content}")
    except discord.HTTPException:
        lines.append("[Unable to read complete message history]")
    return "\n".join(lines)

class TicketPanel(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        config = get_config(cog.guild_id)
        options = []
        for key, t in list(config["templates"].items())[:25]:
            options.append(discord.SelectOption(
                label=str(t.get("label", key))[:100],
                value=key,
                description=str(t.get("description", "Open a ticket."))[:100],
                emoji=t.get("emoji") or None,
            ))
        if not options:
            options = [discord.SelectOption(label="Support", value="support", emoji="🎫")]
        self.add_item(TicketSelect(cog, options))

class TicketSelect(discord.ui.Select):
    def __init__(self, cog, options):
        self.cog = cog
        super().__init__(
            placeholder="🎫 Select a ticket type...",
            min_values=1, max_values=1, options=options,
            custom_id=f"air_ticket_select:{cog.guild_id}",
        )

    async def callback(self, interaction):
        await self.cog.open_ticket(interaction, self.values[0])

class TicketActions(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

    @discord.ui.button(label="Claim", emoji="🙋", style=discord.ButtonStyle.primary, custom_id="air_ticket_claim")
    async def claim(self, interaction, button):
        await self.cog.claim(interaction)

    @discord.ui.button(label="Close", emoji="🔒", style=discord.ButtonStyle.secondary, custom_id="air_ticket_close")
    async def close(self, interaction, button):
        await self.cog.close(interaction)

    @discord.ui.button(label="Delete", emoji="🗑️", style=discord.ButtonStyle.danger, custom_id="air_ticket_delete")
    async def delete(self, interaction, button):
        await self.cog.delete(interaction)

class TicketSystem(commands.Cog):
    ticket = app_commands.Group(name="ticket", description="Advanced ticket management.")

    def __init__(self, bot):
        self.bot = bot
        self.guild_id = 0

    async def cog_load(self):
        # Persistent buttons. Select menus are re-created when panels are sent.
        self.bot.add_view(TicketActions(self))

    def cfg(self, guild):
        return get_config(guild.id)

    async def open_ticket(self, interaction, template_key):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member):
            return
        config = self.cfg(guild)
        template = config["templates"].get(template_key)
        if not template:
            await interaction.response.send_message("❌ Ticket template not found.", ephemeral=True)
            return

        for ch in guild.text_channels:
            if ch.name.startswith(f"ticket-{interaction.user.id}-"):
                await interaction.response.send_message(f"⚠️ You already have {ch.mention}.", ephemeral=True)
                return

        category = guild.get_channel(int(config["category_id"])) if config.get("category_id") else None
        if not isinstance(category, discord.CategoryChannel):
            category = None
        support = guild.get_role(int(config["support_role_id"])) if config.get("support_role_id") else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                attach_files=True, embed_links=True
            ),
        }
        if support:
            overwrites[support] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_messages=True, attach_files=True, embed_links=True
            )
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True,
                manage_channels=True, manage_messages=True
            )

        try:
            channel = await guild.create_text_channel(
                f"ticket-{interaction.user.id}-{slug(template_key)}"[:100],
                category=category, overwrites=overwrites,
                topic=f"Air Commander ticket | owner={interaction.user.id} | type={template_key}",
                reason=f"Ticket opened by {interaction.user}",
            )
        except discord.Forbidden:
            await interaction.response.send_message("❌ I need Manage Channels permission.", ephemeral=True)
            return

        embed = discord.Embed(
            title=template.get("welcome_title", "🎫 Ticket"),
            description=template.get("welcome_description", "Please explain your request."),
            color=int(template.get("color", 0x5865F2)),
            timestamp=datetime.now(timezone.utc),
        )
        embed.add_field(name="👤 Owner", value=interaction.user.mention)
        embed.add_field(name="📁 Type", value=template.get("label", template_key))
        embed.set_footer(text=config.get("panel_footer", "Air Commander Tickets"))

        content = interaction.user.mention
        if support:
            content += f" {support.mention}"

        await channel.send(content=content, embed=embed, view=TicketActions(self))
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

        log = discord.Embed(title="🎫 Ticket Opened", color=0x57F287, timestamp=datetime.now(timezone.utc))
        log.add_field(name="User", value=interaction.user.mention)
        log.add_field(name="Type", value=template.get("label", template_key))
        log.add_field(name="Channel", value=channel.mention)
        await log_event(guild, config, log)

    async def claim(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        config = self.cfg(interaction.guild)
        if not is_support(interaction.user, config):
            await interaction.response.send_message("❌ Support team only.", ephemeral=True)
            return
        if not is_ticket(interaction.channel):
            await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
            return
        await interaction.response.send_message(f"🙋 Ticket claimed by {interaction.user.mention}.")

    async def close(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_ticket(interaction.channel):
            await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
            return
        owner = ticket_owner(interaction.channel)
        config = self.cfg(interaction.guild)
        if not is_support(interaction.user, config) and owner != interaction.user.id:
            await interaction.response.send_message("❌ Only the owner or support team can close this ticket.", ephemeral=True)
            return
        await interaction.channel.edit(
            name=f"closed-{interaction.channel.name[7:]}" if interaction.channel.name.startswith("ticket-") else interaction.channel.name
        )
        await interaction.response.send_message("🔒 Ticket closed.")
        log = discord.Embed(title="🔒 Ticket Closed", color=0xFEE75C)
        log.add_field(name="By", value=interaction.user.mention)
        log.add_field(name="Channel", value=f"`{interaction.channel.name}`")
        await log_event(interaction.guild, config, log)

    async def delete(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_ticket(interaction.channel):
            await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
            return
        config = self.cfg(interaction.guild)
        if not is_support(interaction.user, config):
            await interaction.response.send_message("❌ Support team only.", ephemeral=True)
            return

        channel = interaction.channel
        text = await transcript(channel)
        transcript_channel = (
            interaction.guild.get_channel(int(config["transcript_channel_id"]))
            if config.get("transcript_channel_id") else None
        )
        if isinstance(transcript_channel, discord.TextChannel):
            await transcript_channel.send(
                content=f"🧾 Transcript for `{channel.name}` — deleted by {interaction.user.mention}",
                file=discord.File(fp=__import__("io").BytesIO(text.encode("utf-8")), filename=f"{channel.name}.txt"),
            )
        await interaction.response.send_message("🗑️ Deleting ticket...")
        await asyncio.sleep(1)
        await channel.delete(reason=f"Ticket deleted by {interaction.user}")

    @ticket.command(name="setup", description="Configure ticket category, support role and logs.")
    @app_commands.describe(support_role="Support/staff role.", category="Ticket category.", log_channel="Ticket log channel.", transcript_channel="Transcript channel.")
    async def slash_setup(self, interaction, support_role: discord.Role, category: discord.CategoryChannel, log_channel: Optional[discord.TextChannel] = None, transcript_channel: Optional[discord.TextChannel] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
            return
        c = self.cfg(interaction.guild)
        c.update({
            "support_role_id": support_role.id, "category_id": category.id,
            "log_channel_id": log_channel.id if log_channel else None,
            "transcript_channel_id": transcript_channel.id if transcript_channel else None,
        })
        save_config(interaction.guild.id, c)
        await interaction.response.send_message("✅ Ticket system configured.")

    @ticket.command(name="panel", description="Send a ticket panel.")
    async def slash_panel(self, interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
            return
        self.guild_id = interaction.guild.id
        c = self.cfg(interaction.guild)
        e = discord.Embed(title=c["panel_title"], description=c["panel_description"], color=int(c["panel_color"]))
        e.set_footer(text=c.get("panel_footer", "Air Commander Tickets"))
        msg = await channel.send(embed=e, view=TicketPanel(self))
        c["panel_channel_id"], c["panel_message_id"] = channel.id, msg.id
        save_config(interaction.guild.id, c)
        await interaction.response.send_message(f"✅ Panel sent to {channel.mention}.", ephemeral=True)

    @ticket.command(name="template", description="Create or edit a ticket template.")
    @app_commands.describe(key="Unique key.", label="Dropdown label.", description="Short description.", emoji="Emoji.")
    async def slash_template(self, interaction, key: str, label: str, description: str, emoji: Optional[str] = None):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
            return
        key = slug(key).replace("-", "_")[:32]
        c = self.cfg(interaction.guild)
        old = c["templates"].get(key, {})
        c["templates"][key] = {
            "label": label[:100], "emoji": emoji or old.get("emoji", "🎫"),
            "description": description[:100], "color": old.get("color", 0x5865F2),
            "welcome_title": old.get("welcome_title", f"🎫 {label} Ticket"),
            "welcome_description": old.get("welcome_description", description),
        }
        save_config(interaction.guild.id, c)
        await interaction.response.send_message(f"✅ Template `{key}` saved.")

    @ticket.command(name="settings", description="Show ticket settings.")
    async def slash_settings(self, interaction):
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
            return
        c = self.cfg(interaction.guild)
        role = interaction.guild.get_role(c["support_role_id"]) if c.get("support_role_id") else None
        cat = interaction.guild.get_channel(c["category_id"]) if c.get("category_id") else None
        log = interaction.guild.get_channel(c["log_channel_id"]) if c.get("log_channel_id") else None
        e = discord.Embed(title="⚙️ Ticket Settings", color=0x5865F2)
        e.add_field(name="👥 Support Role", value=role.mention if role else "Not set", inline=False)
        e.add_field(name="📁 Category", value=cat.mention if cat else "Not set", inline=False)
        e.add_field(name="📜 Logs", value=log.mention if log else "Not set", inline=False)
        e.add_field(name="🎫 Templates", value=str(len(c["templates"])))
        await interaction.response.send_message(embed=e, ephemeral=True)

    @ticket.command(name="close", description="Close the current ticket.")
    async def slash_close(self, interaction):
        await self.close(interaction)

    @ticket.command(name="delete", description="Delete the current ticket.")
    async def slash_delete(self, interaction):
        await self.delete(interaction)

    @ticket.command(name="claim", description="Claim the current ticket.")
    async def slash_claim(self, interaction):
        await self.claim(interaction)

    @ticket.command(name="reopen", description="Reopen the current ticket.")
    async def slash_reopen(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        if not is_support(interaction.user, self.cfg(interaction.guild)):
            await interaction.response.send_message("❌ Support team only.", ephemeral=True)
            return
        if not isinstance(interaction.channel, discord.TextChannel) or not interaction.channel.name.startswith("closed-"):
            await interaction.response.send_message("❌ This is not a closed ticket.", ephemeral=True)
            return
        await interaction.channel.edit(name=f"ticket-{interaction.channel.name[7:]}")
        await interaction.response.send_message("🔓 Ticket reopened.")

    @ticket.command(name="add", description="Add a member to the current ticket.")
    async def slash_add(self, interaction, member: discord.Member):
        if not interaction.guild or not is_support(interaction.user, self.cfg(interaction.guild)) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Support team only.", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)
        await interaction.response.send_message(f"✅ Added {member.mention}.")

    @ticket.command(name="remove", description="Remove a member from the current ticket.")
    async def slash_remove(self, interaction, member: discord.Member):
        if not interaction.guild or not is_support(interaction.user, self.cfg(interaction.guild)) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Support team only.", ephemeral=True)
            return
        await interaction.channel.set_permissions(member, overwrite=None)
        await interaction.response.send_message(f"✅ Removed {member.mention}.")

    @ticket.command(name="rename", description="Rename the current ticket.")
    async def slash_rename(self, interaction, name: str):
        if not interaction.guild or not is_support(interaction.user, self.cfg(interaction.guild)) or not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("❌ Support team only.", ephemeral=True)
            return
        new_name = slug(name)
        await interaction.channel.edit(name=new_name)
        await interaction.response.send_message(f"✅ Renamed to `{new_name}`.")

    @ticket.command(name="info", description="Show current ticket information.")
    async def slash_info(self, interaction):
        if not isinstance(interaction.channel, discord.TextChannel) or not is_ticket(interaction.channel):
            await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
            return
        owner = ticket_owner(interaction.channel)
        member = interaction.guild.get_member(owner) if owner else None
        e = discord.Embed(title="🎫 Ticket Information", color=0x5865F2)
        e.add_field(name="👤 Owner", value=member.mention if member else str(owner or "Unknown"))
        e.add_field(name="📌 Channel", value=interaction.channel.mention)
        await interaction.response.send_message(embed=e, ephemeral=True)

    @commands.group(name="ticket", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_ticket(self, ctx):
        await ctx.send("🎫 **Ticket:** `,ticket setup` `,ticket panel #channel` `,ticket template` `,ticket settings` `,ticket close` `,ticket reopen` `,ticket claim` `,ticket delete` `,ticket info`")

    @prefix_ticket.command(name="panel")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_panel(self, ctx, channel: discord.TextChannel):
        self.guild_id = ctx.guild.id
        c = self.cfg(ctx.guild)
        e = discord.Embed(title=c["panel_title"], description=c["panel_description"], color=int(c["panel_color"]))
        e.set_footer(text=c.get("panel_footer", "Air Commander Tickets"))
        msg = await channel.send(embed=e, view=TicketPanel(self))
        c["panel_channel_id"], c["panel_message_id"] = channel.id, msg.id
        save_config(ctx.guild.id, c)
        await ctx.send(f"✅ Panel sent to {channel.mention}.")

    @prefix_ticket.command(name="setup")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_setup(self, ctx, support_role: discord.Role, category: discord.CategoryChannel, log_channel: Optional[discord.TextChannel] = None, transcript_channel: Optional[discord.TextChannel] = None):
        c = self.cfg(ctx.guild)
        c.update({
            "support_role_id": support_role.id, "category_id": category.id,
            "log_channel_id": log_channel.id if log_channel else None,
            "transcript_channel_id": transcript_channel.id if transcript_channel else None,
        })
        save_config(ctx.guild.id, c)
        await ctx.send("✅ Ticket system configured.")

    @prefix_ticket.command(name="close")
    async def prefix_close(self, ctx):
        await self._prefix_action(ctx, "close")

    @prefix_ticket.command(name="delete")
    async def prefix_delete(self, ctx):
        await self._prefix_action(ctx, "delete")

    @prefix_ticket.command(name="claim")
    async def prefix_claim(self, ctx):
        await self._prefix_action(ctx, "claim")

    async def _prefix_action(self, ctx, action):
        class R:
            def __init__(self, ctx):
                self.ctx, self.guild, self.user, self.channel = ctx, ctx.guild, ctx.author, ctx.channel
                self.response = self
                self.followup = self
            async def send_message(self, content=None, **kwargs):
                return await self.ctx.send(content=content, **kwargs)
            async def defer(self, **kwargs):
                return None
            async def send(self, content=None, **kwargs):
                return await self.ctx.send(content=content, **kwargs)
        r = R(ctx)
        await getattr(self, action)(r)

async def setup(bot):
    """Install the ticket system into an already-created Discord bot."""
    cog = TicketSystem(bot)
    await bot.add_cog(cog)
    return cog


async def restore_panels(bot, cog):
    """Restore dropdowns on previously sent panels after a bot restart."""
    data = load_all()
    for guild in bot.guilds:
        config = data.get(str(guild.id))
        if not config:
            continue
        channel_id = config.get("panel_channel_id")
        message_id = config.get("panel_message_id")
        if not channel_id or not message_id:
            continue
        channel = guild.get_channel(int(channel_id))
        if not isinstance(channel, discord.TextChannel):
            continue
        try:
            message = await channel.fetch_message(int(message_id))
            cog.guild_id = guild.id
            await message.edit(view=TicketPanel(cog))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            continue
        except Exception as exc:
            print(f"[Ticket] Panel restore error in {guild.id}: {type(exc).__name__}: {exc}")
