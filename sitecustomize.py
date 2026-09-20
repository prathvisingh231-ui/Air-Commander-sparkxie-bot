"""Air Commander startup compatibility hook.

Provides prefixless text-command parsing for the two configured bot owners
without changing the existing command implementations or slash commands.
"""

from discord.ext import commands


OWNER_IDS = frozenset({
    1504354088538869892,
    880350253239373855,
})

_original_bot_init = commands.Bot.__init__


def _owner_aware_prefix(bot, message):
    """Return an empty prefix for the owners, otherwise the bot's normal prefix."""
    if getattr(message, "guild", None) is not None:
        author = getattr(message, "author", None)
        if author is not None and getattr(author, "id", None) in OWNER_IDS:
            return ""
    return ","


def _patched_bot_init(self, *args, **kwargs):
    # Preserve the bot's existing constructor configuration, while replacing
    # only the prefix resolver. All command decorators and permission checks
    # remain untouched.
    kwargs["command_prefix"] = _owner_aware_prefix
    _original_bot_init(self, *args, **kwargs)


commands.Bot.__init__ = _patched_bot_init
