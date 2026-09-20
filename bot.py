import os
import time
import threading
import asyncio
import inspect
import shlex

from flask import Flask
import discord
import db
import games
import basic_commands
import moderation_extra
import security
import antinuke_rollback
import purge_steal
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is required")

OWNER_ID = 1504354088538869892
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

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
bot._air_owner_id = OWNER_ID
bot._air_start_time = time.time()
bot.is_air_owner = lambda user: bool(user and getattr(user, "id", None) == OWNER_ID)

games.setup(bot)
basic_commands.setup(bot)
moderation_extra.setup(bot)


class PrefixResponse:
    def __init__(self, ctx):
        self.ctx = ctx
        self._done = False

    def is_done(self):
        return self._done

    async def send_message(self, content=None, *, embed=None, embeds=None, ephemeral=False, **kwargs):
        self._done = True
        kwargs.pop("ephemeral", None)
        return await self.ctx.send(content=content, embed=embed, embeds=embeds, **kwargs)

    async def defer(self, *, ephemeral=False, thinking=False):
        self._done = True

    async def edit_message(self, **kwargs):
        self._done = True
        return await self.ctx.message.edit(**kwargs) if self.ctx.message else None


class PrefixFollowup:
    def __init__(self, ctx):
        self.ctx = ctx

    async def send(self, content=None, *, embed=None, embeds=None, ephemeral=False, **kwargs):
        kwargs.pop("ephemeral", None)
        return await self.ctx.send(content=content, embed=embed, embeds=embeds, **kwargs)


class PrefixInteraction:
    def __init__(self, ctx, command):
        self.client = ctx.bot
        self.user = ctx.author
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.message = ctx.message
        self.command = command
        self.guild_id = ctx.guild.id if ctx.guild else None
        self.channel_id = ctx.channel.id if ctx.channel else None
        self.response = PrefixResponse(ctx)
        self.followup = PrefixFollowup(ctx)
        self.locale = discord.Locale.american_english
        self.guild_locale = discord.Locale.american_english

    @property
    def permissions(self):
        return self.user.guild_permissions if self.guild else discord.Permissions.none()

    def is_guild_integration(self):
        return self.guild is not None


async def _convert_prefix_argument(ctx, parameter, raw):
    option_type = getattr(parameter, "type", None)
    if option_type in (app_commands.AppCommandOptionType.string, None):
        return raw
    if option_type == app_commands.AppCommandOptionType.integer:
        return int(raw)
    if option_type == app_commands.AppCommandOptionType.number:
        return float(raw)
    if option_type == app_commands.AppCommandOptionType.boolean:
        value = raw.lower()
        if value in {"true", "yes", "on", "1"}:
            return True
        if value in {"false", "no", "off", "0"}:
            return False
        raise ValueError("use true/false")
    if option_type == app_commands.AppCommandOptionType.user:
        return await commands.MemberConverter().convert(ctx, raw)
    if option_type == app_commands.AppCommandOptionType.mentionable:
        try:
            return await commands.MemberConverter().convert(ctx, raw)
        except commands.BadArgument:
            return await commands.RoleConverter().convert(ctx, raw)
    if option_type == app_commands.AppCommandOptionType.role:
        return await commands.RoleConverter().convert(ctx, raw)
    if option_type == app_commands.AppCommandOptionType.channel:
        return await commands.GuildChannelConverter().convert(ctx, raw)
    return raw


async def _run_prefix_checks(command, interaction):
    if interaction.user.id == OWNER_ID:
        return
    for check in getattr(command, "checks", []):
        result = check(interaction)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            raise commands.CheckFailure("You do not have permission to use this command.")


def _find_command(ctx, name):
    name = name.lower()
    if ctx.guild:
        command = bot.tree.get_command(name, guild=ctx.guild)
        if command:
            return command
    command = bot.tree.get_command(name)
    if command:
        return command
    return bot.get_command(name)


def _find_child(group, name):
    return next((child for child in getattr(group, "commands", []) if child.name.lower() == name.lower()), None)


async def _invoke_native_command(ctx, command, tokens):
    try:
        await ctx.invoke(command, *tokens)
    except commands.CommandError as exc:
        await ctx.send(f"❌ {exc}")
    return True


async def _invoke_tree_command(ctx, command, tokens):
    if command is None:
        return False
    if isinstance(command, commands.Command):
        return await _invoke_native_command(ctx, command, tokens)

    interaction = PrefixInteraction(ctx, command)
    if ctx.guild is None and getattr(command, "guild_only", False):
        await ctx.send("❌ This command can only be used in a server.")
        return True

    try:
        await _run_prefix_checks(command, interaction)
    except commands.CheckFailure as exc:
        await ctx.send(f"❌ {exc}")
        return True

    parameters = list(getattr(command, "parameters", []))
    position = 0
    args = [interaction]

    for index, parameter in enumerate(parameters):
        if position >= len(tokens):
            if not parameter.required:
                default = parameter.default
                args.append(None if default is app_commands.MISSING else default)
                continue
            await ctx.send(f"❌ Missing required argument: `{parameter.display_name}`")
            return True

        if parameter.type == app_commands.AppCommandOptionType.string and index == len(parameters) - 1:
            raw = " ".join(tokens[position:])
            position = len(tokens)
        else:
            raw = tokens[position]
            position += 1

        try:
            args.append(await _convert_prefix_argument(ctx, parameter, raw))
        except Exception as exc:
            await ctx.send(f"❌ Invalid value for `{parameter.display_name}`: {exc}")
            return True

    if position < len(tokens):
        await ctx.send("❌ Too many arguments. Check the command usage.")
        return True

    try:
        await command.callback(*args)
    except discord.Forbidden:
        await ctx.send("❌ Discord denied that action. Check my permissions and role hierarchy.")
    except app_commands.AppCommandError as exc:
        await ctx.send(f"❌ {exc}")
    except Exception as exc:
        print(f"[PrefixBridge] {command.qualified_name}: {exc!r}")
        await ctx.send("❌ The command failed while running. Check the bot logs for details.")
    return True


async def dispatch_prefix_tree(ctx, text):
    try:
        tokens = shlex.split(text) if text.strip() else []
    except ValueError as exc:
        await ctx.send(f"❌ Invalid arguments: {exc}")
        return True
    if not tokens:
        return False

    current = _find_command(ctx, tokens[0])
    if current is None:
        return False

    if isinstance(current, commands.Command):
        return await _invoke_tree_command(ctx, current, tokens[1:])

    index = 1
    while isinstance(current, app_commands.Group):
        if index >= len(tokens):
            await ctx.send(f"❌ Please specify a subcommand for `{current.name}`.")
            return True
        current = _find_child(current, tokens[index])
        if current is None:
            await ctx.send("❌ Unknown subcommand. Check `/help` for the available commands.")
            return True
        index += 1

    return await _invoke_tree_command(ctx, current, tokens[index:])


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    content = message.content.strip()
    if not content:
        return

    ctx = await bot.get_context(message)

    # Owner 1504354088538869892 can run every registered command without a prefix.
    if message.author.id == OWNER_ID:
        if await dispatch_prefix_tree(ctx, content):
            return

    # Use the actual persisted prefix cache rather than relying on discord.py's
    # command parser. This makes custom prefixes work reliably after restart.
    prefix = bot._air_prefixes.get(message.guild.id, "!") if message.guild else "!"
    if prefix and content.startswith(prefix):
        remainder = content[len(prefix):].strip()
        if remainder:
            if await dispatch_prefix_tree(ctx, remainder):
                return

    # Native discord.py commands (including ping) remain supported.
    await bot.process_commands(message)


@bot.event
async def on_ready():
    print(f"✈️ Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"👑 Air Commander owner configured: {OWNER_ID}")
    await db.init_db()
    await security.init_security_db()
    if hasattr(bot, "_air_load_prefixes"):
        await bot._air_load_prefixes()

    try:
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} global slash commands")
    except Exception as exc:
        print(f"❌ Command sync failed: {type(exc).__name__}: {exc}")

    for guild in bot.guilds:
        try:
            bot.tree.clear_commands(guild=guild)
            await bot.tree.sync(guild=guild)
        except Exception as exc:
            print(f"⚠️ Guild command cleanup failed for {guild.id}: {type(exc).__name__}: {exc}")

    if hasattr(bot, "_air_load_custom_commands"):
        await bot._air_load_custom_commands()


async def start_bot():
    await bot.add_cog(security.Security(bot))
    await bot.add_cog(antinuke_rollback.AntiNukeRollback(bot))
    await bot.add_cog(purge_steal.PurgeSteal(bot))

    existing = {command.name for command in bot.tree.get_commands()}
    for group_cls in (security.WarningGroup, security.AutoModGroup, security.AntiNukeGroup, security.AntiLinkGroup):
        group = group_cls()
        if group.name not in existing:
            bot.tree.add_command(group)
            existing.add(group.name)

    await bot.start(TOKEN)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot())
