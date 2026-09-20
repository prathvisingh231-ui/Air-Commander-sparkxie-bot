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
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is required")

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

bot = commands.Bot(command_prefix=",", intents=intents)
start_time = time.time()
bot._air_start_time = start_time

games.setup(bot)
basic_commands.setup(bot)
autosetup.setup(bot)
autorolesetup.setup(bot)
security.setup(bot)

@bot.event
async def on_ready():
    print(f"✈️ Logged in as {bot.user} (ID: {bot.user.id})")
    await db.init_db()
    await security.init_security_db()

    try:
        # Keep one authoritative global registration path. Global slash commands
        # are available in every server where the bot is installed and this avoids
        # duplicate global + guild registrations.
        synced = await bot.tree.sync()
        print(f"✅ Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")

async def start_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot())
