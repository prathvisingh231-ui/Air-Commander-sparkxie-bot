"""Guild-scoped role allowlists for prefix and slash commands.

No restriction is applied unless a server admin enables one for a command.
Server administrators retain an emergency bypass.
"""
from __future__ import annotations

import json
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

TITLE = "🔐 Command Permissions"
DATA_FILE = Path("data/command_permissions.json")
DATA: dict = {}


def _embed(desc, color=0x5865F2):
    embed = discord.Embed(title=TITLE, description=desc, color=color)
    embed.set_footer(text="AirMarshal Commander • Air Commander")
    return embed


def load_data():
    global DATA
    try:
        loaded = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        DATA = loaded if isinstance(loaded, dict) else {}
    except (OSError, ValueError, TypeError):
        DATA = {}
    return DATA


def save_data(data=None):
    global DATA
    if data is not None:
        DATA = data
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_FILE.with_suffix(".json.tmp")
    temp.write_text(json.dumps(DATA, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_FILE)


def _policy(guild_id, command_name):
    guild = DATA.get(str(guild_id), {})
    policies = guild.get("commands", {}) if isinstance(guild, dict) else {}
    policy = policies.get(command_name, {}) if isinstance(policies, dict) else {}
    if not isinstance(policy, dict) or not policy.get("enabled"):
        return None
    role_ids = policy.get("role_ids", [])
    try:
        return {int(value) for value in role_ids}
    except (TypeError, ValueError):
        return set()


def _allowed(member, guild_id, command_name):
    role_ids = _policy(guild_id, command_name)
    if role_ids is None:
        return True
    permissions = getattr(member, "guild_permissions", None)
    if permissions and (permissions.administrator or permissions.manage_guild):
        return True
    member_roles = {int(role.id) for role in getattr(member, "roles", [])}
    return bool(member_roles.intersection(role_ids))


def setup(bot):
    load_data()
    bot._air_command_permissions_data = DATA

    # Keep the existing command name and both interfaces.
    if bot.get_command("cmdperm") is None:
        @bot.command(name="cmdperm")
        @commands.guild_only()
        async def _prefix(ctx, *, value: str = ""):
            if not ctx.author.guild_permissions.manage_guild and not ctx.author.guild_permissions.administrator:
                return await ctx.send("Manage Server permission required.")
            await ctx.send(embed=_embed(
                "Command restrictions are managed in the Air Commander Dashboard. "
                "Open Dashboard → Command Permissions to configure role allowlists."
            ))

    if bot.tree.get_command("cmdperm") is None:
        @bot.tree.command(name="cmdperm", description="View command permission settings.")
        @app_commands.guild_only()
        async def _slash(interaction: discord.Interaction):
            perms = interaction.user.guild_permissions
            if not (perms.manage_guild or perms.administrator):
                return await interaction.response.send_message("Manage Server permission required.", ephemeral=True)
            await interaction.response.send_message(embed=_embed(
                "Command restrictions are managed in the Air Commander Dashboard. "
                "Open Dashboard → Command Permissions to configure role allowlists."
            ), ephemeral=True)

    if not getattr(bot, "_air_command_permissions_prefix_check", False):
        async def prefix_permission_check(ctx):
            if not ctx.guild or not ctx.command:
                return True
            # Restrict the invoked command and nested subcommands independently.
            candidates = [ctx.command.qualified_name, ctx.command.root_parent.qualified_name if ctx.command.root_parent else ctx.command.name, ctx.command.name]
            for name in dict.fromkeys(candidates):
                if _policy(ctx.guild.id, name) is not None:
                    if not _allowed(ctx.author, ctx.guild.id, name):
                        await ctx.send("You do not have a role allowed to use this command.")
                        return False
                    return True
            return True
        bot.add_check(prefix_permission_check)
        bot._air_command_permissions_prefix_check = True

    if not getattr(bot, "_air_command_permissions_slash_check", False):
        tree = bot.tree
        original_check = tree.interaction_check

        async def slash_permission_check(interaction: discord.Interaction):
            base_allowed = await original_check(interaction)
            if not base_allowed or not interaction.guild or not interaction.command:
                return base_allowed
            command = interaction.command
            # Check the full subcommand, its top-level group, and its leaf name.
            # This lets admins restrict either one nested command or an entire group.
            names = [command.qualified_name]
            parent = getattr(command, "parent", None)
            while parent is not None:
                names.append(parent.qualified_name)
                parent = getattr(parent, "parent", None)
            names.append(command.name)
            for name in dict.fromkeys(names):
                if _policy(interaction.guild.id, name) is not None:
                    allowed = _allowed(interaction.user, interaction.guild.id, name)
                    if not allowed and not interaction.response.is_done():
                        await interaction.response.send_message("You do not have a role allowed to use this command.", ephemeral=True)
                    return allowed
            return True

        tree.interaction_check = slash_permission_check
        bot._air_command_permissions_slash_check = True

    print("Command permissions loaded: per-guild role allowlists enabled for prefix and slash commands.", flush=True)
