import os
import time
import threading
import asyncio
import inspect
import shlex
from typing import get_args, get_origin, Union

from flask import Flask
import discord
import db
import games
import basic_commands
import autosetup
import autorolesetup
import security
import antinuke_rollback
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is required")

OWNER_ID = 1504354088538869892
DEFAULT_PREFIX = ","

app = Flask(__name__)

@app.get("/")
def home():
    return "✈️ Air Commander is online!", 200

@app.get("/health")
def health():
    return {"status": "ok", "discord": bot.is_ready() if "bot" in globals() else False}, 200

def run_web():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port, threaded=True, use_reloader=False)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

async def command_prefix(bot_instance, message):
    if message.author and message.author.id == OWNER_ID:
        return [DEFAULT_PREFIX]
    return DEFAULT_PREFIX

bot = commands.Bot(command_prefix=command_prefix, intents=intents, help_command=None)
bot._air_owner_id = OWNER_ID


def is_air_owner(user):
    return bool(user and getattr(user, "id", None) == OWNER_ID)

bot.is_air_owner = is_air_owner
start_time = time.time()
bot._air_start_time = start_time


games.setup(bot)
basic_commands.setup(bot)
autosetup.setup(bot)
autorolesetup.setup(bot)


class _PrefixResponse:
    def __init__(self, ctx):
        self.ctx = ctx
        self.is_done = lambda: False

    async def send_message(self, content=None, *, embed=None, embeds=None, ephemeral=False, view=None, **kwargs):
        return await self.ctx.send(content=content, embed=embed, embeds=embeds, view=view)

    async def defer(self, *, ephemeral=False, thinking=False):
        return None


class _PrefixFollowup:
    def __init__(self, ctx):
        self.ctx = ctx

    async def send(self, content=None, *, embed=None, embeds=None, ephemeral=False, view=None, **kwargs):
        return await self.ctx.send(content=content, embed=embed, embeds=embeds, view=view)


class _PrefixInteraction:
    def __init__(self, ctx, command):
        self.user = ctx.author
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.client = ctx.bot
        self.message = ctx.message
        self.command = command
        self.permissions = getattr(ctx.author, "guild_permissions", discord.Permissions.none())
        self.response = _PrefixResponse(ctx)
        self.followup = _PrefixFollowup(ctx)

    def is_guild_integration(self):
        return self.guild is not None


def _unwrap_annotation(annotation):
    if annotation is inspect.Parameter.empty:
        return str
    origin = get_origin(annotation)
    if origin is Union:
        options = [x for x in get_args(annotation) if x is not type(None)]
        return options[0] if options else str
    return annotation


async def _prefix_convert(ctx, raw, annotation):
    annotation = _unwrap_annotation(annotation)
    if annotation is str:
        return raw
    if annotation is int:
        return int(raw)
    if annotation is float:
        return float(raw)
    if annotation is bool:
        value = raw.lower()
        if value in {"true", "yes", "on", "1"}:
            return True
        if value in {"false", "no", "off", "0"}:
            return False
        raise ValueError("use true/false")

    converters = {
        discord.Member: commands.MemberConverter(),
        discord.User: commands.UserConverter(),
        discord.Role: commands.RoleConverter(),
        discord.TextChannel: commands.TextChannelConverter(),
        discord.VoiceChannel: commands.VoiceChannelConverter(),
        discord.CategoryChannel: commands.CategoryChannelConverter(),
    }
    converter = converters.get(annotation)
    if converter:
        return await converter.convert(ctx, raw)

    # app_commands.Range[int, ...] and similar wrappers expose their base type.
    origin = getattr(annotation, "__origin__", None)
    if origin in (int, float, str):
        return await _prefix_convert(ctx, raw, origin)
    return raw


async def _invoke_prefix_app_command(ctx, command, args):
    interaction = _PrefixInteraction(ctx, command)

    # Reuse the application's local checks (permissions, roles, custom checks).
    for check in getattr(command, "checks", []):
        result = check(interaction)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            return await ctx.send("❌ You don't have permission to use this command.")

    callback = command.callback
    signature = inspect.signature(callback)
    params = list(signature.parameters.values())[1:]
    values = list(args)
    kwargs = {}
    pos = 0

    for param in params:
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            kwargs[param.name] = " ".join(values[pos:])
            pos = len(values)
            continue

        if pos >= len(values):
            if param.default is inspect.Parameter.empty:
                return await ctx.send(f"❌ Missing required argument: **{param.name}**")
            continue

        annotation = _unwrap_annotation(param.annotation)
        # Final string parameters (reason/layout/prompt/etc.) consume the remainder.
        if annotation is str and pos < len(values) - 1:
            kwargs[param.name] = " ".join(values[pos:])
            pos = len(values)
            continue

        try:
            kwargs[param.name] = await _prefix_convert(ctx, values[pos], param.annotation)
        except (ValueError, commands.BadArgument):
            return await ctx.send(f"❌ Invalid value for **{param.name}**.")
        pos += 1

    if pos < len(values):
        return await ctx.send("❌ Too many arguments. Check the command usage.")

    try:
        return await callback(interaction, **kwargs)
    except discord.Forbidden:
        return await ctx.send("❌ I don't have the Discord permissions needed for that command.")
    except app_commands.AppCommandError:
        return await ctx.send("❌ You don't meet this command's requirements.")


async def _prefix_dispatch(ctx):
    tokens = list(getattr(ctx, "_air_prefix_tokens", []))
    if not tokens:
        return
    root = bot.tree.get_command(tokens[0])
    if root is None:
        return

    current = root
    index = 1
    while isinstance(current, app_commands.Group):
        if index >= len(tokens):
            return await ctx.send("❌ Please specify a subcommand.")
        child = next((c for c in current.commands if c.name == tokens[index]), None)
        if child is None:
            return await ctx.send("❌ Unknown subcommand. Check the command help.")
        current = child
        index += 1

    if isinstance(current, app_commands.Command):
        await _invoke_prefix_app_command(ctx, current, tokens[index:])


def install_prefix_commands():
    """Expose all chat-input slash commands through the normal prefix system.

    No slash commands are copied or re-registered, so this cannot create duplicate
    slash commands. Prefix commands are thin adapters around the existing callbacks.
    """
    added = 0
    for root in bot.tree.get_commands():
        if not isinstance(root, (app_commands.Command, app_commands.Group)):
            continue
        name = root.name
        if bot.get_command(name) is not None:
            continue

        async def prefix_entry(ctx, *, _name=name):
            content = ctx.message.content.strip()
            if content.startswith(DEFAULT_PREFIX):
                content = content[len(DEFAULT_PREFIX):].strip()
            try:
                tokens = shlex.split(content)
            except ValueError:
                return await ctx.send("❌ Invalid quotes in the command.")
            if not tokens or tokens[0].lower() != _name.lower():
                return
            ctx._air_prefix_tokens = tokens
            await _prefix_dispatch(ctx)

        prefix_entry.__name__ = f"prefix_{name}"
        prefix_entry.__doc__ = getattr(root, "description", "Prefix command")
        bot.add_command(commands.Command(prefix_entry, name=name))
        added += 1
    print(f"⌨️ Prefix bridge: registered {added} commands")


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    content = message.content.strip()
    if not content:
        return

    # The owner can omit the comma. Everyone else must use the configured prefix.
    if message.author.id == OWNER_ID and not content.startswith(DEFAULT_PREFIX):
        try:
            tokens = shlex.split(content)
        except ValueError:
            return
        if tokens and bot.tree.get_command(tokens[0].lower()) is not None:
            ctx = await bot.get_context(message)
            ctx._air_prefix_tokens = tokens
            await _prefix_dispatch(ctx)
            return

    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"✈️ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"👑 Air Commander owner configured: {OWNER_ID}")
    await db.init_db()
    await security.init_security_db()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")


async def start_bot():
    await bot.add_cog(security.Security(bot))
    await bot.add_cog(antinuke_rollback.AntiNukeRollback(bot))
    bot.tree.add_command(security.WarningGroup())
    bot.tree.add_command(security.AutoModGroup())
    bot.tree.add_command(security.AntiNukeGroup())
    bot.tree.add_command(security.AntiLinkGroup())
    install_prefix_commands()
    await bot.start(TOKEN)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot())
