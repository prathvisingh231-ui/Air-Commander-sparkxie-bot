import os
import time
import threading
from flask import Flask
import discord
import db
import games
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
games.setup(bot)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    await db.init_db()
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

@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return
    try:
        await db.log_activity(message.guild.id, message.channel.id, message.author.id)
    except Exception as e:
        print(f"Activity log error: {e}")
    await bot.process_commands(message)

def air_embed(title, description="", color=None):
    return discord.Embed(title=f"✈️ {title}", description=description, color=color or discord.Color.blurple(), timestamp=discord.utils.utcnow())

@bot.tree.command(name="ghostscan", description="Scan inactive/ghost members")
@app_commands.describe(days="Joined before this many days ago")
async def ghostscan(i, days: app_commands.Range[int,1,365]=30):
    if not i.guild: return await i.response.send_message("Server only.", ephemeral=True)
    await i.response.defer()
    cutoff=discord.utils.utcnow().timestamp()-days*86400
    ghosts=[m for m in i.guild.members if not m.bot and m.joined_at and m.joined_at.timestamp()<cutoff]
    e=air_embed("GhostScan",f"Inactive-member candidates using a {days}-day threshold.",discord.Color.orange())
    e.add_field(name="Scanned",value=str(len(i.guild.members)),inline=True)
    e.add_field(name="Candidates",value=str(len(ghosts)),inline=True)
    e.add_field(name="Note",value="Old joins are candidates. Accurate inactivity uses activity history collected while Air Commander is online.",inline=False)
    if ghosts: e.add_field(name="Candidates",value="\n".join(f"• {m.mention} — joined {discord.utils.format_dt(m.joined_at,'R')}" for m in ghosts[:20]),inline=False)
    await i.followup.send(embed=e)

@bot.tree.command(name="activitymap", description="Show channel/category activity intelligence")
async def activitymap(i):
    if not i.guild: return await i.response.send_message("Server only.", ephemeral=True)
    rows=await db.activity_counts(i.guild.id)
    e=air_embed("ActivityMap","Live activity collected while Air Commander is online.",discord.Color.teal())
    if rows:
        lines=[]
        for row in rows:
            ch=i.guild.get_channel(row["channel_id"])
            if ch: lines.append(f"• {ch.mention} — {row['messages']} messages")
        e.add_field(name="Most Active Channels",value="\n".join(lines) or "No recorded activity yet.",inline=False)
    else: e.add_field(name="Activity",value="No stored activity yet. Start chatting and Air Commander will build the map.",inline=False)
    cats={}
    for ch in i.guild.text_channels:
        key=ch.category.name if ch.category else "No Category"
        cats[key]=cats.get(key,0)+1
    e.add_field(name="Channel Distribution",value="\n".join(f"• {k}: {v} channels" for k,v in sorted(cats.items(),key=lambda x:x[1],reverse=True)[:10]) or "None",inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="membercard", description="Detailed Discord profile and server card")
@app_commands.describe(member="Member to inspect")
async def membercard(i, member: discord.Member=None):
    if not i.guild: return await i.response.send_message("Server only.", ephemeral=True)
    member=member or i.user
    e=air_embed(f"MemberCard • {member.display_name}","Detailed member profile.",discord.Color.blurple())
    e.set_thumbnail(url=member.display_avatar.url)
    e.add_field(name="Identity",value=f"{member.mention}\n{member.id}\nBot: {'Yes' if member.bot else 'No'}",inline=True)
    e.add_field(name="Dates",value=f"Created {discord.utils.format_dt(member.created_at,'R')}\nJoined {discord.utils.format_dt(member.joined_at,'R') if member.joined_at else 'Unknown'}",inline=True)
    e.add_field(name="Roles",value=", ".join(r.mention for r in member.roles[1:])[:1024] or "None",inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="modcase", description="Create a persistent moderation case")
@app_commands.describe(action="Action", target="Target member", reason="Reason", evidence="Evidence/reference")
@app_commands.choices(action=[app_commands.Choice(name=x.title(),value=x) for x in ("warn","kick","ban","timeout","unban","other")])
async def modcase(i, action: app_commands.Choice[str], target: discord.Member, reason: str, evidence: str="Not provided"):
    if not i.guild: return await i.response.send_message("Server only.",ephemeral=True)
    if not i.user.guild_permissions.moderate_members and not i.user.guild_permissions.manage_guild:
        return await i.response.send_message("Moderation permission required.",ephemeral=True)
    code=await db.next_case(i.guild.id,target.id,i.user.id,action.value,reason,evidence)
    e=air_embed(f"ModCase • {code}","Persistent Air Commander moderation record.",discord.Color.red())
    e.add_field(name="Action",value=action.name.upper(),inline=True)
    e.add_field(name="Target",value=f"{target.mention}\n{target.id}",inline=True)
    e.add_field(name="Moderator",value=i.user.mention,inline=True)
    e.add_field(name="Reason",value=reason[:1024],inline=False)
    e.add_field(name="Evidence",value=evidence[:1024],inline=False)
    e.set_footer(text=f"AirCommander Case • {code}")
    await i.response.send_message(embed=e)

@bot.tree.command(name="suggestionlab", description="Create or manage a suggestion")
@app_commands.describe(action="Create, update status, or add staff response", suggestion="Suggestion text for create", suggestion_id="Suggestion number for staff actions", status="New status", staff_response="Staff response")
@app_commands.choices(action=[
    app_commands.Choice(name="Create",value="create"),
    app_commands.Choice(name="Set Status",value="status"),
    app_commands.Choice(name="Staff Response",value="response")
])
@app_commands.choices(status=[
    app_commands.Choice(name="Pending",value="Pending"),
    app_commands.Choice(name="Under Review",value="Under Review"),
    app_commands.Choice(name="Approved",value="Approved"),
    app_commands.Choice(name="Rejected",value="Rejected"),
    app_commands.Choice(name="Implemented",value="Implemented")
])
async def suggestionlab(i, action: app_commands.Choice[str], suggestion: str=None, suggestion_id: int=None, status: app_commands.Choice[str]=None, staff_response: str=None):
    if not i.guild: return await i.response.send_message("Server only.",ephemeral=True)
    if action.value == "create":
        if not suggestion: return await i.response.send_message("Provide suggestion text.",ephemeral=True)
        sid=await db.save_suggestion(i.guild.id,i.user.id,suggestion)
        e=air_embed("SuggestionLab • New Suggestion",suggestion,discord.Color.gold())
        e.add_field(name="Status",value="Pending",inline=True)
        e.add_field(name="Author",value=i.user.mention,inline=True)
        e.add_field(name="Voting",value="👍 Approve    👎 Reject",inline=False)
        if sid: e.set_footer(text=f"Suggestion #{sid} • Staff review")
        await i.response.send_message(embed=e)
        msg=await i.original_response()
        await msg.add_reaction("👍"); await msg.add_reaction("👎")
        return
    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message("Manage Server permission required for staff actions.",ephemeral=True)
    if not suggestion_id: return await i.response.send_message("Provide suggestion_id.",ephemeral=True)
    if action.value=="status" and not status: return await i.response.send_message("Choose a status.",ephemeral=True)
    if action.value=="response" and not staff_response: return await i.response.send_message("Provide staff_response.",ephemeral=True)
    ok=await db.update_suggestion(suggestion_id,i.guild.id,status.value if status else None,staff_response if action.value=="response" else None)
    if not ok: return await i.response.send_message("Suggestion not found.",ephemeral=True)
    e=air_embed(f"SuggestionLab • #{suggestion_id}","Suggestion workflow updated.",discord.Color.green())
    e.add_field(name="Action",value=action.name,inline=True)
    if status: e.add_field(name="Status",value=status.name,inline=True)
    if staff_response: e.add_field(name="Staff Response",value=staff_response[:1024],inline=False)
    await i.response.send_message(embed=e)

@bot.tree.command(name="airscan", description="Generate a full AirCommander intelligence report")
async def airscan(i):
    if not i.guild: return await i.response.send_message("Server only.",ephemeral=True)
    if not i.user.guild_permissions.manage_guild: return await i.response.send_message("Manage Server permission required.",ephemeral=True)
    await i.response.defer()
    g=i.guild
    bots=sum(1 for m in g.members if m.bot)
    admin=[r for r in g.roles if r!=g.default_role and r.permissions.administrator]
    uncategorized=[ch for ch in g.channels if isinstance(ch,(discord.TextChannel,discord.VoiceChannel)) and ch.category is None]
    e=air_embed("AirScan • Intelligence Report",f"Security, moderation, activity and configuration snapshot for {g.name}.",discord.Color.blurple())
    if g.icon: e.set_thumbnail(url=g.icon.url)
    e.add_field(name="MEMBERS",value=f"Total {g.member_count}\nHumans {g.member_count-bots}\nBots {bots}",inline=True)
    e.add_field(name="CHANNELS",value=f"Total {len(g.channels)}\nText {len(g.text_channels)}\nVoice {len(g.voice_channels)}\nCategories {len(g.categories)}",inline=True)
    e.add_field(name="ROLES",value=f"Total {len(g.roles)}\nAdmin roles {len(admin)}",inline=True)
    e.add_field(name="SECURITY",value=("Warning: "+", ".join(r.mention for r in admin[:8]) if admin else "No extra Administrator roles detected"),inline=False)
    e.add_field(name="CONFIGURATION",value=f"Verification {g.verification_level.name}\n2FA moderation {'Enabled' if g.mfa_level else 'Disabled'}\nSystem channel {g.system_channel.mention if g.system_channel else 'None'}",inline=False)
    e.add_field(name="STRUCTURE",value=f"Uncategorized channels {len(uncategorized)}\nText channels {len(g.text_channels)}\nRoles {len(g.roles)}",inline=False)
    e.add_field(name="TICKETS / LOGGING",value="AirScan reports visible Discord configuration. It does not falsely claim to know third-party bot internals.",inline=False)
    e.add_field(name="ACTIVITY",value="Message activity is being collected in PostgreSQL for ActivityMap and future intelligence scans.",inline=False)
    e.set_footer(text="AirCommander Intelligence • Live scan")
    await i.followup.send(embed=e)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    bot.run(TOKEN)
