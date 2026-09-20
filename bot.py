import os
import time
import threading
import asyncio

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

# Bot owner. This ID is trusted for owner-only bot controls and can invoke
# prefix commands without typing the configured prefix.
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
    # Owner can use every normal prefix command either with or without the
    # prefix. Other users continue to use the normal configured prefix.
    if message.author and message.author.id == OWNER_ID:
        return ["", DEFAULT_PREFIX]
    return DEFAULT_PREFIX

bot = commands.Bot(command_prefix=command_prefix, intents=intents)
bot._air_owner_id = OWNER_ID

# Custom owner helper for commands that need a bot-owner check.
def is_air_owner(user):
    return bool(user and getattr(user, "id", None) == OWNER_ID)

bot.is_air_owner = is_air_owner
start_time = time.time()
bot._air_start_time = start_time

games.setup(bot)
basic_commands.setup(bot)
autosetup.setup(bot)
autorolesetup.setup(bot)

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
