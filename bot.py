import os
import time
import threading
import asyncio
from datetime import datetime, timezone

from flask import Flask
import discord
import db
import games
import basic_commands
import autosetup
import autorolesetup
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

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

@bot.event
async def on_ready():
    print(f"✈️ Logged in as {bot.user} (ID: {bot.user.id})")
    await db.init_db()

    try:
        # Global commands can take a while to appear in Discord. During startup,
        # also sync the complete command tree to every connected guild so newly
        # added commands such as /autosetup and /autorolesetup appear immediately.
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"✅ Synced {len(synced)} slash commands to guild {GUILD_ID}")
        else:
            global_synced = await bot.tree.sync()
            print(f"✅ Synced {len(global_synced)} global slash commands")
            for guild in bot.guilds:
                try:
                    bot.tree.copy_global_to(guild=guild)
                    guild_synced = await bot.tree.sync(guild=guild)
                    print(f"✅ Synced {len(guild_synced)} slash commands to {guild.name} ({guild.id})")
                except Exception as guild_error:
                    print(f"⚠️ Guild slash sync failed for {guild.id}: {guild_error}")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")

async def start_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot())
