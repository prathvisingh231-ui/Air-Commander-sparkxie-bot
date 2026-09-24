"""
Air Commander - Owner Prefixless Command Compatibility

Owners can use prefixless text commands.
Normal users must use the configured prefix.

Owner IDs:
- 1504354088538869892
- 880350253239373855

Examples:
Owner:
    ping
    purge 10
    kick @user

Normal users:
    ,ping
    ,purge 10
    ,kick @user

Slash commands are unaffected.
"""

import discord
from discord.ext import commands


# ============================================================
# CONFIG
# ============================================================

PREFIX = ","

OWNER_IDS = frozenset({
    1504354088538869892,
    880350253239373855,
})


# ============================================================
# COMMAND PREFIX
# ============================================================

def get_command_prefix(
    bot: commands.Bot,
    message: discord.Message
):
    """
    Return the prefix based on the message author.

    Owners:
        No prefix required.

    Everyone else:
        Normal configured prefix is required.
    """

    # Ignore messages without an author
    if message.author is None:
        return PREFIX

    # Owner can use commands without prefix
    if message.author.id in OWNER_IDS:
        return ""

    # Everyone else uses normal prefix
    return PREFIX


# ============================================================
# INTENTS
# ============================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True


# ============================================================
# BOT
# ============================================================

bot = commands.Bot(
    command_prefix=get_command_prefix,
    intents=intents,
)


# ============================================================
# READY
# ============================================================

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} ({bot.user.id})")
    print(f"✅ Normal prefix: {PREFIX}")
    print("✅ Owner prefixless commands: ENABLED")


# ============================================================
# TEST COMMAND
# ============================================================

@bot.command(name="ping")
async def ping(ctx: commands.Context):
    latency = round(bot.latency * 1000)

    await ctx.send(
        f"🏓 Pong! `{latency}ms`"
    )


# ============================================================
# OPTIONAL ERROR HANDLER
# ============================================================

@bot.event
async def on_command_error(
    ctx: commands.Context,
    error: commands.CommandError
):
    # Ignore unknown commands.
    # This prevents unnecessary error messages.
    if isinstance(error, commands.CommandNotFound):
        return

    # Ignore missing permissions if you already handle
    # permissions inside individual commands.
    if isinstance(error, commands.CheckFailure):
        return

    print(
        f"⚠️ Command error in "
        f"{getattr(ctx.command, 'name', 'unknown')}: "
        f"{type(error).__name__}: {error}"
    )


# ============================================================
# START BOT
# ============================================================

# Put your existing token here / load it from environment.
#
# TOKEN = os.getenv("DISCORD_TOKEN")
# bot.run(TOKEN)
