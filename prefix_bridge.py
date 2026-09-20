import inspect
import shlex
from types import SimpleNamespace

import discord
from discord import app_commands
from discord.ext import commands


class _PrefixResponse:
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
        if self.ctx.message:
            return await self.ctx.message.edit(**kwargs)


class _PrefixFollowup:
    def __init__(self, ctx):
        self.ctx = ctx

    async def send(self, content=None, *, embed=None, embeds=None, ephemeral=False, **kwargs):
        kwargs.pop("ephemeral", None)
        return await self.ctx.send(content=content, embed=embed, embeds=embeds, **kwargs)


class PrefixInteraction:
    """Small Interaction-compatible adapter so existing slash callbacks can run from prefix commands."""
    def __init__(self, ctx, command):
        self.client = ctx.bot
        self.user = ctx.author
        self.guild = ctx.guild
        self.channel = ctx.channel
        self.message = ctx.message
        self.command = command
        self.guild_id = ctx.guild.id if ctx.guild else None
        self.channel_id = ctx.channel.id if ctx.channel else None
        self.response = _PrefixResponse(ctx)
        self.followup = _PrefixFollowup(ctx)
        self.locale = discord.Locale.american_english
        self.guild_locale = discord.Locale.american_english

    @property
    def permissions(self):
        return self.user.guild_permissions if self.guild else discord.Permissions.none()


async def _convert(ctx, interaction, parameter, raw):
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
        raise ValueError(f"`{raw}` is not a valid boolean.")
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


async def _run_checks(command, interaction):
    for check in command.checks:
        result = check(interaction)
        if inspect.isawaitable(result):
            result = await result
        if not result:
            raise commands.CheckFailure("You do not have permission to use this command.")


async def _invoke(ctx, command, text):
    if ctx.guild is None and command.guild_only:
        return await ctx.send("❌ This command can only be used in a server.")

    interaction = PrefixInteraction(ctx, command)
    await _run_checks(command, interaction)

    try:
        tokens = shlex.split(text) if text.strip() else []
    except ValueError as exc:
        return await ctx.send(f"❌ Invalid arguments: {exc}")

    args = [interaction]
    parameters = list(command.parameters)
    position = 0

    for parameter in parameters:
        if position >= len(tokens):
            if not parameter.required:
                default = parameter.default
                args.append(None if default is app_commands.MISSING else default)
                continue
            return await ctx.send(f"❌ Missing required argument: `{parameter.display_name}`")

        # Prefix commands use the remaining text for a final string argument when it
        # has a default/description pattern that commonly represents a reason/prompt.
        if parameter.type == app_commands.AppCommandOptionType.string and parameter is parameters[-1]:
            raw = " ".join(tokens[position:])
            position = len(tokens)
        else:
            raw = tokens[position]
            position += 1

        try:
            args.append(await _convert(ctx, interaction, parameter, raw))
        except Exception as exc:
            return await ctx.send(f"❌ Invalid value for `{parameter.display_name}`: {exc}")

    try:
        return await command.callback(*args)
    except app_commands.AppCommandError as exc:
        return await ctx.send(f"❌ {exc}")
    except discord.Forbidden:
        return await ctx.send("❌ Discord denied that action. Check the bot's permissions and role hierarchy.")
    except Exception as exc:
        print(f"[PrefixBridge] {command.qualified_name}: {exc!r}")
        return await ctx.send("❌ The command failed while running. Check the bot logs for details.")


def setup(bot: commands.Bot):
    registered = set()

    async def register_all():
        # Re-run after command modules have registered their application commands.
        for command in bot.tree.walk_commands():
            if not isinstance(command, app_commands.Command):
                continue
            if command.name in registered or bot.get_command(command.name):
                continue

            async def prefix_command(ctx, *, _text="", _command=command):
                await _invoke(ctx, _command, _text)

            prefix_command.__name__ = f"prefix_{command.name.replace('-', '_')}"
            prefix_command.__doc__ = command.description or f"Prefix version of /{command.qualified_name}"
            bot.add_command(commands.Command(prefix_command, name=command.name, help=prefix_command.__doc__))
            registered.add(command.name)

    bot._register_prefix_commands = register_all
