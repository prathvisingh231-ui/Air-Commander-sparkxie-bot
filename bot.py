import os
import time
import threading
import asyncio
import io
from datetime import datetime, timezone

from flask import Flask
import discord
import db
import games
import basic_commands
import autosetup
import autorolesetup
from discord import app_commands
from discord.ext import commands


# =========================================================
# CONFIGURATION
# =========================================================
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is required")


# =========================================================
# WEB / HEALTH SERVER
# =========================================================
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


# =========================================================
# BOT CONFIGURATION
# =========================================================
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


# =========================================================
# BOT READY
# =========================================================
@bot.event
async def on_ready():
    print(f"✈️ Logged in as {bot.user} (ID: {bot.user.id})")
    await db.init_db()
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"✅ Synced {len(synced)} slash commands to guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"✅ Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"❌ Command sync failed: {e}")


# =========================================================
# PREFIX COMMANDS — EXISTING COMMANDS
# Prefix: ,
# =========================================================
def prefix_embed(title, description="", color=discord.Color.blurple()):
    return discord.Embed(title=title, description=description, color=color, timestamp=datetime.now(timezone.utc))

@bot.command(name="about")
async def prefix_about(ctx):
    e = prefix_embed("✈️ About Air Commander", "Advanced Discord security, moderation and utility system.")
    e.add_field(name="🤖 Bot", value="Air Commander", inline=True)
    e.add_field(name="⚡ Prefix", value="`,`", inline=True)
    e.add_field(name="🌐 Servers", value=str(len(bot.guilds)), inline=True)
    e.add_field(name="👥 Users", value=str(len(bot.users)), inline=True)
    if bot.user:
        e.set_thumbnail(url=bot.user.display_avatar.url)
    e.set_footer(text=f"Requested by {ctx.author}")
    await ctx.send(embed=e)

@bot.command(name="serverinfo")
async def prefix_serverinfo(ctx):
    if not ctx.guild:
        return await ctx.send(embed=prefix_embed("Server Only", "This command can only be used in a server.", discord.Color.red()))
    g = ctx.guild
    e = prefix_embed(f"🛡️ {g.name}", f"Server ID: `{g.id}`")
    e.add_field(name="👥 Members", value=str(g.member_count), inline=True)
    e.add_field(name="📁 Channels", value=str(len(g.channels)), inline=True)
    e.add_field(name="🎭 Roles", value=str(len(g.roles)), inline=True)
    await ctx.send(embed=e)


# =========================================================
# STARTUP
# =========================================================
async def start_bot():
    await bot.start(TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    asyncio.run(start_bot())
