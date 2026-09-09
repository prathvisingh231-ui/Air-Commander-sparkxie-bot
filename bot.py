import os
import time
import threading
from flask import Flask
import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN environment variable is required")

# Render Web Service health server
app = Flask(__name__)

@app.get("/")
def home():
    return "Air Commander is online!", 200

@app.get("/health")
def health():
    return {"status": "ok"}, 200

def run_web():
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
start_time = time.time()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        if GUILD_ID:
            guild = discord.Object(id=int(GUILD_ID))
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} slash commands to guild {GUILD_ID}")
        else:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} global slash commands")
    except Exception as e:
        print(f"Command sync failed: {e}")

@bot.tree.command(name="ping", description="Check the bot's latency.")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! 🏓 {round(bot.latency * 1000)}ms")

@bot.tree.command(name="help", description="Show the basic bot commands.")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(title="Air Commander — Commands", color=discord.Color.blurple())
    embed.add_field(name="/ping", value="Check bot latency.", inline=False)
    embed.add_field(name="/help", value="Show this command list.", inline=False)
    embed.add_field(name="/about", value="Show bot information.", inline=False)
    embed.add_field(name="/serverinfo", value="Show server information.", inline=False)
    embed.add_field(name="/userinfo", value="Show user information.", inline=False)
    embed.add_field(name="/avatar", value="Show a user's avatar.", inline=False)
    embed.add_field(name="/uptime", value="Show bot uptime.", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="about", description="Show information about Air Commander.")
async def about(interaction: discord.Interaction):
    embed = discord.Embed(title="Air Commander", description="All-in-one Discord bot.", color=discord.Color.blurple())
    embed.add_field(name="Developer", value="Prithvi", inline=True)
    embed.add_field(name="Servers", value=str(len(bot.guilds)), inline=True)
    embed.add_field(name="Library", value="discord.py", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Show information about this server.")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    if not guild:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="Server ID", value=str(guild.id), inline=False)
    embed.add_field(name="Members", value=str(guild.member_count), inline=True)
    embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
    embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="userinfo", description="Show information about a user.")
@app_commands.describe(user="The user to inspect")
async def userinfo(interaction: discord.Interaction, user: discord.Member | None = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"User Info — {user}", color=discord.Color.blurple())
    embed.set_thumbnail(url=user.display_avatar.url)
    embed.add_field(name="Username", value=str(user), inline=False)
    embed.add_field(name="User ID", value=str(user.id), inline=False)
    embed.add_field(name="Joined Server", value=discord.utils.format_dt(user.joined_at, "F") if user.joined_at else "Unknown", inline=False)
    embed.add_field(name="Account Created", value=discord.utils.format_dt(user.created_at, "F"), inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="Show a user's avatar.")
@app_commands.describe(user="The user whose avatar you want to see")
async def avatar(interaction: discord.Interaction, user: discord.User | None = None):
    user = user or interaction.user
    embed = discord.Embed(title=f"{user.display_name}'s Avatar", color=discord.Color.blurple())
    embed.set_image(url=user.display_avatar.replace(size=1024).url)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="uptime", description="Show how long the bot has been online.")
async def uptime(interaction: discord.Interaction):
    seconds = int(time.time() - start_time)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    await interaction.response.send_message(
        f"⏱️ Uptime: **{days}d {hours}h {minutes}m {seconds}s**"
    )

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
