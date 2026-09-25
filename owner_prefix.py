"""
Air Commander — Owner Prefixless Command System

Purpose:
- Normal users continue using the configured prefix, e.g. ,ping
- Bot owners can use commands without a prefix, e.g. ping
- Slash commands are unaffected
- Unknown owner messages are ignored normally
- Only registered text/prefix commands can be executed
- Owner IDs are kept in one place

IMPORTANT:
Add this module after the bot and its prefix commands have been registered.

In bot.py, after your command modules/setup calls, add:

    from owner_prefix import setup_owner_prefixless
    setup_owner_prefixless(bot)

Do NOT add another on_message for this feature in bot.py.
Your existing on_message should continue to end with:

    await bot.process_commands(message)
"""

from __future__ import annotations

import discord
from discord.ext import commands

# Air Commander owners
OWNER_IDS = {
    880350253239373855,
}

# Keep the normal prefix as a fallback.
DEFAULT_PREFIX = ","


def _is_owner(user_id: int) -> bool:
    return user_id in OWNER_IDS


async def owner_aware_prefix(bot: commands.Bot, message: discord.Message):
    """
    Prefix resolver.

    Owners:
        ping
        purge 10
        kick @user
        warn @user testing

    Normal users:
        ,ping
        ,purge 10
        ,kick @user
        ,warn @user testing
    """
    if message.author and _is_owner(message.author.id):
        # Empty prefix lets discord.py parse `ping` directly.
        # Keep the normal prefix too, so owners can still use ,ping.
        return ("", DEFAULT_PREFIX)

    return (DEFAULT_PREFIX,)


def setup_owner_prefixless(bot: commands.Bot):
    """
    Install the owner-aware prefix resolver.

    Call this ONCE after creating the bot.
    """
    bot.command_prefix = lambda b, m: owner_aware_prefix(b, m)

    # Expose the owner IDs for other Air Commander modules if needed.
    bot._air_owner_ids = OWNER_IDS

    return bot


def is_air_owner(user: discord.abc.User | discord.Member) -> bool:
    """Public helper for owner-only checks in other modules."""
    return user.id in OWNER_IDS


def owner_only():
    """Decorator helper for owner-only commands."""

    async def predicate(ctx: commands.Context) -> bool:
        return is_air_owner(ctx.author)

    return commands.check(predicate)
