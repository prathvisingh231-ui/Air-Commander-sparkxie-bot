# selfrole.py
# Air Commander - Self Role System
#
# Prefix:
# ,selfrole create colors
# ,selfrole edit colors
# ,selfrole list
# ,selfrole delete colors
# ,selfrole send colors #roles
# ,selfrole test colors
# ,selfrole reaction add MESSAGE_ID EMOJI @ROLE
#
# Slash:
# /selfrole create
# /selfrole edit
# /selfrole list
# /selfrole delete
# /selfrole send
# /selfrole test
# /selfrole reaction add

import json
import os
import re

import discord
from discord.ext import commands
from discord import app_commands


DATA_FILE = "selfrole_config.json"


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


def save_data():
    temp = DATA_FILE + ".tmp"

    with open(temp, "w", encoding="utf-8") as f:
        json.dump(DATA, f, indent=4, ensure_ascii=False)

    os.replace(temp, DATA_FILE)


DATA = load_data()


def guild_data(guild_id):
    gid = str(guild_id)

    if gid not in DATA:
        DATA[gid] = {
            "panels": {},
            "messages": {}
        }

    DATA[gid].setdefault("panels", {})
    DATA[gid].setdefault("messages", {})

    return DATA[gid]


def default_panel():
    return {
        "title": "🎭 Choose Your Roles",
        "description": "Click a button below to get or remove a role.",
        "color": 0x5865F2,
        "mode": "button",
        "roles": []
    }


# ============================================================
# EMOJI HELPERS
# ============================================================

def emoji_key(emoji):
    if isinstance(emoji, discord.Emoji):
        return f"<:{emoji.name}:{emoji.id}>"

    if isinstance(emoji, discord.PartialEmoji):
        if emoji.id:
            return f"<:{emoji.name}:{emoji.id}>"

    return str(emoji)


def emoji_from_string(value):
    value = str(value)

    match = re.match(
        r"<a?:([^:]+):(\d+)>",
        value
    )

    if match:
        animated = value.startswith("<a:")
        return discord.PartialEmoji(
            name=match.group(1),
            id=int(match.group(2)),
            animated=animated
        )

    return value


# ============================================================
# ROLE LOOKUP
# ============================================================

def get_role(guild, role_id):
    return guild.get_role(int(role_id))


# ============================================================
# PANEL EMBED
# ============================================================

def build_panel_embed(panel, guild):
    color = panel.get("color", 0x5865F2)

    try:
        color = int(color)
    except (ValueError, TypeError):
        color = 0x5865F2

    embed = discord.Embed(
        title=panel.get("title") or None,
        description=panel.get("description") or None,
        color=color
    )

    role_lines = []

    for item in panel.get("roles", []):
        role = guild.get_role(int(item["role_id"]))

        if not role:
            continue

        emoji = item.get("emoji", "🎭")

        role_lines.append(
            f"{emoji} — {role.mention}"
        )

    if role_lines:
        embed.add_field(
            name="Available Roles",
            value="\n".join(role_lines),
            inline=False
        )

    return embed


# ============================================================
# BUTTON VIEW
# ============================================================

class SelfRoleButton(discord.ui.Button):
    def __init__(
        self,
        panel_name,
        role_id,
        emoji,
        label,
        row=0
    ):
        super().__init__(
            label=label[:80],
            emoji=emoji_from_string(emoji),
            style=discord.ButtonStyle.secondary,
            custom_id=f"selfrole:{panel_name}:{role_id}",
            row=row
        )

        self.role_id = int(role_id)

    async def callback(self, interaction):
        if not interaction.guild:
            return

        role = interaction.guild.get_role(self.role_id)

        if not role:
            await interaction.response.send_message(
                "❌ This role no longer exists.",
                ephemeral=True
            )
            return

        member = interaction.user

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ I cannot manage this role because it is above my highest role.",
                ephemeral=True
            )
            return

        try:
            if role in member.roles:
                await member.remove_roles(role)

                await interaction.response.send_message(
                    f"➖ Removed {role.mention}.",
                    ephemeral=True
                )
            else:
                await member.add_roles(role)

                await interaction.response.send_message(
                    f"➕ Added {role.mention}.",
                    ephemeral=True
                )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I don't have permission to manage this role.",
                ephemeral=True
            )


class SelfRoleView(discord.ui.View):
    def __init__(self, panel_name, panel):
        super().__init__(timeout=None)

        roles = panel.get("roles", [])

        for index, item in enumerate(roles):
            if index >= 25:
                break

            role_id = item["role_id"]
            emoji = item.get("emoji", "🎭")
            label = item.get("label", "Role")

            self.add_item(
                SelfRoleButton(
                    panel_name,
                    role_id,
                    emoji,
                    label,
                    row=index // 5
                )
            )


# ============================================================
# EDITOR MODALS
# ============================================================

class PanelTextModal(discord.ui.Modal):
    def __init__(
        self,
        panel_name,
        field,
        title,
        current
    ):
        super().__init__(title=title)

        self.panel_name = panel_name
        self.field = field

        self.input = discord.ui.TextInput(
            label=title[:45],
            default=current or "",
            required=False,
            style=discord.TextStyle.paragraph,
            max_length=4000
        )

        self.add_item(self.input)

    async def on_submit(self, interaction):
        data = guild_data(interaction.guild.id)

        panel = data["panels"].get(self.panel_name)

        if not panel:
            await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )
            return

        panel[self.field] = self.input.value

        save_data()

        await interaction.response.send_message(
            f"✅ `{self.field}` updated.",
            ephemeral=True
        )


class PanelColorModal(discord.ui.Modal):
    def __init__(self, panel_name, current):
        super().__init__(title="Edit Panel Color")

        self.panel_name = panel_name

        self.input = discord.ui.TextInput(
            label="Hex Color",
            placeholder="#5865F2",
            default=f"#{current:06X}",
            max_length=7
        )

        self.add_item(self.input)

    async def on_submit(self, interaction):
        value = self.input.value.strip().replace("#", "")

        try:
            color = int(value, 16)

            if not 0 <= color <= 0xFFFFFF:
                raise ValueError

        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid hex color.",
                ephemeral=True
            )
            return

        data = guild_data(interaction.guild.id)

        panel = data["panels"].get(self.panel_name)

        if not panel:
            await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )
            return

        panel["color"] = color

        save_data()

        await interaction.response.send_message(
            "🎨 Panel color updated.",
            ephemeral=True
        )


# ============================================================
# ADD ROLE MODAL
# ============================================================

class AddRoleModal(discord.ui.Modal):
    def __init__(self, panel_name):
        super().__init__(title="Add Self Role")

        self.panel_name = panel_name

        self.role_id = discord.ui.TextInput(
            label="Role ID",
            placeholder="123456789012345678",
            max_length=30
        )

        self.emoji = discord.ui.TextInput(
            label="Emoji",
            placeholder="🎮",
            max_length=100
        )

        self.label = discord.ui.TextInput(
            label="Button Label",
            placeholder="Gaming",
            max_length=80
        )

        self.add_item(self.role_id)
        self.add_item(self.emoji)
        self.add_item(self.label)

    async def on_submit(self, interaction):
        data = guild_data(interaction.guild.id)

        panel = data["panels"].get(self.panel_name)

        if not panel:
            await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )
            return

        try:
            role_id = int(self.role_id.value)
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid role ID.",
                ephemeral=True
            )
            return

        role = interaction.guild.get_role(role_id)

        if not role:
            await interaction.response.send_message(
                "❌ Role not found in this server.",
                ephemeral=True
            )
            return

        if len(panel["roles"]) >= 25:
            await interaction.response.send_message(
                "❌ Discord allows a maximum of 25 buttons in this panel.",
                ephemeral=True
            )
            return

        panel["roles"].append({
            "role_id": role_id,
            "emoji": self.emoji.value,
            "label": self.label.value or role.name
        })

        save_data()

        await interaction.response.send_message(
            f"✅ Added {role.mention} to `{self.panel_name}`.",
            ephemeral=True
        )


# ============================================================
# EDITOR VIEW
# ============================================================

class SelfRoleEditor(discord.ui.View):
    def __init__(self, panel_name):
        super().__init__(timeout=300)

        self.panel_name = panel_name

    def get_panel(self, guild_id):
        return guild_data(guild_id)["panels"].get(
            self.panel_name
        )

    @discord.ui.button(
        label="Title",
        emoji="📝",
        style=discord.ButtonStyle.secondary,
        row=0
    )
    async def title(
        self,
        interaction,
        button
    ):
        panel = self.get_panel(interaction.guild.id)

        await interaction.response.send_modal(
            PanelTextModal(
                self.panel_name,
                "title",
                "Edit Title",
                panel.get("title", "")
            )
        )

    @discord.ui.button(
        label="Description",
        emoji="📄",
        style=discord.ButtonStyle.secondary,
        row=0
    )
    async def description(
        self,
        interaction,
        button
    ):
        panel = self.get_panel(interaction.guild.id)

        await interaction.response.send_modal(
            PanelTextModal(
                self.panel_name,
                "description",
                "Edit Description",
                panel.get("description", "")
            )
        )

    @discord.ui.button(
        label="Color",
        emoji="🎨",
        style=discord.ButtonStyle.secondary,
        row=0
    )
    async def color(
        self,
        interaction,
        button
    ):
        panel = self.get_panel(interaction.guild.id)

        await interaction.response.send_modal(
            PanelColorModal(
                self.panel_name,
                panel.get("color", 0x5865F2)
            )
        )

    @discord.ui.button(
        label="Add Role",
        emoji="➕",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def add_role(
        self,
        interaction,
        button
    ):
        await interaction.response.send_modal(
            AddRoleModal(
                self.panel_name
            )
        )

    @discord.ui.button(
        label="Preview",
        emoji="👁️",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def preview(
        self,
        interaction,
        button
    ):
        panel = self.get_panel(interaction.guild.id)

        embed = build_panel_embed(
            panel,
            interaction.guild
        )

        await interaction.response.send_message(
            embed=embed,
            view=SelfRoleView(
                self.panel_name,
                panel
            ),
            ephemeral=True
        )

    @discord.ui.button(
        label="Save",
        emoji="💾",
        style=discord.ButtonStyle.success,
        row=1
    )
    async def save(
        self,
        interaction,
        button
    ):
        save_data()

        await interaction.response.send_message(
            f"✅ Self-role panel `{self.panel_name}` saved.",
            ephemeral=True
        )


# ============================================================
# COG
# ============================================================

class SelfRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ========================================================
    # PREFIX GROUP
    # ========================================================

    @commands.group(
        name="selfrole",
        invoke_without_command=True
    )
    @commands.guild_only()
    @commands.has_guild_permissions(manage_roles=True)
    async def selfrole(self, ctx):
        await ctx.send(
            "🎭 **Self Role System**\n\n"
            "`,selfrole create <name>`\n"
            "`,selfrole edit <name>`\n"
            "`,selfrole list`\n"
            "`,selfrole delete <name>`\n"
            "`,selfrole send <name> #channel`\n"
            "`,selfrole test <name>`\n"
            "`,selfrole reaction add <message_id> <emoji> @role`"
        )

    # ========================================================
    # CREATE
    # ========================================================

    @selfrole.command(name="create")
    async def create_prefix(
        self,
        ctx,
        name: str
    ):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        if name in data["panels"]:
            await ctx.send(
                f"❌ Panel `{name}` already exists."
            )
            return

        data["panels"][name] = default_panel()

        save_data()

        await ctx.send(
            f"✅ Self-role panel `{name}` created.\n"
            f"Use `,selfrole edit {name}` to configure it."
        )

    # ========================================================
    # EDIT
    # ========================================================

    @selfrole.command(name="edit")
    async def edit_prefix(
        self,
        ctx,
        name: str
    ):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        if name not in data["panels"]:
            await ctx.send(
                f"❌ Panel `{name}` doesn't exist."
            )
            return

        await ctx.send(
            f"✏️ **Self Role Editor — `{name}`**",
            view=SelfRoleEditor(name)
        )

    # ========================================================
    # LIST
    # ========================================================

    @selfrole.command(name="list")
    async def list_prefix(self, ctx):
        data = guild_data(ctx.guild.id)

        if not data["panels"]:
            await ctx.send(
                "📭 No self-role panels created."
            )
            return

        lines = []

        for name, panel in data["panels"].items():
            count = len(panel.get("roles", []))

            lines.append(
                f"• `{name}` — {count} role(s)"
            )

        await ctx.send(
            "📋 **Self Role Panels**\n\n" +
            "\n".join(lines)
        )

    # ========================================================
    # DELETE
    # ========================================================

    @selfrole.command(name="delete")
    async def delete_prefix(
        self,
        ctx,
        name: str
    ):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        if name not in data["panels"]:
            await ctx.send(
                f"❌ Panel `{name}` doesn't exist."
            )
            return

        del data["panels"][name]

        save_data()

        await ctx.send(
            f"🗑️ Self-role panel `{name}` deleted."
        )

    # ========================================================
    # SEND
    # ========================================================

    @selfrole.command(name="send")
    async def send_prefix(
        self,
        ctx,
        name: str,
        channel: discord.TextChannel = None
    ):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        panel = data["panels"].get(name)

        if not panel:
            await ctx.send(
                f"❌ Panel `{name}` doesn't exist."
            )
            return

        channel = channel or ctx.channel

        embed = build_panel_embed(
            panel,
            ctx.guild
        )

        try:
            message = await channel.send(
                embed=embed,
                view=SelfRoleView(
                    name,
                    panel
                )
            )

            await ctx.send(
                f"✅ Self-role panel sent to {channel.mention}.\n"
                f"Message ID: `{message.id}`"
            )

        except discord.Forbidden:
            await ctx.send(
                "❌ I don't have permission to send messages there."
            )

    # ========================================================
    # TEST
    # ========================================================

    @selfrole.command(name="test")
    async def test_prefix(
        self,
        ctx,
        name: str
    ):
        data = guild_data(ctx.guild.id)

        name = name.lower()

        panel = data["panels"].get(name)

        if not panel:
            await ctx.send(
                f"❌ Panel `{name}` doesn't exist."
            )
            return

        embed = build_panel_embed(
            panel,
            ctx.guild
        )

        await ctx.send(
            "🧪 **Self-role test:**",
            embed=embed,
            view=SelfRoleView(
                name,
                panel
            )
        )

    # ========================================================
    # REACTION GROUP
    # ========================================================

    @selfrole.group(
        name="reaction",
        invoke_without_command=True
    )
    async def reaction_group(self, ctx):
        await ctx.send(
            "Use:\n"
            "`,selfrole reaction add <message_id> <emoji> @role`"
        )

    @reaction_group.command(name="add")
    async def reaction_add_prefix(
        self,
        ctx,
        message_id: int,
        emoji: str,
        role: discord.Role
    ):
        try:
            message = await ctx.channel.fetch_message(
                message_id
            )
        except discord.NotFound:
            await ctx.send(
                "❌ Message not found."
            )
            return
        except discord.Forbidden:
            await ctx.send(
                "❌ I cannot access that message."
            )
            return

        if role >= ctx.guild.me.top_role:
            await ctx.send(
                "❌ I cannot manage that role."
            )
            return

        data = guild_data(ctx.guild.id)

        data["messages"].setdefault(
            str(message_id),
            []
        )

        data["messages"][str(message_id)].append({
            "emoji": emoji,
            "role_id": role.id
        })

        save_data()

        try:
            await message.add_reaction(
                emoji_from_string(emoji)
            )
        except discord.HTTPException:
            await ctx.send(
                "⚠️ Role saved, but I couldn't add that reaction."
            )
            return

        await ctx.send(
            f"✅ Reaction role added.\n"
            f"{emoji} → {role.mention}"
        )

    # ========================================================
    # REACTION ADD EVENT
    # ========================================================

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.guild_id is None:
            return

        data = guild_data(payload.guild_id)

        mappings = data["messages"].get(
            str(payload.message_id),
            []
        )

        if not mappings:
            return

        guild = self.bot.get_guild(payload.guild_id)

        if not guild:
            return

        member = guild.get_member(payload.user_id)

        if not member or member.bot:
            return

        received = str(payload.emoji)

        for mapping in mappings:
            if str(mapping["emoji"]) != received:
                continue

            role = guild.get_role(
                int(mapping["role_id"])
            )

            if not role:
                continue

            if role >= guild.me.top_role:
                continue

            try:
                await member.add_roles(role)
            except discord.HTTPException:
                pass

    # ========================================================
    # REACTION REMOVE EVENT
    # ========================================================

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        if payload.guild_id is None:
            return

        data = guild_data(payload.guild_id)

        mappings = data["messages"].get(
            str(payload.message_id),
            []
        )

        if not mappings:
            return

        guild = self.bot.get_guild(payload.guild_id)

        if not guild:
            return

        member = guild.get_member(payload.user_id)

        if not member or member.bot:
            return

        received = str(payload.emoji)

        for mapping in mappings:
            if str(mapping["emoji"]) != received:
                continue

            role = guild.get_role(
                int(mapping["role_id"])
            )

            if not role:
                continue

            if role >= guild.me.top_role:
                continue

            try:
                await member.remove_roles(role)
            except discord.HTTPException:
                pass

    # ========================================================
    # SLASH GROUPS
    # ========================================================

    selfrole_app = app_commands.Group(
        name="selfrole",
        description="Manage self roles."
    )

    # ========================================================
    # SLASH CREATE
    # ========================================================

    @selfrole_app.command(
        name="create",
        description="Create a self-role panel."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_create(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name in data["panels"]:
            await interaction.response.send_message(
                f"❌ Panel `{name}` already exists.",
                ephemeral=True
            )
            return

        data["panels"][name] = default_panel()

        save_data()

        await interaction.response.send_message(
            f"✅ Self-role panel `{name}` created.",
            ephemeral=True
        )

    # ========================================================
    # SLASH EDIT
    # ========================================================

    @selfrole_app.command(
        name="edit",
        description="Edit a self-role panel."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_edit(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name not in data["panels"]:
            await interaction.response.send_message(
                f"❌ Panel `{name}` doesn't exist.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✏️ **Self Role Editor — `{name}`**",
            view=SelfRoleEditor(name),
            ephemeral=True
        )

    # ========================================================
    # SLASH LIST
    # ========================================================

    @selfrole_app.command(
        name="list",
        description="List self-role panels."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_list(
        self,
        interaction: discord.Interaction
    ):
        data = guild_data(interaction.guild.id)

        if not data["panels"]:
            await interaction.response.send_message(
                "📭 No self-role panels created.",
                ephemeral=True
            )
            return

        lines = []

        for name, panel in data["panels"].items():
            lines.append(
                f"• `{name}` — "
                f"{len(panel.get('roles', []))} role(s)"
            )

        await interaction.response.send_message(
            "📋 **Self Role Panels**\n\n" +
            "\n".join(lines),
            ephemeral=True
        )

    # ========================================================
    # SLASH DELETE
    # ========================================================

    @selfrole_app.command(
        name="delete",
        description="Delete a self-role panel."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_delete(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        if name not in data["panels"]:
            await interaction.response.send_message(
                f"❌ Panel `{name}` doesn't exist.",
                ephemeral=True
            )
            return

        del data["panels"][name]

        save_data()

        await interaction.response.send_message(
            f"🗑️ Panel `{name}` deleted.",
            ephemeral=True
        )

    # ========================================================
    # SLASH SEND
    # ========================================================

    @selfrole_app.command(
        name="send",
        description="Send a self-role panel."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_send(
        self,
        interaction: discord.Interaction,
        name: str,
        channel: discord.TextChannel
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        panel = data["panels"].get(name)

        if not panel:
            await interaction.response.send_message(
                f"❌ Panel `{name}` doesn't exist.",
                ephemeral=True
            )
            return

        embed = build_panel_embed(
            panel,
            interaction.guild
        )

        try:
            message = await channel.send(
                embed=embed,
                view=SelfRoleView(
                    name,
                    panel
                )
            )

            await interaction.response.send_message(
                f"✅ Panel sent to {channel.mention}.\n"
                f"Message ID: `{message.id}`",
                ephemeral=True
            )

        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I cannot send messages there.",
                ephemeral=True
            )

    # ========================================================
    # SLASH TEST
    # ========================================================

    @selfrole_app.command(
        name="test",
        description="Test a self-role panel."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_test(
        self,
        interaction: discord.Interaction,
        name: str
    ):
        data = guild_data(interaction.guild.id)

        name = name.lower()

        panel = data["panels"].get(name)

        if not panel:
            await interaction.response.send_message(
                f"❌ Panel `{name}` doesn't exist.",
                ephemeral=True
            )
            return

        embed = build_panel_embed(
            panel,
            interaction.guild
        )

        await interaction.response.send_message(
            "🧪 **Self-role test:**",
            embed=embed,
            view=SelfRoleView(
                name,
                panel
            )
        )

    # ========================================================
    # SLASH REACTION ADD
    # ========================================================

    reaction_app = app_commands.Group(
        name="reaction",
        description="Manage reaction roles.",
        parent=selfrole_app
    )

    @reaction_app.command(
        name="add",
        description="Add a reaction role to an existing message."
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def slash_reaction_add(
        self,
        interaction: discord.Interaction,
        message_id: str,
        emoji: str,
        role: discord.Role
    ):
        try:
            message = await interaction.channel.fetch_message(
                int(message_id)
            )
        except (discord.NotFound, ValueError):
            await interaction.response.send_message(
                "❌ Message not found.",
                ephemeral=True
            )
            return
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ I cannot access that message.",
                ephemeral=True
            )
            return

        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "❌ I cannot manage that role.",
                ephemeral=True
            )
            return

        data = guild_data(interaction.guild.id)

        data["messages"].setdefault(
            str(message.id),
            []
        )

        data["messages"][str(message.id)].append({
            "emoji": emoji,
            "role_id": role.id
        })

        save_data()

        try:
            await message.add_reaction(
                emoji_from_string(emoji)
            )
        except discord.HTTPException:
            await interaction.response.send_message(
                "⚠️ Saved, but I couldn't add the reaction.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ Reaction role added.\n"
            f"{emoji} → {role.mention}",
            ephemeral=True
        )

    # ========================================================
    # LOAD
    # ========================================================

    async def cog_load(self):
        try:
            self.bot.tree.add_command(
                self.selfrole_app
            )
        except app_commands.CommandAlreadyRegistered:
            pass

    async def cog_unload(self):
        try:
            self.bot.tree.remove_command(
                self.selfrole_app.name
            )
        except Exception:
            pass


# ============================================================
# SETUP
# ============================================================

async def setup(bot):
    await bot.add_cog(SelfRole(bot))
