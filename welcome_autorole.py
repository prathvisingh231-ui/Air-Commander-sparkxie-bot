# welcome.py
# Air Commander - Configurable Welcome System
#
# Prefix examples:
# ,welcome embed create main
# ,welcome embed edit main
# ,welcome enable main #welcome
# ,welcome message set Welcome {user}! {embed}
# ,welcome test
#
# Slash examples:
# /welcome embed create name:main
# /welcome enable name:main channel:#welcome
# /welcome test name:main channel:#welcome

import json
import os
import re
from copy import deepcopy

import discord
from discord.ext import commands
from discord import app_commands


# ============================================================
# CONFIG
# ============================================================

DATA_FILE = "welcome_config.json"

DEFAULT_COLOR = 0x5865F2

IMAGE_OPTIONS = {
    "member": "Member Avatar",
    "server": "Server Icon",
    "custom": "Custom URL",
    "none": "None",
}


# ============================================================
# DATABASE
# ============================================================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def save_data(data):
    temp_file = DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    os.replace(temp_file, DATA_FILE)


DATA = load_data()


def guild_data(guild_id: int):
    gid = str(guild_id)

    if gid not in DATA:
        DATA[gid] = {
            "channel_id": None,
            "message": "",
            "active_embed": None,
            "embeds": {}
        }

    DATA[gid].setdefault("channel_id", None)
    DATA[gid].setdefault("message", "")
    DATA[gid].setdefault("active_embed", None)
    DATA[gid].setdefault("embeds", {})

    return DATA[gid]


# ============================================================
# VARIABLES
# ============================================================

def replace_variables(text: str, member: discord.Member):
    if not text:
        return ""

    guild = member.guild

    replacements = {
        "{user}": member.mention,
        "{username}": member.name,
        "{displayname}": member.display_name,
        "{server}": guild.name,
        "{membercount}": str(guild.member_count or len(guild.members)),
        "{user_id}": str(member.id),
        "{server_id}": str(guild.id),
    }

    for key, value in replacements.items():
        text = text.replace(key, value)

    return text


def replace_test_variables(text: str, member: discord.Member):
    return replace_variables(text, member)


# ============================================================
# IMAGE HELPERS
# ============================================================

def get_member_avatar(member: discord.Member):
    return member.display_avatar.url


def get_server_icon(guild: discord.Guild):
    if guild.icon:
        return guild.icon.url

    return None


def apply_image(embed: discord.Embed, mode: str, custom_url: str, member):
    mode = (mode or "none").lower()

    if mode == "member":
        embed.set_image(url=get_member_avatar(member))

    elif mode == "server":
        url = get_server_icon(member.guild)

        if url:
            embed.set_image(url=url)

    elif mode == "custom":
        if custom_url:
            embed.set_image(url=custom_url)


def apply_thumbnail(embed: discord.Embed, mode: str, custom_url: str, member):
    mode = (mode or "none").lower()

    if mode == "member":
        embed.set_thumbnail(url=get_member_avatar(member))

    elif mode == "server":
        url = get_server_icon(member.guild)

        if url:
            embed.set_thumbnail(url=url)

    elif mode == "custom":
        if custom_url:
            embed.set_thumbnail(url=custom_url)


# ============================================================
# EMBED BUILDER
# ============================================================

def build_welcome_embed(template, member: discord.Member):
    title = replace_variables(template.get("title", ""), member)
    description = replace_variables(template.get("description", ""), member)
    footer = replace_variables(template.get("footer", ""), member)
    author = replace_variables(template.get("author", ""), member)

    color = template.get("color", DEFAULT_COLOR)

    try:
        color = int(color)
    except (ValueError, TypeError):
        color = DEFAULT_COLOR

    embed = discord.Embed(
        title=title or None,
        description=description or None,
        color=color
    )

    if author:
        embed.set_author(name=author)

    if footer:
        embed.set_footer(text=footer)

    apply_image(
        embed,
        template.get("image_mode", "none"),
        template.get("image_url", ""),
        member
    )

    apply_thumbnail(
        embed,
        template.get("thumbnail_mode", "none"),
        template.get("thumbnail_url", ""),
        member
    )

    return embed


# ============================================================
# TEMPLATE
# ============================================================

def default_template():
    return {
        "title": "Welcome {user}! 👋",
        "description": (
            "Hey {user}, welcome to **{server}**!\n\n"
            "You are our **{membercount}th member.**"
        ),
        "author": "",
        "footer": "Enjoy your stay • {server}",
        "color": DEFAULT_COLOR,

        "image_mode": "server",
        "image_url": "",

        "thumbnail_mode": "member",
        "thumbnail_url": "",
    }


# ============================================================
# UI - EDITOR
# ============================================================

class TextModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, template_name, field, title, label, current):
        super().__init__(title=title)

        self.cog = cog
        self.guild_id = guild_id
        self.template_name = template_name
        self.field = field

        self.value_input = discord.ui.TextInput(
            label=label,
            default=current[:4000] if current else "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000
        )

        self.add_item(self.value_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = guild_data(self.guild_id)

        template = data["embeds"].get(self.template_name)

        if not template:
            await interaction.response.send_message(
                "❌ That embed template no longer exists.",
                ephemeral=True
            )
            return

        template[self.field] = self.value_input.value

        save_data(DATA)

        await interaction.response.edit_message(
            content=f"✅ `{self.field}` updated.",
            view=EmbedEditorView(
                self.cog,
                self.guild_id,
                self.template_name
            )
        )


class ColorModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, template_name, current):
        super().__init__(title="Edit Embed Color")

        self.cog = cog
        self.guild_id = guild_id
        self.template_name = template_name

        self.color_input = discord.ui.TextInput(
            label="Hex Color",
            placeholder="#5865F2",
            default=f"#{current:06X}",
            required=True,
            max_length=7
        )

        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        value = self.color_input.value.strip().replace("#", "")

        try:
            color = int(value, 16)

            if not 0 <= color <= 0xFFFFFF:
                raise ValueError

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid color. Example: `#5865F2`",
                ephemeral=True
            )
            return

        data = guild_data(self.guild_id)
        template = data["embeds"].get(self.template_name)

        if not template:
            await interaction.response.send_message(
                "❌ Template not found.",
                ephemeral=True
            )
            return

        template["color"] = color
        save_data(DATA)

        await interaction.response.edit_message(
            content="✅ Color updated.",
            view=EmbedEditorView(
                self.cog,
                self.guild_id,
                self.template_name
            )
        )


class ImageModal(discord.ui.Modal):
    def __init__(self, cog, guild_id, template_name, field, title):
        super().__init__(title=title)

        self.cog = cog
        self.guild_id = guild_id
        self.template_name = template_name
        self.field = field

        self.url_input = discord.ui.TextInput(
            label="Custom Image URL",
            placeholder="https://example.com/image.png",
            required=True,
            max_length=1000
        )

        self.add_item(self.url_input)

    async def on_submit(self, interaction: discord.Interaction):
        data = guild_data(self.guild_id)
        template = data["embeds"].get(self.template_name)

        if not template:
            await interaction.response.send_message(
                "❌ Template not found.",
                ephemeral=True
            )
            return

        template[self.field + "_mode"] = "custom"
        template[self.field + "_url"] = self.url_input.value.strip()

        save_data(DATA)

        await interaction.response.edit_message(
            content="✅ Custom image saved.",
            view=EmbedEditorView(
                self.cog,
                self.guild_id,
                self.template_name
            )
        )


class ImageSelect(discord.ui.Select):
    def __init__(self, cog, guild_id, template_name, field):
        self.cog = cog
        self.guild_id = guild_id
        self.template_name = template_name
        self.field = field

        options = [
            discord.SelectOption(
                label="Member Avatar",
                value="member",
                emoji="👤"
            ),
            discord.SelectOption(
                label="Server Icon",
                value="server",
                emoji="🏠"
            ),
            discord.SelectOption(
                label="Custom URL",
                value="custom",
                emoji="🔗"
            ),
            discord.SelectOption(
                label="None",
                value="none",
                emoji="❌"
            ),
        ]

        super().__init__(
            placeholder="Choose image type...",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]

        data = guild_data(self.guild_id)
        template = data["embeds"].get(self.template_name)

        if not template:
            await interaction.response.send_message(
                "❌ Template not found.",
                ephemeral=True
            )
            return

        template[f"{self.field}_mode"] = value

        if value == "custom":
            await interaction.response.send_modal(
                ImageModal(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    self.field,
                    "Custom Image URL"
                )
            )
            return

        template[f"{self.field}_url"] = ""

        save_data(DATA)

        await interaction.response.edit_message(
            content=f"✅ {self.field.title()} set to **{IMAGE_OPTIONS[value]}**.",
            view=EmbedEditorView(
                self.cog,
                self.guild_id,
                self.template_name
            )
        )


class ImageView(discord.ui.View):
    def __init__(self, cog, guild_id, template_name, field):
        super().__init__(timeout=120)

        self.add_item(
            ImageSelect(
                cog,
                guild_id,
                template_name,
                field
            )
        )


# ============================================================
# EDITOR VIEW
# ============================================================

class EmbedEditorView(discord.ui.View):
    def __init__(self, cog, guild_id, template_name):
        super().__init__(timeout=300)

        self.cog = cog
        self.guild_id = guild_id
        self.template_name = template_name

        self.add_item(self.title_button())
        self.add_item(self.description_button())
        self.add_item(self.author_button())
        self.add_item(self.footer_button())
        self.add_item(self.image_button())
        self.add_item(self.thumbnail_button())
        self.add_item(self.color_button())
        self.add_item(self.preview_button())
        self.add_item(self.save_button())

    def template(self):
        return guild_data(self.guild_id)["embeds"].get(
            self.template_name
        )

    def title_button(self):
        button = discord.ui.Button(
            label="Title",
            emoji="📝",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            template = self.template()

            if not template:
                await interaction.response.send_message(
                    "❌ Template not found.",
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(
                TextModal(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    "title",
                    "Edit Title",
                    "Title",
                    template.get("title", "")
                )
            )

        button.callback = callback
        return button

    def description_button(self):
        button = discord.ui.Button(
            label="Description",
            emoji="📄",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            template = self.template()

            await interaction.response.send_modal(
                TextModal(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    "description",
                    "Edit Description",
                    "Description",
                    template.get("description", "")
                )
            )

        button.callback = callback
        return button

    def author_button(self):
        button = discord.ui.Button(
            label="Author",
            emoji="👤",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            template = self.template()

            await interaction.response.send_modal(
                TextModal(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    "author",
                    "Edit Author",
                    "Author",
                    template.get("author", "")
                )
            )

        button.callback = callback
        return button

    def footer_button(self):
        button = discord.ui.Button(
            label="Footer",
            emoji="🔻",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            template = self.template()

            await interaction.response.send_modal(
                TextModal(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    "footer",
                    "Edit Footer",
                    "Footer",
                    template.get("footer", "")
                )
            )

        button.callback = callback
        return button

    def image_button(self):
        button = discord.ui.Button(
            label="Image",
            emoji="🖼️",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            await interaction.response.send_message(
                "Choose what the main image should use:",
                view=ImageView(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    "image"
                ),
                ephemeral=True
            )

        button.callback = callback
        return button

    def thumbnail_button(self):
        button = discord.ui.Button(
            label="Thumbnail",
            emoji="🔲",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            await interaction.response.send_message(
                "Choose what the thumbnail should use:",
                view=ImageView(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    "thumbnail"
                ),
                ephemeral=True
            )

        button.callback = callback
        return button

    def color_button(self):
        button = discord.ui.Button(
            label="Color",
            emoji="🎨",
            style=discord.ButtonStyle.secondary
        )

        async def callback(interaction):
            template = self.template()

            await interaction.response.send_modal(
                ColorModal(
                    self.cog,
                    self.guild_id,
                    self.template_name,
                    template.get("color", DEFAULT_COLOR)
                )
            )

        button.callback = callback
        return button

    def preview_button(self):
        button = discord.ui.Button(
            label="Preview",
            emoji="👁️",
            style=discord.ButtonStyle.primary
        )

        async def callback(interaction):
            template = self.template()

            if not template:
                await interaction.response.send_message(
                    "❌ Template not found.",
                    ephemeral=True
                )
                return

            embed = build_welcome_embed(
                template,
                interaction.user
            )

            data = guild_data(self.guild_id)
            message = replace_variables(
                data.get("message", ""),
                interaction.user
            )

            message = message.replace(
                "{embed}",
                ""
            ).strip()

            await interaction.response.send_message(
                content=message or None,
                embed=embed,
                ephemeral=True
            )

        button.callback = callback
        return button

    def save_button(self):
        button = discord.ui.Button(
            label="Save",
            emoji="💾",
            style=discord.ButtonStyle.success
        )

        async def callback(interaction):
            save_data(DATA)

            await interaction.response.send_message(
                f"✅ Welcome embed `{self.template_name}` saved.",
                ephemeral=True
            )

        button.callback = callback
        return button


# ============================================================
# COG
# ============================================================

class Welcome(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========================================================
    # JOIN EVENT
    # ========================================================

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        data = guild_data(member.guild.id)

        channel_id = data.get("channel_id")
        active_name = data.get("active_embed")

        if not channel_id:
            return

        if not active_name:
            return

        template = data["embeds"].get(active_name)

        if not template:
            return

        channel = member.guild.get_channel(channel_id)

        if not channel:
            return

        message = data.get("message", "")

        message = replace_variables(
            message,
            member
        )

        # {embed} is only a marker.
        # The actual Discord embed is sent separately.
        message = message.replace("{embed}", "").strip()

        embed = build_welcome_embed(
            template,
            member
        )

        try:
            await channel.send(
                content=message or None,
                embed=embed
            )
        except discord.Forbidden:
            pass
        except discord.HTTPException:
            pass

    # ========================================================
    # PERMISSION CHECK
    # ========================================================

    async def has_permission(self, interaction):
        if not interaction.guild:
            return False

        member = interaction.user

        return (
            member.guild_permissions.manage_guild
            or member.guild_permissions.administrator
        )

    # ========================================================
    # PREFIX GROUP
    # ========================================================

    @commands.group(
        name="welcome",
        invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome(self, ctx):
        await ctx.send(
            "👋 **Welcome System**\n\n"
            "`,welcome embed create <name>`\n"
            "`,welcome embed edit <name>`\n"
            "`,welcome embed delete <name>`\n"
            "`,welcome embed list`\n\n"
            "`,welcome enable <name> #channel`\n"
            "`,welcome disable`\n"
            "`,welcome channel set #channel`\n"
            "`,welcome message set <message>`\n"
            "`,welcome message clear`\n"
            "`,welcome test [name] [#channel]`"
        )

    # ========================================================
    # PREFIX EMBED GROUP
    # ========================================================

    @welcome.group(
        name="embed",
        invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def welcome_embed(self, ctx):
        await ctx.send(
            "Use:\n"
            "`,welcome embed create <name>`\n"
            "`,welcome embed edit <name>`\n"
            "`,welcome embed delete <name>`\n"
            "`,welcome embed list`"
        )

    @welcome_embed.command(name="create")
    async def embed_create_prefix(self, ctx, name: str):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        if name in data["embeds"]:
            await ctx.send(
                f"❌ Embed `{name}` already exists."
            )
            return

        data["embeds"][name] = default_template()

        save_data(DATA)

        await ctx.send(
            f"✅ Welcome embed `{name}` created.\n"
            f"Use `,welcome embed edit {name}` to configure it."
        )

    @welcome_embed.command(name="edit")
    async def embed_edit_prefix(self, ctx, name: str):
        data = guild_data(ctx.guild.id)
        name = name.lower()

        if name not in data["embeds"]:
            await ctx.send(
                f"❌ Embed `{name}` does not exist."
            )
            return

        await ctx.send(
            f"✏️ **Edit Welcome Embed: `{name}`**",
            view=EmbedEditorView(
                self,
                ctx.guild.id,
                name
            )
        )

    @welcome_embed.command(name="delete")
    async def embed_delete_prefix(self, ctx, name: str):
        data = guild_data(ctx.guild.id)
        name = name.lower()

        if name not in data["embeds"]:
            await ctx.send(
                f"❌ Embed `{name}` does not exist."
            )
            return

        del data["embeds"][name]

        if data.get("active_embed") == name:
            data["active_embed"] = None

        save_data(DATA)

        await ctx.send(
            f"🗑️ Welcome embed `{name}` deleted."
        )

    @welcome_embed.command(name="list")
    async def embed_list_prefix(self, ctx):
        data = guild_data(ctx.guild.id)

        embeds = data["embeds"]

        if not embeds:
            await ctx.send(
                "📭 No welcome embeds created."
            )
            return

        active = data.get("active_embed")

        lines = []

        for name in embeds:
            marker = " 🟢 ACTIVE" if name == active else ""
            lines.append(f"• `{name}`{marker}")

        await ctx.send(
            "📋 **Welcome Embeds**\n\n" +
            "\n".join(lines)
        )

    # ========================================================
    # ENABLE
    # ========================================================

    @welcome.command(name="enable")
    async def enable_prefix(
        self,
        ctx,
        name: str,
        channel: discord.TextChannel = None
    ):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        if name not in data["embeds"]:
            await ctx.send(
                f"❌ Embed `{name}` does not exist."
            )
            return

        if channel is None:
            channel = ctx.channel

        data["active_embed"] = name
        data["channel_id"] = channel.id

        save_data(DATA)

        await ctx.send(
            f"🟢 Welcome system enabled.\n"
            f"**Embed:** `{name}`\n"
            f"**Channel:** {channel.mention}"
        )

    # ========================================================
    # DISABLE
    # ========================================================

    @welcome.command(name="disable")
    async def disable_prefix(self, ctx):
        data = guild_data(ctx.guild.id)

        data["active_embed"] = None

        save_data(DATA)

        await ctx.send(
            "🔴 Welcome system disabled."
        )

    # ========================================================
    # CHANNEL
    # ========================================================

    @welcome.group(
        name="channel",
        invoke_without_command=True
    )
    async def welcome_channel(self, ctx):
        await ctx.send(
            "Use `,welcome channel set #channel`"
        )

    @welcome_channel.command(name="set")
    async def channel_set_prefix(
        self,
        ctx,
        channel: discord.TextChannel
    ):
        data = guild_data(ctx.guild.id)

        data["channel_id"] = channel.id

        save_data(DATA)

        await ctx.send(
            f"📍 Welcome channel set to {channel.mention}"
        )

    @welcome_channel.command(name="view")
    async def channel_view_prefix(self, ctx):
        data = guild_data(ctx.guild.id)

        channel_id = data.get("channel_id")

        if not channel_id:
            await ctx.send(
                "❌ Welcome channel is not configured."
            )
            return

        channel = ctx.guild.get_channel(channel_id)

        if not channel:
            await ctx.send(
                "⚠️ Configured channel no longer exists."
            )
            return

        await ctx.send(
            f"📍 Welcome channel: {channel.mention}"
        )

    # ========================================================
    # MESSAGE
    # ========================================================

    @welcome.group(
        name="message",
        invoke_without_command=True
    )
    async def welcome_message(self, ctx):
        await ctx.send(
            "Use:\n"
            "`,welcome message set <message>`\n"
            "`,welcome message clear`"
        )

    @welcome_message.command(name="set")
    async def message_set_prefix(self, ctx, *, message: str):
        data = guild_data(ctx.guild.id)

        if len(message) > 2000:
            await ctx.send(
                "❌ Welcome message cannot exceed 2000 characters."
            )
            return

        data["message"] = message

        save_data(DATA)

        await ctx.send(
            "✅ Welcome message saved."
        )

    @welcome_message.command(name="clear")
    async def message_clear_prefix(self, ctx):
        data = guild_data(ctx.guild.id)

        data["message"] = ""

        save_data(DATA)

        await ctx.send(
            "🧹 Welcome message cleared."
        )

    # ========================================================
    # TEST
    # ========================================================

    @welcome.command(name="test")
    async def test_prefix(
        self,
        ctx,
        name: str = None,
        channel: discord.TextChannel = None
    ):
        data = guild_data(ctx.guild.id)

        if name:
            name = name.lower()
        else:
            name = data.get("active_embed")

        if not name:
            await ctx.send(
                "❌ No embed specified and no active embed exists."
            )
            return

        template = data["embeds"].get(name)

        if not template:
            await ctx.send(
                f"❌ Embed `{name}` does not exist."
            )
            return

        if channel is None:
            channel_id = data.get("channel_id")

            if channel_id:
                channel = ctx.guild.get_channel(channel_id)

        if channel is None:
            channel = ctx.channel

        message = replace_variables(
            data.get("message", ""),
            ctx.author
        )

        message = message.replace(
            "{embed}",
            ""
        ).strip()

        embed = build_welcome_embed(
            template,
            ctx.author
        )

        try:
            await channel.send(
                content=message or None,
                embed=embed
            )

            await ctx.send(
                f"🧪 Test sent to {channel.mention}."
            )

        except discord.Forbidden:
            await ctx.send(
                "❌ I don't have permission to send messages/embeds there."
            )

    # ========================================================
    # SLASH COMMAND GROUP
    # ========================================================

    welcome_app = app_commands.Group(
        name="welcome",
        description="Configure the welcome system."
    )

    embed_app = app_commands.Group(
        name="embed",
        description="Manage welcome embed templates.",
        parent=welcome_app
    )

    channel_app = app_commands.Group(
        name="channel",
        description="Manage welcome channel.",
        parent=welcome_app
    )

    message_app = app_commands.Group(
        name="message",
        description="Manage welcome message.",
        parent=welcome_app
    )

    # ========================================================
    # SLASH CREATE
    # ========================================================

    @embed_app.command(
        name="create",
        description="Create a welcome embed template."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_embed_create(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name in data["embeds"]:
            await interaction.response.send_message(
                f"❌ Embed `{name}` already exists.",
                ephemeral=True
            )
            return

        data["embeds"][name] = default_template()

        save_data(DATA)

        await interaction.response.send_message(
            f"✅ Welcome embed `{name}` created.\n"
            f"Use `/welcome embed edit` to configure it.",
            ephemeral=True
        )

    # ========================================================
    # SLASH EDIT
    # ========================================================

    @embed_app.command(
        name="edit",
        description="Open the welcome embed editor."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_embed_edit(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name not in data["embeds"]:
            await interaction.response.send_message(
                f"❌ Embed `{name}` does not exist.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✏️ **Edit Welcome Embed: `{name}`**",
            view=EmbedEditorView(
                self,
                interaction.guild.id,
                name
            ),
            ephemeral=True
        )

    # ========================================================
    # SLASH DELETE
    # ========================================================

    @embed_app.command(
        name="delete",
        description="Delete a welcome embed template."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_embed_delete(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name not in data["embeds"]:
            await interaction.response.send_message(
                f"❌ Embed `{name}` does not exist.",
                ephemeral=True
            )
            return

        del data["embeds"][name]

        if data.get("active_embed") == name:
            data["active_embed"] = None

        save_data(DATA)

        await interaction.response.send_message(
            f"🗑️ Welcome embed `{name}` deleted.",
            ephemeral=True
        )

    # ========================================================
    # SLASH LIST
    # ========================================================

    @embed_app.command(
        name="list",
        description="List welcome embed templates."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_embed_list(
        self,
        interaction: discord.Interaction
    ):
        data = guild_data(interaction.guild.id)

        if not data["embeds"]:
            await interaction.response.send_message(
                "📭 No welcome embeds created.",
                ephemeral=True
            )
            return

        active = data.get("active_embed")

        lines = []

        for name in data["embeds"]:
            marker = " 🟢 ACTIVE" if name == active else ""
            lines.append(f"• `{name}`{marker}")

        await interaction.response.send_message(
            "📋 **Welcome Embeds**\n\n" +
            "\n".join(lines),
            ephemeral=True
        )

    # ========================================================
    # SLASH ENABLE
    # ========================================================

    @welcome_app.command(
        name="enable",
        description="Enable a welcome embed."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_enable(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name not in data["embeds"]:
            await interaction.response.send_message(
                f"❌ Embed `{name}` does not exist.",
                ephemeral=True
            )
            return

        data["active_embed"] = name
        data["channel_id"] = channel.id

        save_data(DATA)

        await interaction.response.send_message(
            f"🟢 Welcome system enabled.\n"
            f"**Embed:** `{name}`\n"
            f"**Channel:** {channel.mention}"
        )

    # ========================================================
    # SLASH DISABLE
    # ========================================================

    @welcome_app.command(
        name="disable",
        description="Disable the welcome system."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_disable(
        self,
        interaction: discord.Interaction
    ):
        data = guild_data(interaction.guild.id)

        data["active_embed"] = None

        save_data(DATA)

        await interaction.response.send_message(
            "🔴 Welcome system disabled."
        )

    # ========================================================
    # SLASH CHANNEL SET
    # ========================================================

    @channel_app.command(
        name="set",
        description="Set the welcome channel."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_set(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel
    ):
        data = guild_data(interaction.guild.id)

        data["channel_id"] = channel.id

        save_data(DATA)

        await interaction.response.send_message(
            f"📍 Welcome channel set to {channel.mention}",
            ephemeral=True
        )

    # ========================================================
    # SLASH CHANNEL VIEW
    # ========================================================

    @channel_app.command(
        name="view",
        description="View the configured welcome channel."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_channel_view(
        self,
        interaction: discord.Interaction
    ):
        data = guild_data(interaction.guild.id)

        channel_id = data.get("channel_id")

        if not channel_id:
            await interaction.response.send_message(
                "❌ Welcome channel is not configured.",
                ephemeral=True
            )
            return

        channel = interaction.guild.get_channel(channel_id)

        if not channel:
            await interaction.response.send_message(
                "⚠️ Configured channel no longer exists.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"📍 Welcome channel: {channel.mention}",
            ephemeral=True
        )

    # ========================================================
    # SLASH MESSAGE SET
    # ========================================================

    @message_app.command(
        name="set",
        description="Set the welcome message."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_message_set(
        self,
        interaction: discord.Interaction,
        message: str
    ):
        data = guild_data(interaction.guild.id)

        if len(message) > 2000:
            await interaction.response.send_message(
                "❌ Message cannot exceed 2000 characters.",
                ephemeral=True
            )
            return

        data["message"] = message

        save_data(DATA)

        await interaction.response.send_message(
            "✅ Welcome message saved.",
            ephemeral=True
        )

    # ========================================================
    # SLASH MESSAGE CLEAR
    # ========================================================

    @message_app.command(
        name="clear",
        description="Clear the welcome message."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_message_clear(
        self,
        interaction: discord.Interaction
    ):
        data = guild_data(interaction.guild.id)

        data["message"] = ""

        save_data(DATA)

        await interaction.response.send_message(
            "🧹 Welcome message cleared.",
            ephemeral=True
        )

    # ========================================================
    # SLASH TEST
    # ========================================================

    @welcome_app.command(
        name="test",
        description="Test a welcome embed."
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def slash_test(
        self,
        interaction: discord.Interaction,
        name: str = None,
        channel: discord.TextChannel = None
    ):
        data = guild_data(interaction.guild.id)

        if name:
            name = name.lower()
        else:
            name = data.get("active_embed")

        if not name:
            await interaction.response.send_message(
                "❌ No embed specified and no active embed exists.",
                ephemeral=True
            )
            return

        template = data["embeds"].get(name)

        if not template:
            await interaction.response.send_message(
                f"❌ Embed `{name}` does not exist.",
                ephemeral=True
            )
            return

        if channel is None:
            channel_id = data.get("channel_id")

            if channel_id:
                channel = interaction.guild.get_channel(
                    channel_id
                )

        if channel is None:
            channel = interaction.channel

        message = replace_variables(
            data.get("message", ""),
            interaction.user
        )

        message = message.replace(
            "{embed}",
            ""
        ).strip()

        embed = build_welcome_embed(
            template,
            interaction.user
        )

        try:
            await channel.send(
                content=message or None,
                embed=embed
            )

            await interaction.response.send_message(
                f"🧪 Test sent to {channel.mention}.",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to send messages/embeds there.",
                ephemeral=True
            )

    # ========================================================
    # REGISTER SLASH GROUP
    # ========================================================

    async def cog_load(self):
        try:
            self.bot.tree.add_command(
                self.welcome_app
            )
        except app_commands.CommandAlreadyRegistered:
            pass

    async def cog_unload(self):
        try:
            self.bot.tree.remove_command(
                self.welcome_app.name
            )
        except Exception:
            pass


# ============================================================
# SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(Welcome(bot))
