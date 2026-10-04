# ============================================================
# Air Commander - YouTube Alerts
# API-FREE VERSION
#
# No YouTube Data API
# No Google Cloud
# No Billing
#
# Prefix:
# ,youtube setup
# ,youtube add @channel
# ,youtube remove @channel
# ,youtube list
# ,youtube config
# ,youtube enable
# ,youtube disable
# ,youtube test
# ,youtube role set @Role
# ,youtube role remove
#
# Slash:
# /youtube setup
# /youtube add
# /youtube remove
# /youtube list
# /youtube config
# /youtube enable
# /youtube disable
# /youtube test
# /youtube role set
# /youtube role remove
# ============================================================

import os
import re
import json
import asyncio
import aiohttp
import discord

from discord.ext import commands, tasks
from discord import app_commands
from xml.etree import ElementTree as ET


# ============================================================
# CONFIG
# ============================================================

DATA_FILE = "data/youtube_alerts.json"

CHECK_INTERVAL = 30

YOUTUBE_RSS_URL = (
    "https://www.youtube.com/feeds/videos.xml?channel_id={}"
)

DEFAULT_COLOR = discord.Color.red()


# ============================================================
# DATA
# ============================================================

def ensure_data_folder():
    os.makedirs("data", exist_ok=True)


def default_data():
    return {
        "guilds": {}
    }


def load_data():
    ensure_data_folder()

    if not os.path.exists(DATA_FILE):
        save_data(default_data())

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return default_data()

        if "guilds" not in data:
            data["guilds"] = {}

        return data

    except Exception:
        return default_data()


def save_data(data):
    ensure_data_folder()

    temp_file = DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    os.replace(temp_file, DATA_FILE)


DATA = load_data()


# ============================================================
# HELPERS
# ============================================================

def guild_data(guild_id: int):
    gid = str(guild_id)

    if gid not in DATA["guilds"]:
        DATA["guilds"][gid] = {
            "enabled": True,
            "default_channel": None,
            "ping_role": None,
            "channels": {}
        }

    guild = DATA["guilds"][gid]

    guild.setdefault("enabled", True)
    guild.setdefault("default_channel", None)
    guild.setdefault("ping_role", None)
    guild.setdefault("channels", {})

    return guild


def clean_channel_input(value: str):
    value = value.strip()

    value = value.replace("<", "")
    value = value.replace(">", "")

    if value.startswith("https://www.youtube.com/"):
        return value

    if value.startswith("https://youtube.com/"):
        return value

    if value.startswith("http://www.youtube.com/"):
        return value

    if value.startswith("http://youtube.com/"):
        return value

    return value


def extract_channel_id(value: str):
    """
    Supports:
    https://www.youtube.com/channel/UCxxxx
    youtube.com/channel/UCxxxx
    UCxxxx
    """

    value = clean_channel_input(value)

    match = re.search(
        r"(?:youtube\.com/)?channel/(UC[a-zA-Z0-9_-]+)",
        value
    )

    if match:
        return match.group(1)

    if re.fullmatch(r"UC[a-zA-Z0-9_-]{10,}", value):
        return value

    return None


def extract_handle(value: str):
    value = clean_channel_input(value)

    match = re.search(
        r"(?:youtube\.com/)?@([a-zA-Z0-9._-]+)",
        value
    )

    if match:
        return match.group(1)

    if value.startswith("@"):
        return value[1:]

    return None


def make_embed(
    title,
    description="",
    color=DEFAULT_COLOR,
):
    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    embed.set_footer(
        text="Air Commander • YouTube Alerts"
    )

    return embed


def youtube_url(video_id: str, video_type: str = "video"):
    if video_type == "short":
        return f"https://www.youtube.com/shorts/{video_id}"

    return f"https://www.youtube.com/watch?v={video_id}"


def classify_video(title: str, description: str):
    """
    RSS itself does not provide a perfect Shorts flag.

    We use a safe heuristic:
    - #shorts in title/description => Shorts

    Otherwise normal video.

    Live streams will still use the normal YouTube watch URL.
    """

    text = f"{title} {description}".lower()

    if "#shorts" in text or "#short" in text:
        return "short"

    return "video"


# ============================================================
# RSS
# ============================================================

async def fetch_rss(channel_id: str):
    url = YOUTUBE_RSS_URL.format(channel_id)

    timeout = aiohttp.ClientTimeout(total=15)

    try:
        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            headers = {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(compatible; AirCommanderYouTubeAlerts/1.0)"
                )
            }

            async with session.get(
                url,
                headers=headers
            ) as response:

                if response.status != 200:
                    return None

                return await response.text()

    except Exception as e:
        print(
            f"⚠️ YouTube RSS error for {channel_id}: {e}"
        )

        return None


def parse_rss(xml_text: str):
    try:
        root = ET.fromstring(xml_text)

    except Exception as e:
        print(f"⚠️ RSS XML parse error: {e}")
        return []

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/"
    }

    videos = []

    for entry in root.findall("atom:entry", ns):

        video_id = entry.findtext(
            "yt:videoId",
            default="",
            namespaces=ns
        )

        channel_id = entry.findtext(
            "yt:channelId",
            default="",
            namespaces=ns
        )

        title = entry.findtext(
            "atom:title",
            default="YouTube Upload",
            namespaces=ns
        )

        published = entry.findtext(
            "atom:published",
            default="",
            namespaces=ns
        )

        updated = entry.findtext(
            "atom:updated",
            default="",
            namespaces=ns
        )

        author_name = entry.findtext(
            "atom:author/atom:name",
            default="YouTube Channel",
            namespaces=ns
        )

        media_group = entry.find(
            "media:group",
            ns
        )

        description = ""

        if media_group is not None:
            description = media_group.findtext(
                "media:description",
                default="",
                namespaces=ns
            )

        if not video_id:
            continue

        videos.append({
            "video_id": video_id,
            "channel_id": channel_id,
            "title": title,
            "description": description,
            "published": published,
            "updated": updated,
            "author": author_name
        })

    return videos


# ============================================================
# DISCORD ALERT
# ============================================================

async def send_alert(
    bot,
    guild,
    channel_id,
    youtube_channel,
    video
):

    discord_channel_id = youtube_channel.get(
        "discord_channel_id"
    )

    if discord_channel_id:
        target = guild.get_channel(
            int(discord_channel_id)
        )
    else:
        target = guild.get_channel(
            int(channel_id)
        )

    if target is None:
        default_channel = guild_data(
            guild.id
        ).get("default_channel")

        if default_channel:
            target = guild.get_channel(
                int(default_channel)
            )

    if target is None:
        return False

    video_id = video["video_id"]

    title = video.get(
        "title",
        "New YouTube Upload"
    )

    description = video.get(
        "description",
        ""
    )

    author = video.get(
        "author",
        youtube_channel.get(
            "name",
            "YouTube"
        )
    )

    video_type = classify_video(
        title,
        description
    )

    url = youtube_url(
        video_id,
        video_type
    )

    if video_type == "short":
        label = "🎬 NEW SHORT"
        color = discord.Color.orange()

    else:
        label = "🔴 NEW YOUTUBE UPLOAD"
        color = discord.Color.red()

    embed = make_embed(
        label,
        color=color
    )

    embed.add_field(
        name="🎥 Video",
        value=f"**{title}**",
        inline=False
    )

    embed.add_field(
        name="📺 Channel",
        value=author,
        inline=True
    )

    embed.add_field(
        name="🔗 Watch",
        value=f"[Open on YouTube]({url})",
        inline=True
    )

    if description:
        clean_description = description.strip()

        if len(clean_description) > 500:
            clean_description = (
                clean_description[:497] + "..."
            )

        embed.add_field(
            name="📝 Description",
            value=clean_description,
            inline=False
        )

    embed.set_thumbnail(
        url=(
            f"https://i.ytimg.com/vi/"
            f"{video_id}/hqdefault.jpg"
        )
    )

    embed.set_footer(
        text=(
            "Air Commander • YouTube Alerts"
        )
    )

    # ========================================================
    # ROLE PING
    # ========================================================

    ping_role_id = youtube_channel.get(
        "ping_role_id"
    )

    if not ping_role_id:
        ping_role_id = guild_data(
            guild.id
        ).get("ping_role")

    content = None

    role = None

    if ping_role_id:
        role = guild.get_role(
            int(ping_role_id)
        )

        if role:
            content = role.mention

    allowed_mentions = discord.AllowedMentions(
        everyone=False,
        users=False,
        roles=True,
        replied_user=False
    )

    try:
        await target.send(
            content=content,
            embed=embed,
            allowed_mentions=allowed_mentions,
            view=YouTubeWatchView(url)
        )

        print(
            f"📺 YouTube alert sent | "
            f"{guild.name} | {title}"
        )

        return True

    except discord.Forbidden:
        print(
            f"❌ Cannot send YouTube alert in "
            f"{target}"
        )

    except Exception as e:
        print(
            f"❌ YouTube alert send error: {e}"
        )

    return False


# ============================================================
# BUTTON
# ============================================================

class YouTubeWatchView(discord.ui.View):

    def __init__(self, url):
        super().__init__(timeout=None)

        self.add_item(
            discord.ui.Button(
                label="Watch on YouTube",
                emoji="▶️",
                style=discord.ButtonStyle.link,
                url=url
            )
        )


# ============================================================
# MAIN COG
# ============================================================

class YouTubeAlerts(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

        self.youtube_loop.start()

    def cog_unload(self):
        self.youtube_loop.cancel()

    # ========================================================
    # RSS CHECK LOOP
    # ========================================================

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def youtube_loop(self):

        if not self.bot.is_ready():
            return

        for guild_id, config in list(
            DATA.get("guilds", {}).items()
        ):

            if not config.get("enabled", True):
                continue

            guild = self.bot.get_guild(
                int(guild_id)
            )

            if guild is None:
                continue

            channels = config.get(
                "channels",
                {}
            )

            for yt_id, yt_channel in list(
                channels.items()
            ):

                try:
                    xml = await fetch_rss(
                        yt_id
                    )

                    if not xml:
                        continue

                    videos = parse_rss(xml)

                    if not videos:
                        continue

                    latest = videos[0]

                    latest_id = latest[
                        "video_id"
                    ]

                    old_id = yt_channel.get(
                        "last_video_id"
                    )

                    # =================================================
                    # FIRST RUN
                    # =================================================

                    if not old_id:
                        yt_channel[
                            "last_video_id"
                        ] = latest_id

                        save_data(DATA)

                        print(
                            f"📺 Initialized YouTube channel: "
                            f"{yt_channel.get('name', yt_id)}"
                        )

                        continue

                    if latest_id == old_id:
                        continue

                    # =================================================
                    # Find all new uploads
                    # =================================================

                    new_videos = []

                    for video in reversed(videos):

                        if video[
                            "video_id"
                        ] == old_id:

                            break

                        new_videos.append(video)

                    # =================================================
                    # Send alerts
                    # =================================================

                    for video in new_videos:

                        await send_alert(
                            self.bot,
                            guild,
                            config.get(
                                "default_channel"
                            ),
                            yt_channel,
                            video
                        )

                    yt_channel[
                        "last_video_id"
                    ] = latest_id

                    save_data(DATA)

                except Exception as e:

                    print(
                        f"❌ YouTube checker error "
                        f"[{guild.name}] "
                        f"[{yt_id}]: {e}"
                    )

    @youtube_loop.before_loop
    async def before_youtube_loop(self):

        await self.bot.wait_until_ready()


# ============================================================
# PREFIX COMMAND
# ============================================================

def setup_prefix_commands(bot):

    @bot.group(
        name="youtube",
        invoke_without_command=True
    )
    @commands.guild_only()
    async def youtube(ctx):

        embed = make_embed(
            "📺 YouTube Alerts",
            (
                "**Available commands:**\n\n"
                "`,youtube setup`\n"
                "`,youtube add @Channel`\n"
                "`,youtube remove @Channel`\n"
                "`,youtube list`\n"
                "`,youtube config`\n"
                "`,youtube enable`\n"
                "`,youtube disable`\n"
                "`,youtube test`\n"
                "`,youtube role set @Role`\n"
                "`,youtube role remove`"
            )
        )

        await ctx.send(embed=embed)

    # ========================================================
    # SETUP
    # ========================================================

    @youtube.command(name="setup")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_setup(ctx):

        config = guild_data(
            ctx.guild.id
        )

        config["default_channel"] = ctx.channel.id

        save_data(DATA)

        embed = make_embed(
            "✅ YouTube Alerts Setup",
            (
                f"Alerts will be sent in "
                f"{ctx.channel.mention}."
            ),
            discord.Color.green()
        )

        await ctx.send(embed=embed)

    # ========================================================
    # ADD
    # ========================================================

    @youtube.command(name="add")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_add(ctx, *, channel: str = None):

        if not channel:

            await ctx.send(
                "❌ Usage: `,youtube add @Channel`"
            )

            return

        channel = clean_channel_input(channel)

        channel_id = extract_channel_id(
            channel
        )

        handle = extract_handle(
            channel
        )

        # ----------------------------------------------------
        # Direct channel ID
        # ----------------------------------------------------

        if channel_id:

            rss = await fetch_rss(
                channel_id
            )

            if not rss:

                await ctx.send(
                    "❌ Couldn't access that YouTube channel."
                )

                return

            videos = parse_rss(rss)

            if not videos:

                await ctx.send(
                    "❌ No RSS information found "
                    "for this channel."
                )

                return

            channel_name = videos[0].get(
                "author",
                "YouTube Channel"
            )

        # ----------------------------------------------------
        # Handle
        # ----------------------------------------------------

        elif handle:

            # RSS does not directly resolve handles.
            # We ask user for channel URL/ID because
            # no API is being used.
            await ctx.send(
                (
                    "❌ API-free mode me YouTube handle "
                    "ko Channel ID me resolve nahi kar sakte.\n\n"
                    "Use the channel's URL in this format:\n"
                    "`https://www.youtube.com/channel/UC...`"
                )
            )

            return

        else:

            await ctx.send(
                (
                    "❌ Invalid YouTube channel.\n"
                    "Use a channel URL like:\n"
                    "`https://www.youtube.com/channel/UC...`"
                )
            )

            return

        config = guild_data(
            ctx.guild.id
        )

        if channel_id in config["channels"]:

            await ctx.send(
                "⚠️ This YouTube channel is already tracked."
            )

            return

        config["channels"][channel_id] = {
            "name": channel_name,
            "channel_id": channel_id,
            "discord_channel_id": (
                config.get("default_channel")
                or ctx.channel.id
            ),
            "ping_role_id": (
                config.get("ping_role")
            ),
            "last_video_id": None
        }

        save_data(DATA)

        embed = make_embed(
            "📺 YouTube Channel Added",
            (
                f"**Channel:** {channel_name}\n"
                f"**Channel ID:** `{channel_id}`\n"
                f"**Alert Channel:** "
                f"<#{config['channels'][channel_id]['discord_channel_id']}>\n\n"
                "The latest existing upload will be "
                "**initialized without sending an alert**."
            ),
            discord.Color.green()
        )

        await ctx.send(embed=embed)

    # ========================================================
    # REMOVE
    # ========================================================

    @youtube.command(name="remove")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_remove(
        ctx,
        *,
        channel_id: str = None
    ):

        if not channel_id:

            await ctx.send(
                "❌ Usage: `,youtube remove CHANNEL_ID`"
            )

            return

        config = guild_data(
            ctx.guild.id
        )

        if channel_id not in config["channels"]:

            await ctx.send(
                "❌ That channel is not being tracked."
            )

            return

        removed = config[
            "channels"
        ].pop(channel_id)

        save_data(DATA)

        await ctx.send(
            embed=make_embed(
                "🗑️ YouTube Channel Removed",
                (
                    f"Removed **{removed.get('name', channel_id)}**."
                ),
                discord.Color.orange()
            )
        )

    # ========================================================
    # LIST
    # ========================================================

    @youtube.command(name="list")
    @commands.guild_only()
    async def youtube_list(ctx):

        config = guild_data(
            ctx.guild.id
        )

        channels = config.get(
            "channels",
            {}
        )

        if not channels:

            await ctx.send(
                embed=make_embed(
                    "📺 YouTube Channels",
                    "No YouTube channels are being tracked."
                )
            )

            return

        lines = []

        for yt_id, info in channels.items():

            discord_channel_id = info.get(
                "discord_channel_id"
            )

            ping_role_id = info.get(
                "ping_role_id"
            )

            line = (
                f"**{info.get('name', 'Unknown')}**\n"
                f"🆔 `{yt_id}`\n"
            )

            if discord_channel_id:
                line += (
                    f"📢 <#{discord_channel_id}>\n"
                )

            if ping_role_id:
                line += (
                    f"🔔 <@&{ping_role_id}>\n"
                )

            lines.append(line)

        embed = make_embed(
            "📺 Tracked YouTube Channels",
            "\n".join(lines)
        )

        await ctx.send(embed=embed)

    # ========================================================
    # CONFIG
    # ========================================================

    @youtube.command(name="config")
    @commands.guild_only()
    async def youtube_config(ctx):

        config = guild_data(
            ctx.guild.id
        )

        status = (
            "🟢 Enabled"
            if config.get("enabled", True)
            else "🔴 Disabled"
        )

        default_channel = config.get(
            "default_channel"
        )

        ping_role = config.get(
            "ping_role"
        )

        embed = make_embed(
            "⚙️ YouTube Alerts Configuration",
            (
                f"**Status:** {status}\n"
                f"**Tracked Channels:** "
                f"{len(config.get('channels', {}))}\n"
                f"**Alert Channel:** "
                f"{f'<#{default_channel}>' if default_channel else 'Not set'}\n"
                f"**Ping Role:** "
                f"{f'<@&{ping_role}>' if ping_role else 'Not set'}\n"
                f"**Check Interval:** `{CHECK_INTERVAL}s`"
            )
        )

        await ctx.send(embed=embed)

    # ========================================================
    # ENABLE
    # ========================================================

    @youtube.command(name="enable")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_enable(ctx):

        config = guild_data(
            ctx.guild.id
        )

        config["enabled"] = True

        save_data(DATA)

        await ctx.send(
            embed=make_embed(
                "🟢 YouTube Alerts Enabled",
                "YouTube notifications are now enabled.",
                discord.Color.green()
            )
        )

    # ========================================================
    # DISABLE
    # ========================================================

    @youtube.command(name="disable")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_disable(ctx):

        config = guild_data(
            ctx.guild.id
        )

        config["enabled"] = False

        save_data(DATA)

        await ctx.send(
            embed=make_embed(
                "🔴 YouTube Alerts Disabled",
                "YouTube notifications are now disabled.",
                discord.Color.red()
            )
        )

    # ========================================================
    # ROLE SET
    # ========================================================

    @youtube.command(name="role")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_role(
        ctx,
        action: str = None,
        role: discord.Role = None
    ):

        config = guild_data(
            ctx.guild.id
        )

        if action == "set":

            if role is None:

                await ctx.send(
                    "❌ Usage: `,youtube role set @Role`"
                )

                return

            config["ping_role"] = role.id

            # Apply default to existing channels
            for info in config["channels"].values():

                if not info.get("ping_role_id"):
                    info["ping_role_id"] = role.id

            save_data(DATA)

            await ctx.send(
                embed=make_embed(
                    "🔔 YouTube Ping Role Set",
                    (
                        f"Every new YouTube alert will ping "
                        f"{role.mention}."
                    ),
                    discord.Color.green()
                )
            )

            return

        if action == "remove":

            config["ping_role"] = None

            save_data(DATA)

            await ctx.send(
                embed=make_embed(
                    "🔕 YouTube Ping Role Removed",
                    "New YouTube alerts will no longer use the default ping role.",
                    discord.Color.orange()
                )
            )

            return

        await ctx.send(
            "❌ Use `,youtube role set @Role` or `,youtube role remove`."
        )

    # ========================================================
    # TEST
    # ========================================================

    @youtube.command(name="test")
    @commands.guild_only()
    @commands.has_guild_permissions(manage_guild=True)
    async def youtube_test(ctx):

        config = guild_data(
            ctx.guild.id
        )

        role_id = config.get(
            "ping_role"
        )

        content = None

        if role_id:

            role = ctx.guild.get_role(
                int(role_id)
            )

            if role:
                content = role.mention

        embed = make_embed(
            "🔴 NEW YOUTUBE UPLOAD",
            (
                "**Test Video**\n\n"
                "This is a test notification from "
                "Air Commander.\n\n"
                "🔗 [Watch on YouTube]"
                "(https://www.youtube.com/)"
            ),
            discord.Color.red()
        )

        embed.set_thumbnail(
            url=(
                "https://www.youtube.com/"
                "img/desktop/yt_1200.png"
            )
        )

        await ctx.send(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True
            ),
            view=YouTubeWatchView(
                "https://www.youtube.com/"
            )
        )


# ============================================================
# SLASH COMMANDS
# ============================================================

def setup_slash_commands(bot):

    tree = bot.tree

    existing = tree.get_command(
        "youtube"
    )

    if existing is not None:

        print(
            "⚠️ YouTube slash command already exists. "
            "Skipping duplicate registration."
        )

        return

    youtube = app_commands.Group(
        name="youtube",
        description="YouTube alert controls"
    )

    # ========================================================
    # /youtube setup
    # ========================================================

    @youtube.command(
        name="setup",
        description="Set this channel as the YouTube alert channel"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def slash_setup(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        config["default_channel"] = (
            interaction.channel.id
        )

        save_data(DATA)

        await interaction.response.send_message(
            embed=make_embed(
                "✅ YouTube Alerts Setup",
                (
                    f"Alerts will be sent in "
                    f"{interaction.channel.mention}."
                ),
                discord.Color.green()
            ),
            ephemeral=True
        )

    # ========================================================
    # /youtube add
    # ========================================================

    @youtube.command(
        name="add",
        description="Track a YouTube channel"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def slash_add(
        interaction: discord.Interaction,
        channel: str
    ):

        channel_id = extract_channel_id(
            channel
        )

        if not channel_id:

            await interaction.response.send_message(
                (
                    "❌ API-free mode requires the "
                    "YouTube Channel URL.\n\n"
                    "`https://www.youtube.com/channel/UC...`"
                ),
                ephemeral=True
            )

            return

        await interaction.response.defer(
            ephemeral=True
        )

        rss = await fetch_rss(
            channel_id
        )

        if not rss:

            await interaction.followup.send(
                "❌ Couldn't access that YouTube channel.",
                ephemeral=True
            )

            return

        videos = parse_rss(rss)

        if not videos:

            await interaction.followup.send(
                "❌ No channel information found.",
                ephemeral=True
            )

            return

        config = guild_data(
            interaction.guild.id
        )

        if channel_id in config["channels"]:

            await interaction.followup.send(
                "⚠️ This channel is already tracked.",
                ephemeral=True
            )

            return

        channel_name = videos[0].get(
            "author",
            "YouTube Channel"
        )

        config["channels"][channel_id] = {
            "name": channel_name,
            "channel_id": channel_id,
            "discord_channel_id": (
                config.get("default_channel")
                or interaction.channel.id
            ),
            "ping_role_id": (
                config.get("ping_role")
            ),
            "last_video_id": None
        }

        save_data(DATA)

        await interaction.followup.send(
            embed=make_embed(
                "📺 YouTube Channel Added",
                (
                    f"**Channel:** {channel_name}\n"
                    f"**Channel ID:** `{channel_id}`\n\n"
                    "The latest existing upload will be "
                    "initialized without an alert."
                ),
                discord.Color.green()
            ),
            ephemeral=True
        )

    # ========================================================
    # /youtube remove
    # ========================================================

    @youtube.command(
        name="remove",
        description="Stop tracking a YouTube channel"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def slash_remove(
        interaction: discord.Interaction,
        channel_id: str
    ):

        config = guild_data(
            interaction.guild.id
        )

        if channel_id not in config["channels"]:

            await interaction.response.send_message(
                "❌ That channel is not being tracked.",
                ephemeral=True
            )

            return

        removed = config[
            "channels"
        ].pop(channel_id)

        save_data(DATA)

        await interaction.response.send_message(
            embed=make_embed(
                "🗑️ YouTube Channel Removed",
                (
                    f"Removed **{removed.get('name', channel_id)}**."
                ),
                discord.Color.orange()
            ),
            ephemeral=True
        )

    # ========================================================
    # /youtube list
    # ========================================================

    @youtube.command(
        name="list",
        description="Show tracked YouTube channels"
    )
    async def slash_list(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        channels = config.get(
            "channels",
            {}
        )

        if not channels:

            await interaction.response.send_message(
                embed=make_embed(
                    "📺 YouTube Channels",
                    "No YouTube channels are being tracked."
                ),
                ephemeral=True
            )

            return

        lines = []

        for yt_id, info in channels.items():

            line = (
                f"**{info.get('name', 'Unknown')}**\n"
                f"🆔 `{yt_id}`\n"
                f"📢 <#{info.get('discord_channel_id')}>\n"
            )

            if info.get("ping_role_id"):
                line += (
                    f"🔔 <@&{info['ping_role_id']}>\n"
                )

            lines.append(line)

        await interaction.response.send_message(
            embed=make_embed(
                "📺 Tracked YouTube Channels",
                "\n".join(lines)
            ),
            ephemeral=True
        )

      # ========================================================
    # /youtube config
    # ========================================================

    @youtube.command(
        name="config",
        description="Show YouTube alert configuration"
    )
    async def slash_config(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        default_channel = config.get(
            "default_channel"
        )

        ping_role = config.get(
            "ping_role"
        )

        alert_channel_text = (
            f"<#{default_channel}>"
            if default_channel
            else "Not set"
        )

        ping_role_text = (
            f"<@&{ping_role}>"
            if ping_role
            else "Not set"
        )

        status_text = (
            "🟢 Enabled"
            if config.get("enabled", True)
            else "🔴 Disabled"
        )

        tracked_count = len(
            config.get("channels", {})
        )

        embed = make_embed(
            "⚙️ YouTube Alerts Configuration",
            (
                f"**Status:** {status_text}\n"
                f"**Tracked:** {tracked_count}\n"
                f"**Alert Channel:** "
                f"{alert_channel_text}\n"
                f"**Ping Role:** "
                f"{ping_role_text}\n"
                f"**Check:** `{CHECK_INTERVAL}s`"
            )
        )

        await interaction.response.send_message(
            embed=embed,
            ephemeral=True
        )

    # ========================================================
    # /youtube enable
    # ========================================================

    @youtube.command(
        name="enable",
        description="Enable YouTube alerts"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def slash_enable(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        config["enabled"] = True

        save_data(DATA)

        await interaction.response.send_message(
            "🟢 YouTube Alerts enabled.",
            ephemeral=True
        )

    # ========================================================
    # /youtube disable
    # ========================================================

    @youtube.command(
        name="disable",
        description="Disable YouTube alerts"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def slash_disable(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        config["enabled"] = False

        save_data(DATA)

        await interaction.response.send_message(
            "🔴 YouTube Alerts disabled.",
            ephemeral=True
        )

    # ========================================================
    # /youtube test
    # ========================================================

    @youtube.command(
        name="test",
        description="Send a test YouTube alert"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def slash_test(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        role_id = config.get(
            "ping_role"
        )

        content = None

        if role_id:

            role = interaction.guild.get_role(
                int(role_id)
            )

            if role:
                content = role.mention

        embed = make_embed(
            "🔴 NEW YOUTUBE UPLOAD",
            (
                "**Test Video**\n\n"
                "This is a test notification."
            ),
            discord.Color.red()
        )

        await interaction.response.send_message(
            content=content,
            embed=embed,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True
            ),
            view=YouTubeWatchView(
                "https://www.youtube.com/"
            )
        )

    # ========================================================
    # /youtube role
    # ========================================================

    role_group = app_commands.Group(
        name="role",
        description="Manage YouTube ping role"
    )

    @role_group.command(
        name="set",
        description="Set the role to ping for YouTube uploads"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def role_set(
        interaction: discord.Interaction,
        role: discord.Role
    ):

        config = guild_data(
            interaction.guild.id
        )

        config["ping_role"] = role.id

        for info in config["channels"].values():

            if not info.get("ping_role_id"):
                info["ping_role_id"] = role.id

        save_data(DATA)

        await interaction.response.send_message(
            embed=make_embed(
                "🔔 YouTube Ping Role Set",
                (
                    f"Alerts will ping {role.mention}."
                ),
                discord.Color.green()
            ),
            ephemeral=True
        )

    @role_group.command(
        name="remove",
        description="Remove the default YouTube ping role"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def role_remove(
        interaction: discord.Interaction
    ):

        config = guild_data(
            interaction.guild.id
        )

        config["ping_role"] = None

        save_data(DATA)

        await interaction.response.send_message(
            "🔕 YouTube ping role removed.",
            ephemeral=True
        )

    youtube.add_command(
        role_group
    )

    tree.add_command(
        youtube
    )

    print(
        "📺 YouTube Alerts slash command group registered."
    )


# ============================================================
# SETUP
# ============================================================

def setup(bot):

    # Prevent duplicate setup
    if getattr(
        bot,
        "_air_youtube_alerts_loaded",
        False
    ):
        print(
            "⚠️ YouTube Alerts already loaded."
        )

        return

    bot._air_youtube_alerts_loaded = True

    cog = YouTubeAlerts(bot)

    async def add_cog():

        await bot.add_cog(cog)

    # discord.py setup can be called after bot creation
    bot.loop.create_task(
        add_cog()
    )

    setup_prefix_commands(bot)
    setup_slash_commands(bot)

    print(
        "📺 YouTube Alerts system initialized "
        "(API-free RSS mode)."
    )
