import os
import asyncio
import threading
import discord
from discord.ext import commands
from flask import Flask

# =========================================================
# WEB HEALTH SERVER (Render Keep-Alive)
# =========================================================
app = Flask('')

@app.route('/')
def home():
    return "🤖 AirCommander Intelligence System is online!"

def run_web():
    port = int(os.getenv('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

# =========================================================
# BOT CONFIGURATION & INTENTS
# =========================================================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(
    command_prefix="!", 
    intents=intents, 
    help_command=None
)

TOKEN = os.getenv('DISCORD_TOKEN')

@bot.event
async def on_ready():
    print(f"=========================================================")
    print(f" 🚀 Logged in as: {bot.user} (ID: {bot.user.id})")
    print(f" 🛡️ AirCommander Intelligence System Active & Secure")
    print(f"=========================================================")
    
    extensions = [
        'basic_commands',
        '02_tickets',
        '03_server_roles',
        '04_logs_automation',
        '05_ai_utility_youtube',
        '06_community_games',
        '07_voice_backup_applications',
        '08_owner_analytics_health'
    ]
    
    for ext in extensions:
        try:
            await bot.load_extension(ext)
            print(f" 📦 Loaded extension: {ext}")
        except Exception as e:
            print(f" ⚠️ Failed to load extension {ext}: {e}")

    try:
        synced = await bot.tree.sync()
        print(f" ✨ Synced {len(synced)} slash commands successfully.")
    except Exception as e:
        print(f" ❌ Failed to sync slash commands: {e}")

# =========================================================
# BOT STARTUP (Strictly at the last)
# =========================================================
def main():
    threading.Thread(
        target=run_web,
        daemon=True,
        name="render-health"
    ).start()

    print(
        f"🌐 Health server starting on "
        f"0.0.0.0:{os.getenv('PORT', '10000')}"
    )

    if not TOKEN:
        print("❌ Error: DISCORD_TOKEN environment variable is missing!")
        return

    bot.run(TOKEN)

if __name__ == "__main__":
    main()
