"""Air Commander Advanced Ticket System - Panel/Template Manager Prototype.

This module is loaded by bot.py with:
    import ticket
    await ticket.setup(bot)
    await ticket.restore_panels(bot, ticket_cog)
"""

from __future__ import annotations

import asyncio
import io
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
    "panels": {},
    "next_panel_id": 1,
}


def clone_default():
    return json.loads(json.dumps(DEFAULT))


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
        data[key] = clone_default()
        save_all(data)
        return data[key]

    config = data[key]
    changed = False
    for k, v in DEFAULT.items():
        if k not in config:
            config[k] = json.loads(json.dumps(v))
            changed = True
    config.setdefault("panels", {})
    config.setdefault("next_panel_id", 1)
    if changed:
        save_all(data)
    return config


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
    if not isinstance(member, discord.Member):
        return False
    if member.guild_permissions.administrator or member.guild_permissions.manage_guild:
        return True
    role_id = config.get("support_role_id")
    return bool(role_id and any(r.id == int(role_id) for r in member.roles))


def admin_check(member):
    return isinstance(member, discord.Member) and member.guild_permissions.manage_guild


def panel_color(panel):
    try:
        return int(str(panel.get("color", "5865F2")).replace("#", ""), 16)
    except (ValueError, TypeError):
        return 0x5865F2


def template_color(template):
    try:
        return int(str(template.get("color", "5865F2")).replace("#", ""), 16)
    except (ValueError, TypeError):
        return 0x5865F2


def get_templates_for_panel(config, panel):
    out = []
    for key in panel.get("template_keys", []):
        if key in config.get("templates", {}):
            out.append((key, config["templates"][key]))
    return out


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
    lines = [f"Ticket: #{channel.name}", f"Created: {channel.created_at.isoformat()}", ""]
    try:
        async for m in channel.history(limit=None, oldest_first=True):
            stamp = m.created_at.strftime("%Y-%m-%d %H:%M:%S UTC")
            content = m.content or ""
            if m.attachments:
                content += " " + " ".join(a.url for a in m.attachments)
            lines.append(f"[{stamp}] {m.author} ({m.author.id}): {content}")
    except discord.HTTPException:
        lines.append("[Unable to read complete message history]")
    return "\n".join(lines)


# =========================================================
# LIVE TICKET PANEL
# =========================================================


class TicketPanel(discord.ui.View):
    def __init__(self, cog, guild_id, panel_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.panel_id = panel_id
        config = get_config(guild_id)
        panel = config.get("panels", {}).get(str(panel_id), {})
        options = []
        for key, template in get_templates_for_panel(config, panel)[:25]:
            options.append(discord.SelectOption(
                label=str(template.get("label", key))[:100],
                value=key,
                description=str(template.get("description", "Open a ticket."))[:100],
                emoji=template.get("emoji") or None,
            ))
        if not options:
            options = [discord.SelectOption(label="Support", value="support", emoji="🎫")]
        self.add_item(TicketSelect(cog, guild_id, options))


class TicketSelect(discord.ui.Select):
    def __init__(self, cog, guild_id, options):
        self.cog = cog
        self.guild_id = guild_id
        super().__init__(
            placeholder="🎫 Select a ticket type...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"air_ticket_select:{guild_id}",
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


# =========================================================
# MANAGER MODALS
# =========================================================


class PanelCreateModal(discord.ui.Modal, title="➕ Create Ticket Panel"):
    name = discord.ui.TextInput(label="Panel Name", placeholder="Support Center", max_length=80)
    description = discord.ui.TextInput(label="Description", placeholder="Choose a ticket type below.", style=discord.TextStyle.paragraph, max_length=2000)
    channel_id = discord.ui.TextInput(label="Panel Channel ID", placeholder="123456789012345678", max_length=25)
    color = discord.ui.TextInput(label="Embed Color", placeholder="#5865F2", required=False, max_length=7)
    footer = discord.ui.TextInput(label="Footer", placeholder="Air Commander Tickets", required=False, max_length=200)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction):
        try:
            channel_id = int(self.channel_id.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
        channel = interaction.guild.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        color = panel_color({"color": self.color.value or "#5865F2"})
        config = self.cog.cfg(interaction.guild)
        panel_id = int(config.get("next_panel_id", 1))
        config["next_panel_id"] = panel_id + 1
        config.setdefault("panels", {})[str(panel_id)] = {
            "id": panel_id,
            "name": self.name.value.strip(),
            "description": self.description.value.strip(),
            "channel_id": channel.id,
            "color": color,
            "footer": self.footer.value.strip() or "Air Commander Tickets",
            "template_keys": [],
            "message_id": None,
        }
        save_config(interaction.guild.id, config)
        await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))


class PanelEditModal(discord.ui.Modal, title="🎨 Edit Ticket Panel"):
    name = discord.ui.TextInput(label="Panel Name", max_length=80)
    description = discord.ui.TextInput(label="Description", style=discord.TextStyle.paragraph, max_length=2000)
    channel_id = discord.ui.TextInput(label="Panel Channel ID", max_length=25)
    color = discord.ui.TextInput(label="Embed Color", required=False, max_length=7)
    footer = discord.ui.TextInput(label="Footer", required=False, max_length=200)

    def __init__(self, cog, panel_id, panel):
        super().__init__()
        self.cog = cog
        self.panel_id = panel_id
        self.name.default = panel.get("name", "")
        self.description.default = panel.get("description", "")
        self.channel_id.default = str(panel.get("channel_id", ""))
        self.color.default = f"#{int(panel.get('color', 0x5865F2)):06X}"
        self.footer.default = panel.get("footer", "Air Commander Tickets")

    async def on_submit(self, interaction):
        try:
            channel_id = int(self.channel_id.value.strip())
        except ValueError:
            return await interaction.response.send_message("❌ Invalid channel ID.", ephemeral=True)
        if not isinstance(interaction.guild.get_channel(channel_id), discord.TextChannel):
            return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
        config = self.cog.cfg(interaction.guild)
        panel = config["panels"].get(str(self.panel_id))
        if not panel:
            return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)
        panel.update({
            "name": self.name.value.strip(),
            "description": self.description.value.strip(),
            "channel_id": channel_id,
            "color": panel_color({"color": self.color.value or "#5865F2"}),
            "footer": self.footer.value.strip() or "Air Commander Tickets",
        })
        save_config(interaction.guild.id, config)
        await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))


class TemplateCreateModal(discord.ui.Modal, title="➕ Create Ticket Template"):
    key = discord.ui.TextInput(label="Template Key", placeholder="support", max_length=32)
    label = discord.ui.TextInput(label="Dropdown Label", placeholder="Support", max_length=100)
    description = discord.ui.TextInput(label="Dropdown Description", placeholder="Open a support ticket.", max_length=100)
    emoji = discord.ui.TextInput(label="Emoji", placeholder="🎫", required=False, max_length=10)
    welcome = discord.ui.TextInput(label="Welcome Message", placeholder="Please explain your issue clearly.", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction):
        key = slug(self.key.value).replace("-", "_")[:32]
        config = self.cog.cfg(interaction.guild)
        config.setdefault("templates", {})[key] = {
            "label": self.label.value.strip(),
            "emoji": self.emoji.value.strip() or "🎫",
            "description": self.description.value.strip(),
            "color": 0x5865F2,
            "welcome_title": f"🎫 {self.label.value.strip()} Ticket",
            "welcome_description": self.welcome.value.strip(),
        }
        save_config(interaction.guild.id, config)
        await interaction.response.edit_message(embed=self.cog.template_manager_embed(interaction.guild), view=TemplateManagerView(self.cog))


class TemplateEditModal(discord.ui.Modal, title="🎨 Edit Ticket Template"):
    label = discord.ui.TextInput(label="Dropdown Label", max_length=100)
    description = discord.ui.TextInput(label="Dropdown Description", max_length=100)
    emoji = discord.ui.TextInput(label="Emoji", required=False, max_length=10)
    welcome_title = discord.ui.TextInput(label="Welcome Title", max_length=200)
    welcome_description = discord.ui.TextInput(label="Welcome Message", style=discord.TextStyle.paragraph, max_length=2000)

    def __init__(self, cog, key, template):
        super().__init__()
        self.cog = cog
        self.key = key
        self.label.default = template.get("label", "")
        self.description.default = template.get("description", "")
        self.emoji.default = template.get("emoji", "🎫")
        self.welcome_title.default = template.get("welcome_title", f"🎫 {template.get('label', key)} Ticket")
        self.welcome_description.default = template.get("welcome_description", "")

    async def on_submit(self, interaction):
        config = self.cog.cfg(interaction.guild)
        template = config.get("templates", {}).get(self.key)
        if not template:
            return await interaction.response.send_message("❌ Template not found.", ephemeral=True)
        template.update({
            "label": self.label.value.strip(),
            "description": self.description.value.strip(),
            "emoji": self.emoji.value.strip() or "🎫",
            "welcome_title": self.welcome_title.value.strip(),
            "welcome_description": self.welcome_description.value.strip(),
        })
        save_config(interaction.guild.id, config)
        await interaction.response.edit_message(embed=self.cog.template_manager_embed(interaction.guild), view=TemplateManagerView(self.cog))


# =========================================================
# SELECT VIEWS
# =========================================================


class PanelSelect(discord.ui.Select):
    def __init__(self, cog, panels, action):
        self.cog, self.action = cog, action
        options = [discord.SelectOption(label=p.get("name", f"Panel {p.get('id')}" )[:100], value=str(p["id"]), emoji="🧩") for p in panels[:25]]
        super().__init__(placeholder=f"🧩 Select a panel to {action}...", options=options)

    async def callback(self, interaction):
        panel_id = int(self.values[0])
        config = self.cog.cfg(interaction.guild)
        panel = config.get("panels", {}).get(str(panel_id))
        if not panel:
            return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)
        if self.action == "edit":
            return await interaction.response.send_modal(PanelEditModal(self.cog, panel_id, panel))
        if self.action == "delete":
            config["panels"].pop(str(panel_id), None)
            save_config(interaction.guild.id, config)
            return await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))
        if self.action == "send":
            await interaction.response.defer(ephemeral=True)
            msg, error = await self.cog.send_panel(interaction.guild, panel)
            return await interaction.followup.send(error or f"✅ **{panel['name']}** sent. Message ID: `{msg.id}`", ephemeral=True)
        if self.action == "templates":
            return await interaction.response.edit_message(embed=self.cog.add_template_embed(interaction.guild, panel), view=PanelTemplateView(self.cog, panel_id))


class PanelTemplateView(discord.ui.View):
    def __init__(self, cog, panel_id):
        super().__init__(timeout=300)
        self.cog, self.panel_id = cog, panel_id
        config = cog.cfg(cog._current_guild_id)
        templates = list(config.get("templates", {}).items())
        options = [discord.SelectOption(label=t.get("label", key)[:100], value=key, default=key in config["panels"].get(str(panel_id), {}).get("template_keys", []), emoji=t.get("emoji") or None) for key,t in templates[:25]]
        if options:
            self.add_item(TemplateMultiSelect(cog, panel_id, options))
        back = discord.ui.Button(label="Back", emoji="↩️", style=discord.ButtonStyle.secondary, row=1)
        back.callback = self.back
        self.add_item(back)

    async def back(self, interaction):
        await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))


class TemplateMultiSelect(discord.ui.Select):
    def __init__(self, cog, panel_id, options):
        self.cog, self.panel_id = cog, panel_id
        super().__init__(placeholder="🎫 Select templates for this panel...", min_values=0, max_values=min(25, len(options)), options=options)

    async def callback(self, interaction):
        config = self.cog.cfg(interaction.guild)
        panel = config["panels"].get(str(self.panel_id))
        if not panel:
            return await interaction.response.send_message("❌ Panel not found.", ephemeral=True)
        panel["template_keys"] = list(self.values)
        save_config(interaction.guild.id, config)
        await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))


class ConfigureModal(discord.ui.Modal, title="⚙️ Configure Ticket System"):
    support_role_id = discord.ui.TextInput(label="Support Role ID", placeholder="Role ID (blank = keep current)", required=False, max_length=30)
    category_id = discord.ui.TextInput(label="Ticket Category ID", placeholder="Category channel ID", required=False, max_length=30)
    log_channel_id = discord.ui.TextInput(label="Log Channel ID", placeholder="Log channel ID", required=False, max_length=30)
    transcript_channel_id = discord.ui.TextInput(label="Transcript Channel ID", placeholder="Transcript channel ID", required=False, max_length=30)
    footer = discord.ui.TextInput(label="Ticket Footer", placeholder="Air Commander Tickets", required=False, max_length=100)

    def __init__(self, cog):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction):
        if not admin_check(interaction.user):
            return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        c = self.cog.cfg(interaction.guild)
        values = {
            "support_role_id": (self.support_role_id.value or "").strip(),
            "category_id": (self.category_id.value or "").strip(),
            "log_channel_id": (self.log_channel_id.value or "").strip(),
            "transcript_channel_id": (self.transcript_channel_id.value or "").strip(),
        }
        for key, value in values.items():
            if value:
                try:
                    c[key] = int(value)
                except ValueError:
                    return await interaction.response.send_message(f"❌ Invalid ID for `{key}`.", ephemeral=True)
        if self.footer.value.strip():
            c["panel_footer"] = self.footer.value.strip()
        save_config(interaction.guild.id, c)
        await interaction.response.edit_message(embed=self.cog.configure_embed(interaction.guild), view=ConfigureView(self.cog))


class ConfigureView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Configure", emoji="⚙️", style=discord.ButtonStyle.primary)
    async def configure(self, interaction, button):
        if not admin_check(interaction.user):
            return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        c = self.cog.cfg(interaction.guild)
        modal = ConfigureModal(self.cog)
        modal.support_role_id.default = str(c.get("support_role_id") or "")
        modal.category_id.default = str(c.get("category_id") or "")
        modal.log_channel_id.default = str(c.get("log_channel_id") or "")
        modal.transcript_channel_id.default = str(c.get("transcript_channel_id") or "")
        modal.footer.default = str(c.get("panel_footer") or "Air Commander Tickets")
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.configure_embed(interaction.guild), view=ConfigureView(self.cog))

    @discord.ui.button(label="Back", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))


# =========================================================
# MANAGER VIEWS
# =========================================================


class PanelManagerView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Create Panel", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def create(self, interaction, button):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        await interaction.response.send_modal(PanelCreateModal(self.cog))

    @discord.ui.button(label="Panel List", emoji="📋", style=discord.ButtonStyle.primary, row=0)
    async def listing(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.panel_list_embed(interaction.guild), view=PanelListView(self.cog))

    @discord.ui.button(label="Edit Panel", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def edit(self, interaction, button):
        await self.cog.panel_select_action(interaction, "edit")

    @discord.ui.button(label="Delete Panel", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction, button):
        await self.cog.panel_select_action(interaction, "delete")

    @discord.ui.button(label="Add Template", emoji="🎫", style=discord.ButtonStyle.primary, row=1)
    async def templates(self, interaction, button):
        await self.cog.panel_select_action(interaction, "templates")

    @discord.ui.button(label="Send Panel", emoji="📤", style=discord.ButtonStyle.success, row=1)
    async def send(self, interaction, button):
        await self.cog.panel_select_action(interaction, "send")

    @discord.ui.button(label="Configure", emoji="⚙️", style=discord.ButtonStyle.secondary, row=2)
    async def configure(self, interaction, button):
        if not admin_check(interaction.user):
            return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        await interaction.response.edit_message(embed=self.cog.configure_embed(interaction.guild), view=ConfigureView(self.cog))


class PanelListView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Back", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.panel_manager_embed(interaction.guild), view=PanelManagerView(self.cog))


class TemplateManagerView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Create Template", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def create(self, interaction, button):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        await interaction.response.send_modal(TemplateCreateModal(self.cog))

    @discord.ui.button(label="Template List", emoji="📋", style=discord.ButtonStyle.primary, row=0)
    async def listing(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.template_list_embed(interaction.guild), view=TemplateListView(self.cog))

    @discord.ui.button(label="Edit Template", emoji="🎨", style=discord.ButtonStyle.primary, row=0)
    async def edit(self, interaction, button):
        await self.cog.template_select_edit(interaction)

    @discord.ui.button(label="Delete Template", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction, button):
        await self.cog.template_select_delete(interaction)

    @discord.ui.button(label="Refresh", emoji="🔄", style=discord.ButtonStyle.secondary, row=1)
    async def refresh(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.template_manager_embed(interaction.guild), view=TemplateManagerView(self.cog))


class TemplateListView(discord.ui.View):
    def __init__(self, cog):
        super().__init__(timeout=300)
        self.cog = cog

    @discord.ui.button(label="Back", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction, button):
        await interaction.response.edit_message(embed=self.cog.template_manager_embed(interaction.guild), view=TemplateManagerView(self.cog))


class KeySelect(discord.ui.Select):
    def __init__(self, cog, keys, action):
        self.cog, self.action = cog, action
        options = [discord.SelectOption(label=str(k)[:100], value=str(k), emoji="🎫") for k in keys[:25]]
        super().__init__(placeholder=f"🎫 Select a template to {action}...", options=options)

    async def callback(self, interaction):
        key = self.values[0]
        config = self.cog.cfg(interaction.guild)
        template = config.get("templates", {}).get(key)
        if not template:
            return await interaction.response.send_message("❌ Template not found.", ephemeral=True)
        if self.action == "edit":
            return await interaction.response.send_modal(TemplateEditModal(self.cog, key, template))
        config["templates"].pop(key, None)
        for panel in config.get("panels", {}).values():
            panel["template_keys"] = [x for x in panel.get("template_keys", []) if x != key]
        save_config(interaction.guild.id, config)
        await interaction.response.edit_message(embed=self.cog.template_manager_embed(interaction.guild), view=TemplateManagerView(self.cog))


class KeySelectView(discord.ui.View):
    def __init__(self, cog, keys, action):
        super().__init__(timeout=300)
        self.cog = cog
        self.add_item(KeySelect(cog, keys, action))
        back = discord.ui.Button(label="Back", emoji="↩️", style=discord.ButtonStyle.secondary)
        back.callback = self.back
        self.add_item(back)

    async def back(self, interaction):
        await interaction.response.edit_message(embed=self.cog.template_manager_embed(interaction.guild), view=TemplateManagerView(self.cog))


# =========================================================
# COG
# =========================================================


class TicketSystem(commands.Cog):
    ticket = app_commands.Group(name="ticket", description="Advanced ticket management.")

    def __init__(self, bot):
        self.bot = bot
        self._current_guild_id = 0

    async def cog_load(self):
        self.bot.add_view(TicketActions(self))

    def cfg(self, guild):
        self._current_guild_id = guild.id
        return get_config(guild.id)

    # ---------- manager embeds ----------
    def panel_manager_embed(self, guild):
        config = self.cfg(guild)
        e = discord.Embed(title="🎫 Ticket Panel Manager", description="Manage all ticket panels from the buttons below.", color=0x5865F2)
        panels = config.get("panels", {})
        e.add_field(name="📊 Panels", value=f"`{len(panels)}` panel(s) created", inline=True)
        e.add_field(name="🎫 Templates", value=f"`{len(config.get('templates', {}))}` available", inline=True)
        e.set_footer(text="Air Commander • Ticket System")
        return e

    def configure_embed(self, guild):
        config = self.cfg(guild)
        role = guild.get_role(int(config["support_role_id"])) if config.get("support_role_id") else None
        category = guild.get_channel(int(config["category_id"])) if config.get("category_id") else None
        logs = guild.get_channel(int(config["log_channel_id"])) if config.get("log_channel_id") else None
        transcript = guild.get_channel(int(config["transcript_channel_id"])) if config.get("transcript_channel_id") else None
        e = discord.Embed(title="⚙️ Ticket Configuration", description="Configure the core ticket system settings from the button below.", color=0x5865F2)
        e.add_field(name="👥 Support Role", value=role.mention if role else "Not configured", inline=False)
        e.add_field(name="📁 Ticket Category", value=category.mention if category else "Not configured", inline=False)
        e.add_field(name="📜 Log Channel", value=logs.mention if logs else "Not configured", inline=False)
        e.add_field(name="🧾 Transcript Channel", value=transcript.mention if transcript else "Not configured", inline=False)
        e.add_field(name="📝 Footer", value=config.get("panel_footer", "Air Commander Tickets"), inline=False)
        e.set_footer(text="Air Commander • Ticket System")
        return e

    def panel_list_embed(self, guild):
        config = self.cfg(guild)
        e = discord.Embed(title="📋 Ticket Panel List", color=0x5865F2)
        panels = list(config.get("panels", {}).values())
        if not panels:
            e.description = "📭 No panels created yet."
            return e
        for p in panels[:25]:
            channel = guild.get_channel(int(p.get("channel_id", 0))) if p.get("channel_id") else None
            names = [config.get("templates", {}).get(k, {}).get("label", k) for k in p.get("template_keys", [])]
            e.add_field(name=f"🧩 #{p['id']} • {p.get('name', 'Unnamed')}", value=f"📍 {channel.mention if channel else 'Channel not found'}\n🎫 {', '.join(names) if names else 'No templates attached'}\n📨 Message: `{p.get('message_id') or 'Not sent'}`", inline=False)
        return e

    def template_manager_embed(self, guild):
        config = self.cfg(guild)
        e = discord.Embed(title="🎫 Ticket Template Manager", description="Create, list, edit and delete ticket templates.", color=0x5865F2)
        e.add_field(name="📊 Templates", value=f"`{len(config.get('templates', {}))}` template(s)", inline=True)
        e.set_footer(text="Air Commander • Ticket System")
        return e

    def template_list_embed(self, guild):
        config = self.cfg(guild)
        e = discord.Embed(title="📋 Ticket Template List", color=0x5865F2)
        templates = config.get("templates", {})
        if not templates:
            e.description = "📭 No templates created."
            return e
        for key, t in list(templates.items())[:25]:
            e.add_field(name=f"🎫 `{key}` • {t.get('label', key)}", value=f"{t.get('emoji','🎫')} {t.get('description','No description')}", inline=False)
        return e

    def add_template_embed(self, guild, panel):
        e = discord.Embed(title=f"🎫 Add Templates • {panel.get('name','Panel')}", description="Select the templates that should appear in this panel. Selected items are saved immediately.", color=0x5865F2)
        return e

    async def panel_select_action(self, interaction, action):
        if not admin_check(interaction.user):
            return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        panels = list(self.cfg(interaction.guild).get("panels", {}).values())
        if not panels:
            return await interaction.response.send_message("📭 Create a panel first.", ephemeral=True)
        view = discord.ui.View(timeout=300)
        view.add_item(PanelSelect(self, panels, action))
        back = discord.ui.Button(label="Back", emoji="↩️", style=discord.ButtonStyle.secondary)
        async def back_cb(i):
            await i.response.edit_message(embed=self.panel_manager_embed(i.guild), view=PanelManagerView(self))
        back.callback = back_cb
        view.add_item(back)
        await interaction.response.edit_message(embed=discord.Embed(title=f"🧩 Select Panel • {action.title()}", description="Choose a panel below.", color=0x5865F2), view=view)

    async def template_select_edit(self, interaction):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        keys = list(self.cfg(interaction.guild).get("templates", {}).keys())
        if not keys: return await interaction.response.send_message("📭 No templates available.", ephemeral=True)
        await interaction.response.edit_message(embed=discord.Embed(title="🎨 Edit Template", description="Select a template.", color=0x5865F2), view=KeySelectView(self, keys, "edit"))

    async def template_select_delete(self, interaction):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        keys = list(self.cfg(interaction.guild).get("templates", {}).keys())
        if not keys: return await interaction.response.send_message("📭 No templates available.", ephemeral=True)
        await interaction.response.edit_message(embed=discord.Embed(title="🗑️ Delete Template", description="Select a template. It will also be removed from every panel.", color=0xED4245), view=KeySelectView(self, keys, "delete"))

    async def send_panel(self, guild, panel):
        config = self.cfg(guild)
        templates = get_templates_for_panel(config, panel)
        if not templates:
            return None, "❌ Add at least one template to this panel first."
        channel = guild.get_channel(int(panel.get("channel_id", 0))) if panel.get("channel_id") else None
        if not isinstance(channel, discord.TextChannel):
            return None, "❌ Panel channel not found. Edit the panel and set a valid channel."
        embed = discord.Embed(title=panel.get("name", "Ticket Panel"), description=panel.get("description", ""), color=panel_color(panel))
        embed.set_footer(text=panel.get("footer", "Air Commander Tickets"))
        view = TicketPanel(self, guild.id, int(panel["id"]))
        try:
            message = await channel.send(embed=embed, view=view)
        except discord.Forbidden:
            return None, "❌ I don't have permission to send messages in that channel."
        panel["message_id"] = message.id
        config["panel_channel_id"] = channel.id
        config["panel_message_id"] = message.id
        save_config(guild.id, config)
        return message, None

    # ---------- ticket runtime ----------
    async def open_ticket(self, interaction, template_key):
        guild = interaction.guild
        if not guild or not isinstance(interaction.user, discord.Member): return
        config = self.cfg(guild)
        template = config["templates"].get(template_key)
        if not template:
            return await interaction.response.send_message("❌ Ticket template not found.", ephemeral=True)
        for ch in guild.text_channels:
            if ch.name.startswith(f"ticket-{interaction.user.id}-"):
                return await interaction.response.send_message(f"⚠️ You already have {ch.mention}.", ephemeral=True)
        category = guild.get_channel(int(config["category_id"])) if config.get("category_id") else None
        if not isinstance(category, discord.CategoryChannel): category = None
        support = guild.get_role(int(config["support_role_id"])) if config.get("support_role_id") else None
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True, embed_links=True),
        }
        if support:
            overwrites[support] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_messages=True, attach_files=True, embed_links=True)
        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, manage_channels=True, manage_messages=True)
        try:
            channel = await guild.create_text_channel(f"ticket-{interaction.user.id}-{slug(template_key)}"[:100], category=category, overwrites=overwrites, topic=f"Air Commander ticket | owner={interaction.user.id} | type={template_key}", reason=f"Ticket opened by {interaction.user}")
        except discord.Forbidden:
            return await interaction.response.send_message("❌ I need Manage Channels permission.", ephemeral=True)
        embed = discord.Embed(title=template.get("welcome_title", "🎫 Ticket"), description=template.get("welcome_description", "Please explain your request."), color=template_color(template), timestamp=datetime.now(timezone.utc))
        embed.add_field(name="👤 Owner", value=interaction.user.mention)
        embed.add_field(name="📁 Type", value=template.get("label", template_key))
        embed.set_footer(text=config.get("panel_footer", "Air Commander Tickets"))
        content = interaction.user.mention + (f" {support.mention}" if support else "")
        await channel.send(content=content, embed=embed, view=TicketActions(self))
        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)
        log = discord.Embed(title="🎫 Ticket Opened", color=0x57F287, timestamp=datetime.now(timezone.utc))
        log.add_field(name="User", value=interaction.user.mention); log.add_field(name="Type", value=template.get("label", template_key)); log.add_field(name="Channel", value=channel.mention)
        await log_event(guild, config, log)

    async def claim(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member): return
        config = self.cfg(interaction.guild)
        if not is_support(interaction.user, config): return await interaction.response.send_message("❌ Support team only.", ephemeral=True)
        if not is_ticket(interaction.channel): return await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
        await interaction.response.send_message(f"🙋 Ticket claimed by {interaction.user.mention}.")

    async def close(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_ticket(interaction.channel): return await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
        owner = ticket_owner(interaction.channel); config = self.cfg(interaction.guild)
        if not is_support(interaction.user, config) and owner != interaction.user.id: return await interaction.response.send_message("❌ Only the owner or support team can close this ticket.", ephemeral=True)
        await interaction.channel.edit(name=f"closed-{interaction.channel.name[7:]}" if interaction.channel.name.startswith("ticket-") else interaction.channel.name)
        await interaction.response.send_message("🔒 Ticket closed.")

    async def delete(self, interaction):
        if not interaction.guild or not isinstance(interaction.user, discord.Member) or not is_ticket(interaction.channel): return await interaction.response.send_message("❌ This is not a ticket.", ephemeral=True)
        config = self.cfg(interaction.guild)
        if not is_support(interaction.user, config): return await interaction.response.send_message("❌ Support team only.", ephemeral=True)
        channel = interaction.channel; text = await transcript(channel)
        transcript_channel = interaction.guild.get_channel(int(config["transcript_channel_id"])) if config.get("transcript_channel_id") else None
        if isinstance(transcript_channel, discord.TextChannel):
            await transcript_channel.send(content=f"🧾 Transcript for `{channel.name}` — deleted by {interaction.user.mention}", file=discord.File(io.BytesIO(text.encode("utf-8")), filename=f"{channel.name}.txt"))
        await interaction.response.send_message("🗑️ Deleting ticket..."); await asyncio.sleep(1); await channel.delete(reason=f"Ticket deleted by {interaction.user}")

    # ---------- slash manager commands ----------
    @ticket.command(name="panel", description="Open the Ticket Panel Manager.")
    async def slash_panel(self, interaction):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        await interaction.response.send_message(embed=self.panel_manager_embed(interaction.guild), view=PanelManagerView(self), ephemeral=True)

    @ticket.command(name="template", description="Open the Ticket Template Manager.")
    async def slash_template(self, interaction):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        await interaction.response.send_message(embed=self.template_manager_embed(interaction.guild), view=TemplateManagerView(self), ephemeral=True)

    @ticket.command(name="configure", description="Open the Ticket Configuration manager.")
    async def slash_configure(self, interaction):
        if not admin_check(interaction.user):
            return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        await interaction.response.send_message(embed=self.configure_embed(interaction.guild), view=ConfigureView(self), ephemeral=True)

    @ticket.command(name="setup", description="Configure ticket category, support role and logs.")
    @app_commands.describe(support_role="Support/staff role.", category="Ticket category.", log_channel="Ticket log channel.", transcript_channel="Transcript channel.")
    async def slash_setup(self, interaction, support_role: discord.Role, category: discord.CategoryChannel, log_channel: Optional[discord.TextChannel] = None, transcript_channel: Optional[discord.TextChannel] = None):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        c = self.cfg(interaction.guild); c.update({"support_role_id": support_role.id, "category_id": category.id, "log_channel_id": log_channel.id if log_channel else None, "transcript_channel_id": transcript_channel.id if transcript_channel else None}); save_config(interaction.guild.id, c)
        await interaction.response.send_message("✅ Ticket system configured.", ephemeral=True)

    @ticket.command(name="settings", description="Show ticket settings.")
    async def slash_settings(self, interaction):
        if not admin_check(interaction.user): return await interaction.response.send_message("❌ Manage Server permission required.", ephemeral=True)
        c = self.cfg(interaction.guild); role = interaction.guild.get_role(c["support_role_id"]) if c.get("support_role_id") else None; cat = interaction.guild.get_channel(c["category_id"]) if c.get("category_id") else None; log = interaction.guild.get_channel(c["log_channel_id"]) if c.get("log_channel_id") else None
        e = discord.Embed(title="⚙️ Ticket Settings", color=0x5865F2); e.add_field(name="👥 Support Role", value=role.mention if role else "Not set", inline=False); e.add_field(name="📁 Category", value=cat.mention if cat else "Not set", inline=False); e.add_field(name="📜 Logs", value=log.mention if log else "Not set", inline=False); await interaction.response.send_message(embed=e, ephemeral=True)

    @ticket.command(name="close", description="Close the current ticket.")
    async def slash_close(self, interaction): await self.close(interaction)

    @ticket.command(name="delete", description="Delete the current ticket.")
    async def slash_delete(self, interaction): await self.delete(interaction)

    @ticket.command(name="claim", description="Claim the current ticket.")
    async def slash_claim(self, interaction): await self.claim(interaction)

    # ---------- prefix manager ----------
    @commands.group(name="ticket", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_ticket(self, ctx):
        await ctx.send("🎫 Use `,ticket panel` or `,ticket template` to open the managers.")

    @prefix_ticket.command(name="panel")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_panel(self, ctx):
        await ctx.send(embed=self.panel_manager_embed(ctx.guild), view=PanelManagerView(self))

    @prefix_ticket.command(name="template")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_template(self, ctx):
        await ctx.send(embed=self.template_manager_embed(ctx.guild), view=TemplateManagerView(self))

    @prefix_ticket.command(name="configure")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_configure(self, ctx):
        await ctx.send(embed=self.configure_embed(ctx.guild), view=ConfigureView(self))

    @prefix_ticket.command(name="setup")
    @commands.has_guild_permissions(manage_guild=True)
    async def prefix_setup(self, ctx, support_role: discord.Role, category: discord.CategoryChannel, log_channel: Optional[discord.TextChannel] = None, transcript_channel: Optional[discord.TextChannel] = None):
        c = self.cfg(ctx.guild); c.update({"support_role_id": support_role.id, "category_id": category.id, "log_channel_id": log_channel.id if log_channel else None, "transcript_channel_id": transcript_channel.id if transcript_channel else None}); save_config(ctx.guild.id, c); await ctx.send("✅ Ticket system configured.")

    @prefix_ticket.command(name="close")
    async def prefix_close(self, ctx): await self._prefix_action(ctx, "close")

    @prefix_ticket.command(name="delete")
    async def prefix_delete(self, ctx): await self._prefix_action(ctx, "delete")

    @prefix_ticket.command(name="claim")
    async def prefix_claim(self, ctx): await self._prefix_action(ctx, "claim")

    async def _prefix_action(self, ctx, action):
        class R:
            def __init__(self, ctx): self.ctx, self.guild, self.user, self.channel, self.response, self.followup = ctx, ctx.guild, ctx.author, ctx.channel, self, self
            async def send_message(self, content=None, **kwargs): return await self.ctx.send(content=content, **kwargs)
            async def defer(self, **kwargs): return None
            async def send(self, content=None, **kwargs): return await self.ctx.send(content=content, **kwargs)
        await getattr(self, action)(R(ctx))


async def setup(bot):
    cog = TicketSystem(bot)
    await bot.add_cog(cog)
    return cog


async def restore_panels(bot, cog):
    data = load_all()
    for guild in bot.guilds:
        config = data.get(str(guild.id))
        if not config:
            continue
        for panel in config.get("panels", {}).values():
            channel_id, message_id = panel.get("channel_id"), panel.get("message_id")
            if not channel_id or not message_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                message = await channel.fetch_message(int(message_id))
                await message.edit(view=TicketPanel(cog, guild.id, int(panel["id"])))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                continue
            except Exception as exc:
                print(f"[Ticket] Panel restore error in {guild.id}: {type(exc).__name__}: {exc}")
