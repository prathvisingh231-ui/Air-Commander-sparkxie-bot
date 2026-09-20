import os
import time
import threading
import asyncio
import inspect

from flask import Flask
import discord
import db
import games
import basic_commands
import autosetup
import autorolesetup
import security
import antinuke_rollback
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
    # Normal prefix remains comma. Owner may also use the comma-less form.
    if message.author and message.author.id == OWNER_ID:
        return [DEFAULT_PREFIX, ""]
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

# Keep prefix command processing enabled for every message.  Commands in the
# bot's modules are primarily slash commands; prefix aliases are registered by
# those modules when available.  The owner-only bare form is intentionally
# handled here so it never gets confused with ordinary Discord messages.
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
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
    await bot.start(TOKEN)


if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot())
