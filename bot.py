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
    return {
        "status": "ok",
        "discord": bot.is_ready() if "bot" in globals() else False
    }, 200


def run_web():
    port = int(os.getenv("PORT", "10000"))
    app.run(
        host="0.0.0.0",
        port=port,
        threaded=True,
        use_reloader=False
    )


# =========================================================
# BOT CONFIGURATION
# =========================================================

intents = discord.Intents.default()

intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=",",
    intents=intents
)

start_time = time.time()
bot._air_start_time = start_time

games.setup(bot)
basic_commands.setup(bot)


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

            print(
                f"✅ Synced {len(synced)} slash commands "
                f"to guild {GUILD_ID}"
            )

        else:
            synced = await bot.tree.sync()

            print(
                f"✅ Synced {len(synced)} global slash commands"
            )

    except Exception as e:
        print(f"❌ Command sync failed: {e}")



# =========================================================
# PREFIX COMMANDS — MISSING COMMANDS
# Prefix: ,
# =========================================================

from datetime import datetime, timezone


def prefix_embed(title, description="", color=discord.Color.blurple()):
    return discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc)
    )


# =========================================================
# ,about
# =========================================================

@bot.command(name="about")
async def prefix_about(ctx):

    e = prefix_embed(
        "✈️ About Air Commander",
        "Advanced Discord security, moderation and utility system."
    )

    e.add_field(
        name="🤖 Bot",
        value="Air Commander",
        inline=True
    )

    e.add_field(
        name="⚡ Prefix",
        value="`,`",
        inline=True
    )

    e.add_field(
        name="🌐 Servers",
        value=str(len(bot.guilds)),
        inline=True
    )

    e.add_field(
        name="👥 Users",
        value=str(len(bot.users)),
        inline=True
    )

    e.set_thumbnail(url=bot.user.display_avatar.url)

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,serverinfo
# =========================================================

@bot.command(name="serverinfo")
async def prefix_serverinfo(ctx):

    if ctx.guild is None:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Server Only",
                "This command can only be used inside a server.",
                discord.Color.red()
            )
        )

    guild = ctx.guild

    e = prefix_embed(
        f"🏰 {guild.name}",
        "Complete information about this server."
    )

    e.add_field(
        name="👑 Owner",
        value=f"<@{guild.owner_id}>" if guild.owner_id else "Unknown",
        inline=True
    )

    e.add_field(
        name="👥 Members",
        value=str(guild.member_count),
        inline=True
    )

    e.add_field(
        name="💬 Channels",
        value=str(len(guild.channels)),
        inline=True
    )

    e.add_field(
        name="🎭 Roles",
        value=str(len(guild.roles)),
        inline=True
    )

    e.add_field(
        name="😀 Emojis",
        value=str(len(guild.emojis)),
        inline=True
    )

    e.add_field(
        name="🆔 Server ID",
        value=str(guild.id),
        inline=True
    )

    e.add_field(
        name="📅 Created",
        value=discord.utils.format_dt(guild.created_at, "F"),
        inline=False
    )

    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,userinfo
# =========================================================

@bot.command(name="userinfo")
async def prefix_userinfo(
    ctx,
    member: discord.Member = None
):

    member = member or ctx.author

    e = prefix_embed(
        f"👤 User Information",
        f"Information about {member.mention}"
    )

    e.add_field(
        name="🏷️ Username",
        value=str(member),
        inline=True
    )

    e.add_field(
        name="🆔 User ID",
        value=str(member.id),
        inline=True
    )

    e.add_field(
        name="🤖 Bot",
        value="Yes" if member.bot else "No",
        inline=True
    )

    e.add_field(
        name="🎭 Highest Role",
        value=member.top_role.mention,
        inline=True
    )

    e.add_field(
        name="📅 Account Created",
        value=discord.utils.format_dt(
            member.created_at,
            "F"
        ),
        inline=False
    )

    if member.joined_at:
        e.add_field(
            name="📥 Joined Server",
            value=discord.utils.format_dt(
                member.joined_at,
                "F"
            ),
            inline=False
        )

    e.set_thumbnail(
        url=member.display_avatar.url
    )

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,avatar
# =========================================================

@bot.command(name="avatar")
async def prefix_avatar(
    ctx,
    member: discord.Member = None
):

    member = member or ctx.author

    e = prefix_embed(
        f"🖼️ {member.display_name}'s Avatar",
        f"[🔗 Open Full Resolution]({member.display_avatar.url})"
    )

    e.set_image(
        url=member.display_avatar.url
    )

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,uptime
# =========================================================

@bot.command(name="uptime")
async def prefix_uptime(ctx):

    if not hasattr(bot, "start_time"):
        return await ctx.send(
            embed=prefix_embed(
                "⏱️ Uptime",
                "Bot start time is not available.",
                discord.Color.orange()
            )
        )

    delta = datetime.now(
        timezone.utc
    ) - bot.start_time

    days = delta.days

    hours, remainder = divmod(
        delta.seconds,
        3600
    )

    minutes, seconds = divmod(
        remainder,
        60
    )

    e = prefix_embed(
        "⏱️ Air Commander Uptime",
        f"🟢 **{days}d {hours}h {minutes}m {seconds}s**"
    )

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,ghostscan
# =========================================================

@bot.command(name="ghostscan")
async def prefix_ghostscan(
    ctx,
    days: int = 30
):

    if ctx.guild is None:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Server Only",
                "This command can only be used inside a server.",
                discord.Color.red()
            )
        )

    if days < 1 or days > 365:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Invalid Days",
                "Days must be between **1 and 365**.",
                discord.Color.red()
            )
        )

    cutoff = (
        datetime.now(timezone.utc).timestamp()
        - (days * 86400)
    )

    inactive = []

    for member in ctx.guild.members:

        if member.bot:
            continue

        if (
            member.joined_at
            and member.joined_at.timestamp() < cutoff
        ):
            inactive.append(member)

    e = prefix_embed(
        "👻 Ghost Scan",
        f"Members checked against **{days} days** inactivity."
    )

    e.add_field(
        name="👻 Possible Ghost Members",
        value=str(len(inactive)),
        inline=True
    )

    e.add_field(
        name="👥 Total Members",
        value=str(ctx.guild.member_count),
        inline=True
    )

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,activitymap
# =========================================================

@bot.command(name="activitymap")
async def prefix_activitymap(ctx):

    if ctx.guild is None:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Server Only",
                "This command can only be used inside a server.",
                discord.Color.red()
            )
        )

    try:

        counts = await db.activity_counts(
            ctx.guild.id
        )

        if not counts:

            description = (
                "📭 No activity data is available yet."
            )

        else:

            lines = []

            for name, count in counts[:10]:

                lines.append(
                    f"👤 **{name}** — `{count}` activities"
                )

            description = "\n".join(lines)

        e = prefix_embed(
            "📊 Activity Map",
            description
        )

        e.set_footer(
            text=f"Requested by {ctx.author}"
        )

        await ctx.send(embed=e)

    except Exception as ex:

        await ctx.send(
            embed=prefix_embed(
                "❌ Activity Map Error",
                f"Could not load activity data.\n```{ex}```",
                discord.Color.red()
            )
        )


# =========================================================
# ,membercard
# =========================================================

@bot.command(name="membercard")
async def prefix_membercard(
    ctx,
    member: discord.Member = None
):

    member = member or ctx.author

    e = prefix_embed(
        f"🪪 Member Card",
        f"### {member.mention}"
    )

    e.add_field(
        name="🏷️ Username",
        value=str(member),
        inline=True
    )

    e.add_field(
        name="🆔 ID",
        value=str(member.id),
        inline=True
    )

    e.add_field(
        name="🤖 Bot",
        value="Yes" if member.bot else "No",
        inline=True
    )

    e.add_field(
        name="🎭 Highest Role",
        value=member.top_role.mention,
        inline=True
    )

    e.add_field(
        name="📅 Account",
        value=discord.utils.format_dt(
            member.created_at,
            "R"
        ),
        inline=True
    )

    e.add_field(
        name="📥 Joined",
        value=(
            discord.utils.format_dt(
                member.joined_at,
                "R"
            )
            if member.joined_at
            else "Unknown"
        ),
        inline=True
    )

    e.set_thumbnail(
        url=member.display_avatar.url
    )

    e.set_footer(
        text=f"Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# ,modcase
# =========================================================

@bot.command(name="modcase")
async def prefix_modcase(
    ctx,
    action: str,
    target: discord.Member,
    *,
    details: str = None
):

    if ctx.guild is None:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Server Only",
                "This command can only be used inside a server.",
                discord.Color.red()
            )
        )

    if not (
        ctx.author.guild_permissions.moderate_members
        or ctx.author.guild_permissions.manage_guild
    ):
        return await ctx.send(
            embed=prefix_embed(
                "🚫 Permission Denied",
                "You need **Moderate Members** or **Manage Server**.",
                discord.Color.red()
            )
        )

    allowed = {
        "warn",
        "timeout",
        "kick",
        "ban",
        "note"
    }

    action = action.lower()

    if action not in allowed:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Invalid Action",
                "`warn` • `timeout` • `kick` • `ban` • `note`",
                discord.Color.red()
            )
        )

    if not details:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Reason Required",
                "Example:\n"
                "`,modcase warn @User Spamming | evidence`",
                discord.Color.red()
            )
        )

    parts = details.split("|", 1)

    reason = parts[0].strip()

    evidence = (
        parts[1].strip()
        if len(parts) > 1
        else "Not provided"
    )

    try:

        case_id = await db.create_mod_case(
            ctx.guild.id,
            target.id,
            ctx.author.id,
            action,
            reason,
            evidence
        )

        e = prefix_embed(
            "🛡️ Moderation Case Created",
            f"Case **#{case_id}** created successfully.",
            discord.Color.green()
        )

        e.add_field(
            name="🎯 Target",
            value=target.mention,
            inline=True
        )

        e.add_field(
            name="⚔️ Action",
            value=action.title(),
            inline=True
        )

        e.add_field(
            name="📝 Reason",
            value=reason,
            inline=False
        )

        e.add_field(
            name="🔎 Evidence",
            value=evidence,
            inline=False
        )

        await ctx.send(embed=e)

    except Exception as ex:

        await ctx.send(
            embed=prefix_embed(
                "❌ Modcase Error",
                f"```{ex}```",
                discord.Color.red()
            )
        )


# =========================================================
# ,suggestionlab
# =========================================================

@bot.command(name="suggestionlab")
async def prefix_suggestionlab(
    ctx,
    action: str,
    *,
    text: str = None
):

    if ctx.guild is None:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Server Only",
                "This command can only be used inside a server.",
                discord.Color.red()
            )
        )

    action = action.lower()

    # =====================================================
    # CREATE
    # =====================================================

    if action == "create":

        if not text:
            return await ctx.send(
                embed=prefix_embed(
                    "❌ Missing Suggestion",
                    "Example:\n"
                    "`,suggestionlab create Add a music system`",
                    discord.Color.red()
                )
            )

        suggestion_id = await db.create_suggestion(
            ctx.guild.id,
            ctx.author.id,
            text
        )

        e = prefix_embed(
            "💡 Suggestion Created",
            f"Suggestion **#{suggestion_id}** submitted successfully.",
            discord.Color.green()
        )

        e.add_field(
            name="💭 Suggestion",
            value=text,
            inline=False
        )

        await ctx.send(embed=e)

        return

    # =====================================================
    # STAFF CHECK
    # =====================================================

    if not ctx.author.guild_permissions.manage_guild:

        return await ctx.send(
            embed=prefix_embed(
                "🚫 Permission Denied",
                "You need **Manage Server** permission.",
                discord.Color.red()
            )
        )

    if not text:

        return await ctx.send(
            embed=prefix_embed(
                "❌ Missing Arguments",
                "Use:\n"
                "`,suggestionlab status <id> <status>`\n"
                "`,suggestionlab response <id> <response>`",
                discord.Color.red()
            )
        )

    parts = text.split(maxsplit=1)

    try:

        suggestion_id = int(parts[0])

    except ValueError:

        return await ctx.send(
            embed=prefix_embed(
                "❌ Invalid ID",
                "Suggestion ID must be a number.",
                discord.Color.red()
            )
        )

    # =====================================================
    # STATUS
    # =====================================================

    if action == "status":

        if len(parts) < 2:

            return await ctx.send(
                embed=prefix_embed(
                    "❌ Missing Status",
                    "Example:\n"
                    "`,suggestionlab status 12 Approved`",
                    discord.Color.red()
                )
            )

        raw_status = parts[1].strip().lower()

        statuses = {
            "pending": "Pending",
            "under review": "Under Review",
            "approved": "Approved",
            "rejected": "Rejected",
            "implemented": "Implemented"
        }

        status = statuses.get(raw_status)

        if not status:

            return await ctx.send(
                embed=prefix_embed(
                    "❌ Invalid Status",
                    "Available:\n"
                    "`Pending` • `Under Review` • "
                    "`Approved` • `Rejected` • `Implemented`",
                    discord.Color.red()
                )
            )

        await db.update_suggestion(
            ctx.guild.id,
            suggestion_id,
            status=status
        )

        await ctx.send(
            embed=prefix_embed(
                "📌 Suggestion Updated",
                f"Suggestion **#{suggestion_id}** → **{status}**",
                discord.Color.green()
            )
        )

        return

    # =====================================================
    # RESPONSE
    # =====================================================

    if action == "response":

        if len(parts) < 2:

            return await ctx.send(
                embed=prefix_embed(
                    "❌ Missing Response",
                    "Example:\n"
                    "`,suggestionlab response 12 Thanks for the idea!`",
                    discord.Color.red()
                )
            )

        response = parts[1].strip()

        await db.update_suggestion(
            ctx.guild.id,
            suggestion_id,
            staff_response=response
        )

        await ctx.send(
            embed=prefix_embed(
                "💬 Staff Response Added",
                f"Response added to suggestion **#{suggestion_id}**.",
                discord.Color.green()
            )
        )

        return

    await ctx.send(
        embed=prefix_embed(
            "❌ Unknown Action",
            "Available: `create` • `status` • `response`",
            discord.Color.red()
        )
    )


# =========================================================
# ,airscan
# =========================================================

@bot.command(name="airscan")
async def prefix_airscan(ctx):

    if ctx.guild is None:
        return await ctx.send(
            embed=prefix_embed(
                "❌ Server Only",
                "This command can only be used inside a server.",
                discord.Color.red()
            )
        )

    if not ctx.author.guild_permissions.manage_guild:

        return await ctx.send(
            embed=prefix_embed(
                "🚫 Permission Denied",
                "You need **Manage Server** permission.",
                discord.Color.red()
            )
        )

    guild = ctx.guild

    bots = sum(
        1
        for member in guild.members
        if member.bot
    )

    humans = sum(
        1
        for member in guild.members
        if not member.bot
    )

    e = prefix_embed(
        "🛰️ Air Scan",
        f"Security overview for **{guild.name}**."
    )

    e.add_field(
        name="👥 Humans",
        value=str(humans),
        inline=True
    )

    e.add_field(
        name="🤖 Bots",
        value=str(bots),
        inline=True
    )

    e.add_field(
        name="💬 Channels",
        value=str(len(guild.channels)),
        inline=True
    )

    e.add_field(
        name="🎭 Roles",
        value=str(len(guild.roles)),
        inline=True
    )

    e.add_field(
        name="😀 Emojis",
        value=str(len(guild.emojis)),
        inline=True
    )

    e.add_field(
        name="🚀 Boost Level",
        value=str(guild.premium_tier),
        inline=True
    )

    e.set_thumbnail(
        url=guild.icon.url
    ) if guild.icon else None

    e.set_footer(
        text=f"Air Commander • Requested by {ctx.author}"
    )

    await ctx.send(embed=e)


# =========================================================
# /ping
# =========================================================

@bot.tree.command(
    name="ping",
    description="Check the bot's latency."
)
async def ping(interaction: discord.Interaction):

    latency = round(bot.latency * 1000)

    e = discord.Embed(
        title="✈️ Air Commander • Ping Check",
        description=(
            "╭────────────────────╮\n"
            "     **Gateway Status**\n"
            "╰────────────────────╯\n\n"
            "📡 Air Commander is connected "
            "and responding normally."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    e.add_field(
        name="📡 Latency",
        value=f"**{latency} ms**",
        inline=True
    )

    e.add_field(
        name="🟢 Status",
        value="**Operational**",
        inline=True
    )

    e.set_footer(
        text="✈️ Air Commander • Systems Operational"
    )

    await interaction.response.send_message(embed=e)


# =========================================================
# /help
# =========================================================

@bot.tree.command(
    name="help",
    description="Show Air Commander command categories."
)
async def help_command(interaction: discord.Interaction):

    e = discord.Embed(
        title="✈️ Air Commander • Command Center",
        description=(
            "╭────────────────────────╮\n"
            "      **Command Directory**\n"
            "╰────────────────────────╯\n\n"
            "🧭 Explore the available Air Commander "
            "systems below."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    e.add_field(
        name="🛠️ Utility Systems",
        value=(
            "`/ping` `/help` `/about` `/uptime` `/botinfo`\n"
            "`/serverinfo` `/membercount` `/userinfo` `/membercard`\n"
            "`/avatar` `/servericon` `/banner` `/channelinfo` `/roleinfo`"
        ),
        inline=False
    )

    e.add_field(
        name="🛡️ Moderation Systems",
        value=(
            "`/clear` `/kick` `/ban` `/unban` `/timeout` `/untimeout`\n"
            "`/slowmode` `/lock` `/unlock` `/nick` `/role`"
        ),
        inline=False
    )

    e.add_field(
        name="📢 Community Systems",
        value="`/say` `/announce` `/poll`",
        inline=False
    )

    e.add_field(
        name="🛰️ Air Commander Intelligence",
        value=(
            "`/ghostscan` `/activitymap` `/airscan`\n"
            "`/modcase` `/suggestionlab`"
        ),
        inline=False
    )

    e.add_field(
        name="🎮 Games & Fun",
        value=(
            "Use the game commands already installed "
            "by **Air Commander**."
        ),
        inline=False
    )

    e.set_footer(
        text="✈️ Air Commander • Use /help whenever you need the command map"
    )

    await interaction.response.send_message(embed=e)


# =========================================================
# /about
# =========================================================

@bot.tree.command(
    name="about",
    description="Show information about Air Commander."
)
async def about(interaction: discord.Interaction):

    e = discord.Embed(
        title="✈️ Air Commander • About",
        description=(
            "╭────────────────────────╮\n"
            "     **Air Commander System**\n"
            "╰────────────────────────╯\n\n"
            "⚙️ Moderation • Utility • Intelligence • Games"
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    e.add_field(
        name="👨‍💻 Developer",
        value="**Prithvi**",
        inline=True
    )

    e.add_field(
        name="🌐 Servers",
        value=f"**{len(bot.guilds)}**",
        inline=True
    )

    e.add_field(
        name="⚙️ Library",
        value="**discord.py**",
        inline=True
    )

    e.add_field(
        name="🟢 Status",
        value="**Online**",
        inline=True
    )

    e.add_field(
        name="⚡ Slash Commands",
        value=f"**{len(bot.tree.get_commands())}**",
        inline=True
    )

    e.set_footer(
        text="✈️ Air Commander • Built for clean server management"
    )

    await interaction.response.send_message(embed=e)


# =========================================================
# /serverinfo
# =========================================================

@bot.tree.command(
    name="serverinfo",
    description="Show detailed server information."
)
async def serverinfo(interaction: discord.Interaction):

    guild = interaction.guild

    if not guild:
        return await interaction.response.send_message(
            "❌ **This command can only be used inside a server.**",
            ephemeral=True
        )

    bots = sum(
        1 for m in guild.members if m.bot
    )

    e = discord.Embed(
        title=f"✈️ {guild.name} • Server Overview",
        description=(
            "📊 **Server Intelligence Snapshot**\n"
            "A quick overview of this Discord server."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    if guild.icon:
        e.set_thumbnail(url=guild.icon.url)

    e.add_field(
        name="👥 Members",
        value=(
            f"Total • **{guild.member_count}**\n"
            f"Humans • **{guild.member_count - bots}**\n"
            f"Bots • **{bots}**"
        ),
        inline=True
    )

    e.add_field(
        name="🗂️ Structure",
        value=(
            f"Channels • **{len(guild.channels)}**\n"
            f"Roles • **{len(guild.roles)}**\n"
            f"Categories • **{len(guild.categories)}**"
        ),
        inline=True
    )

    e.add_field(
        name="🔐 Security",
        value=(
            f"Verification • **{guild.verification_level.name}**\n"
            f"2FA Moderation • "
            f"**{'Enabled' if guild.mfa_level else 'Disabled'}**"
        ),
        inline=True
    )

    e.add_field(
        name="📅 Created",
        value=discord.utils.format_dt(
            guild.created_at,
            "F"
        ),
        inline=False
    )

    e.set_footer(
        text=f"✈️ Air Commander • Server ID • {guild.id}"
    )

    await interaction.response.send_message(embed=e)


# =========================================================
# /userinfo
# =========================================================

@bot.tree.command(
    name="userinfo",
    description="Show detailed information about a user."
)
@app_commands.describe(
    user="The user to inspect"
)
async def userinfo(
    interaction: discord.Interaction,
    user: discord.Member | None = None
):

    user = user or interaction.user

    e = discord.Embed(
        title=f"✈️ User Profile • {user.display_name}",
        description=(
            f"🔎 Detailed profile information for {user.mention}"
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    e.set_thumbnail(
        url=user.display_avatar.url
    )

    e.add_field(
        name="🪪 Identity",
        value=(
            f"Username • **{user}**\n"
            f"ID • `{user.id}`\n"
            f"Bot • **{'Yes' if user.bot else 'No'}**"
        ),
        inline=True
    )

    e.add_field(
        name="📅 Dates",
        value=(
            f"Created • "
            f"{discord.utils.format_dt(user.created_at, 'R')}\n"
            f"Joined • "
            f"{discord.utils.format_dt(user.joined_at, 'R') if user.joined_at else 'Unknown'}"
        ),
        inline=True
    )

    e.add_field(
        name="👑 Top Role",
        value=user.top_role.mention,
        inline=True
    )

    e.set_footer(
        text=f"✈️ Air Commander • User ID • {user.id}"
    )

    await interaction.response.send_message(
        embed=e
    )


# =========================================================
# /avatar
# =========================================================

@bot.tree.command(
    name="avatar",
    description="Show a user's avatar."
)
@app_commands.describe(
    user="The user whose avatar you want to see"
)
async def avatar(
    interaction: discord.Interaction,
    user: discord.User | None = None
):

    user = user or interaction.user

    e = discord.Embed(
        title=f"🖼️ {user.display_name} • Avatar",
        description="✨ High-resolution profile avatar.",
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    e.set_image(
        url=user.display_avatar.replace(
            size=1024
        ).url
    )

    e.set_footer(
        text=f"✈️ Air Commander • User ID • {user.id}"
    )

    await interaction.response.send_message(
        embed=e
    )


# =========================================================
# /uptime
# =========================================================

@bot.tree.command(
    name="uptime",
    description="Show how long Air Commander has been online."
)
async def uptime(interaction: discord.Interaction):

    seconds = int(
        time.time() - start_time
    )

    days, seconds = divmod(
        seconds,
        86400
    )

    hours, seconds = divmod(
        seconds,
        3600
    )

    minutes, seconds = divmod(
        seconds,
        60
    )

    e = discord.Embed(
        title="✈️ Air Commander • Uptime",
        description=(
            "🟢 **System availability report**\n"
            "Air Commander has remained operational for:"
        ),
        color=discord.Color.green(),
        timestamp=discord.utils.utcnow()
    )

    e.add_field(
        name="⏱️ Online For",
        value=(
            f"**{days}d {hours}h "
            f"{minutes}m {seconds}s**"
        ),
        inline=False
    )

    e.set_footer(
        text="🟢 Air Commander • System continuously monitored"
    )

    await interaction.response.send_message(
        embed=e
    )


# =========================================================
# MESSAGE ACTIVITY LOGGER
# =========================================================

@bot.event
async def on_message(message):

    if message.author.bot or not message.guild:
        return

    try:
        await db.log_activity(
            message.guild.id,
            message.channel.id,
            message.author.id
        )

    except Exception as e:
        print(
            f"⚠️ Activity log error: {e}"
        )

    await bot.process_commands(message)


# =========================================================
# EMBED HELPER
# =========================================================

def air_embed(
    title,
    description="",
    color=None
):

    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=(
            color
            or discord.Color.blurple()
        ),
        timestamp=discord.utils.utcnow()
    )

    e.set_footer(
        text="✈️ Air Commander • Intelligence System"
    )

    return e


# =========================================================
# /ghostscan
# =========================================================

@bot.tree.command(
    name="ghostscan",
    description="Scan inactive/ghost members"
)
@app_commands.describe(
    days="Joined before this many days ago"
)
async def ghostscan(
    i,
    days: app_commands.Range[int, 1, 365] = 30
):

    if not i.guild:
        return await i.response.send_message(
            "❌ **This command can only be used in a server.**",
            ephemeral=True
        )

    await i.response.defer()

    cutoff = (
        discord.utils.utcnow().timestamp()
        - days * 86400
    )

    ghosts = [
        m
        for m in i.guild.members
        if not m.bot
        and m.joined_at
        and m.joined_at.timestamp() < cutoff
    ]

    e = air_embed(
        "GhostScan • Member Intelligence",
        (
            "🔎 Scanning for members who joined "
            f"before the **{days}-day** threshold.\n\n"
            "⚠️ These are candidates only, "
            "not confirmed inactive users."
        ),
        discord.Color.orange()
    )

    e.add_field(
        name="👥 Members Scanned",
        value=f"**{len(i.guild.members)}**",
        inline=True
    )

    e.add_field(
        name="👻 Candidates",
        value=f"**{len(ghosts)}**",
        inline=True
    )

    e.add_field(
        name="🧠 Method",
        value=(
            "Older joins are treated as candidates. "
            "Activity history is based on messages collected "
            "while Air Commander is online."
        ),
        inline=False
    )

    if ghosts:
        e.add_field(
            name="👻 Candidate Members",
            value="\n".join(
                f"• {m.mention} — joined "
                f"{discord.utils.format_dt(m.joined_at, 'R')}"
                for m in ghosts[:20]
            ),
            inline=False
        )

    await i.followup.send(
        embed=e
    )


# =========================================================
# /activitymap
# =========================================================

@bot.tree.command(
    name="activitymap",
    description="Show channel/category activity intelligence"
)
async def activitymap(i):

    if not i.guild:
        return await i.response.send_message(
            "❌ **This command can only be used in a server.**",
            ephemeral=True
        )

    rows = await db.activity_counts(
        i.guild.id
    )

    e = air_embed(
        "ActivityMap • Server Activity",
        (
            "📊 Live activity collected while "
            "**Air Commander** is online."
        ),
        discord.Color.teal()
    )

    lines = []

    for row in rows or []:

        ch = i.guild.get_channel(
            row["channel_id"]
        )

        if ch:
            lines.append(
                f"• {ch.mention} — "
                f"**{row['messages']}** messages"
            )

    e.add_field(
        name="🔥 Most Active Channels",
        value=(
            "\n".join(lines)
            or "📭 No recorded activity yet."
        ),
        inline=False
    )

    cats = {}

    for ch in i.guild.text_channels:

        key = (
            ch.category.name
            if ch.category
            else "No Category"
        )

        cats[key] = cats.get(key, 0) + 1

    e.add_field(
        name="🗂️ Channel Distribution",
        value=(
            "\n".join(
                f"• {k}: **{v}** channels"
                for k, v in sorted(
                    cats.items(),
                    key=lambda x: x[1],
                    reverse=True
                )[:10]
            )
            or "📭 None"
        ),
        inline=False
    )

    await i.response.send_message(
        embed=e
    )


# =========================================================
# /membercard
# =========================================================

@bot.tree.command(
    name="membercard",
    description="Detailed Discord profile and server card"
)
@app_commands.describe(
    member="Member to inspect"
)
async def membercard(
    i,
    member: discord.Member = None
):

    if not i.guild:
        return await i.response.send_message(
            "❌ **This command can only be used in a server.**",
            ephemeral=True
        )

    member = member or i.user

    e = air_embed(
        f"MemberCard • {member.display_name}",
        "🪪 Detailed member profile.",
        discord.Color.blurple()
    )

    e.set_thumbnail(
        url=member.display_avatar.url
    )

    e.add_field(
        name="🪪 Identity",
        value=(
            f"{member.mention}\n"
            f"`{member.id}`\n"
            f"Bot: **{'Yes' if member.bot else 'No'}**"
        ),
        inline=True
    )

    e.add_field(
        name="📅 Dates",
        value=(
            f"Created • "
            f"{discord.utils.format_dt(member.created_at, 'R')}\n"
            f"Joined • "
            f"{discord.utils.format_dt(member.joined_at, 'R') if member.joined_at else 'Unknown'}"
        ),
        inline=True
    )

    e.add_field(
        name="🎭 Roles",
        value=(
            ", ".join(
                r.mention
                for r in member.roles[1:]
            )[:1024]
            or "None"
        ),
        inline=False
    )

    e.set_footer(
        text=f"✈️ Air Commander • Member ID • {member.id}"
    )

    await i.response.send_message(
        embed=e
    )


# =========================================================
# /modcase
# =========================================================

@bot.tree.command(
    name="modcase",
    description="Create a persistent moderation case"
)
@app_commands.describe(
    action="Action",
    target="Target member",
    reason="Reason",
    evidence="Evidence/reference"
)
@app_commands.choices(
    action=[
        app_commands.Choice(
            name=x.title(),
            value=x
        )
        for x in (
            "warn",
            "kick",
            "ban",
            "timeout",
            "unban",
            "other"
        )
    ]
)
async def modcase(
    i,
    action: app_commands.Choice[str],
    target: discord.Member,
    reason: str,
    evidence: str = "Not provided"
):

    if not i.guild:
        return await i.response.send_message(
            "❌ **This command can only be used in a server.**",
            ephemeral=True
        )

    if (
        not i.user.guild_permissions.moderate_members
        and not i.user.guild_permissions.manage_guild
    ):
        return await i.response.send_message(
            "🚫 **Moderation permission required.**",
            ephemeral=True
        )

    code = await db.next_case(
        i.guild.id,
        target.id,
        i.user.id,
        action.value,
        reason,
        evidence
    )

    e = air_embed(
        f"ModCase • {code}",
        (
            "🛡️ Persistent Air Commander "
            "moderation record."
        ),
        discord.Color.red()
    )

    e.add_field(
        name="⚔️ Action",
        value=action.name.upper(),
        inline=True
    )

    e.add_field(
        name="🎯 Target",
        value=f"{target.mention}\n`{target.id}`",
        inline=True
    )

    e.add_field(
        name="👮 Moderator",
        value=i.user.mention,
        inline=True
    )

    e.add_field(
        name="📝 Reason",
        value=reason[:1024],
        inline=False
    )

    e.add_field(
        name="📎 Evidence",
        value=evidence[:1024],
        inline=False
    )

    e.set_footer(
        text=f"✈️ Air Commander • Case • {code}"
    )

    await i.response.send_message(
        embed=e
    )


# =========================================================
# /suggestionlab
# =========================================================

@bot.tree.command(
    name="suggestionlab",
    description="Create or manage a suggestion"
)
@app_commands.describe(
    action="Create, update status, or add staff response",
    suggestion="Suggestion text for create",
    suggestion_id="Suggestion number for staff actions",
    status="New status",
    staff_response="Staff response"
)
@app_commands.choices(
    action=[
        app_commands.Choice(
            name="Create",
            value="create"
        ),
        app_commands.Choice(
            name="Set Status",
            value="status"
        ),
        app_commands.Choice(
            name="Staff Response",
            value="response"
        )
    ]
)
@app_commands.choices(
    status=[
        app_commands.Choice(
            name=x,
            value=x
        )
        for x in (
            "Pending",
            "Under Review",
            "Approved",
            "Rejected",
            "Implemented"
        )
    ]
)
async def suggestionlab(
    i,
    action: app_commands.Choice[str],
    suggestion: str = None,
    suggestion_id: int = None,
    status: app_commands.Choice[str] = None,
    staff_response: str = None
):

    if not i.guild:
        return await i.response.send_message(
            "❌ **This command can only be used in a server.**",
            ephemeral=True
        )

    # -----------------------------------------------------
    # CREATE SUGGESTION
    # -----------------------------------------------------

    if action.value == "create":

        if not suggestion:
            return await i.response.send_message(
                "📝 **Please provide suggestion text.**",
                ephemeral=True
            )

        sid = await db.save_suggestion(
            i.guild.id,
            i.user.id,
            suggestion
        )

        e = air_embed(
            "SuggestionLab • New Suggestion",
            (
                f"💡 **Suggestion submitted by {i.user.mention}**\n\n"
                f"{suggestion}"
            ),
            discord.Color.gold()
        )

        e.add_field(
            name="📌 Status",
            value="🟡 **Pending**",
            inline=True
        )

        e.add_field(
            name="👤 Author",
            value=i.user.mention,
            inline=True
        )

        e.add_field(
            name="🗳️ Voting",
            value="👍 Approve    👎 Reject",
            inline=False
        )

        if sid:
            e.set_footer(
                text=f"✈️ Air Commander • Suggestion #{sid} • Staff Review"
            )

        await i.response.send_message(
            embed=e
        )

        msg = await i.original_response()

        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

        return

    # -----------------------------------------------------
    # STAFF PERMISSION
    # -----------------------------------------------------

    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(
            "🚫 **Manage Server permission required for staff actions.**",
            ephemeral=True
        )

    if not suggestion_id:
        return await i.response.send_message(
            "🔢 **Please provide `suggestion_id`.**",
            ephemeral=True
        )

    if action.value == "status" and not status:
        return await i.response.send_message(
            "📌 **Please choose a status.**",
            ephemeral=True
        )

    if action.value == "response" and not staff_response:
        return await i.response.send_message(
            "💬 **Please provide a staff response.**",
            ephemeral=True
        )

    ok = await db.update_suggestion(
        suggestion_id,
        i.guild.id,
        status.value if status else None,
        staff_response
        if action.value == "response"
        else None
    )

    if not ok:
        return await i.response.send_message(
            "❌ **Suggestion not found.**",
            ephemeral=True
        )

    e = air_embed(
        f"SuggestionLab • #{suggestion_id}",
        "✨ Suggestion workflow updated successfully.",
        discord.Color.green()
    )

    e.add_field(
        name="⚙️ Action",
        value=action.name,
        inline=True
    )

    if status:
        e.add_field(
            name="📌 Status",
            value=status.name,
            inline=True
        )

    if staff_response:
        e.add_field(
            name="💬 Staff Response",
            value=staff_response[:1024],
            inline=False
        )

    e.set_footer(
        text=f"✈️ Air Commander • Suggestion #{suggestion_id}"
    )

    await i.response.send_message(
        embed=e
    )


# =========================================================
# /airscan
# =========================================================

@bot.tree.command(
    name="airscan",
    description="Generate a full AirCommander intelligence report"
)
async def airscan(i):

    if not i.guild:
        return await i.response.send_message(
            "❌ **This command can only be used in a server.**",
            ephemeral=True
        )

    if not i.user.guild_permissions.manage_guild:
        return await i.response.send_message(
            "🚫 **Manage Server permission required.**",
            ephemeral=True
        )

    await i.response.defer()

    g = i.guild

    bots = sum(
        1
        for m in g.members
        if m.bot
    )

    admin = [
        r
        for r in g.roles
        if r != g.default_role
        and r.permissions.administrator
    ]

    uncategorized = [
        ch
        for ch in g.channels
        if isinstance(
            ch,
            (
                discord.TextChannel,
                discord.VoiceChannel
            )
        )
        and ch.category is None
    ]

    e = air_embed(
        "AirScan • Intelligence Report",
        (
            f"🛰️ Security, moderation, activity and "
            f"configuration snapshot for **{g.name}**."
        ),
        discord.Color.blurple()
    )

    if g.icon:
        e.set_thumbnail(
            url=g.icon.url
        )

    e.add_field(
        name="👥 MEMBERS",
        value=(
            f"Total • **{g.member_count}**\n"
            f"Humans • **{g.member_count - bots}**\n"
            f"Bots • **{bots}**"
        ),
        inline=True
    )

    e.add_field(
        name="📚 CHANNELS",
        value=(
            f"Total • **{len(g.channels)}**\n"
            f"Text • **{len(g.text_channels)}**\n"
            f"Voice • **{len(g.voice_channels)}**\n"
            f"Categories • **{len(g.categories)}**"
        ),
        inline=True
    )

    e.add_field(
        name="🎭 ROLES",
        value=(
            f"Total • **{len(g.roles)}**\n"
            f"Admin Roles • **{len(admin)}**"
        ),
        inline=True
    )

    e.add_field(
        name="🔐 SECURITY",
        value=(
            (
                "⚠️ " +
                ", ".join(
                    r.mention
                    for r in admin[:8]
                )
            )
            if admin
            else "🟢 No extra Administrator roles detected"
        ),
        inline=False
    )

    e.add_field(
        name="⚙️ CONFIGURATION",
        value=(
            f"Verification • **{g.verification_level.name}**\n"
            f"2FA Moderation • "
            f"**{'Enabled' if g.mfa_level else 'Disabled'}**\n"
            f"System Channel • "
            f"**{g.system_channel.mention if g.system_channel else 'None'}**"
        ),
        inline=False
    )

    e.add_field(
        name="🗂️ STRUCTURE",
        value=(
            f"Uncategorized channels: "
            f"**{len(uncategorized)}**"
        ),
        inline=False
    )

    e.set_footer(
        text="🛰️ Air Commander • Intelligence Scan Complete"
    )

    await i.followup.send(
        embed=e
    )

# =========================================================
# 🎫 AIR COMMANDER — TICKET DATABASE SYSTEM
# =========================================================

# ---------------------------------------------------------
# 🎫 Ticket Tables
# ---------------------------------------------------------

async def init_ticket_db():

    if not _pool:
        print("⚠️ Ticket database disabled: PostgreSQL pool unavailable.")
        return

    async with _pool.acquire() as conn:

        # =================================================
        # 🎫 TICKET CONFIG
        # =================================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id BIGINT PRIMARY KEY,

                enabled BOOLEAN DEFAULT TRUE,

                category_id BIGINT,
                log_channel_id BIGINT,
                transcript_channel_id BIGINT,

                support_role_ids JSONB DEFAULT '[]'::jsonb,
                admin_role_ids JSONB DEFAULT '[]'::jsonb,

                max_open_tickets INT DEFAULT 1,

                user_can_close BOOLEAN DEFAULT TRUE,
                user_can_reopen BOOLEAN DEFAULT TRUE,

                auto_close_minutes INT DEFAULT 0,
                auto_delete_minutes INT DEFAULT 0,

                channel_name_format TEXT
                    DEFAULT 'ticket-{number}',

                close_message TEXT
                    DEFAULT '🔒 This ticket has been closed.',

                welcome_message TEXT
                    DEFAULT '👋 Hello {user}! Support will be with you shortly.',

                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # =================================================
        # 📝 TICKET TEMPLATES
        # =================================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_templates (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,

                name TEXT NOT NULL,
                description TEXT
                    DEFAULT 'No description provided.',

                emoji TEXT DEFAULT '🎫',

                category_id BIGINT,

                support_role_ids JSONB
                    DEFAULT '[]'::jsonb,

                channel_name_format TEXT
                    DEFAULT 'ticket-{number}',

                max_open_tickets INT DEFAULT 1,

                welcome_message TEXT
                    DEFAULT '👋 Hello {user}! Support will be with you shortly.',

                questions JSONB
                    DEFAULT '[]'::jsonb,

                enabled BOOLEAN DEFAULT TRUE,

                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # =================================================
        # 🧩 TICKET PANELS
        # =================================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_panels (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,

                channel_id BIGINT,
                message_id BIGINT,

                title TEXT
                    DEFAULT '🎫 Contact Support',

                description TEXT
                    DEFAULT 'Select a ticket type below to open a ticket.',

                color BIGINT
                    DEFAULT 5793266,

                thumbnail_url TEXT,
                image_url TEXT,

                footer_text TEXT
                    DEFAULT '✈️ Air Commander',

                template_ids JSONB
                    DEFAULT '[]'::jsonb,

                panel_type TEXT
                    DEFAULT 'buttons',

                enabled BOOLEAN DEFAULT TRUE,

                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # =================================================
        # 🎟️ TICKETS
        # =================================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,

                channel_id BIGINT,
                user_id BIGINT NOT NULL,

                template_id BIGINT,

                ticket_number INT NOT NULL,

                status TEXT
                    DEFAULT 'open',

                claimed_by BIGINT,

                created_at TIMESTAMPTZ DEFAULT NOW(),
                closed_at TIMESTAMPTZ,

                closed_by BIGINT,

                UNIQUE(guild_id, ticket_number)
            );
        """)

        # =================================================
        # 📋 TICKET EVENTS / LOG
        # =================================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_events (
                id BIGSERIAL PRIMARY KEY,

                guild_id BIGINT NOT NULL,

                ticket_id BIGINT,

                event_type TEXT NOT NULL,

                actor_id BIGINT,

                details JSONB
                    DEFAULT '{}'::jsonb,

                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

        # =================================================
        # 🔢 TICKET NUMBER SEQUENCE
        # =================================================

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS ticket_counters (
                guild_id BIGINT PRIMARY KEY,

                last_number INT DEFAULT 0
            );
        """)

    print("✅ Ticket database tables are ready.")


# =========================================================
# 🎫 Ticket Config Helpers
# =========================================================

async def get_ticket_config(guild_id):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM ticket_config
        WHERE guild_id=$1
        """,
        guild_id
    )

    return dict(row) if row else None


async def create_ticket_config(guild_id):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        INSERT INTO ticket_config(guild_id)
        VALUES($1)
        ON CONFLICT(guild_id)
        DO UPDATE SET updated_at=NOW()
        RETURNING *
        """,
        guild_id
    )

    return dict(row)


async def update_ticket_config(
    guild_id,
    **settings
):

    if not _pool or not settings:
        return None

    allowed = {
        "enabled",
        "category_id",
        "log_channel_id",
        "transcript_channel_id",
        "support_role_ids",
        "admin_role_ids",
        "max_open_tickets",
        "user_can_close",
        "user_can_reopen",
        "auto_close_minutes",
        "auto_delete_minutes",
        "channel_name_format",
        "close_message",
        "welcome_message"
    }

    settings = {
        key: value
        for key, value in settings.items()
        if key in allowed
    }

    if not settings:
        return None

    columns = []
    values = []

    for key, value in settings.items():

        if key in {
            "support_role_ids",
            "admin_role_ids"
        }:
            value = json.dumps(value)

        columns.append(
            f"{key}=${len(values) + 2}"
        )

        values.append(value)

    query = f"""
        INSERT INTO ticket_config(guild_id)
        VALUES($1)
        ON CONFLICT(guild_id)
        DO UPDATE SET
            {", ".join(columns)},
            updated_at=NOW()
        RETURNING *
    """

    row = await _pool.fetchrow(
        query,
        guild_id,
        *values
    )

    return dict(row)


# =========================================================
# 🔢 Ticket Number Generator
# =========================================================

async def next_ticket_number(guild_id):

    if not _pool:
        return 1

    async with _pool.acquire() as conn:

        async with conn.transaction():

            number = await conn.fetchval(
                """
                INSERT INTO ticket_counters(
                    guild_id,
                    last_number
                )
                VALUES($1, 1)

                ON CONFLICT(guild_id)
                DO UPDATE SET
                    last_number =
                        ticket_counters.last_number + 1

                RETURNING last_number
                """,
                guild_id
            )

            return int(number)


# =========================================================
# 📝 Ticket Template Helpers
# =========================================================

async def create_ticket_template(
    guild_id,
    name,
    description="No description provided.",
    emoji="🎫",
    category_id=None,
    support_role_ids=None,
    channel_name_format="ticket-{number}",
    max_open_tickets=1,
    welcome_message=None,
    questions=None
):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        INSERT INTO ticket_templates(
            guild_id,
            name,
            description,
            emoji,
            category_id,
            support_role_ids,
            channel_name_format,
            max_open_tickets,
            welcome_message,
            questions
        )
        VALUES(
            $1,$2,$3,$4,$5,$6::jsonb,
            $7,$8,$9,$10::jsonb
        )
        RETURNING *
        """,
        guild_id,
        name,
        description,
        emoji,
        category_id,
        json.dumps(support_role_ids or []),
        channel_name_format,
        max_open_tickets,
        welcome_message
        or "👋 Hello {user}! Support will be with you shortly.",
        json.dumps(questions or [])
    )

    return dict(row)


async def get_ticket_templates(guild_id):

    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM ticket_templates
        WHERE guild_id=$1
        ORDER BY id ASC
        """,
        guild_id
    )

    return [dict(row) for row in rows]


async def get_ticket_template(
    guild_id,
    template_id
):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM ticket_templates
        WHERE guild_id=$1
        AND id=$2
        """,
        guild_id,
        template_id
    )

    return dict(row) if row else None


async def delete_ticket_template(
    guild_id,
    template_id
):

    if not _pool:
        return False

    result = await _pool.execute(
        """
        DELETE FROM ticket_templates
        WHERE guild_id=$1
        AND id=$2
        """,
        guild_id,
        template_id
    )

    return result.endswith("1")


# =========================================================
# 🧩 Ticket Panel Helpers
# =========================================================

async def create_ticket_panel(
    guild_id,
    channel_id=None,
    message_id=None,
    title="🎫 Contact Support",
    description="Select a ticket type below to open a ticket.",
    color=5793266,
    thumbnail_url=None,
    image_url=None,
    footer_text="✈️ Air Commander",
    template_ids=None,
    panel_type="buttons"
):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        INSERT INTO ticket_panels(
            guild_id,
            channel_id,
            message_id,
            title,
            description,
            color,
            thumbnail_url,
            image_url,
            footer_text,
            template_ids,
            panel_type
        )
        VALUES(
            $1,$2,$3,$4,$5,$6,$7,$8,$9,$10::jsonb,$11
        )
        RETURNING *
        """,
        guild_id,
        channel_id,
        message_id,
        title,
        description,
        color,
        thumbnail_url,
        image_url,
        footer_text,
        json.dumps(template_ids or []),
        panel_type
    )

    return dict(row)


async def get_ticket_panels(guild_id):

    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM ticket_panels
        WHERE guild_id=$1
        ORDER BY id ASC
        """,
        guild_id
    )

    return [dict(row) for row in rows]


async def get_ticket_panel(
    guild_id,
    panel_id
):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM ticket_panels
        WHERE guild_id=$1
        AND id=$2
        """,
        guild_id,
        panel_id
    )

    return dict(row) if row else None


async def delete_ticket_panel(
    guild_id,
    panel_id
):

    if not _pool:
        return False

    result = await _pool.execute(
        """
        DELETE FROM ticket_panels
        WHERE guild_id=$1
        AND id=$2
        """,
        guild_id,
        panel_id
    )

    return result.endswith("1")


# =========================================================
# 🎟️ Active Ticket Helpers
# =========================================================

async def create_ticket(
    guild_id,
    channel_id,
    user_id,
    ticket_number,
    template_id=None
):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        INSERT INTO tickets(
            guild_id,
            channel_id,
            user_id,
            template_id,
            ticket_number,
            status
        )
        VALUES($1,$2,$3,$4,$5,'open')
        RETURNING *
        """,
        guild_id,
        channel_id,
        user_id,
        template_id,
        ticket_number
    )

    return dict(row)


async def get_ticket_by_channel(
    guild_id,
    channel_id
):

    if not _pool:
        return None

    row = await _pool.fetchrow(
        """
        SELECT *
        FROM tickets
        WHERE guild_id=$1
        AND channel_id=$2
        AND status='open'
        LIMIT 1
        """,
        guild_id,
        channel_id
    )

    return dict(row) if row else None


async def get_user_open_tickets(
    guild_id,
    user_id
):

    if not _pool:
        return []

    rows = await _pool.fetch(
        """
        SELECT *
        FROM tickets
        WHERE guild_id=$1
        AND user_id=$2
        AND status='open'
        ORDER BY created_at DESC
        """,
        guild_id,
        user_id
    )

    return [dict(row) for row in rows]


async def close_ticket(
    guild_id,
    channel_id,
    closed_by
):

    if not _pool:
        return False

    result = await _pool.execute(
        """
        UPDATE tickets
        SET
            status='closed',
            closed_at=NOW(),
            closed_by=$3
        WHERE guild_id=$1
        AND channel_id=$2
        AND status='open'
        """,
        guild_id,
        channel_id,
        closed_by
    )

    return result.endswith("1")


async def reopen_ticket(
    guild_id,
    channel_id
):

    if not _pool:
        return False

    result = await _pool.execute(
        """
        UPDATE tickets
        SET
            status='open',
            closed_at=NULL,
            closed_by=NULL
        WHERE guild_id=$1
        AND channel_id=$2
        AND status='closed'
        """,
        guild_id,
        channel_id
    )

    return result.endswith("1")


async def claim_ticket(
    guild_id,
    channel_id,
    staff_id
):

    if not _pool:
        return False

    result = await _pool.execute(
        """
        UPDATE tickets
        SET claimed_by=$3
        WHERE guild_id=$1
        AND channel_id=$2
        AND status='open'
        """,
        guild_id,
        channel_id,
        staff_id
    )

    return result.endswith("1")


# =========================================================
# 📋 Ticket Event Logger
# =========================================================

async def log_ticket_event(
    guild_id,
    ticket_id,
    event_type,
    actor_id=None,
    details=None
):

    if not _pool:
        return

    await _pool.execute(
        """
        INSERT INTO ticket_events(
            guild_id,
            ticket_id,
            event_type,
            actor_id,
            details
        )
        VALUES(
            $1,$2,$3,$4,$5::jsonb
        )
        """,
        guild_id,
        ticket_id,
        event_type,
        actor_id,
        json.dumps(details or {})
    )

# =========================================================
# 🎫 TICKET ADMIN CONFIG PANEL
# =========================================================

def ticket_admin_check(member):
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
    )


async def get_or_create_ticket_config(guild_id):
    config = await db.get_ticket_config(guild_id)

    if not config:
        config = await db.create_ticket_config(guild_id)

    return config


def ticket_config_embed(config):
    enabled = config.get("enabled", True)
    category_id = config.get("category_id")
    max_open = config.get("max_open_tickets", 1)
    naming = config.get("ticket_naming", "ticket-{number}")
    support_roles = config.get("support_role_ids", [])
    admin_roles = config.get("admin_role_ids", [])
    log_channel = config.get("log_channel_id")
    transcript_channel = config.get("transcript_channel_id")

    embed = discord.Embed(
        title="🎫 AIR COMMANDER — TICKET CONFIG",
        description=(
            "Configure your complete ticket system from this panel.\n\n"
            "Use the buttons below to edit each section."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    embed.add_field(
        name="⚙️ General",
        value=(
            f"**Status:** {'🟢 Enabled' if enabled else '🔴 Disabled'}\n"
            f"**Max Open:** `{max_open}`\n"
            f"**Naming:** `{naming}`\n"
            f"**Category:** `{category_id or 'Not Set'}`"
        ),
        inline=False
    )

    embed.add_field(
        name="👥 Support Team",
        value=(
            f"**Support Roles:** `{len(support_roles)}`\n"
            f"**Admin Roles:** `{len(admin_roles)}`"
        ),
        inline=True
    )

    embed.add_field(
        name="📄 Logs",
        value=(
            f"**Log Channel:** `{log_channel or 'Not Set'}`\n"
            f"**Transcript:** `{transcript_channel or 'Not Set'}`"
        ),
        inline=True
    )

    embed.set_footer(
        text="Air Commander • Ticket Management"
    )

    return embed


class TicketGeneralModal(discord.ui.Modal, title="⚙️ General Ticket Settings"):

    category_id = discord.ui.TextInput(
        label="Ticket Category ID",
        placeholder="Example: 123456789012345678",
        required=False,
        max_length=30
    )

    max_open = discord.ui.TextInput(
        label="Maximum Open Tickets",
        placeholder="Example: 1",
        required=True,
        max_length=3
    )

    naming = discord.ui.TextInput(
        label="Ticket Channel Naming",
        placeholder="ticket-{number}",
        required=True,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):

        try:
            max_open = int(self.max_open.value)

            if max_open < 1 or max_open > 100:
                raise ValueError

        except ValueError:
            return await interaction.response.send_message(
                "❌ Maximum open tickets must be a number between `1` and `100`.",
                ephemeral=True
            )

        category_id = self.category_id.value.strip()

        if category_id:
            try:
                category_id = int(category_id)
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Category ID must contain only numbers.",
                    ephemeral=True
                )
        else:
            category_id = None

        await db.update_ticket_config(
            interaction.guild.id,
            category_id=category_id,
            max_open_tickets=max_open,
            ticket_naming=self.naming.value.strip()
        )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_config_embed(config),
            view=TicketConfigView()
        )


class TicketSupportModal(discord.ui.Modal, title="👥 Support Team Settings"):

    support_roles = discord.ui.TextInput(
        label="Support Role IDs",
        placeholder="123456789, 987654321",
        required=False,
        max_length=1000
    )

    admin_roles = discord.ui.TextInput(
        label="Ticket Admin Role IDs",
        placeholder="123456789, 987654321",
        required=False,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):

        def parse_ids(value):
            result = []

            for item in value.replace(" ", "").split(","):
                if not item:
                    continue

                try:
                    result.append(int(item))
                except ValueError:
                    raise ValueError

            return result

        try:
            support_roles = parse_ids(self.support_roles.value)
            admin_roles = parse_ids(self.admin_roles.value)
        except ValueError:
            return await interaction.response.send_message(
                "❌ Role IDs must be valid Discord IDs separated by commas.",
                ephemeral=True
            )

        await db.update_ticket_config(
            interaction.guild.id,
            support_role_ids=support_roles,
            admin_role_ids=admin_roles
        )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_config_embed(config),
            view=TicketConfigView()
        )


class TicketLogsModal(discord.ui.Modal, title="📄 Ticket Logs Settings"):

    log_channel = discord.ui.TextInput(
        label="Log Channel ID",
        placeholder="123456789012345678",
        required=False,
        max_length=30
    )

    transcript_channel = discord.ui.TextInput(
        label="Transcript Channel ID",
        placeholder="123456789012345678",
        required=False,
        max_length=30
    )

    async def on_submit(self, interaction: discord.Interaction):

        def parse_channel(value):
            value = value.strip()

            if not value:
                return None

            try:
                return int(value)
            except ValueError:
                return "invalid"

        log_channel = parse_channel(self.log_channel.value)
        transcript_channel = parse_channel(
            self.transcript_channel.value
        )

        if log_channel == "invalid" or transcript_channel == "invalid":
            return await interaction.response.send_message(
                "❌ Channel IDs must contain only numbers.",
                ephemeral=True
            )

        await db.update_ticket_config(
            interaction.guild.id,
            log_channel_id=log_channel,
            transcript_channel_id=transcript_channel
        )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_config_embed(config),
            view=TicketConfigView()
        )


class TicketConfigView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)

    # =========================================================
    # ⚙️ GENERAL
    # =========================================================

    @discord.ui.button(
        label="General",
        emoji="⚙️",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def general(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(interaction.user):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission to use this.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            TicketGeneralModal()
        )

    # =========================================================
    # 👥 SUPPORT
    # =========================================================

    @discord.ui.button(
        label="Support",
        emoji="👥",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def support(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(interaction.user):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission to use this.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            TicketSupportModal()
        )
# =========================================================
# 📝 TEMPLATES
# =========================================================

@discord.ui.button(
    label="Templates",
    emoji="📝",
    style=discord.ButtonStyle.secondary,
    row=1
)
async def templates(
    self,
    interaction: discord.Interaction,
    button: discord.ui.Button
):

    if not ticket_admin_check(interaction.user):
        return await interaction.response.send_message(
            "❌ You need **Manage Server** permission.",
            ephemeral=True
        )

    templates = await db.get_ticket_templates(
        interaction.guild.id
    )

    await interaction.response.edit_message(
        embed=ticket_template_embed(
            interaction.guild,
            templates
        ),
        view=TicketTemplateView()
                                 )
    

# =========================================================
# 🧩 PANELS
# =========================================================

@discord.ui.button(
    label="Panels",
    emoji="🧩",
    style=discord.ButtonStyle.secondary,
    row=1
)
async def panels(
    self,
    interaction: discord.Interaction,
    button: discord.ui.Button
):

    if not ticket_admin_check(interaction.user):
        return await interaction.response.send_message(
            "❌ You need **Manage Server** permission.",
            ephemeral=True
        )

    panels = await db.get_ticket_panels(
        interaction.guild.id
    )

    await interaction.response.edit_message(
        embed=ticket_panels_embed(panels),
        view=TicketPanelManagerView()
    )

    
    # =========================================================
    # 📄 LOGS
    # =========================================================

    @discord.ui.button(
        label="Logs",
        emoji="📄",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def logs(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(interaction.user):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission to use this.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            TicketLogsModal()
        )

    # =========================================================
    # 🔄 ENABLE / DISABLE
    # =========================================================

    @discord.ui.button(
        label="Enable / Disable",
        emoji="🔄",
        style=discord.ButtonStyle.success,
        row=2
    )
    async def toggle(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(interaction.user):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission to use this.",
                ephemeral=True
            )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        current = config.get("enabled", True)

        await db.update_ticket_config(
            interaction.guild.id,
            enabled=not current
        )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_config_embed(config),
            view=TicketConfigView()
        )

    # =========================================================
    # 🔒 CLOSE PANEL
    # =========================================================

    @discord.ui.button(
        label="Close",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        row=3
    )
    async def close_panel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="🎫 Ticket configuration panel closed.",
            embed=None,
            view=None
        )


# =========================================================
# /ticket
# =========================================================

@bot.tree.command(
    name="ticket",
    description="Open the Air Commander ticket management system"
)
@app_commands.describe(
    action="Choose a ticket management action"
)
@app_commands.choices(
    action=[
        app_commands.Choice(
            name="Config Panel",
            value="config"
        ),
        app_commands.Choice(
            name="Setup",
            value="setup"
        )
    ]
)
async def ticket_command(
    interaction: discord.Interaction,
    action: app_commands.Choice[str]
):

    if not interaction.guild:
        return await interaction.response.send_message(
            "❌ This command can only be used inside a server.",
            ephemeral=True
        )

    if not ticket_admin_check(interaction.user):
        return await interaction.response.send_message(
            "❌ You need **Manage Server** permission.",
            ephemeral=True
        )

    if action.value == "config":

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.send_message(
            embed=ticket_config_embed(config),
            view=TicketConfigView(),
            ephemeral=True
        )

    elif action.value == "setup":

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.send_message(
            embed=ticket_config_embed(config),
            view=TicketConfigView(),
            ephemeral=True
        )


# =========================================================
# ,ticket config
# =========================================================

@bot.group(
    name="ticket",
    invoke_without_command=True
)
async def prefix_ticket(ctx):

    if not ctx.guild:
        return

    if not ticket_admin_check(ctx.author):
        return await ctx.send(
            "❌ You need **Manage Server** permission."
        )

    config = await get_or_create_ticket_config(
        ctx.guild.id
    )

    await ctx.send(
        embed=ticket_config_embed(config),
        view=TicketConfigView()
    )


# =========================================================
# ,ticket config
# =========================================================

@prefix_ticket.command(
    name="config"
)
async def prefix_ticket_config(ctx):

    if not ticket_admin_check(ctx.author):
        return await ctx.send(
            "❌ You need **Manage Server** permission."
        )

    config = await get_or_create_ticket_config(
        ctx.guild.id
    )

    await ctx.send(
        embed=ticket_config_embed(config),
        view=TicketConfigView()
    )
# =========================================================
# 📝 TICKET TEMPLATE MANAGER
# =========================================================


def ticket_template_embed(guild, templates):
    embed = discord.Embed(
        title="📝 AIR COMMANDER — TICKET TEMPLATES",
        description=(
            "Create and manage reusable ticket templates.\n\n"
            "Templates can later be attached to ticket panels."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    if not templates:
        embed.add_field(
            name="📭 No Templates",
            value=(
                "No ticket templates have been created yet.\n\n"
                "Click **Create Template** to make your first one."
            ),
            inline=False
        )
    else:
        for template in templates[:20]:
            template_id = template.get("id")
            name = template.get("name", "Unnamed")
            description = template.get(
                "description",
                "No description"
            )
            category_id = template.get("category_id")
            support_roles = template.get(
                "support_role_ids",
                []
            )

            embed.add_field(
                name=f"🎫 {name}",
                value=(
                    f"**ID:** `{template_id}`\n"
                    f"**Description:** {description[:150]}\n"
                    f"**Category:** `{category_id or 'Default'}`\n"
                    f"**Support Roles:** `{len(support_roles)}`"
                ),
                inline=False
            )

    embed.set_footer(
        text="Air Commander • Ticket Templates"
    )

    return embed


class TicketTemplateCreateModal(
    discord.ui.Modal,
    title="📝 Create Ticket Template"
):

    name = discord.ui.TextInput(
        label="Template Name",
        placeholder="Example: Support",
        required=True,
        max_length=50
    )

    description = discord.ui.TextInput(
        label="Template Description",
        placeholder="General support ticket",
        required=True,
        max_length=200
    )

    category_id = discord.ui.TextInput(
        label="Category ID",
        placeholder="Leave empty to use General Ticket Category",
        required=False,
        max_length=30
    )

    support_roles = discord.ui.TextInput(
        label="Support Role IDs",
        placeholder="123456789, 987654321",
        required=False,
        max_length=1000
    )

    welcome_message = discord.ui.TextInput(
        label="Ticket Welcome Message",
        placeholder="Thanks for contacting support!",
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    async def on_submit(self, interaction: discord.Interaction):

        # ---------------------------------------------------------
        # Validate category
        # ---------------------------------------------------------

        category_id = self.category_id.value.strip()

        if category_id:

            try:
                category_id = int(category_id)
            except ValueError:

                return await interaction.response.send_message(
                    "❌ Category ID must contain only numbers.",
                    ephemeral=True
                )

        else:
            category_id = None

        # ---------------------------------------------------------
        # Parse support roles
        # ---------------------------------------------------------

        support_roles = []

        raw_roles = (
            self.support_roles.value
            .replace(" ", "")
            .strip()
        )

        if raw_roles:

            for role_id in raw_roles.split(","):

                if not role_id:
                    continue

                try:
                    support_roles.append(
                        int(role_id)
                    )
                except ValueError:

                    return await interaction.response.send_message(
                        "❌ Support role IDs must be valid Discord IDs.",
                        ephemeral=True
                    )

        # ---------------------------------------------------------
        # Create template
        # ---------------------------------------------------------

        try:

            await db.create_ticket_template(
                interaction.guild.id,
                self.name.value.strip(),
                self.description.value.strip(),
                category_id=category_id,
                support_role_ids=support_roles,
                welcome_message=self.welcome_message.value.strip()
                or "Thanks for contacting support!"
            )

        except Exception as e:

            print(
                f"❌ Ticket template creation error: {e}"
            )

            return await interaction.response.send_message(
                "❌ Failed to create the ticket template.",
                ephemeral=True
            )

        templates = await db.get_ticket_templates(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_template_embed(
                interaction.guild,
                templates
            ),
            view=TicketTemplateView()
        )


class TicketTemplateDeleteSelect(
    discord.ui.Select
):

    def __init__(self, templates):

        options = []

        for template in templates[:25]:

            options.append(
                discord.SelectOption(
                    label=template.get(
                        "name",
                        "Unnamed"
                    )[:100],
                    description=(
                        template.get(
                            "description",
                            "Ticket template"
                        )[:100]
                    ),
                    value=str(
                        template.get("id")
                    ),
                    emoji="🎫"
                )
            )

        super().__init__(
            placeholder="🗑️ Select a template to delete...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        template_id = int(
            self.values[0]
        )

        template = await db.get_ticket_template(
            interaction.guild.id,
            template_id
        )

        if not template:

            return await interaction.response.send_message(
                "❌ Template not found.",
                ephemeral=True
            )

        await db.delete_ticket_template(
            interaction.guild.id,
            template_id
        )

        templates = await db.get_ticket_templates(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_template_embed(
                interaction.guild,
                templates
            ),
            view=TicketTemplateView()
        )


class TicketTemplateDeleteView(
    discord.ui.View
):

    def __init__(self, templates):

        super().__init__(timeout=120)

        self.add_item(
            TicketTemplateDeleteSelect(
                templates
            )
        )

        back_button = discord.ui.Button(
            label="Back",
            emoji="↩️",
            style=discord.ButtonStyle.secondary
        )

        async def back_callback(
            interaction: discord.Interaction
        ):

            if not ticket_admin_check(
                interaction.user
            ):
                return await interaction.response.send_message(
                    "❌ You need **Manage Server** permission.",
                    ephemeral=True
                )

            templates = await db.get_ticket_templates(
                interaction.guild.id
            )

            await interaction.response.edit_message(
                embed=ticket_template_embed(
                    interaction.guild,
                    templates
                ),
                view=TicketTemplateView()
            )

        back_button.callback = back_callback

        self.add_item(back_button)


class TicketTemplateView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(timeout=300)

    # =========================================================
    # ➕ CREATE TEMPLATE
    # =========================================================

    @discord.ui.button(
        label="Create Template",
        emoji="➕",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def create_template(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            TicketTemplateCreateModal()
        )

    # =========================================================
    # 🗑️ DELETE TEMPLATE
    # =========================================================

    @discord.ui.button(
        label="Delete Template",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=0
    )
    async def delete_template(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        templates = await db.get_ticket_templates(
            interaction.guild.id
        )

        if not templates:

            return await interaction.response.send_message(
                "📭 There are no ticket templates to delete.",
                ephemeral=True
            )

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🗑️ DELETE TICKET TEMPLATE",
                description=(
                    "Select the template you want to delete.\n\n"
                    "⚠️ Deleting a template does not delete "
                    "existing tickets."
                ),
                color=discord.Color.red()
            ),
            view=TicketTemplateDeleteView(
                templates
            )
        )

    # =========================================================
    # 🔄 REFRESH
    # =========================================================

    @discord.ui.button(
        label="Refresh",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        templates = await db.get_ticket_templates(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_template_embed(
                interaction.guild,
                templates
            ),
            view=TicketTemplateView()
        )

    # =========================================================
    # ↩️ BACK
    # =========================================================

    @discord.ui.button(
        label="Back",
        emoji="↩️",
        style=discord.ButtonStyle.primary,
        row=1
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_config_embed(
                config
            ),
            view=TicketConfigView()
        )


# =========================================================
# 🔗 CONNECT TEMPLATES BUTTON TO TEMPLATE MANAGER
# =========================================================

# IMPORTANT:
# Replace the existing "templates" button method inside
# TicketConfigView with this version.

async def open_ticket_templates(
    interaction: discord.Interaction
):

    if not ticket_admin_check(
        interaction.user
    ):
        return await interaction.response.send_message(
            "❌ You need **Manage Server** permission.",
            ephemeral=True
        )

    templates = await db.get_ticket_templates(
        interaction.guild.id
    )

    await interaction.response.edit_message(
        embed=ticket_template_embed(
            interaction.guild,
            templates
        ),
        view=TicketTemplateView()
    )



# =========================================================
# 🧩 TICKET PANEL BUILDER
# =========================================================


def ticket_panel_embed(panel, templates):
    name = panel.get("name", "Unnamed Panel")
    description = panel.get(
        "description",
        "Create a ticket by selecting an option below."
    )

    template_ids = panel.get(
        "template_ids",
        []
    )

    embed = discord.Embed(
        title=f"🧩 {name}",
        description=description,
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    if template_ids:
        template_lines = []

        for template in templates:

            if template.get("id") in template_ids:
                template_lines.append(
                    f"🎫 **{template.get('name', 'Unnamed')}**"
                )

        if template_lines:
            embed.add_field(
                name="🎫 Available Tickets",
                value="\n".join(template_lines),
                inline=False
            )

    else:
        embed.add_field(
            name="📭 No Templates",
            value="No ticket templates have been attached yet.",
            inline=False
        )

    embed.set_footer(
        text="Air Commander • Ticket Support"
    )

    return embed


class TicketPanelCreateModal(
    discord.ui.Modal,
    title="🧩 Create Ticket Panel"
):

    name = discord.ui.TextInput(
        label="Panel Name",
        placeholder="Example: Support Center",
        required=True,
        max_length=80
    )

    description = discord.ui.TextInput(
        label="Panel Description",
        placeholder="Choose the type of ticket you need.",
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=1000
    )

    channel_id = discord.ui.TextInput(
        label="Send Panel To Channel ID",
        placeholder="123456789012345678",
        required=False,
        max_length=30
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        channel_id = self.channel_id.value.strip()

        if channel_id:

            try:
                channel_id = int(channel_id)

            except ValueError:

                return await interaction.response.send_message(
                    "❌ Channel ID must contain only numbers.",
                    ephemeral=True
                )

        else:
            channel_id = None

        try:

            await db.create_ticket_panel(
                interaction.guild.id,
                self.name.value.strip(),
                self.description.value.strip(),
                channel_id=channel_id,
                template_ids=[]
            )

        except Exception as e:

            print(
                f"❌ Ticket panel creation error: {e}"
            )

            return await interaction.response.send_message(
                "❌ Failed to create ticket panel.",
                ephemeral=True
            )

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_panels_embed(
                panels
            ),
            view=TicketPanelManagerView()
        )


def ticket_panels_embed(panels):

    embed = discord.Embed(
        title="🧩 AIR COMMANDER — TICKET PANELS",
        description=(
            "Create and manage ticket panels.\n\n"
            "Panels can contain multiple reusable ticket templates."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    if not panels:

        embed.add_field(
            name="📭 No Panels",
            value=(
                "No ticket panels have been created yet.\n\n"
                "Click **Create Panel** to create one."
            ),
            inline=False
        )

    else:

        for panel in panels[:20]:

            panel_id = panel.get("id")
            name = panel.get(
                "name",
                "Unnamed Panel"
            )

            description = panel.get(
                "description",
                "No description"
            )

            channel_id = panel.get(
                "channel_id"
            )

            template_ids = panel.get(
                "template_ids",
                []
            )

            embed.add_field(
                name=f"🧩 {name}",
                value=(
                    f"**ID:** `{panel_id}`\n"
                    f"**Description:** {description[:150]}\n"
                    f"**Channel:** `{channel_id or 'Not Set'}`\n"
                    f"**Templates:** `{len(template_ids)}`"
                ),
                inline=False
            )

    embed.set_footer(
        text="Air Commander • Ticket Panel Manager"
    )

    return embed


# =========================================================
# 🎫 TEMPLATE SELECT FOR PANEL
# =========================================================

class TicketPanelTemplateSelect(
    discord.ui.Select
):

    def __init__(
        self,
        panel_id,
        templates
    ):

        self.panel_id = panel_id

        options = []

        for template in templates[:25]:

            options.append(
                discord.SelectOption(
                    label=template.get(
                        "name",
                        "Unnamed"
                    )[:100],
                    description=template.get(
                        "description",
                        "Ticket template"
                    )[:100],
                    value=str(
                        template.get("id")
                    ),
                    emoji="🎫"
                )
            )

        super().__init__(
            placeholder="🎫 Select templates for this panel...",
            min_values=1,
            max_values=min(
                len(options),
                25
            ),
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        template_ids = [
            int(value)
            for value in self.values
        ]

        try:

            await db.update_ticket_panel(
                interaction.guild.id,
                self.panel_id,
                template_ids=template_ids
            )

        except Exception as e:

            print(
                f"❌ Panel template update error: {e}"
            )

            return await interaction.response.send_message(
                "❌ Failed to attach templates.",
                ephemeral=True
            )

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_panels_embed(
                panels
            ),
            view=TicketPanelManagerView()
        )


# =========================================================
# 🧩 PANEL TEMPLATE VIEW
# =========================================================

class TicketPanelTemplateView(
    discord.ui.View
):

    def __init__(
        self,
        panel_id,
        templates
    ):

        super().__init__(
            timeout=180
        )

        self.panel_id = panel_id

        if templates:

            self.add_item(
                TicketPanelTemplateSelect(
                    panel_id,
                    templates
                )
            )

        back_button = discord.ui.Button(
            label="Back",
            emoji="↩️",
            style=discord.ButtonStyle.secondary
        )

        async def back_callback(
            interaction: discord.Interaction
        ):

            if not ticket_admin_check(
                interaction.user
            ):
                return await interaction.response.send_message(
                    "❌ You need **Manage Server** permission.",
                    ephemeral=True
                )

            panels = await db.get_ticket_panels(
                interaction.guild.id
            )

            await interaction.response.edit_message(
                embed=ticket_panels_embed(
                    panels
                ),
                view=TicketPanelManagerView()
            )

        back_button.callback = back_callback

        self.add_item(
            back_button
        )


# =========================================================
# 🗑️ PANEL DELETE SELECT
# =========================================================

class TicketPanelDeleteSelect(
    discord.ui.Select
):

    def __init__(
        self,
        panels
    ):

        options = []

        for panel in panels[:25]:

            options.append(
                discord.SelectOption(
                    label=panel.get(
                        "name",
                        "Unnamed Panel"
                    )[:100],
                    description=(
                        panel.get(
                            "description",
                            "Ticket panel"
                        )[:100]
                    ),
                    value=str(
                        panel.get("id")
                    ),
                    emoji="🧩"
                )
            )

        super().__init__(
            placeholder="🗑️ Select a panel to delete...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panel_id = int(
            self.values[0]
        )

        panel = await db.get_ticket_panel(
            interaction.guild.id,
            panel_id
        )

        if not panel:

            return await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )

        await db.delete_ticket_panel(
            interaction.guild.id,
            panel_id
        )

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_panels_embed(
                panels
            ),
            view=TicketPanelManagerView()
        )


# =========================================================
# 🧩 PANEL MANAGER VIEW
# =========================================================

class TicketPanelManagerView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=300
        )

    # =========================================================
    # ➕ CREATE PANEL
    # =========================================================

    @discord.ui.button(
        label="Create Panel",
        emoji="➕",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def create_panel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            TicketPanelCreateModal()
        )

    # =========================================================
    # 🎫 ADD TEMPLATES
    # =========================================================

    @discord.ui.button(
        label="Add Templates",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def add_templates(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        if not panels:

            return await interaction.response.send_message(
                "📭 Create a panel first.",
                ephemeral=True
            )

        templates = await db.get_ticket_templates(
            interaction.guild.id
        )

        if not templates:

            return await interaction.response.send_message(
                "📭 Create at least one ticket template first.",
                ephemeral=True
            )

        options = []

        for panel in panels[:25]:

            options.append(
                discord.SelectOption(
                    label=panel.get(
                        "name",
                        "Unnamed Panel"
                    )[:100],
                    description="Choose this panel",
                    value=str(
                        panel.get("id")
                    ),
                    emoji="🧩"
                )
            )

        select = discord.ui.Select(
            placeholder="🧩 Select a panel...",
            options=options,
            min_values=1,
            max_values=1
        )

        async def select_callback(
            select_interaction
        ):

            panel_id = int(
                select.values[0]
            )

            await select_interaction.response.edit_message(
                embed=discord.Embed(
                    title="🎫 ADD TEMPLATES TO PANEL",
                    description=(
                        "Select the ticket templates you "
                        "want to attach to this panel."
                    ),
                    color=discord.Color.blurple()
                ),
                view=TicketPanelTemplateView(
                    panel_id,
                    templates
                )
            )

        select.callback = select_callback

        view = discord.ui.View(
            timeout=180
        )

        view.add_item(select)

        await interaction.response.send_message(
            "🧩 Select the panel you want to edit:",
            view=view,
            ephemeral=True
        )

    # =========================================================
    # 🗑️ DELETE PANEL
    # =========================================================

    @discord.ui.button(
        label="Delete Panel",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=1
    )
    async def delete_panel(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        if not panels:

            return await interaction.response.send_message(
                "📭 There are no panels to delete.",
                ephemeral=True
            )

        view = discord.ui.View(
            timeout=120
        )

        view.add_item(
            TicketPanelDeleteSelect(
                panels
            )
        )

        await interaction.response.send_message(
            "🗑️ Select the panel you want to delete:",
            view=view,
            ephemeral=True
        )

    # =========================================================
    # 🔄 REFRESH
    # =========================================================

    @discord.ui.button(
        label="Refresh",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_panels_embed(
                panels
            ),
            view=TicketPanelManagerView()
        )

    # =========================================================
    # ↩️ BACK
    # =========================================================

    @discord.ui.button(
        label="Back",
        emoji="↩️",
        style=discord.ButtonStyle.primary,
        row=2
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_config_embed(
                config
            ),
            view=TicketConfigView()
        )


# =========================================================
# 🔗 CONNECT PANELS BUTTON
# =========================================================

# Replace the existing "panels" method inside
# TicketConfigView with this version.


@discord.ui.button(
    label="Panels",
    emoji="🧩",
    style=discord.ButtonStyle.secondary,
    row=1
)
async def ticket_panels_button(
    self,
    interaction: discord.Interaction,
    button: discord.ui.Button
):

    if not ticket_admin_check(
        interaction.user
    ):
        return await interaction.response.send_message(
            "❌ You need **Manage Server** permission.",
            ephemeral=True
        )

    panels = await db.get_ticket_panels(
        interaction.guild.id
    )

    await interaction.response.edit_message(
        embed=ticket_panels_embed(
            panels
        ),
        view=TicketPanelManagerView()
            )

# =========================================================
# 🎫 ACTUAL TICKET CREATION SYSTEM
# =========================================================


def get_ticket_category(guild, category_id):
    if not category_id:
        return None

    return guild.get_channel(int(category_id))


def get_ticket_support_roles(guild, role_ids):
    roles = []

    for role_id in role_ids or []:
        role = guild.get_role(int(role_id))

        if role:
            roles.append(role)

    return roles


async def create_ticket_channel(
    interaction,
    template
):

    guild = interaction.guild
    user = interaction.user

    # =========================================================
    # ⚙️ LOAD CONFIG
    # =========================================================

    config = await get_or_create_ticket_config(
        guild.id
    )

    if not config.get("enabled", True):
        return None, "❌ The ticket system is currently disabled."

    # =========================================================
    # 🔢 CHECK OPEN TICKET LIMIT
    # =========================================================

    open_tickets = await db.get_user_open_tickets(
        guild.id,
        user.id
    )

    max_open = config.get(
        "max_open_tickets",
        1
    )

    if len(open_tickets) >= max_open:

        return (
            None,
            f"❌ You already have `{len(open_tickets)}` "
            f"open ticket(s). Maximum allowed: `{max_open}`."
        )

    # =========================================================
    # 🎫 TEMPLATE DATA
    # =========================================================

    template_id = template.get("id")

    template_name = template.get(
        "name",
        "Support"
    )

    category_id = template.get(
        "category_id"
    ) or config.get(
        "category_id"
    )

    support_role_ids = template.get(
        "support_role_ids",
        []
    )

    if not support_role_ids:

        support_role_ids = config.get(
            "support_role_ids",
            []
        )

    # =========================================================
    # 🔢 TICKET NUMBER
    # =========================================================

    ticket_number = await db.next_ticket_number(
        guild.id
    )

    naming = config.get(
        "ticket_naming",
        "ticket-{number}"
    )

    channel_name = naming.replace(
        "{number}",
        str(ticket_number)
    )

    channel_name = channel_name.replace(
        "{user}",
        user.name.lower()
    )

    # Discord channel name limit
    channel_name = channel_name[:100]

    # =========================================================
    # 📁 CATEGORY
    # =========================================================

    category = get_ticket_category(
        guild,
        category_id
    )

    # =========================================================
    # 🔐 PERMISSIONS
    # =========================================================

    overwrites = {

        guild.default_role: discord.PermissionOverwrite(
            view_channel=False
        ),

        user: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        ),

        guild.me: discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            manage_channels=True,
            manage_messages=True
        )
    }

    # =========================================================
    # 👥 SUPPORT ROLE PERMISSIONS
    # =========================================================

    support_roles = get_ticket_support_roles(
        guild,
        support_role_ids
    )

    for role in support_roles:

        overwrites[role] = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
            attach_files=True,
            embed_links=True
        )

    # =========================================================
    # 🎫 CREATE CHANNEL
    # =========================================================

    try:

        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            reason=(
                f"Ticket created by {user} "
                f"using template {template_name}"
            )
        )

    except discord.Forbidden:

        return (
            None,
            "❌ I don't have permission to create ticket channels."
        )

    except Exception as e:

        print(
            f"❌ Ticket channel creation error: {e}"
        )

        return (
            None,
            "❌ Failed to create the ticket channel."
        )

    # =========================================================
    # 💾 SAVE TICKET
    # =========================================================

    try:

        ticket = await db.create_ticket(
            guild.id,
            channel.id,
            user.id,
            template_id,
            ticket_number
        )

    except Exception as e:

        print(
            f"❌ Ticket database error: {e}"
        )

        try:
            await channel.delete(
                reason="Ticket database creation failed"
            )
        except Exception:
            pass

        return (
            None,
            "❌ Failed to save the ticket in the database."
        )

    # =========================================================
    # 📨 WELCOME EMBED
    # =========================================================

    welcome_message = template.get(
        "welcome_message",
        "Thanks for contacting support!"
    )

    embed = discord.Embed(
        title=f"🎫 {template_name}",
        description=(
            f"{welcome_message}\n\n"
            f"👤 **Opened by:** {user.mention}\n"
            f"🔢 **Ticket:** `#{ticket_number}`\n\n"
            "A member of the support team will assist you shortly."
        ),
        color=discord.Color.blurple(),
        timestamp=discord.utils.utcnow()
    )

    embed.set_footer(
        text="Air Commander • Ticket System"
    )

    # =========================================================
    # 🔘 TICKET CONTROL VIEW
    # =========================================================

    await channel.send(
        content=(
            " ".join(
                role.mention
                for role in support_roles
            ) if support_roles else None
        ),
        embed=embed,
        view=TicketControlView()
    )

    # =========================================================
    # 📝 LOG EVENT
    # =========================================================

    try:

        await db.log_ticket_event(
            guild.id,
            channel.id,
            user.id,
            "created",
            f"Ticket #{ticket_number} created"
        )

    except Exception as e:

        print(
            f"⚠️ Ticket event log error: {e}"
        )

    return channel, None


# =========================================================
# 🎫 TEMPLATE SELECT MENU
# =========================================================


class TicketTemplateCreateSelect(
    discord.ui.Select
):

    def __init__(
        self,
        templates
    ):

        options = []

        for template in templates[:25]:

            options.append(
                discord.SelectOption(
                    label=template.get(
                        "name",
                        "Support"
                    )[:100],
                    description=template.get(
                        "description",
                        "Create a ticket"
                    )[:100],
                    value=str(
                        template.get("id")
                    ),
                    emoji="🎫"
                )
            )

        super().__init__(
            placeholder="🎫 Choose a ticket type...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        template_id = int(
            self.values[0]
        )

        template = await db.get_ticket_template(
            interaction.guild.id,
            template_id
        )

        if not template:

            return await interaction.response.send_message(
                "❌ This ticket template no longer exists.",
                ephemeral=True
            )

        await interaction.response.defer(
            ephemeral=True
        )

        channel, error = await create_ticket_channel(
            interaction,
            template
        )

        if error:

            return await interaction.followup.send(
                error,
                ephemeral=True
            )

        await interaction.followup.send(
            f"✅ Your ticket has been created: {channel.mention}",
            ephemeral=True
        )


# =========================================================
# 🎫 PUBLIC TICKET PANEL VIEW
# =========================================================


class PublicTicketPanelView(
    discord.ui.View
):

    def __init__(
        self,
        templates
    ):

        super().__init__(
            timeout=None
        )

        if templates:

            self.add_item(
                TicketTemplateCreateSelect(
                    templates
                )
            )


# =========================================================
# 🔘 TICKET CONTROL VIEW
# =========================================================


class TicketControlView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    # =========================================================
    # 🔒 CLOSE
    # =========================================================

    @discord.ui.button(
        label="Close",
        emoji="🔒",
        style=discord.ButtonStyle.danger,
        custom_id="aircommander_ticket_close"
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        ticket = await db.get_ticket_by_channel(
            interaction.guild.id,
            interaction.channel.id
        )

        if not ticket:

            return await interaction.response.send_message(
                "❌ This channel is not a registered ticket.",
                ephemeral=True
            )

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        support_roles = get_ticket_support_roles(
            interaction.guild,
            config.get(
                "support_role_ids",
                []
            )
        )

        is_support = (
            interaction.user.guild_permissions.manage_guild
            or interaction.user.guild_permissions.administrator
            or any(
                role in interaction.user.roles
                for role in support_roles
            )
        )

        if interaction.user.id != ticket.get(
            "user_id"
        ) and not is_support:

            return await interaction.response.send_message(
                "❌ You don't have permission to close this ticket.",
                ephemeral=True
            )

        await interaction.response.defer()

        await db.close_ticket(
            interaction.guild.id,
            interaction.channel.id
        )

        await db.log_ticket_event(
            interaction.guild.id,
            interaction.channel.id,
            interaction.user.id,
            "closed",
            "Ticket closed"
        )

        embed = discord.Embed(
            title="🔒 Ticket Closed",
            description=(
                f"This ticket was closed by "
                f"{interaction.user.mention}.\n\n"
                "Use **Reopen** if you want to reopen it."
            ),
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )

        await interaction.followup.send(
            embed=embed,
            view=TicketClosedView()
        )

        # Remove normal user access after closing
        try:

            ticket_owner = interaction.guild.get_member(
                ticket.get("user_id")
            )

            if ticket_owner:

                await interaction.channel.set_permissions(
                    ticket_owner,
                    view_channel=False,
                    send_messages=False
                )

        except Exception as e:

            print(
                f"⚠️ Ticket permission update error: {e}"
            )

    # =========================================================
    # 👤 CLAIM
    # =========================================================

    @discord.ui.button(
        label="Claim",
        emoji="🙋",
        style=discord.ButtonStyle.primary,
        custom_id="aircommander_ticket_claim"
    )
    async def claim_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        support_roles = get_ticket_support_roles(
            interaction.guild,
            config.get(
                "support_role_ids",
                []
            )
        )

        is_support = (
            interaction.user.guild_permissions.manage_guild
            or interaction.user.guild_permissions.administrator
            or any(
                role in interaction.user.roles
                for role in support_roles
            )
        )

        if not is_support:

            return await interaction.response.send_message(
                "❌ Only the support team can claim tickets.",
                ephemeral=True
            )

        ticket = await db.get_ticket_by_channel(
            interaction.guild.id,
            interaction.channel.id
        )

        if not ticket:

            return await interaction.response.send_message(
                "❌ Ticket record not found.",
                ephemeral=True
            )

        await db.claim_ticket(
            interaction.guild.id,
            interaction.channel.id,
            interaction.user.id
        )

        await db.log_ticket_event(
            interaction.guild.id,
            interaction.channel.id,
            interaction.user.id,
            "claimed",
            f"Ticket claimed by {interaction.user}"
        )

        await interaction.response.send_message(
            f"🙋 **Ticket claimed by {interaction.user.mention}.**"
        )


# =========================================================
# 🔓 CLOSED TICKET VIEW
# =========================================================


class TicketClosedView(
    discord.ui.View
):

    def __init__(self):

        super().__init__(
            timeout=None
        )

    # =========================================================
    # 🔓 REOPEN
    # =========================================================

    @discord.ui.button(
        label="Reopen",
        emoji="🔓",
        style=discord.ButtonStyle.success,
        custom_id="aircommander_ticket_reopen"
    )
    async def reopen_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        support_roles = get_ticket_support_roles(
            interaction.guild,
            config.get(
                "support_role_ids",
                []
            )
        )

        is_support = (
            interaction.user.guild_permissions.manage_guild
            or interaction.user.guild_permissions.administrator
            or any(
                role in interaction.user.roles
                for role in support_roles
            )
        )

        if not is_support:

            return await interaction.response.send_message(
                "❌ Only the support team can reopen this ticket.",
                ephemeral=True
            )

        ticket = await db.get_ticket_by_channel(
            interaction.guild.id,
            interaction.channel.id
        )

        if not ticket:

            return await interaction.response.send_message(
                "❌ Ticket record not found.",
                ephemeral=True
            )

        await db.reopen_ticket(
            interaction.guild.id,
            interaction.channel.id
        )

        ticket_owner = interaction.guild.get_member(
            ticket.get("user_id")
        )

        if ticket_owner:

            await interaction.channel.set_permissions(
                ticket_owner,
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        await db.log_ticket_event(
            interaction.guild.id,
            interaction.channel.id,
            interaction.user.id,
            "reopened",
            "Ticket reopened"
        )

        await interaction.response.send_message(
            f"🔓 Ticket reopened by {interaction.user.mention}."
        )

    # =========================================================
    # 🗑️ DELETE
    # =========================================================

    @discord.ui.button(
        label="Delete",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        custom_id="aircommander_ticket_delete"
    )
    async def delete_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not (
            interaction.user.guild_permissions.manage_guild
            or interaction.user.guild_permissions.administrator
        ):

            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        ticket = await db.get_ticket_by_channel(
            interaction.guild.id,
            interaction.channel.id
        )

        if not ticket:

            return await interaction.response.send_message(
                "❌ Ticket record not found.",
                ephemeral=True
            )

        await db.log_ticket_event(
            interaction.guild.id,
            interaction.channel.id,
            interaction.user.id,
            "deleted",
            "Ticket channel deleted"
        )

        await interaction.response.send_message(
            "🗑️ Deleting this ticket channel..."
        )

        await interaction.channel.delete(
            reason=(
                f"Ticket deleted by "
                f"{interaction.user}"
            )
        )

# =========================================================
# 📤 SEND TICKET PANEL
# =========================================================


async def send_ticket_panel(
    guild,
    panel
):

    panel_id = panel.get("id")

    template_ids = panel.get(
        "template_ids",
        []
    )

    if not template_ids:
        return None, "❌ This panel has no ticket templates attached."

    channel_id = panel.get(
        "channel_id"
    )

    if not channel_id:
        return None, "❌ No channel has been configured for this panel."

    channel = guild.get_channel(
        int(channel_id)
    )

    if not channel:
        return None, "❌ The configured panel channel was not found."

    templates = []

    for template_id in template_ids:

        template = await db.get_ticket_template(
            guild.id,
            int(template_id)
        )

        if template:
            templates.append(template)

    if not templates:
        return None, "❌ None of the attached templates exist."

    embed = ticket_panel_embed(
        panel,
        templates
    )

    view = PublicTicketPanelView(
        templates
    )

    try:

        message = await channel.send(
            embed=embed,
            view=view
        )

    except discord.Forbidden:

        return (
            None,
            "❌ I don't have permission to send messages in that channel."
        )

    except Exception as e:

        print(
            f"❌ Ticket panel send error: {e}"
        )

        return (
            None,
            "❌ Failed to send the ticket panel."
        )

    return message, None


# =========================================================
# 📤 SEND PANEL SELECT
# =========================================================


class TicketPanelSendSelect(
    discord.ui.Select
):

    def __init__(
        self,
        panels
    ):

        options = []

        for panel in panels[:25]:

            options.append(
                discord.SelectOption(
                    label=panel.get(
                        "name",
                        "Unnamed Panel"
                    )[:100],
                    description=(
                        panel.get(
                            "description",
                            "Ticket panel"
                        )[:100]
                    ),
                    value=str(
                        panel.get("id")
                    ),
                    emoji="🧩"
                )
            )

        super().__init__(
            placeholder="📤 Select a panel to send...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panel_id = int(
            self.values[0]
        )

        panel = await db.get_ticket_panel(
            interaction.guild.id,
            panel_id
        )

        if not panel:

            return await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )

        await interaction.response.defer(
            ephemeral=True
        )

        message, error = await send_ticket_panel(
            interaction.guild,
            panel
        )

        if error:

            return await interaction.followup.send(
                error,
                ephemeral=True
            )

        await interaction.followup.send(
            (
                f"✅ **{panel.get('name', 'Ticket Panel')}** "
                f"has been sent successfully.\n"
                f"📨 Message ID: `{message.id}`"
            ),
            ephemeral=True
        )


# =========================================================
# 📤 PANEL SEND VIEW
# =========================================================


class TicketPanelSendView(
    discord.ui.View
):

    def __init__(
        self,
        panels
    ):

        super().__init__(
            timeout=120
        )

        self.add_item(
            TicketPanelSendSelect(
                panels
            )
        )


# =========================================================
# 📤 SEND PANEL BUTTON
# =========================================================

# =========================================================
# 🎨 ADVANCED TICKET PANEL EDITOR
# =========================================================


def hex_to_color(value):
    value = value.strip().replace("#", "")

    if not value:
        return discord.Color.blurple()

    try:
        return discord.Color(int(value, 16))
    except ValueError:
        return None


class TicketPanelEditModal(
    discord.ui.Modal,
    title="🎨 Edit Ticket Panel"
):

    panel_name = discord.ui.TextInput(
        label="Panel Name",
        placeholder="Support Center",
        required=True,
        max_length=80
    )

    panel_description = discord.ui.TextInput(
        label="Panel Description",
        placeholder="Choose a ticket type below.",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=2000
    )

    footer = discord.ui.TextInput(
        label="Footer Text",
        placeholder="Air Commander • Support",
        required=False,
        max_length=200
    )

    color = discord.ui.TextInput(
        label="Embed Color",
        placeholder="#5865F2",
        required=False,
        max_length=7
    )

    image_url = discord.ui.TextInput(
        label="Image URL",
        placeholder="https://example.com/image.png",
        required=False,
        max_length=500
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        panel_id = self.panel_id

        embed_color = hex_to_color(
            self.color.value
        )

        if embed_color is None:

            return await interaction.response.send_message(
                "❌ Invalid hex color. Example: `#5865F2`",
                ephemeral=True
            )

        updates = {
            "name": self.panel_name.value.strip(),
            "description": self.panel_description.value.strip()
        }

        # -----------------------------------------------------
        # Save extra visual settings
        # -----------------------------------------------------

        await db.update_ticket_panel(
            interaction.guild.id,
            panel_id,
            **updates
        )

        panel = await db.get_ticket_panel(
            interaction.guild.id,
            panel_id
        )

        if not panel:

            return await interaction.response.send_message(
                "❌ Panel no longer exists.",
                ephemeral=True
            )

        # -----------------------------------------------------
        # Temporary visual preview
        # -----------------------------------------------------

        embed = discord.Embed(
            title=panel.get(
                "name",
                "Ticket Panel"
            ),
            description=panel.get(
                "description",
                ""
            ),
            color=embed_color
        )

        if self.footer.value.strip():

            embed.set_footer(
                text=self.footer.value.strip()
            )

        if self.image_url.value.strip():

            embed.set_image(
                url=self.image_url.value.strip()
            )

        await interaction.response.edit_message(
            embed=embed,
            view=TicketPanelEditView(
                panel_id
            )
        )

    @classmethod
    def for_panel(
        cls,
        panel
    ):

        modal = cls()

        modal.panel_id = panel.get(
            "id"
        )

        modal.panel_name.default = panel.get(
            "name",
            ""
        )

        modal.panel_description.default = panel.get(
            "description",
            ""
        )

        return modal


# =========================================================
# 🧩 PANEL SELECT FOR EDITING
# =========================================================


class TicketPanelEditSelect(
    discord.ui.Select
):

    def __init__(
        self,
        panels
    ):

        self.panels = panels

        options = []

        for panel in panels[:25]:

            options.append(
                discord.SelectOption(
                    label=panel.get(
                        "name",
                        "Unnamed Panel"
                    )[:100],
                    description=panel.get(
                        "description",
                        "Ticket panel"
                    )[:100],
                    value=str(
                        panel.get("id")
                    ),
                    emoji="🎨"
                )
            )

        super().__init__(
            placeholder="🎨 Select a panel to edit...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panel_id = int(
            self.values[0]
        )

        panel = await db.get_ticket_panel(
            interaction.guild.id,
            panel_id
        )

        if not panel:

            return await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            TicketPanelEditModal.for_panel(
                panel
            )
        )


# =========================================================
# 🎨 PANEL EDIT VIEW
# =========================================================


class TicketPanelEditView(
    discord.ui.View
):

    def __init__(
        self,
        panel_id
    ):

        super().__init__(
            timeout=300
        )

        self.panel_id = panel_id

    # =========================================================
    # 🎫 MANAGE TEMPLATES
    # =========================================================

    @discord.ui.button(
        label="Templates",
        emoji="🎫",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def templates(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        templates = await db.get_ticket_templates(
            interaction.guild.id
        )

        if not templates:

            return await interaction.response.send_message(
                "📭 No ticket templates exist.",
                ephemeral=True
            )

        await interaction.response.edit_message(
            content="🎫 Select the templates for this panel:",
            embed=None,
            view=TicketPanelTemplateView(
                self.panel_id,
                templates
            )
        )

    # =========================================================
    # 📤 SEND PANEL
    # =========================================================

    @discord.ui.button(
        label="Send",
        emoji="📤",
        style=discord.ButtonStyle.success,
        row=0
    )
    async def send(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(
            interaction.user
        ):
            return await interaction.response.send_message(
                "❌ You need **Manage Server** permission.",
                ephemeral=True
            )

        panel = await db.get_ticket_panel(
            interaction.guild.id,
            self.panel_id
        )

        if not panel:

            return await interaction.response.send_message(
                "❌ Panel not found.",
                ephemeral=True
            )

        await interaction.response.defer(
            ephemeral=True
        )

        message, error = await send_ticket_panel(
            interaction.guild,
            panel
        )

        if error:

            return await interaction.followup.send(
                error,
                ephemeral=True
            )

        await interaction.followup.send(
            f"✅ Panel sent successfully: {message.jump_url}",
            ephemeral=True
        )

    # =========================================================
    # ↩️ BACK
    # =========================================================

    @discord.ui.button(
        label="Back",
        emoji="↩️",
        style=discord.ButtonStyle.secondary,
        row=1
    )
    async def back(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        panels = await db.get_ticket_panels(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            content=None,
            embed=ticket_panels_embed(
                panels
            ),
            view=TicketPanelManagerView()
        )


# =========================================================
# 🎨 EDIT PANEL SELECT VIEW
# =========================================================


class TicketPanelEditSelectView(
    discord.ui.View
):

    def __init__(
        self,
        panels
    ):

        super().__init__(
            timeout=180
        )

        self.add_item(
            TicketPanelEditSelect(
                panels
            )
        )


# =========================================================
# 🎨 ADD EDIT BUTTON TO PANEL MANAGER
# =========================================================


    # =========================================================
# 🧾 TICKET TRANSCRIPT GENERATOR
# =========================================================

async def build_ticket_transcript(channel):

    lines = []

    try:

        async for message in channel.history(
            limit=None,
            oldest_first=True
        ):

            # -------------------------------------------------
            # 🕐 Timestamp
            # -------------------------------------------------

            timestamp = discord.utils.format_dt(
                message.created_at,
                "F"
            )

            # -------------------------------------------------
            # 👤 Author
            # -------------------------------------------------

            author = (
                f"{message.author} "
                f"({message.author.id})"
            )

            # -------------------------------------------------
            # 💬 Message Content
            # -------------------------------------------------

            content = (
                message.clean_content
                if message.content
                else ""
            )

            if not content:
                content = "[No text content]"

            # -------------------------------------------------
            # 📎 Attachments
            # -------------------------------------------------

            if message.attachments:

                attachment_urls = "\n".join(
                    f"    📎 {attachment.url}"
                    for attachment in message.attachments
                )

                content += (
                    "\n"
                    + attachment_urls
                )

            # -------------------------------------------------
            # 🔗 Embeds
            # -------------------------------------------------

            if message.embeds:

                for embed in message.embeds:

                    if embed.title:

                        content += (
                            f"\n    "
                            f"[Embed Title: {embed.title}]"
                        )

                    if embed.description:

                        content += (
                            f"\n    "
                            f"[Embed Description: "
                            f"{embed.description}]"
                        )

            # -------------------------------------------------
            # 📝 Final Line
            # -------------------------------------------------

            lines.append(
                f"[{timestamp}] "
                f"{author}: "
                f"{content}"
            )

    except discord.Forbidden:

        lines.append(
            "[ERROR] Bot does not have permission "
            "to read this channel history."
        )

    except discord.HTTPException:

        lines.append(
            "[ERROR] Discord API error while "
            "reading channel history."
        )

    except Exception as e:

        print(
            f"⚠️ Transcript error: {e}"
        )

        lines.append(
            f"[ERROR] Transcript generation failed: {e}"
        )

    if not lines:

        return "No messages were found in this ticket."

    return "\n".join(lines)


# =========================================================
# 📄 CREATE TRANSCRIPT FILE
# =========================================================

def create_transcript_file(
    ticket_number,
    transcript
):

    # Discord upload limit ke liye safety limit
    max_size = 7_500_000

    data = transcript.encode(
        "utf-8",
        errors="replace"
    )

    # ---------------------------------------------------------
    # ⚠️ Large Transcript Protection
    # ---------------------------------------------------------

    if len(data) > max_size:

        warning = (
            "\n\n"
            "==================================================\n"
            "⚠️ TRANSCRIPT TRUNCATED\n"
            "The transcript was too large to fit in one file.\n"
            "==================================================\n"
        ).encode("utf-8")

        data = (
            data[:max_size - len(warning)]
            + warning
        )

    return discord.File(
        fp=io.BytesIO(data),
        filename=(
            f"ticket-{ticket_number}-transcript.txt"
        )
    )

# =========================================================
# 📋 TICKET LOG EMBED
# =========================================================

def build_ticket_log_embed(
    title,
    ticket,
    guild,
    actor=None,
    color=None,
    reason=None
):

    if color is None:

        color = discord.Color.blurple()

    ticket_number = ticket.get(
        "ticket_number",
        "Unknown"
    )

    user_id = ticket.get(
        "user_id"
    )

    channel_id = ticket.get(
        "channel_id"
    )

    embed = discord.Embed(
        title=title,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    # ---------------------------------------------------------
    # 🎫 Ticket
    # ---------------------------------------------------------

    embed.add_field(
        name="🎫 Ticket",
        value=f"`#{ticket_number}`",
        inline=True
    )

    # ---------------------------------------------------------
    # 👤 Owner
    # ---------------------------------------------------------

    if user_id:

        embed.add_field(
            name="👤 Opened By",
            value=f"<@{user_id}>",
            inline=True
        )

    # ---------------------------------------------------------
    # 📁 Channel
    # ---------------------------------------------------------

    if channel_id:

        embed.add_field(
            name="📁 Channel",
            value=f"<#{channel_id}>",
            inline=True
        )

    # ---------------------------------------------------------
    # 🛡️ Actor
    # ---------------------------------------------------------

    if actor:

        embed.add_field(
            name="🛡️ Action By",
            value=actor.mention,
            inline=True
        )

    # ---------------------------------------------------------
    # 📝 Reason
    # ---------------------------------------------------------

    if reason:

        embed.add_field(
            name="📝 Reason",
            value=str(reason)[:1024],
            inline=False
        )

    embed.set_footer(
        text="✈️ Air Commander • Ticket Logs"
    )

    return embed

# =========================================================
# 📋 SEND TICKET LOG
# =========================================================

async def send_ticket_log(
    guild,
    ticket,
    title,
    actor=None,
    color=None,
    reason=None
):

    try:

        config = await get_or_create_ticket_config(
            guild.id
        )

        log_channel_id = config.get(
            "log_channel_id"
        )

        if not log_channel_id:

            return

        log_channel = guild.get_channel(
            int(log_channel_id)
        )

        if not log_channel:

            print(
                "⚠️ Ticket log channel not found."
            )

            return

        embed = build_ticket_log_embed(
            title=title,
            ticket=ticket,
            guild=guild,
            actor=actor,
            color=color,
            reason=reason
        )

        await log_channel.send(
            embed=embed
        )

    except discord.Forbidden:

        print(
            "⚠️ Missing permission to send "
            "ticket logs."
        )

    except discord.HTTPException as e:

        print(
            f"⚠️ Ticket log HTTP error: {e}"
        )

    except Exception as e:

        print(
            f"⚠️ Ticket log error: {e}"
        )
# =========================================================
# 🧾 SEND TICKET TRANSCRIPT
# =========================================================

async def send_ticket_transcript(
    guild,
    ticket,
    transcript
):

    try:

        config = await get_or_create_ticket_config(
            guild.id
        )

        transcript_channel_id = config.get(
            "transcript_channel_id"
        )

        if not transcript_channel_id:

            return False

        transcript_channel = guild.get_channel(
            int(transcript_channel_id)
        )

        if not transcript_channel:

            print(
                "⚠️ Transcript channel not found."
            )

            return False

        ticket_number = ticket.get(
            "ticket_number",
            "unknown"
        )

        user_id = ticket.get(
            "user_id"
        )

        embed = discord.Embed(
            title="🧾 Ticket Transcript",
            description=(
                "A ticket has been closed and "
                "its transcript has been archived."
            ),
            color=discord.Color.orange(),
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="🎫 Ticket",
            value=f"`#{ticket_number}`",
            inline=True
        )

        embed.add_field(
            name="👤 Opened By",
            value=(
                f"<@{user_id}>"
                if user_id
                else "Unknown"
            ),
            inline=True
        )

        embed.add_field(
            name="📁 Channel",
            value=(
                f"<#{ticket.get('channel_id')}>"
                if ticket.get("channel_id")
                else "Unknown"
            ),
            inline=True
        )

        embed.set_footer(
            text="✈️ Air Commander • Transcript Archive"
        )

        file = create_transcript_file(
            ticket_number,
            transcript
        )

        await transcript_channel.send(
            embed=embed,
            file=file
        )

        return True

    except discord.Forbidden:

        print(
            "⚠️ Missing permission to send "
            "ticket transcript."
        )

    except discord.HTTPException as e:

        print(
            f"⚠️ Transcript HTTP error: {e}"
        )

    except Exception as e:

        print(
            f"⚠️ Transcript error: {e}"
        )

    return False

    # =========================================================
# PART 9 — ADVANCED TICKET SETTINGS
# =========================================================

import asyncio
from datetime import datetime, timezone


# =========================================================
# /ticket advanced
# =========================================================

def ticket_advanced_embed(config):
    embed = discord.Embed(
        title="⚙️ Ticket Advanced Settings",
        description=(
            "Configure advanced behaviour of the Air Commander "
            "ticket system from this panel."
        ),
        color=discord.Color.blurple(),
        timestamp=datetime.now(timezone.utc)
    )

    auto_close = config.get("auto_close_minutes", 0)
    auto_delete = config.get("auto_delete_minutes", 0)
    user_close = config.get("user_can_close", True)
    max_open = config.get("max_open_tickets", 1)
    naming = config.get("ticket_naming", "ticket-{number}-{user}")

    embed.add_field(
        name="⏱️ Auto Close",
        value=(
            f"`{auto_close} minutes`"
            if auto_close else "`Disabled`"
        ),
        inline=True
    )

    embed.add_field(
        name="🗑️ Auto Delete",
        value=(
            f"`{auto_delete} minutes`"
            if auto_delete else "`Disabled`"
        ),
        inline=True
    )

    embed.add_field(
        name="👤 User Close",
        value="`Enabled`" if user_close else "`Disabled`",
        inline=True
    )

    embed.add_field(
        name="🎫 Max Open Tickets",
        value=f"`{max_open}`",
        inline=True
    )

    embed.add_field(
        name="🏷️ Naming Format",
        value=f"`{naming}`",
        inline=False
    )

    embed.set_footer(
        text="Air Commander • Ticket Advanced Configuration"
    )

    return embed


# =========================================================
# ADVANCED SETTINGS MODAL
# =========================================================

class TicketAdvancedModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="⚙️ Advanced Ticket Settings")

        self.auto_close = discord.ui.TextInput(
            label="Auto Close Minutes",
            placeholder="0 = Disabled",
            required=False,
            max_length=10
        )

        self.auto_delete = discord.ui.TextInput(
            label="Auto Delete Minutes",
            placeholder="0 = Disabled",
            required=False,
            max_length=10
        )

        self.max_open = discord.ui.TextInput(
            label="Maximum Open Tickets",
            placeholder="Example: 2",
            required=True,
            max_length=5
        )

        self.naming = discord.ui.TextInput(
            label="Ticket Naming Format",
            placeholder="ticket-{number}-{user}",
            required=True,
            max_length=100
        )

        self.user_close = discord.ui.TextInput(
            label="Can User Close Ticket? (yes/no)",
            placeholder="yes",
            required=True,
            max_length=5
        )

        self.add_item(self.auto_close)
        self.add_item(self.auto_delete)
        self.add_item(self.max_open)
        self.add_item(self.naming)
        self.add_item(self.user_close)

    async def on_submit(self, interaction: discord.Interaction):

        if not ticket_admin_check(interaction.user):
            await interaction.response.send_message(
                "❌ You need **Administrator** or **Manage Server** permission.",
                ephemeral=True
            )
            return

        try:
            auto_close = int(
                self.auto_close.value.strip()
                or "0"
            )

            auto_delete = int(
                self.auto_delete.value.strip()
                or "0"
            )

            max_open = int(
                self.max_open.value.strip()
            )

        except ValueError:
            await interaction.response.send_message(
                "❌ Minutes and maximum tickets must be valid numbers.",
                ephemeral=True
            )
            return

        if auto_close < 0 or auto_delete < 0:
            await interaction.response.send_message(
                "❌ Time values cannot be negative.",
                ephemeral=True
            )
            return

        if max_open < 1:
            await interaction.response.send_message(
                "❌ Maximum open tickets must be at least `1`.",
                ephemeral=True
            )
            return

        naming = self.naming.value.strip()

        if not naming:
            naming = "ticket-{number}-{user}"

        user_close = (
            self.user_close.value.strip().lower()
            in ("yes", "y", "true", "on", "1")
        )

        try:
            await db.update_ticket_config(
                interaction.guild.id,
                auto_close_minutes=auto_close,
                auto_delete_minutes=auto_delete,
                max_open_tickets=max_open,
                ticket_naming=naming,
                user_can_close=user_close
            )

        except Exception as e:
            print(f"❌ Advanced ticket config error: {e}")

            await interaction.response.send_message(
                "❌ Failed to save advanced ticket settings.",
                ephemeral=True
            )
            return

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.send_message(
            embed=ticket_advanced_embed(config),
            ephemeral=True
        )


# =========================================================
# ADVANCED SETTINGS VIEW
# =========================================================

class TicketAdvancedView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=300)

    # =====================================================
    # EDIT SETTINGS
    # =====================================================

    @discord.ui.button(
        label="Edit Settings",
        emoji="⚙️",
        style=discord.ButtonStyle.primary,
        custom_id="aircommander_ticket_advanced_edit"
    )
    async def edit_settings(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(interaction.user):
            await interaction.response.send_message(
                "❌ You need **Administrator** or **Manage Server** permission.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            TicketAdvancedModal()
        )

    # =====================================================
    # REFRESH
    # =====================================================

    @discord.ui.button(
        label="Refresh",
        emoji="🔄",
        style=discord.ButtonStyle.secondary,
        custom_id="aircommander_ticket_advanced_refresh"
    )
    async def refresh(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        if not ticket_admin_check(interaction.user):
            await interaction.response.send_message(
                "❌ You don't have permission to use this.",
                ephemeral=True
            )
            return

        config = await get_or_create_ticket_config(
            interaction.guild.id
        )

        await interaction.response.edit_message(
            embed=ticket_advanced_embed(config),
            view=self
        )

    # =====================================================
    # CLOSE
    # =====================================================

    @discord.ui.button(
        label="Close",
        emoji="❌",
        style=discord.ButtonStyle.danger,
        custom_id="aircommander_ticket_advanced_close"
    )
    async def close(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):

        await interaction.response.edit_message(
            content="⚙️ Advanced ticket settings closed.",
            embed=None,
            view=None
        )


# =========================================================
# OPEN ADVANCED SETTINGS
# =========================================================

async def open_ticket_advanced(
    interaction: discord.Interaction
):

    if not ticket_admin_check(interaction.user):
        await interaction.response.send_message(
            "❌ You need **Administrator** or **Manage Server** permission.",
            ephemeral=True
        )
        return

    config = await get_or_create_ticket_config(
        interaction.guild.id
    )

    await interaction.response.send_message(
        embed=ticket_advanced_embed(config),
        view=TicketAdvancedView(),
        ephemeral=True
    )


# =========================================================
# PREFIX — ,ticket advanced
# =========================================================
@ticket_prefix.command(
    name="advanced"
)
@commands.guild_only()
@commands.has_permissions(manage_guild=True)
async def ticket_prefix_advanced(ctx):

    config = await get_or_create_ticket_config(
        ctx.guild.id
    )

    await ctx.send(
        embed=ticket_advanced_embed(config),
        view=TicketAdvancedView()
    )


# =========================================================
# SLASH — /ticket-advanced
# =========================================================

@bot.tree.command(
    name="ticket-advanced",
    description="Open advanced ticket settings."
)
@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
async def ticket_advanced_command(
    interaction: discord.Interaction
):

    await open_ticket_advanced(interaction)


# =========================================================
# AUTO CLOSE CHECKER
# =========================================================

async def ticket_auto_close_checker():

    await bot.wait_until_ready()

    while not bot.is_closed():

        try:

            for guild in bot.guilds:

                config = await get_or_create_ticket_config(
                    guild.id
                )

                auto_close = config.get(
                    "auto_close_minutes",
                    0
                )

                if not auto_close:
                    continue

                # Existing open tickets
                # This expects db.get_open_tickets(guild_id)
                # to be available from the ticket DB section.

                try:
                    tickets = await db.get_open_tickets(
                        guild.id
                    )
                except AttributeError:
                    tickets = []

                now = datetime.now(timezone.utc)

                for ticket in tickets:

                    created_at = ticket.get(
                        "created_at"
                    )

                    if not created_at:
                        continue

                    if created_at.tzinfo is None:
                        created_at = created_at.replace(
                            tzinfo=timezone.utc
                        )

                    age_minutes = (
                        now - created_at
                    ).total_seconds() / 60

                    if age_minutes < auto_close:
                        continue

                    channel_id = ticket.get(
                        "channel_id"
                    )

                    channel = guild.get_channel(
                        channel_id
                    )

                    if not channel:
                        continue

                    try:

                        await db.close_ticket(
                            ticket["id"]
                        )

                        await channel.send(
                            embed=discord.Embed(
                                title="⏰ Ticket Auto-Closed",
                                description=(
                                    "This ticket was automatically "
                                    "closed because it reached the "
                                    "configured inactivity/time limit."
                                ),
                                color=discord.Color.orange(),
                                timestamp=now
                            )
                        )

                    except Exception as e:
                        print(
                            f"⚠️ Auto-close error: {e}"
                        )

        except Exception as e:
            print(
                f"⚠️ Ticket auto-close checker error: {e}"
            )

        await asyncio.sleep(60)


# =========================================================
# START AUTO CLOSE TASK
# =========================================================

_ticket_auto_close_task = None


async def start_ticket_background_tasks():

    global _ticket_auto_close_task

    if _ticket_auto_close_task is None:

        _ticket_auto_close_task = asyncio.create_task(
            ticket_auto_close_checker()
)


# =========================================================
# BOT STARTUP
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

    bot.run(TOKEN)


# =========================================================
# MAIN
# =========================================================

if __name__ == "__main__":
    main()
