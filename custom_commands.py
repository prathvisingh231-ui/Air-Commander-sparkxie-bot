"""Air Commander custom_commands compatibility module.

The main bot contains the full custom-command implementation. This module exists
so the feature loader can import it safely without registering duplicate commands.
"""

async def load_custom_commands(bot):
    loader = getattr(bot, "_air_load_custom_commands", None)
    if loader:
        result = loader(bot)
        if hasattr(result, "__await__"):
            await result

def setup(bot):
    # Custom commands are registered by the main bot/cmdmaker implementation.
    # Keeping this hook as a no-op prevents duplicate slash-command registration.
    return None
