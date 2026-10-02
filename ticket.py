# ============================================================
# AIR COMMANDER — ADVANCED TICKET SYSTEM
# ticket.py
#
# PREFIX:
# ,ticket setup
# ,ticket panel create
# ,ticket panel edit
# ,ticket panel send
# ,ticket panel delete
# ,ticket category add
# ,ticket category edit
# ,ticket category remove
# ,ticket category list
# ,ticket config
# ,ticket close
# ,ticket reopen
# ,ticket claim
# ,ticket add @user
# ,ticket remove @user
# ,ticket rename name
#
# SLASH:
# /ticket setup
# /ticket panel create
# /ticket panel edit
# /ticket panel send
# /ticket panel delete
# /ticket category add
# /ticket category edit
# /ticket category remove
# /ticket category list
# /ticket config
# /ticket close
# /ticket reopen
# /ticket claim
# /ticket add
# /ticket remove
# /ticket rename
# ============================================================

import discord
from discord.ext import commands
from discord import app_commands

import asyncio
import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone


# ============================================================
# CONFIG
# ============================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

DATA_FILE = DATA_DIR / "tickets.json"


# ============================================================
# DEFAULT DATA
# ============================================================

DEFAULT_GUILD_DATA = {
    "categories": {
        "general": {
            "name": "General Support",
            "emoji": "🎫",
            "description": "Get general help from our support team.",
            "prefix": "support"
        }
    },
    "panel": {
        "title": "✈️ Air Commander Support Center",
        "description": (
            "Need help? Open a support ticket below.\n\n"
            "Our support team will assist you as soon as possible.\n\n"
            "Select a category from the menu below."
        ),
        "color": 0x5865F2,
        "footer": "Air Commander • Support System",
        "channel_id": None,
        "message_id": None
    },
    "config": {
        "support_role_id": None,
        "log_channel_id": None,
        "ticket_category_id": None,
        "transcript": True,
        "naming": "ticket-{username}"
    },
    "tickets": {}
}


# ============================================================
# DATABASE HELPERS
# ============================================================

def load_data():
    if not DATA_FILE.exists():
        DATA_FILE.write_text(
            json.dumps({}, indent=4),
            encoding="utf-8"
        )

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception:
        return {}


def save_data(data):
    temp_file = DATA_FILE.with_suffix(".tmp")

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    temp_file.replace(DATA_FILE)


def ensure_guild(data, guild_id):
    gid = str(guild_id)

    if gid not in data:
        data[gid] = json.loads(
            json.dumps(DEFAULT_GUILD_DATA)
        )
        save_data(data)

    guild_data = data[gid]

    guild_data.setdefault("categories", {})
    guild_data.setdefault("panel", {})
    guild_data.setdefault("config", {})
    guild_data.setdefault("tickets", {})

    return guild_data


# ============================================================
# HELPERS
# ============================================================

def is_admin(member: discord.Member):
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


def clean_channel_name(name):
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\-_ ]+", "", name)
    name = name.replace(" ", "-")

    if not name:
        name = "ticket"

    return name[:80]


def category_name_from_key(key, category_data):
    emoji = category_data.get("emoji", "🎫")
    name = category_data.get("name", "General Support")

    return f"{emoji} {name}"


def make_ticket_name(template, member, category_key):
    username = clean_channel_name(member.name)

    replacements = {
        "{username}": username,
        "{user}": username,
        "{category}": clean_channel_name(category_key),
        "{userid}": str(member.id)
    }

    result = template or "ticket-{username}"

    for key, value in replacements.items():
        result = result.replace(key, value)

    return clean_channel_name(result)


def find_ticket(guild_data, channel_id):
    channel_id = str(channel_id)

    for ticket_id, ticket in guild_data["tickets"].items():
        if str(ticket.get("channel_id")) == channel_id:
            return ticket_id, ticket

    return None, None


def get_ticket_by_user(guild_data, user_id):
    user_id = str(user_id)

    for ticket_id, ticket in guild_data["tickets"].items():
        if (
            str(ticket.get("user_id")) == user_id
            and ticket.get("closed") is False
        ):
            return ticket_id, ticket

    return None, None


# ============================================================
# TICKET VIEW
# ============================================================

class TicketPanelView(discord.ui.View):

    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog

        self.add_item(
            TicketCategorySelect(cog)
        )


class TicketCategorySelect(discord.ui.Select):

    def __init__(self, cog):
        self.cog = cog

        options = [
            discord.SelectOption(
                label="General Support",
                description="Get general support.",
                emoji="🎫",
                value="general"
            )
        ]

        super().__init__(
            placeholder="🎫 Select a ticket category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="aircommander:ticket_category"
        )

    async def callback(self, interaction: discord.Interaction):

        await self.cog.handle_category_select(
            interaction,
            self.values[0]
        )


# ============================================================
# MAIN COG
# ============================================================

class TicketSystem(commands.Cog):

    ticket = app_commands.Group(
        name="ticket",
        description="Air Commander ticket system."
    )

    panel = app_commands.Group(
        name="panel",
        description="Manage ticket panels.",
        parent=ticket
    )

    category = app_commands.Group(
        name="category",
        description="Manage ticket categories.",
        parent=ticket
    )

    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

        self._register_persistent_view()

    def _register_persistent_view(self):

        try:
            self.bot.add_view(
                TicketPanelView(self)
            )
        except Exception as e:
            print(
                f"[Ticket] Persistent view error: {type(e).__name__}: {e}"
            )

    # ========================================================
    # EMBED
    # ========================================================

    def panel_embed(self, guild_data):

        panel = guild_data["panel"]

        embed = discord.Embed(
            title=panel.get(
                "title",
                "✈️ Air Commander Support Center"
            ),
            description=panel.get(
                "description",
                "Select a ticket category below."
            ),
            color=panel.get(
                "color",
                0x5865F2
            ),
            timestamp=datetime.now(timezone.utc)
        )

        footer = panel.get(
            "footer",
            "Air Commander • Support System"
        )

        embed.set_footer(
            text=footer
        )

        return embed

    # ========================================================
    # CATEGORY SELECT
    # ========================================================

    async def handle_category_select(
        self,
        interaction: discord.Interaction,
        category_key: str
    ):

        guild = interaction.guild

        if guild is None:
            return

        data = load_data()
        guild_data = ensure_guild(
            data,
            guild.id
        )

        categories = guild_data["categories"]

        if category_key not in categories:
            await interaction.response.send_message(
                "❌ This ticket category no longer exists.",
                ephemeral=False
            )
            return

        existing_id, existing_ticket = get_ticket_by_user(
            guild_data,
            interaction.user.id
        )

        if existing_ticket:
            channel = guild.get_channel(
                int(existing_ticket["channel_id"])
            )

            if channel:
                await interaction.response.send_message(
                    f"❌ You already have an open ticket: {channel.mention}",
                    ephemeral=False
                )
                return

        await interaction.response.defer(
            ephemeral=False
        )

        category_data = categories[category_key]

        channel = await self.create_ticket(
            guild,
            interaction.user,
            category_key,
            category_data,
            guild_data
        )

        if channel is None:
            await interaction.followup.send(
                "❌ I couldn't create the ticket. Check my permissions.",
                ephemeral=False
            )
            return

        await interaction.followup.send(
            f"🎫 Your ticket has been created: {channel.mention}",
            ephemeral=False
        )

    # ========================================================
    # CREATE TICKET
    # ========================================================

    async def create_ticket(
        self,
        guild,
        member,
        category_key,
        category_data,
        guild_data
    ):

        config = guild_data["config"]

        support_role = None

        support_role_id = config.get(
            "support_role_id"
        )

        if support_role_id:
            support_role = guild.get_role(
                int(support_role_id)
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                attach_files=True,
                embed_links=True
            )
        }

        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )

        if guild.me:
            overwrites[guild.me] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_channels=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )

        parent = None

        parent_id = config.get(
            "ticket_category_id"
        )

        if parent_id:
            parent = guild.get_channel(
                int(parent_id)
            )

        channel_name = make_ticket_name(
            config.get(
                "naming",
                "ticket-{username}"
            ),
            member,
            category_key
        )

        try:
            channel = await guild.create_text_channel(
                channel_name,
                category=parent,
                overwrites=overwrites,
                reason="Air Commander Ticket Creation"
            )
        except Exception as e:
            print(
                f"[Ticket] Channel creation failed: "
                f"{type(e).__name__}: {e}"
            )
            return None

        data = load_data()
        guild_data = ensure_guild(
            data,
            guild.id
        )

        ticket_id = str(channel.id)

        guild_data["tickets"][ticket_id] = {
            "channel_id": channel.id,
            "user_id": member.id,
            "category": category_key,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "closed": False,
            "claimed_by": None,
            "added_users": []
        }

        save_data(data)

        embed = discord.Embed(
            title=(
                f"{category_data.get('emoji', '🎫')} "
                f"{category_data.get('name', 'Support')}"
            ),
            description=(
                f"Welcome {member.mention}! 👋\n\n"
                f"{category_data.get('description', '')}\n\n"
                "Please explain your issue clearly and "
                "a member of the support team will assist you."
            ),
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )

        embed.add_field(
            name="👤 Created By",
            value=member.mention,
            inline=True
        )

        embed.add_field(
            name="🏷️ Category",
            value=category_data.get(
                "name",
                "General Support"
            ),
            inline=True
        )

        embed.set_footer(
            text="Air Commander • Ticket System"
        )

        view = TicketControlView(
            self
        )

        content = member.mention

        if support_role:
            content += f" {support_role.mention}"

        await channel.send(
            content=content,
            embed=embed,
            view=view
        )

        await self.log_event(
            guild,
            guild_data,
            "🎫 Ticket Created",
            (
                f"Ticket: {channel.mention}\n"
                f"User: {member.mention}\n"
                f"Category: {category_data.get('name')}"
            )
        )

        return channel

    # ========================================================
    # LOGGING
    # ========================================================

    async def log_event(
        self,
        guild,
        guild_data,
        title,
        description
    ):

        channel_id = guild_data["config"].get(
            "log_channel_id"
        )

        if not channel_id:
            return

        channel = guild.get_channel(
            int(channel_id)
        )

        if not channel:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x5865F2,
            timestamp=datetime.now(timezone.utc)
        )

        embed.set_footer(
            text="Air Commander • Ticket Logs"
        )

        try:
            await channel.send(
                embed=embed
            )
        except Exception:
            pass

    # ========================================================
    # TRANSCRIPT
    # ========================================================

    async def create_transcript(
        self,
        channel
    ):

        lines = []

        try:
            async for message in channel.history(
                limit=None,
                oldest_first=True
            ):
                timestamp = message.created_at.strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

                content = message.content or ""

                if message.attachments:
                    attachments = " ".join(
                        a.url
                        for a in message.attachments
                    )
                    content += f" [Attachments: {attachments}]"

                lines.append(
                    f"[{timestamp}] "
                    f"{message.author} ({message.author.id}): "
                    f"{content}"
                )

        except Exception as e:
            lines.append(
                f"Transcript error: {e}"
            )

        return "\n".join(lines)

    # ========================================================
    # TICKET CONTROL VIEW
    # ========================================================

    # ========================================================
    # /ticket setup
    # ========================================================

    @ticket.command(
        name="setup",
        description="Create the basic ticket system configuration."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        save_data(data)

        embed = discord.Embed(
            title="🎫 Ticket System Ready",
            description=(
                "Air Commander Ticket System has been initialized.\n\n"
                "Default category:\n"
                "🎫 **General Support**\n\n"
                "You can now customize categories and send a panel."
            ),
            color=0x5865F2
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # /ticket panel create
    # ========================================================

    @panel.command(
        name="create",
        description="Create or reset the ticket panel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def panel_create(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        guild_data["panel"] = {
            "title": "✈️ Air Commander Support Center",
            "description": (
                "Need help? Open a support ticket below.\n\n"
                "Our support team will assist you as soon as possible.\n\n"
                "Select a category from the menu below."
            ),
            "color": 0x5865F2,
            "footer": "Air Commander • Support System",
            "channel_id": None,
            "message_id": None
        }

        save_data(data)

        await interaction.response.send_message(
            "✅ Ticket panel created/reset successfully."
        )

    # ========================================================
    # /ticket panel edit
    # ========================================================

    @panel.command(
        name="edit",
        description="Edit the ticket panel."
    )
    @app_commands.describe(
        title="Panel title",
        description="Panel description",
        color="Hex color, example: #5865F2"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def panel_edit(
        self,
        interaction: discord.Interaction,
        title: str = None,
        description: str = None,
        color: str = None
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        panel = guild_data["panel"]

        if title:
            panel["title"] = title

        if description:
            panel["description"] = description

        if color:
            try:
                color = color.replace("#", "")
                panel["color"] = int(
                    color,
                    16
                )
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid color. Example: `#5865F2`"
                )
                return

        save_data(data)

        await interaction.response.send_message(
            "✅ Ticket panel updated."
        )

    # ========================================================
    # /ticket panel send
    # ========================================================

    @panel.command(
        name="send",
        description="Send the ticket panel."
    )
    @app_commands.describe(
        channel="Channel where the panel should be sent."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def panel_send(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        embed = self.panel_embed(
            guild_data
        )

        view = TicketPanelView(
            self
        )

        try:
            message = await channel.send(
                embed=embed,
                view=view
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Failed to send panel: `{e}`"
            )
            return

        guild_data["panel"]["channel_id"] = channel.id
        guild_data["panel"]["message_id"] = message.id

        save_data(data)

        await interaction.response.send_message(
            f"✅ Ticket panel sent to {channel.mention}."
        )

    # ========================================================
    # /ticket panel delete
    # ========================================================

    @panel.command(
        name="delete",
        description="Delete the configured ticket panel."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def panel_delete(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        channel_id = guild_data["panel"].get(
            "channel_id"
        )

        message_id = guild_data["panel"].get(
            "message_id"
        )

        if not channel_id or not message_id:
            await interaction.response.send_message(
                "❌ No saved ticket panel found."
            )
            return

        channel = interaction.guild.get_channel(
            int(channel_id)
        )

        if channel:
            try:
                message = await channel.fetch_message(
                    int(message_id)
                )

                await message.delete()

            except Exception:
                pass

        guild_data["panel"]["channel_id"] = None
        guild_data["panel"]["message_id"] = None

        save_data(data)

        await interaction.response.send_message(
            "🗑️ Ticket panel deleted."
        )

    # ========================================================
    # CATEGORY ADD
    # ========================================================

    @category.command(
        name="add",
        description="Add a ticket dropdown category."
    )
    @app_commands.describe(
        name="Category name",
        emoji="Category emoji",
        description="Category description",
        prefix="Ticket channel prefix"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def category_add(
        self,
        interaction: discord.Interaction,
        name: str,
        emoji: str = "🎫",
        description: str = "Get help from our support team.",
        prefix: str = "ticket"
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        key = re.sub(
            r"[^a-z0-9]+",
            "-",
            name.lower()
        ).strip("-")

        if not key:
            await interaction.response.send_message(
                "❌ Invalid category name."
            )
            return

        if key in guild_data["categories"]:
            await interaction.response.send_message(
                "❌ A category with this name already exists."
            )
            return

        guild_data["categories"][key] = {
            "name": name[:100],
            "emoji": emoji[:10],
            "description": description[:300],
            "prefix": clean_channel_name(prefix)
        }

        save_data(data)

        await interaction.response.send_message(
            f"✅ Added `{name}` to the ticket dropdown."
        )

    # ========================================================
    # CATEGORY EDIT
    # ========================================================

    @category.command(
        name="edit",
        description="Edit a ticket dropdown category."
    )
    @app_commands.describe(
        category_key="Existing category key",
        name="New category name",
        emoji="New emoji",
        description="New description",
        prefix="New channel prefix"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def category_edit(
        self,
        interaction: discord.Interaction,
        category_key: str,
        name: str = None,
        emoji: str = None,
        description: str = None,
        prefix: str = None
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        category_key = category_key.lower()

        if category_key not in guild_data["categories"]:
            await interaction.response.send_message(
                "❌ Category not found."
            )
            return

        category_data = guild_data["categories"][
            category_key
        ]

        if name:
            category_data["name"] = name[:100]

        if emoji:
            category_data["emoji"] = emoji[:10]

        if description:
            category_data["description"] = description[:300]

        if prefix:
            category_data["prefix"] = clean_channel_name(
                prefix
            )

        save_data(data)

        await interaction.response.send_message(
            "✅ Ticket category updated."
        )

    # ========================================================
    # CATEGORY REMOVE
    # ========================================================

    @category.command(
        name="remove",
        description="Remove a ticket dropdown category."
    )
    @app_commands.describe(
        category_key="Category key to remove."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def category_remove(
        self,
        interaction: discord.Interaction,
        category_key: str
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        category_key = category_key.lower()

        if category_key not in guild_data["categories"]:
            await interaction.response.send_message(
                "❌ Category not found."
            )
            return

        del guild_data["categories"][
            category_key
        ]

        save_data(data)

        await interaction.response.send_message(
            f"🗑️ Removed `{category_key}` from the dropdown."
        )

    # ========================================================
    # CATEGORY LIST
    # ========================================================

    @category.command(
        name="list",
        description="List all ticket categories."
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def category_list(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        embed = discord.Embed(
            title="🎫 Ticket Categories",
            color=0x5865F2
        )

        categories = guild_data["categories"]

        if not categories:
            embed.description = (
                "No ticket categories configured."
            )
        else:
            lines = []

            for key, value in categories.items():
                lines.append(
                    f"{value.get('emoji', '🎫')} "
                    f"**{value.get('name', key)}**\n"
                    f"`{key}` • {value.get('description', '')}"
                )

            embed.description = "\n\n".join(
                lines
            )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # /ticket config
    # ========================================================

    @ticket.command(
        name="config",
        description="Configure ticket system settings."
    )
    @app_commands.describe(
        support_role="Support team role",
        log_channel="Ticket log channel",
        ticket_category="Discord category for tickets",
        transcript="Enable transcripts",
        naming="Ticket channel naming template"
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def ticket_config(
        self,
        interaction: discord.Interaction,
        support_role: discord.Role = None,
        log_channel: discord.TextChannel = None,
        ticket_category: discord.CategoryChannel = None,
        transcript: bool = None,
        naming: str = None
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        config = guild_data["config"]

        if support_role:
            config["support_role_id"] = support_role.id

        if log_channel:
            config["log_channel_id"] = log_channel.id

        if ticket_category:
            config["ticket_category_id"] = ticket_category.id

        if transcript is not None:
            config["transcript"] = transcript

        if naming:
            config["naming"] = naming[:80]

        save_data(data)

        embed = discord.Embed(
            title="⚙️ Ticket Configuration",
            color=0x5865F2
        )

        role_text = "Not set"

        if config.get("support_role_id"):
            role = interaction.guild.get_role(
                int(config["support_role_id"])
            )

            if role:
                role_text = role.mention

        log_text = "Not set"

        if config.get("log_channel_id"):
            channel = interaction.guild.get_channel(
                int(config["log_channel_id"])
            )

            if channel:
                log_text = channel.mention

        category_text = "Not set"

        if config.get("ticket_category_id"):
            category = interaction.guild.get_channel(
                int(config["ticket_category_id"])
            )

            if category:
                category_text = category.name

        embed.add_field(
            name="🛡️ Support Role",
            value=role_text,
            inline=True
        )

        embed.add_field(
            name="📋 Log Channel",
            value=log_text,
            inline=True
        )

        embed.add_field(
            name="📂 Ticket Category",
            value=category_text,
            inline=True
        )

        embed.add_field(
            name="📄 Transcript",
            value=str(
                config.get("transcript", True)
            ),
            inline=True
        )

        embed.add_field(
            name="🏷️ Naming",
            value=f"`{config.get('naming')}`",
            inline=True
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # CLOSE
    # ========================================================

    @ticket.command(
        name="close",
        description="Close the current ticket."
    )
    async def ticket_close(
        self,
        interaction: discord.Interaction
    ):

        await self.close_ticket(
            interaction
        )

    # ========================================================
    # REOPEN
    # ========================================================

    @ticket.command(
        name="reopen",
        description="Reopen the current ticket."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def ticket_reopen(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )
            return

        member = interaction.guild.get_member(
            int(ticket["user_id"])
        )

        if member:
            await interaction.channel.set_permissions(
                member,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        ticket["closed"] = False

        save_data(data)

        await interaction.response.send_message(
            "🔓 Ticket reopened."
        )

    # ========================================================
    # CLAIM
    # ========================================================

    @ticket.command(
        name="claim",
        description="Claim the current ticket."
    )
    async def ticket_claim(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )
            return

        if not is_admin(interaction.user):
            support_role_id = guild_data["config"].get(
                "support_role_id"
            )

            if not support_role_id or not any(
                role.id == int(support_role_id)
                for role in interaction.user.roles
            ):
                await interaction.response.send_message(
                    "❌ You are not part of the support team."
                )
                return

        ticket["claimed_by"] = interaction.user.id

        save_data(data)

        await interaction.response.send_message(
            f"🙋 Ticket claimed by {interaction.user.mention}."
        )

    # ========================================================
    # ADD USER
    # ========================================================

    @ticket.command(
        name="add",
        description="Add a user to the current ticket."
    )
    @app_commands.describe(
        user="User to add."
    )
    async def ticket_add(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):

        if not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You need administrator permissions."
            )
            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )
            return

        await interaction.channel.set_permissions(
            user,
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )

        ticket.setdefault(
            "added_users",
            []
        )

        if user.id not in ticket["added_users"]:
            ticket["added_users"].append(
                user.id
            )

        save_data(data)

        await interaction.response.send_message(
            f"👥 Added {user.mention} to the ticket."
        )

    # ========================================================
    # REMOVE USER
    # ========================================================

    @ticket.command(
        name="remove",
        description="Remove a user from the current ticket."
    )
    @app_commands.describe(
        user="User to remove."
    )
    async def ticket_remove(
        self,
        interaction: discord.Interaction,
        user: discord.Member
    ):

        if not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You need administrator permissions."
            )
            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )
            return

        if user.id == ticket.get("user_id"):
            await interaction.response.send_message(
                "❌ You cannot remove the ticket creator."
            )
            return

        await interaction.channel.set_permissions(
            user,
            overwrite=None
        )

        if user.id in ticket.get(
            "added_users",
            []
        ):
            ticket["added_users"].remove(
                user.id
            )

        save_data(data)

        await interaction.response.send_message(
            f"👋 Removed {user.mention} from the ticket."
        )

    # ========================================================
    # RENAME
    # ========================================================

    @ticket.command(
        name="rename",
        description="Rename the current ticket."
    )
    @app_commands.describe(
        name="New channel name."
    )
    async def ticket_rename(
        self,
        interaction: discord.Interaction,
        name: str
    ):

        if not is_admin(interaction.user):
            await interaction.response.send_message(
                "❌ You need administrator permissions."
            )
            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )
            return

        name = clean_channel_name(
            name
        )

        await interaction.channel.edit(
            name=name,
            reason="Air Commander Ticket Rename"
        )

        await interaction.response.send_message(
            f"✏️ Ticket renamed to `{name}`."
        )

    # ========================================================
    # PREFIX GROUP
    # ========================================================

    @commands.group(
        name="ticket",
        invoke_without_command=True
    )
    async def ticket_prefix(
        self,
        ctx
    ):

        embed = discord.Embed(
            title="🎫 Air Commander Ticket System",
            description=(
                "` ,ticket setup `\n"
                "` ,ticket panel create `\n"
                "` ,ticket panel edit `\n"
                "` ,ticket panel send #channel `\n"
                "` ,ticket panel delete `\n\n"
                "` ,ticket category add `\n"
                "` ,ticket category edit `\n"
                "` ,ticket category remove `\n"
                "` ,ticket category list `\n\n"
                "` ,ticket config `\n"
                "` ,ticket close `\n"
                "` ,ticket reopen `\n"
                "` ,ticket claim `\n"
                "` ,ticket add @user `\n"
                "` ,ticket remove @user `\n"
                "` ,ticket rename name `"
            ),
            color=0x5865F2
        )

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # PREFIX SETUP
    # ========================================================

    @ticket_prefix.command(
        name="setup"
    )
    @commands.has_permissions(administrator=True)
    async def prefix_setup(
        self,
        ctx
    ):

        data = load_data()

        ensure_guild(
            data,
            ctx.guild.id
        )

        save_data(data)

        await ctx.send(
            "✅ Ticket system initialized."
        )

    # ========================================================
    # PREFIX CATEGORY ADD
    # ========================================================

    @ticket_prefix.group(
        name="category",
        invoke_without_command=True
    )
    @commands.has_permissions(administrator=True)
    async def prefix_category(
        self,
        ctx
    ):

        await ctx.send(
            "🎫 Use `,ticket category add/edit/remove/list`."
        )

    @prefix_category.command(
        name="add"
    )
    async def prefix_category_add(
        self,
        ctx,
        name: str,
        emoji: str = "🎫",
        *,
        description: str = "Get help from our support team."
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            ctx.guild.id
        )

        key = re.sub(
            r"[^a-z0-9]+",
            "-",
            name.lower()
        ).strip("-")

        if key in guild_data["categories"]:
            await ctx.send(
                "❌ Category already exists."
            )
            return

        guild_data["categories"][key] = {
            "name": name[:100],
            "emoji": emoji[:10],
            "description": description[:300],
            "prefix": "ticket"
        }

        save_data(data)

        await ctx.send(
            f"✅ Added `{name}` to the dropdown."
        )

    # ========================================================
    # PREFIX CATEGORY LIST
    # ========================================================

    @prefix_category.command(
        name="list"
    )
    async def prefix_category_list(
        self,
        ctx
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            ctx.guild.id
        )

        embed = discord.Embed(
            title="🎫 Ticket Categories",
            color=0x5865F2
        )

        lines = []

        for key, value in guild_data["categories"].items():
            lines.append(
                f"{value.get('emoji', '🎫')} "
                f"**{value.get('name', key)}** — `{key}`"
            )

        embed.description = (
            "\n".join(lines)
            if lines
            else "No categories."
        )

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # PREFIX CATEGORY REMOVE
    # ========================================================

    @prefix_category.command(
        name="remove"
    )
    async def prefix_category_remove(
        self,
        ctx,
        category_key: str
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            ctx.guild.id
        )

        category_key = category_key.lower()

        if category_key not in guild_data["categories"]:
            await ctx.send(
                "❌ Category not found."
            )
            return

        del guild_data["categories"][
            category_key
        ]

        save_data(data)

        await ctx.send(
            f"🗑️ Removed `{category_key}`."
        )

    # ========================================================
    # PREFIX CLOSE
    # ========================================================

    @ticket_prefix.command(
        name="close"
    )
    async def prefix_close(
        self,
        ctx
    ):

        await self.close_ticket(
            ctx
        )

    # ========================================================
    # PREFIX CLAIM
    # ========================================================

    @ticket_prefix.command(
        name="claim"
    )
    async def prefix_claim(
        self,
        ctx
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            ctx.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            ctx.channel.id
        )

        if not ticket:
            await ctx.send(
                "❌ This is not a ticket."
            )
            return

        if not is_admin(ctx.author):
            support_role_id = guild_data["config"].get(
                "support_role_id"
            )

            if not support_role_id or not any(
                role.id == int(support_role_id)
                for role in ctx.author.roles
            ):
                await ctx.send(
                    "❌ You are not support staff."
                )
                return

        ticket["claimed_by"] = ctx.author.id

        save_data(data)

        await ctx.send(
            f"🙋 Ticket claimed by {ctx.author.mention}."
        )

    # ========================================================
    # PREFIX RENAME
    # ========================================================

    @ticket_prefix.command(
        name="rename"
    )
    @commands.has_permissions(manage_channels=True)
    async def prefix_rename(
        self,
        ctx,
        *,
        name: str
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            ctx.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            ctx.channel.id
        )

        if not ticket:
            await ctx.send(
                "❌ This is not a ticket."
            )
            return

        name = clean_channel_name(
            name
        )

        await ctx.channel.edit(
            name=name
        )

        await ctx.send(
            f"✏️ Renamed to `{name}`."
        )

    # ========================================================
    # CLOSE ENGINE
    # ========================================================

    async def close_ticket(
        self,
        source
    ):

        if isinstance(
            source,
            discord.Interaction
        ):
            guild = source.guild
            channel = source.channel
            user = source.user

            send = source.response.send_message

        else:
            guild = source.guild
            channel = source.channel
            user = source.author

            async def send(*args, **kwargs):
                return await source.send(
                    *args,
                    **kwargs
                )

        if guild is None:
            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            channel.id
        )

        if not ticket:
            await send(
                "❌ This is not a ticket channel."
            )
            return

        if ticket.get("closed"):
            await send(
                "🔒 This ticket is already closed."
            )
            return

        if not is_admin(user):

            owner_id = int(
                ticket.get("user_id")
            )

            support_role_id = guild_data["config"].get(
                "support_role_id"
            )

            is_support = False

            if support_role_id:
                is_support = any(
                    role.id == int(support_role_id)
                    for role in user.roles
                )

            if user.id != owner_id and not is_support:
                await send(
                    "❌ Only the ticket creator or support team can close this ticket."
                )
                return

        ticket["closed"] = True

        save_data(data)

        transcript_file = None

        if guild_data["config"].get(
            "transcript",
            True
        ):

            transcript = await self.create_transcript(
                channel
            )

            transcript_file = discord.File(
                fp=__import__(
                    "io"
                ).BytesIO(
                    transcript.encode(
                        "utf-8",
                        errors="replace"
                    )
                ),
                filename=f"{channel.name}-transcript.txt"
            )

        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=(
                f"This ticket has been closed by {user.mention}.\n\n"
                "Staff can reopen it if needed."
            ),
            color=0xED4245,
            timestamp=datetime.now(timezone.utc)
        )

        if isinstance(
            source,
            discord.Interaction
        ):
            await source.response.send_message(
                embed=embed,
                file=transcript_file
                if transcript_file
                else discord.utils.MISSING
            )

        else:
            await source.send(
                embed=embed,
                file=transcript_file
                if transcript_file
                else discord.utils.MISSING
            )

        # Remove normal member access
        owner = guild.get_member(
            int(ticket["user_id"])
        )

        if owner:
            try:
                await channel.set_permissions(
                    owner,
                    view_channel=False,
                    send_messages=False
                )
            except Exception:
                pass

        await self.log_event(
            guild,
            guild_data,
            "🔒 Ticket Closed",
            (
                f"Channel: {channel.mention}\n"
                f"Closed by: {user.mention}"
            )
        )

    # ========================================================
    # PREFIX ERROR HANDLER
    # ========================================================

    @ticket_prefix.error
    async def ticket_prefix_error(
        self,
        ctx,
        error
    ):

        if isinstance(
            error,
            commands.MissingPermissions
        ):
            await ctx.send(
                "❌ You don't have permission to use this command."
            )


# ============================================================
# TICKET BUTTON VIEW
# ============================================================

class TicketControlView(discord.ui.View):

    def __init__(self, cog):
        super().__init__(
            timeout=None
        )

        self.cog = cog

    @discord.ui.button(
        label="Close Ticket",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="aircommander:ticket_close"
    )
    async def close_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await self.cog.close_ticket(
            interaction
        )

    @discord.ui.button(
        label="Claim",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="aircommander:ticket_claim"
    )
    async def claim_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        ticket_id, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:
            await interaction.response.send_message(
                "❌ This is not a ticket."
            )
            return

        if not is_admin(interaction.user):

            role_id = guild_data["config"].get(
                "support_role_id"
            )

            if not role_id or not any(
                role.id == int(role_id)
                for role in interaction.user.roles
            ):
                await interaction.response.send_message(
                    "❌ You are not support staff."
                )
                return

        ticket["claimed_by"] = interaction.user.id

        save_data(data)

        await interaction.response.send_message(
            f"🙋 Ticket claimed by {interaction.user.mention}."
        )

    @discord.ui.button(
        label="Add User",
        emoji="👥",
        style=discord.ButtonStyle.secondary,
        custom_id="aircommander:ticket_add"
    )
    async def add_button(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.send_message(
            "👥 Use `/ticket add @user` to add someone."
        )


# ============================================================
# PREFIX PANEL COMMAND GROUP
# ============================================================

async def setup(bot):

    await bot.add_cog(
        TicketSystem(bot)
    )

    print(
        "✅ Air Commander Ticket System loaded."
    )
