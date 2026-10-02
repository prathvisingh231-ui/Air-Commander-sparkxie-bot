from __future__ import annotations

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
# AIR COMMANDER — SNIPE SYSTEM
# ============================================================

_snipes = {}


async def send_snipe(target):
    cid = target.channel.id
    data = _snipes.get(cid)

    if not data:
        msg = "❌ No recently deleted message found in this channel."

        if isinstance(target, discord.Interaction):
            if not target.response.is_done():
                return await target.response.send_message(
                    msg,
                    ephemeral=True
                )

            return await target.followup.send(
                msg,
                ephemeral=True
            )

        return await target.send(msg)

    content = data.get("content") or "[attachment/embed/no text]"

    embed = discord.Embed(
        title="🕵️ Snipe",
        description=content[:4000],
        color=0x5865F2
    )

    author = data.get("author")

    if author:
        try:
            embed.set_author(
                name=author.display_name,
                icon_url=author.display_avatar.url
            )
        except Exception:
            embed.set_author(
                name=str(author)
            )

    embed.add_field(
        name="👤 Author",
        value=author.mention if author else "Unknown",
        inline=True
    )

    embed.set_footer(
        text="Air Commander • Snipe"
    )

    if isinstance(target, discord.Interaction):
        if not target.response.is_done():
            return await target.response.send_message(
                embed=embed
            )

        return await target.followup.send(
            embed=embed
        )

    return await target.send(
        embed=embed
    )


async def snipe_message_delete(message):
    """
    Listener instead of @bot.event so this module
    does not overwrite another on_message_delete listener.
    """

    if not message.guild:
        return

    if not message.author:
        return

    if message.author.bot:
        return

    _snipes[message.channel.id] = {
        "author": message.author,
        "content": message.content,
        "created": message.created_at
    }


# ============================================================
# SNIPE PREFIX COMMAND
# ============================================================

@commands.command(
    name="snipe",
    description="Show the most recently deleted message."
)
async def snipe_prefix(ctx):
    await send_snipe(ctx)


# ============================================================
# SNIPE SLASH COMMAND
# ============================================================

async def snipe_slash(interaction: discord.Interaction):
    await send_snipe(interaction)


# ============================================================
# TICKET SYSTEM DATA
# ============================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

DATA_FILE = DATA_DIR / "tickets.json"


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
        try:
            DATA_FILE.write_text(
                json.dumps({}, indent=4),
                encoding="utf-8"
            )
        except Exception:
            pass

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {}

        return data

    except Exception as e:
        print(
            f"[Ticket] Data load error: "
            f"{type(e).__name__}: {e}"
        )
        return {}


def save_data(data):
    temp_file = DATA_FILE.with_suffix(".tmp")

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

        temp_file.replace(DATA_FILE)

    except Exception as e:
        print(
            f"[Ticket] Data save error: "
            f"{type(e).__name__}: {e}"
        )


def ensure_guild(data, guild_id):
    gid = str(guild_id)

    if gid not in data:
        data[gid] = json.loads(
            json.dumps(
                DEFAULT_GUILD_DATA,
                ensure_ascii=False
            )
        )

    guild_data = data[gid]

    guild_data.setdefault(
        "categories",
        {}
    )

    guild_data.setdefault(
        "panel",
        {}
    )

    guild_data.setdefault(
        "config",
        {}
    )

    guild_data.setdefault(
        "tickets",
        {}
    )

    # --------------------------------------------------------
    # Repair missing panel values
    # --------------------------------------------------------

    default_panel = DEFAULT_GUILD_DATA["panel"]

    for key, value in default_panel.items():
        guild_data["panel"].setdefault(
            key,
            value
        )

    # --------------------------------------------------------
    # Repair missing config values
    # --------------------------------------------------------

    default_config = DEFAULT_GUILD_DATA["config"]

    for key, value in default_config.items():
        guild_data["config"].setdefault(
            key,
            value
        )

    # --------------------------------------------------------
    # Ensure General category exists
    # --------------------------------------------------------

    if not guild_data["categories"]:
        guild_data["categories"] = json.loads(
            json.dumps(
                DEFAULT_GUILD_DATA["categories"],
                ensure_ascii=False
            )
        )

    return guild_data


# ============================================================
# GENERAL HELPERS
# ============================================================

def is_admin(member: discord.Member):
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


def clean_channel_name(name):
    name = str(name or "").lower().strip()

    name = re.sub(
        r"[^a-z0-9\-_ ]+",
        "",
        name
    )

    name = name.replace(
        " ",
        "-"
    )

    name = re.sub(
        r"-+",
        "-",
        name
    )

    if not name:
        name = "ticket"

    return name[:80]


def make_category_key(name):
    key = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(name).lower()
    ).strip("-")

    return key[:50]


def category_name_from_key(key, category_data):
    emoji = category_data.get(
        "emoji",
        "🎫"
    )

    name = category_data.get(
        "name",
        "General Support"
    )

    return f"{emoji} {name}"


def find_category(guild_data, value):
    """
    Find category using:
    - exact key
    - case-insensitive key
    - display name
    """

    if not value:
        return None, None

    value = str(value).strip()

    categories = guild_data.get(
        "categories",
        {}
    )

    # Exact key
    if value in categories:
        return value, categories[value]

    # Case-insensitive key
    lowered = value.lower()

    for key, category_data in categories.items():
        if key.lower() == lowered:
            return key, category_data

    # Display name
    for key, category_data in categories.items():

        category_name = str(
            category_data.get(
                "name",
                ""
            )
        )

        if category_name.lower() == lowered:
            return key, category_data

    return None, None


def make_unique_category_key(guild_data, name):
    base_key = make_category_key(name)

    if not base_key:
        return None

    key = base_key
    counter = 2

    while key in guild_data["categories"]:
        key = f"{base_key}-{counter}"
        counter += 1

    return key


def make_ticket_name(
    template,
    member,
    category_key
):
    username = clean_channel_name(
        member.name
    )

    replacements = {
        "{username}": username,
        "{user}": username,
        "{category}": clean_channel_name(
            category_key
        ),
        "{userid}": str(member.id)
    }

    result = template or "ticket-{username}"

    for key, value in replacements.items():
        result = result.replace(
            key,
            value
        )

    return clean_channel_name(
        result
    )


def find_ticket(
    guild_data,
    channel_id
):
    channel_id = str(channel_id)

    for ticket_id, ticket in guild_data["tickets"].items():

        if str(
            ticket.get("channel_id")
        ) == channel_id:

            return ticket_id, ticket

    return None, None


def get_ticket_by_user(
    guild_data,
    user_id
):
    user_id = str(user_id)

    for ticket_id, ticket in guild_data["tickets"].items():

        if (
            str(ticket.get("user_id")) == user_id
            and ticket.get("closed") is False
        ):
            return ticket_id, ticket

    return None, None


# ============================================================
# TICKET PANEL VIEW
# ============================================================

class TicketPanelView(discord.ui.View):

    def __init__(
        self,
        cog,
        guild_id=None
    ):
        super().__init__(
            timeout=None
        )

        self.cog = cog
        self.guild_id = guild_id

        self.add_item(
            TicketCategorySelect(
                cog,
                guild_id
            )
        )


class TicketCategorySelect(discord.ui.Select):

    def __init__(
        self,
        cog,
        guild_id=None
    ):
        self.cog = cog
        self.guild_id = guild_id

        options = []

        # ----------------------------------------------------
        # Load guild categories
        # ----------------------------------------------------

        try:

            data = load_data()

            if guild_id is not None:

                guild_data = ensure_guild(
                    data,
                    guild_id
                )

                categories = guild_data.get(
                    "categories",
                    {}
                )

            else:
                categories = (
                    DEFAULT_GUILD_DATA[
                        "categories"
                    ]
                )

            # Discord select menu max = 25
            for key, category_data in list(
                categories.items()
            )[:25]:

                label = str(
                    category_data.get(
                        "name",
                        key
                    )
                )[:100]

                description = str(
                    category_data.get(
                        "description",
                        "Open a support ticket."
                    )
                )[:100]

                emoji = category_data.get(
                    "emoji",
                    "🎫"
                )

                try:
                    option = discord.SelectOption(
                        label=label,
                        description=description,
                        emoji=emoji[:10],
                        value=key[:100]
                    )

                except Exception:
                    option = discord.SelectOption(
                        label=label,
                        description=description,
                        value=key[:100]
                    )

                options.append(option)

        except Exception as e:

            print(
                f"[Ticket] Category select error: "
                f"{type(e).__name__}: {e}"
            )

        # ----------------------------------------------------
        # Fallback
        # ----------------------------------------------------

        if not options:

            options.append(
                discord.SelectOption(
                    label="General Support",
                    description="Get general support.",
                    emoji="🎫",
                    value="general"
                )
            )

        super().__init__(
            placeholder="🎫 Select a ticket category...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="aircommander:ticket_category"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):
        await self.cog.handle_category_select(
            interaction,
            self.values[0]
        )


# ============================================================
# MAIN TICKET COG
# ============================================================

class TicketSystem(commands.Cog):

    # ========================================================
    # SLASH GROUPS
    # ========================================================

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

    # --------------------------------------------------------
    # NEW CATEGORY ADD GROUP
    # --------------------------------------------------------

    category_add_group = app_commands.Group(
        name="add",
        description="Add a ticket category.",
        parent=category
    )

    # --------------------------------------------------------
    # NEW CATEGORY DELETE GROUP
    # --------------------------------------------------------

    category_del_group = app_commands.Group(
        name="del",
        description="Delete a ticket category.",
        parent=category
    )

    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

        self._register_persistent_view()

    # ========================================================
    # PERSISTENT VIEWS
    # ========================================================

    def _register_persistent_view(self):

        try:

            self.bot.add_view(
                TicketPanelView(
                    self
                )
            )

            self.bot.add_view(
                TicketControlView(
                    self
                )
            )

        except Exception as e:

            print(
                f"[Ticket] Persistent view error: "
                f"{type(e).__name__}: {e}"
            )

    # ========================================================
    # PANEL EMBED
    # ========================================================

    def panel_embed(
        self,
        guild_data
    ):

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
            timestamp=datetime.now(
                timezone.utc
            )
        )

        embed.set_footer(
            text=panel.get(
                "footer",
                "Air Commander • Support System"
            )
        )

        return embed

    # ========================================================
    # REFRESH SAVED PANEL
    # ========================================================

    async def refresh_panel(
        self,
        guild: discord.Guild
    ):
        """
        Refresh the saved panel so newly added/removed
        categories appear immediately.
        """

        data = load_data()

        guild_data = ensure_guild(
            data,
            guild.id
        )

        panel = guild_data.get(
            "panel",
            {}
        )

        channel_id = panel.get(
            "channel_id"
        )

        message_id = panel.get(
            "message_id"
        )

        if not channel_id or not message_id:
            return False

        channel = guild.get_channel(
            int(channel_id)
        )

        if not channel:
            return False

        try:

            message = await channel.fetch_message(
                int(message_id)
            )

            await message.edit(
                embed=self.panel_embed(
                    guild_data
                ),
                view=TicketPanelView(
                    self,
                    guild.id
                )
            )

            return True

        except Exception as e:

            print(
                f"[Ticket] Panel refresh failed: "
                f"{type(e).__name__}: {e}"
            )

            return False

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

        _, existing_ticket = get_ticket_by_user(
            guild_data,
            interaction.user.id
        )

        if existing_ticket:

            channel = guild.get_channel(
                int(
                    existing_ticket[
                        "channel_id"
                    ]
                )
            )

            if channel:

                await interaction.response.send_message(
                    f"❌ You already have an open ticket: "
                    f"{channel.mention}",
                    ephemeral=False
                )

                return

        await interaction.response.defer(
            ephemeral=False
        )

        category_data = categories[
            category_key
        ]

        channel = await self.create_ticket(
            guild,
            interaction.user,
            category_key,
            category_data,
            guild_data
        )

        if channel is None:

            await interaction.followup.send(
                "❌ I couldn't create the ticket. "
                "Check my permissions.",
                ephemeral=False
            )

            return

        await interaction.followup.send(
            f"🎫 Your ticket has been created: "
            f"{channel.mention}",
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

            try:
                support_role = guild.get_role(
                    int(support_role_id)
                )

            except Exception:
                support_role = None

        overwrites = {
            guild.default_role:
                discord.PermissionOverwrite(
                    view_channel=False
                ),

            member:
                discord.PermissionOverwrite(
                    view_channel=True,
                    send_messages=True,
                    read_message_history=True,
                    attach_files=True,
                    embed_links=True
                )
        }

        if support_role:

            overwrites[
                support_role
            ] = discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True,
                manage_messages=True,
                attach_files=True,
                embed_links=True
            )

        if guild.me:

            overwrites[
                guild.me
            ] = discord.PermissionOverwrite(
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

            try:

                parent = guild.get_channel(
                    int(parent_id)
                )

            except Exception:
                parent = None

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

        ticket_id = str(
            channel.id
        )

        guild_data["tickets"][
            ticket_id
        ] = {
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
            timestamp=datetime.now(
                timezone.utc
            )
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
            content += (
                f" {support_role.mention}"
            )

        try:

            await channel.send(
                content=content,
                embed=embed,
                view=view
            )

        except Exception as e:

            print(
                f"[Ticket] Initial ticket message failed: "
                f"{type(e).__name__}: {e}"
            )

        await self.log_event(
            guild,
            guild_data,
            "🎫 Ticket Created",
            (
                f"Ticket: {channel.mention}\n"
                f"User: {member.mention}\n"
                f"Category: "
                f"{category_data.get('name')}"
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

        channel_id = guild_data[
            "config"
        ].get(
            "log_channel_id"
        )

        if not channel_id:
            return

        try:

            channel = guild.get_channel(
                int(channel_id)
            )

        except Exception:
            channel = None

        if not channel:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=0x5865F2,
            timestamp=datetime.now(
                timezone.utc
            )
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

                timestamp = (
                    message.created_at.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                )

                content = (
                    message.content or ""
                )

                if message.attachments:

                    attachments = " ".join(
                        a.url
                        for a in message.attachments
                    )

                    content += (
                        f" [Attachments: {attachments}]"
                    )

                lines.append(
                    f"[{timestamp}] "
                    f"{message.author} "
                    f"({message.author.id}): "
                    f"{content}"
                )

        except Exception as e:

            lines.append(
                f"Transcript error: {e}"
            )

        return "\n".join(
            lines
        )

    # ========================================================
    # /ticket setup
    # ========================================================

    @ticket.command(
        name="setup",
        description="Create the basic ticket system configuration."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def ticket_setup(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.guild:
            await interaction.response.send_message(
                "❌ This command can only be used in a server."
            )
            return

        data = load_data()

        ensure_guild(
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
                "You can now customize categories "
                "and send a panel."
            ),
            color=0x5865F2
        )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # PANEL CREATE
    # ========================================================

    @panel.command(
        name="create",
        description="Create or reset the ticket panel."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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
    # PANEL EDIT
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
    @app_commands.checks.has_permissions(
        administrator=True
    )
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
            panel["title"] = title[:256]

        if description:
            panel["description"] = description[:4000]

        if color:

            try:

                color_value = color.replace(
                    "#",
                    ""
                ).strip()

                if len(color_value) not in (
                    6,
                    8
                ):
                    raise ValueError

                panel["color"] = int(
                    color_value,
                    16
                )

            except ValueError:

                await interaction.response.send_message(
                    "❌ Invalid color. Example: `#5865F2`"
                )

                return

        save_data(data)

        # Refresh live panel too
        await self.refresh_panel(
            interaction.guild
        )

        await interaction.response.send_message(
            "✅ Ticket panel updated."
        )

    # ========================================================
    # PANEL SEND
    # ========================================================

    @panel.command(
        name="send",
        description="Send the ticket panel."
    )
    @app_commands.describe(
        channel="Channel where the panel should be sent."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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

        # Guild-aware dynamic dropdown
        view = TicketPanelView(
            self,
            interaction.guild.id
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

        guild_data["panel"][
            "channel_id"
        ] = channel.id

        guild_data["panel"][
            "message_id"
        ] = message.id

        save_data(data)

        await interaction.response.send_message(
            f"✅ Ticket panel sent to "
            f"{channel.mention}."
        )

    # ========================================================
    # PANEL DELETE
    # ========================================================

    @panel.command(
        name="delete",
        description="Delete the configured ticket panel."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def panel_delete(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        channel_id = guild_data[
            "panel"
        ].get(
            "channel_id"
        )

        message_id = guild_data[
            "panel"
        ].get(
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

        guild_data["panel"][
            "channel_id"
        ] = None

        guild_data["panel"][
            "message_id"
        ] = None

        save_data(data)

        await interaction.response.send_message(
            "🗑️ Ticket panel deleted."
        )

    # ========================================================
    # CATEGORY ADD PANEL
    #
    # /ticket category add panel
    # ========================================================

    @category_add_group.command(
        name="panel",
        description="Add a category to the ticket panel dropdown."
    )
    @app_commands.describe(
        name="Category name",
        emoji="Category emoji",
        description="Category description",
        prefix="Ticket channel prefix"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def category_add_panel(
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

        name = name.strip()

        if not name:

            await interaction.response.send_message(
                "❌ Category name cannot be empty."
            )

            return

        key = make_category_key(
            name
        )

        if not key:

            await interaction.response.send_message(
                "❌ Invalid category name."
            )

            return

        # ----------------------------------------------------
        # Prevent duplicate key
        # ----------------------------------------------------

        if key in guild_data["categories"]:

            await interaction.response.send_message(
                f"❌ Category `{name}` already exists."
            )

            return

        # ----------------------------------------------------
        # Prevent duplicate display name
        # ----------------------------------------------------

        for existing_key, existing_data in (
            guild_data["categories"].items()
        ):

            if (
                str(
                    existing_data.get(
                        "name",
                        ""
                    )
                ).lower()
                == name.lower()
            ):

                await interaction.response.send_message(
                    f"❌ A category named `{name}` already exists."
                )

                return

        # ----------------------------------------------------
        # Save category
        # ----------------------------------------------------

        guild_data["categories"][key] = {
            "name": name[:100],
            "emoji": (
                emoji.strip()[:10]
                if emoji
                else "🎫"
            ),
            "description": (
                description[:300]
                if description
                else "Get help from our support team."
            ),
            "prefix": clean_channel_name(
                prefix
            )
        }

        save_data(data)

        # ----------------------------------------------------
        # Refresh existing panel
        # ----------------------------------------------------

        panel_refreshed = await self.refresh_panel(
            interaction.guild
        )

        embed = discord.Embed(
            title="✅ Ticket Category Added",
            description=(
                f"**Category:** {emoji} {name}\n"
                f"**Key:** `{key}`\n"
                f"**Prefix:** `{clean_channel_name(prefix)}`\n\n"
                "The category has been added to the ticket system."
            ),
            color=0x57F287
        )

        if panel_refreshed:
            embed.set_footer(
                text="Existing ticket panel refreshed automatically."
            )
        else:
            embed.set_footer(
                text="Send a ticket panel to display this category."
            )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # CATEGORY DELETE PANEL
    #
    # /ticket category del panel
    # ========================================================

    @category_del_group.command(
        name="panel",
        description="Delete a category from the ticket panel."
    )
    @app_commands.describe(
        category="Category key or category name"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
    async def category_del_panel(
        self,
        interaction: discord.Interaction,
        category: str
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        category_key, category_data = find_category(
            guild_data,
            category
        )

        if not category_key:

            await interaction.response.send_message(
                "❌ Category not found.\n"
                "Use `/ticket category list` to see available categories."
            )

            return

        # ----------------------------------------------------
        # Protect default General Support
        # ----------------------------------------------------

        if category_key == "general":

            await interaction.response.send_message(
                "❌ The default `General Support` category "
                "cannot be deleted."
            )

            return

        category_display_name = category_data.get(
            "name",
            category_key
        )

        del guild_data[
            "categories"
        ][
            category_key
        ]

        save_data(data)

        # Refresh existing panel
        panel_refreshed = await self.refresh_panel(
            interaction.guild
        )

        embed = discord.Embed(
            title="🗑️ Ticket Category Deleted",
            description=(
                f"Removed **{category_display_name}** "
                f"(`{category_key}`) from the ticket system."
            ),
            color=0xED4245
        )

        if panel_refreshed:
            embed.set_footer(
                text="Existing ticket panel refreshed automatically."
            )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # CATEGORY EDIT
    #
    # Existing command preserved:
    # /ticket category edit
    # ========================================================

    @category.command(
        name="edit",
        description="Edit a ticket dropdown category."
    )
    @app_commands.describe(
        category_key="Existing category key or category name",
        name="New category name",
        emoji="New emoji",
        description="New description",
        prefix="New channel prefix"
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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

        real_key, category_data = find_category(
            guild_data,
            category_key
        )

        if not real_key:

            await interaction.response.send_message(
                "❌ Category not found."
            )

            return

        if name:

            new_name = name.strip()

            if not new_name:

                await interaction.response.send_message(
                    "❌ Category name cannot be empty."
                )

                return

            # Check duplicate display name
            for key, value in guild_data[
                "categories"
            ].items():

                if key == real_key:
                    continue

                if (
                    str(
                        value.get(
                            "name",
                            ""
                        )
                    ).lower()
                    == new_name.lower()
                ):

                    await interaction.response.send_message(
                        "❌ Another category already uses that name."
                    )

                    return

            category_data["name"] = new_name[:100]

        if emoji:
            category_data["emoji"] = emoji[:10]

        if description:
            category_data["description"] = description[:300]

        if prefix:
            category_data["prefix"] = clean_channel_name(
                prefix
            )

        save_data(data)

        panel_refreshed = await self.refresh_panel(
            interaction.guild
        )

        embed = discord.Embed(
            title="✏️ Ticket Category Updated",
            description=(
                f"**Category:** "
                f"{category_data.get('emoji', '🎫')} "
                f"{category_data.get('name', real_key)}\n"
                f"**Key:** `{real_key}`\n"
                f"**Prefix:** `{category_data.get('prefix', 'ticket')}`"
            ),
            color=0x5865F2
        )

        if panel_refreshed:
            embed.set_footer(
                text="Existing ticket panel refreshed automatically."
            )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # CATEGORY REMOVE
    #
    # Existing command preserved:
    # /ticket category remove
    # ========================================================

    @category.command(
        name="remove",
        description="Remove a ticket dropdown category."
    )
    @app_commands.describe(
        category_key="Category key or category name to remove."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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

        real_key, category_data = find_category(
            guild_data,
            category_key
        )

        if not real_key:

            await interaction.response.send_message(
                "❌ Category not found."
            )

            return

        if real_key == "general":

            await interaction.response.send_message(
                "❌ The default `General Support` category "
                "cannot be removed."
            )

            return

        category_name = category_data.get(
            "name",
            real_key
        )

        del guild_data[
            "categories"
        ][
            real_key
        ]

        save_data(data)

        await self.refresh_panel(
            interaction.guild
        )

        await interaction.response.send_message(
            f"🗑️ Removed `{category_name}` "
            f"(`{real_key}`) from the dropdown."
        )

    # ========================================================
    # CATEGORY LIST
    # ========================================================

    @category.command(
        name="list",
        description="List all ticket categories."
    )
    @app_commands.checks.has_permissions(
        administrator=True
    )
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

        categories = guild_data[
            "categories"
        ]

        if not categories:

            embed.description = (
                "No ticket categories configured."
            )

        else:

            lines = []

            for index, (
                key,
                value
            ) in enumerate(
                categories.items()
            ):

                if index >= 25:
                    break

                lines.append(
                    f"{value.get('emoji', '🎫')} "
                    f"**{value.get('name', key)}**\n"
                    f"Key: `{key}`\n"
                    f"Prefix: `{value.get('prefix', 'ticket')}`\n"
                    f"{value.get('description', '')}"
                )

            embed.description = (
                "\n\n".join(
                    lines
                )
            )

            if len(categories) > 25:

                embed.set_footer(
                    text=(
                        f"Showing first 25 of "
                        f"{len(categories)} categories. "
                        "Discord dropdowns support max 25 options."
                    )
                )

        await interaction.response.send_message(
            embed=embed
        )

    # ========================================================
    # CONFIG
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
    @app_commands.checks.has_permissions(
        administrator=True
    )
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
                int(
                    config[
                        "support_role_id"
                    ]
                )
            )

            if role:
                role_text = role.mention

        log_text = "Not set"

        if config.get("log_channel_id"):

            channel = interaction.guild.get_channel(
                int(
                    config[
                        "log_channel_id"
                    ]
                )
            )

            if channel:
                log_text = channel.mention

        category_text = "Not set"

        if config.get("ticket_category_id"):

            category = interaction.guild.get_channel(
                int(
                    config[
                        "ticket_category_id"
                    ]
                )
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
                config.get(
                    "transcript",
                    True
                )
            ),
            inline=True
        )

        embed.add_field(
            name="🏷️ Naming",
            value=(
                f"`{config.get('naming')}`"
            ),
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
    @app_commands.checks.has_permissions(
        manage_channels=True
    )
    async def ticket_reopen(
        self,
        interaction: discord.Interaction
    ):

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        _, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )

            return

        member = interaction.guild.get_member(
            int(
                ticket["user_id"]
            )
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

        _, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )

            return

        if not is_admin(
            interaction.user
        ):

            support_role_id = guild_data[
                "config"
            ].get(
                "support_role_id"
            )

            if (
                not support_role_id
                or not any(
                    role.id == int(
                        support_role_id
                    )
                    for role in interaction.user.roles
                )
            ):

                await interaction.response.send_message(
                    "❌ You are not part of the support team."
                )

                return

        ticket[
            "claimed_by"
        ] = interaction.user.id

        save_data(data)

        await interaction.response.send_message(
            f"🙋 Ticket claimed by "
            f"{interaction.user.mention}."
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

        if not is_admin(
            interaction.user
        ):

            await interaction.response.send_message(
                "❌ You need administrator permissions."
            )

            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        _, ticket = find_ticket(
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

        if user.id not in ticket[
            "added_users"
        ]:

            ticket[
                "added_users"
            ].append(
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

        if not is_admin(
            interaction.user
        ):

            await interaction.response.send_message(
                "❌ You need administrator permissions."
            )

            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        _, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "❌ This is not a ticket channel."
            )

            return

        if user.id == ticket.get(
            "user_id"
        ):

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

            ticket[
                "added_users"
            ].remove(
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

        if not is_admin(
            interaction.user
        ):

            await interaction.response.send_message(
                "❌ You need administrator permissions."
            )

            return

        data = load_data()

        guild_data = ensure_guild(
            data,
            interaction.guild.id
        )

        _, ticket = find_ticket(
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
    # PREFIX TICKET GROUP
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
                "`,ticket setup`\n"
                "`,ticket panel create`\n"
                "`,ticket panel edit`\n"
                "`,ticket panel send #channel`\n"
                "`,ticket panel delete`\n\n"

                "`,ticket category add <name> <emoji>`\n"
                "`,ticket category list`\n"
                "`,ticket category remove <key>`\n\n"

                "`,ticket config`\n"
                "`,ticket close`\n"
                "`,ticket reopen`\n"
                "`,ticket claim`\n"
                "`,ticket add @user`\n"
                "`,ticket remove @user`\n"
                "`,ticket rename name`"
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
    @commands.has_permissions(
        administrator=True
    )
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
    # PREFIX CATEGORY GROUP
    # ========================================================

    @ticket_prefix.group(
        name="category",
        invoke_without_command=True
    )
    @commands.has_permissions(
        administrator=True
    )
    async def prefix_category(
        self,
        ctx
    ):

        await ctx.send(
            "🎫 Use `,ticket category "
            "add/edit/remove/list`."
        )

    # ========================================================
    # PREFIX CATEGORY ADD
    #
    # Old prefix command preserved
    # ========================================================

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

        name = name.strip()

        key = make_category_key(
            name
        )

        if not key:

            await ctx.send(
                "❌ Invalid category name."
            )

            return

        if key in guild_data[
            "categories"
        ]:

            await ctx.send(
                "❌ Category already exists."
            )

            return

        guild_data[
            "categories"
        ][key] = {
            "name": name[:100],
            "emoji": emoji[:10],
            "description": description[:300],
            "prefix": "ticket"
        }

        save_data(data)

        await self.refresh_panel(
            ctx.guild
        )

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

        for index, (
            key,
            value
        ) in enumerate(
            guild_data[
                "categories"
            ].items()
        ):

            if index >= 25:
                break

            lines.append(
                f"{value.get('emoji', '🎫')} "
                f"**{value.get('name', key)}** — "
                f"`{key}`"
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

        real_key, category_data = find_category(
            guild_data,
            category_key
        )

        if not real_key:

            await ctx.send(
                "❌ Category not found."
            )

            return

        if real_key == "general":

            await ctx.send(
                "❌ The default General Support "
                "category cannot be removed."
            )

            return

        del guild_data[
            "categories"
        ][
            real_key
        ]

        save_data(data)

        await self.refresh_panel(
            ctx.guild
        )

        await ctx.send(
            f"🗑️ Removed `{real_key}`."
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

        _, ticket = find_ticket(
            guild_data,
            ctx.channel.id
        )

        if not ticket:

            await ctx.send(
                "❌ This is not a ticket."
            )

            return

        if not is_admin(
            ctx.author
        ):

            support_role_id = guild_data[
                "config"
            ].get(
                "support_role_id"
            )

            if (
                not support_role_id
                or not any(
                    role.id == int(
                        support_role_id
                    )
                    for role in ctx.author.roles
                )
            ):

                await ctx.send(
                    "❌ You are not support staff."
                )

                return

        ticket[
            "claimed_by"
        ] = ctx.author.id

        save_data(data)

        await ctx.send(
            f"🙋 Ticket claimed by "
            f"{ctx.author.mention}."
        )

    # ========================================================
    # PREFIX RENAME
    # ========================================================

    @ticket_prefix.command(
        name="rename"
    )
    @commands.has_permissions(
        manage_channels=True
    )
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

        _, ticket = find_ticket(
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

            async def send(
                *args,
                **kwargs
            ):

                if not source.response.is_done():

                    return await source.response.send_message(
                        *args,
                        **kwargs
                    )

                return await source.followup.send(
                    *args,
                    **kwargs
                )

        else:

            guild = source.guild
            channel = source.channel
            user = source.author

            async def send(
                *args,
                **kwargs
            ):

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

        _, ticket = find_ticket(
            guild_data,
            channel.id
        )

        if not ticket:

            await send(
                "❌ This is not a ticket channel."
            )

            return

        if ticket.get(
            "closed"
        ):

            await send(
                "🔒 This ticket is already closed."
            )

            return

        if not is_admin(
            user
        ):

            owner_id = int(
                ticket.get(
                    "user_id"
                )
            )

            support_role_id = guild_data[
                "config"
            ].get(
                "support_role_id"
            )

            is_support = False

            if support_role_id:

                is_support = any(
                    role.id == int(
                        support_role_id
                    )
                    for role in user.roles
                )

            if (
                user.id != owner_id
                and not is_support
            ):

                await send(
                    "❌ Only the ticket creator or "
                    "support team can close this ticket."
                )

                return

        ticket[
            "closed"
        ] = True

        save_data(data)

        transcript_file = None

        if guild_data[
            "config"
        ].get(
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
                filename=(
                    f"{channel.name}-transcript.txt"
                )
            )

        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=(
                f"This ticket has been closed by "
                f"{user.mention}.\n\n"
                "Staff can reopen it if needed."
            ),
            color=0xED4245,
            timestamp=datetime.now(
                timezone.utc
            )
        )

        if transcript_file:

            await send(
                embed=embed,
                file=transcript_file
            )

        else:

            await send(
                embed=embed
            )

        owner = guild.get_member(
            int(
                ticket[
                    "user_id"
                ]
            )
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
    # PREFIX ERROR
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
                "❌ You don't have permission to use "
                "this command."
            )


# ============================================================
# TICKET CONTROL VIEW
# ============================================================

class TicketControlView(
    discord.ui.View
):

    def __init__(
        self,
        cog
    ):

        super().__init__(
            timeout=None
        )

        self.cog = cog

    # ========================================================
    # CLOSE BUTTON
    # ========================================================

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

    # ========================================================
    # CLAIM BUTTON
    # ========================================================

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

        _, ticket = find_ticket(
            guild_data,
            interaction.channel.id
        )

        if not ticket:

            await interaction.response.send_message(
                "❌ This is not a ticket."
            )

            return

        if not is_admin(
            interaction.user
        ):

            role_id = guild_data[
                "config"
            ].get(
                "support_role_id"
            )

            if (
                not role_id
                or not any(
                    role.id == int(
                        role_id
                    )
                    for role in interaction.user.roles
                )
            ):

                await interaction.response.send_message(
                    "❌ You are not support staff."
                )

                return

        ticket[
            "claimed_by"
        ] = interaction.user.id

        save_data(data)

        await interaction.response.send_message(
            f"🙋 Ticket claimed by "
            f"{interaction.user.mention}."
        )

    # ========================================================
    # ADD USER BUTTON
    # ========================================================

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
            "👥 Use `/ticket add @user` "
            "to add someone."
        )


# ============================================================
# ONE AND ONLY SETUP
# ============================================================

async def setup(bot):

    # ========================================================
    # SNIPE
    # ========================================================

    if bot.get_command(
        "snipe"
    ) is None:

        bot.add_command(
            snipe_prefix
        )

    if bot.tree.get_command(
        "snipe"
    ) is None:

        bot.tree.add_command(
            app_commands.Command(
                name="snipe",
                description=(
                    "Show the most recently "
                    "deleted message in this channel"
                ),
                callback=snipe_slash
            )
        )

    # --------------------------------------------------------
    # Prevent duplicate listener registration
    # --------------------------------------------------------

    existing_listeners = getattr(
        bot,
        "_air_snipe_listener_loaded",
        False
    )

    if not existing_listeners:

        bot.add_listener(
            snipe_message_delete,
            "on_message_delete"
        )

        bot._air_snipe_listener_loaded = True

    # ========================================================
    # TICKET
    # ========================================================

    if bot.get_cog(
        "TicketSystem"
    ) is None:

        await bot.add_cog(
            TicketSystem(bot)
        )

    print(
        "✅ Air Commander Ticket + Snipe System loaded."
    )
