"""Air Commander startup compatibility hooks.

Provides prefixless text-command parsing for the two configured bot owners
and loads the isolated Anti-Nuke enable animation without changing command
implementations or slash-command registration.
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
    kwargs["command_prefix"] = _owner_aware_prefix
    _original_bot_init(self, *args, **kwargs)


commands.Bot.__init__ = _patched_bot_init

# Isolated visual enhancement for the existing /antinuke enable response.
# Importing this module installs the narrow InteractionResponse wrapper.
try:
    import antinuke_animation  # noqa: F401
except Exception as exc:
    print(f"⚠️ Anti-Nuke animation unavailable: {type(exc).__name__}: {exc}")
