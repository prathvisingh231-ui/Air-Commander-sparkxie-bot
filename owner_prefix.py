# ============================================================
# AIR COMMANDER — OWNER PREFIXLESS SYSTEM
# File: owner_prefix.py
# ============================================================

import os
import logging

import discord
from discord.ext import commands

log = logging.getLogger("aircommander.owner_prefix")

# Only these two Discord user IDs can invoke prefix commands without ",".
# DISCORD_OWNER_ID may add extra IDs from Render as a comma-separated list.
OWNER_IDS = {
    880350253239373855,
    1549994657944043663,
}


def _get_owner_ids() -> set[int]:
    owner_ids = set(OWNER_IDS)
    raw_owner_ids = os.getenv("DISCORD_OWNER_ID", "")
    for value in raw_owner_ids.split(","):
        value = value.strip()
        if value.isdigit():
            owner_ids.add(int(value))
    return owner_ids


def setup_owner_prefixless(bot: commands.Bot):
    """Let configured owners run existing prefix commands without the comma.

    This does not register duplicate commands or bypass the permissions checks
    already attached to each command. Everyone else must keep using the normal
    comma prefix.
    """
    if getattr(bot, "_air_owner_prefixless_loaded", False):
        log.info("Owner prefixless system is already loaded.")
        return

    bot._air_owner_prefixless_loaded = True

    @bot.listen("on_message")
    async def owner_prefixless_listener(message: discord.Message):
        if message.author.bot or not message.guild:
            return

        is_owner = message.author.id in _get_owner_ids()
        if not is_owner:
            try:
                is_owner = await bot.is_owner(message.author)
            except discord.DiscordException:
                is_owner = False

        if not is_owner:
            return

        text = (message.content or "").strip()
        if not text:
            return

        # Normal prefixed messages are handled by discord.py as usual.
        prefix = await bot.get_prefix(message)
        prefixes = prefix if isinstance(prefix, (list, tuple)) else [prefix]
        if any(text.startswith(p) for p in prefixes if p):
            return

        # Resolve any existing prefix command, including groups/subcommands.
        command_name = text.split(maxsplit=1)[0].lower()
        command = bot.get_command(command_name)
        if command is None:
            return

        # Reuse the existing command and its permission checks; do not duplicate it.
        ctx = await bot.get_context(message)
        if ctx.command is not None:
            return

        from discord.ext.commands.view import StringView

        ctx.command = command
        ctx.invoked_with = command_name
        ctx.prefix = ""
        ctx.view = StringView(text)
        ctx.view.skip_string(command_name)
        ctx.view.skip_ws()

        await bot.invoke(ctx)

    log.info(
        "Owner prefixless system loaded for %s configured owner IDs.",
        len(_get_owner_ids()),
    )
