import os
import time
import threading
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
intents.members = True
intents.message_content = True

bot = commands.Bot(
    command_prefix=",",
    intents=intents
)

start_time = time.time()
bot._air_start_time = start_time

games.setup(bot)
basic_commands.setup(bot)

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
