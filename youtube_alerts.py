# youtube_alerts.py
# ✈️ Air Commander - YouTube Alerts
#
# Prefix:
# ,youtube setup
# ,youtube add <channel>
# ,youtube remove <channel>
# ,youtube list
# ,youtube config
# ,youtube test
# ,youtube enable
# ,youtube disable
#
# Slash:
# /youtube setup
# /youtube add
# /youtube remove
# /youtube list
# /youtube config
# /youtube test
# /youtube enable
# /youtube disable

import os
import json
import asyncio
import aiohttp
import discord

from discord import app_commands
from discord.ext import commands, tasks


# =========================================================
# CONFIG
# =========================================================

DATA_FILE = "data/youtube_alerts.json"

YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")

CHECK_INTERVAL = 120  # seconds


# =========================================================
# COLORS
# =========================================================

AIR_BLUE = 0x5865F2
SUCCESS = 0x57F287
WARNING = 0xFEE75C
ERROR = 0xED4245
RED = 0xFF0000


# =========================================================
# FILE SYSTEM
# =========================================================

def ensure_data_file():
    os.makedirs("data", exist_ok=True)

    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "guilds": {}
                },
                f,
                indent=4
            )


def load_data():
    ensure_data_file()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            return {"guilds": {}}

        data.setdefault("guilds", {})
        return data

    except Exception:
        return {"guilds": {}}


def save_data(data):
    ensure_data_file()

    temp_file = DATA_FILE + ".tmp"

    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

    os.replace(temp_file, DATA_FILE)


# =========================================================
# EMBEDS
# =========================================================

def make_embed(title, description="", color=AIR_BLUE):
    embed = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )

    embed.set_footer(
        text="Air Commander • YouTube Alerts"
    )

    return embed


# =========================================================
# YOUTUBE API
# =========================================================

async def youtube_request(endpoint, params):
    if not YOUTUBE_API_KEY:
        return None

    params = dict(params)
    params["key"] = YOUTUBE_API_KEY

    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"

    try:
        timeout = aiohttp.ClientTimeout(total=15)

        async with aiohttp.ClientSession(
            timeout=timeout
        ) as session:

            async with session.get(
                url,
                params=params
            ) as response:

                if response.status != 200:
                    return None

                return await response.json()

    except Exception:
        return None


async def resolve_channel(channel_input):
    """
    Accepts:
      @username
      username
      https://youtube.com/@username
      channel ID
    """

    if not YOUTUBE_API_KEY:
        return None

    value = channel_input.strip()

    # Direct channel ID
    if value.startswith("UC") and len(value) >= 20:
        data = await youtube_request(
            "channels",
            {
                "part": "snippet,contentDetails",
                "id": value
            }
        )

        if data and data.get("items"):
            item = data["items"][0]

            return {
                "id": item["id"],
                "name": item["snippet"]["title"],
                "handle": item["snippet"].get("customUrl", ""),
                "uploads_playlist": item[
                    "contentDetails"
                ]["relatedPlaylists"]["uploads"]
            }

    # Extract handle
    value = value.replace("https://", "")
    value = value.replace("http://", "")

    if "youtube.com/" in value:
        value = value.split("youtube.com/", 1)[1]

    value = value.split("/", 1)[0]

    if value.startswith("@"):
        value = value[1:]

    if not value:
        return None

    # Search channel
    data = await youtube_request(
        "search",
        {
            "part": "snippet",
            "q": value,
            "type": "channel",
            "maxResults": 1
        }
    )

    if not data or not data.get("items"):
        return None

    item = data["items"][0]

    channel_id = item["snippet"]["channelId"]

    channel_data = await youtube_request(
        "channels",
        {
            "part": "snippet,contentDetails",
            "id": channel_id
        }
    )

    if not channel_data or not channel_data.get("items"):
        return None

    channel = channel_data["items"][0]

    return {
        "id": channel["id"],
        "name": channel["snippet"]["title"],
        "handle": channel["snippet"].get(
            "customUrl",
            ""
        ),
        "uploads_playlist": channel[
            "contentDetails"
        ]["relatedPlaylists"]["uploads"]
    }


async def get_latest_video(channel):
    data = await youtube_request(
        "playlistItems",
        {
            "part": "snippet,contentDetails",
            "playlistId": channel["uploads_playlist"],
            "maxResults": 1
        }
    )

    if not data or not data.get("items"):
        return None

    item = data["items"][0]

    snippet = item["snippet"]
    video_id = item["contentDetails"]["videoId"]

    return {
        "id": video_id,
        "title": snippet["title"],
        "description": snippet.get(
            "description",
            ""
        ),
        "published": snippet.get(
            "publishedAt"
        ),
        "thumbnail": (
            snippet.get("thumbnails", {})
            .get("maxres", {})
            .get("url")
            or snippet.get("thumbnails", {})
            .get("high", {})
            .get("url")
        ),
        "channel_name": snippet.get(
            "channelTitle",
            channel["name"]
        ),
        "channel_id": channel["id"]
    }


# =========================================================
# MAIN CLASS
# =========================================================

class YouTubeAlerts:

    def __init__(self, bot):
        self.bot = bot
        self.data = load_data()

        self.check_loop.start()

    def cog_unload(self):
        self.check_loop.cancel()

    # =====================================================
    # GUILD DATA
    # =====================================================

    def get_guild(self, guild_id):
        guilds = self.data.setdefault(
            "guilds",
            {}
        )

        gid = str(guild_id)

        if gid not in guilds:
            guilds[gid] = {
                "enabled": True,
                "default_channel": None,
                "channels": {}
            }

        guilds[gid].setdefault(
            "enabled",
            True
        )

        guilds[gid].setdefault(
            "default_channel",
            None
        )

        guilds[gid].setdefault(
            "channels",
            {}
        )

        return guilds[gid]

    # =====================================================
    # PERMISSION
    # =====================================================

    def has_permission(self, member):
        return (
            member.guild_permissions.manage_guild
            or member.guild_permissions.administrator
        )

    # =====================================================
    # PREFIX GROUP
    # =====================================================

    async def youtube_prefix(
        self,
        ctx,
        action=None,
        *,
        argument=None
    ):
        if not ctx.guild:
            await ctx.send(
                embed=make_embed(
                    "Server Only",
                    "This command can only be used inside a server.",
                    ERROR
                )
            )
            return

        if not self.has_permission(ctx.author):
            await ctx.send(
                embed=make_embed(
                    "Permission Denied",
                    "You need **Manage Server** permission.",
                    ERROR
                )
            )
            return

        if not action:
            await self.send_help(ctx)
            return

        action = action.lower()

        if action == "setup":
            await self.setup_prefix(ctx)
            return

        if action == "add":
            if not argument:
                await ctx.send(
                    embed=make_embed(
                        "Missing Channel",
                        "Usage:\n`,youtube add <YouTube channel>`",
                        WARNING
                    )
                )
                return

            await self.add_channel(
                ctx,
                argument
            )
            return

        if action == "remove":
            if not argument:
                await ctx.send(
                    embed=make_embed(
                        "Missing Channel",
                        "Usage:\n`,youtube remove <channel ID>`",
                        WARNING
                    )
                )
                return

            await self.remove_channel(
                ctx,
                argument
            )
            return

        if action == "list":
            await self.list_channels(ctx)
            return

        if action == "config":
            await self.show_config(ctx)
            return

        if action == "test":
            await self.test_alert(ctx)
            return

        if action == "enable":
            await self.set_enabled(
                ctx,
                True
            )
            return

        if action == "disable":
            await self.set_enabled(
                ctx,
                False
            )
            return

        await self.send_help(ctx)

    # =====================================================
    # HELP
    # =====================================================

    async def send_help(self, ctx):
        embed = make_embed(
            "YouTube Alerts",
            (
                "Automatically post new YouTube uploads "
                "into your Discord server.\n\n"

                "**Commands**\n"
                "`,youtube setup`\n"
                "`,youtube add <channel>`\n"
                "`,youtube remove <channel ID>`\n"
                "`,youtube list`\n"
                "`,youtube config`\n"
                "`,youtube test`\n"
                "`,youtube enable`\n"
                "`,youtube disable`"
            )
        )

        await ctx.send(embed=embed)

    # =====================================================
    # SETUP
    # =====================================================

    async def setup_prefix(self, ctx):
        guild_data = self.get_guild(
            ctx.guild.id
        )

        guild_data["default_channel"] = (
            ctx.channel.id
        )

        save_data(self.data)

        await ctx.send(
            embed=make_embed(
                "YouTube Alerts Setup",
                (
                    f"✅ Alert channel set to "
                    f"{ctx.channel.mention}.\n\n"
                    "Now add a YouTube channel with:\n"
                    "`,youtube add <channel>`"
                ),
                SUCCESS
            )
        )

    # =====================================================
    # ADD
    # =====================================================

    async def add_channel(
        self,
        ctx,
        channel_input
    ):
        if not YOUTUBE_API_KEY:
            await ctx.send(
                embed=make_embed(
                    "API Key Missing",
                    (
                        "Set the `YOUTUBE_API_KEY` "
                        "environment variable first."
                    ),
                    ERROR
                )
            )
            return

        msg = await ctx.send(
            embed=make_embed(
                "YouTube",
                "🔎 Finding that channel..."
            )
        )

        channel = await resolve_channel(
            channel_input
        )

        if not channel:
            await msg.edit(
                embed=make_embed(
                    "Channel Not Found",
                    (
                        "I couldn't find that YouTube channel.\n\n"
                        "Try using:\n"
                        "• `@channel`\n"
                        "• YouTube channel URL\n"
                        "• Channel ID"
                    ),
                    ERROR
                )
            )
            return

        guild_data = self.get_guild(
            ctx.guild.id
        )

        if channel["id"] in guild_data["channels"]:
            await msg.edit(
                embed=make_embed(
                    "Already Added",
                    f"📺 **{channel['name']}** is already being tracked.",
                    WARNING
                )
            )
            return

        default_channel = guild_data.get(
            "default_channel"
        )

        if not default_channel:
            default_channel = ctx.channel.id

        latest = await get_latest_video(
            channel
        )

        guild_data["channels"][channel["id"]] = {
            "name": channel["name"],
            "handle": channel.get(
                "handle",
                ""
            ),
            "channel_id": channel["id"],
            "uploads_playlist": channel[
                "uploads_playlist"
            ],
            "discord_channel_id": default_channel,
            "last_video_id": (
                latest["id"]
                if latest
                else None
            )
        }

        save_data(self.data)

        await msg.edit(
            embed=make_embed(
                "YouTube Channel Added",
                (
                    f"📺 **{channel['name']}**\n\n"
                    f"🆔 `{channel['id']}`\n"
                    f"🔔 <#{default_channel}>\n\n"
                    "✅ New uploads will now be announced."
                ),
                SUCCESS
            )
        )

    # =====================================================
    # REMOVE
    # =====================================================

    async def remove_channel(
        self,
        ctx,
        channel_id
    ):
        guild_data = self.get_guild(
            ctx.guild.id
        )

        channels = guild_data["channels"]

        target = None

        if channel_id in channels:
            target = channel_id
        else:
            for cid, info in channels.items():
                if (
                    info["name"].lower()
                    == channel_id.lower()
                ):
                    target = cid
                    break

        if not target:
            await ctx.send(
                embed=make_embed(
                    "Not Found",
                    "That YouTube channel is not being tracked.",
                    ERROR
                )
            )
            return

        name = channels[target]["name"]

        del channels[target]

        save_data(self.data)

        await ctx.send(
            embed=make_embed(
                "YouTube Channel Removed",
                f"🗑️ Removed **{name}** from YouTube alerts.",
                SUCCESS
            )
        )

    # =====================================================
    # LIST
    # =====================================================

    async def list_channels(self, ctx):
        guild_data = self.get_guild(
            ctx.guild.id
        )

        channels = guild_data["channels"]

        if not channels:
            await ctx.send(
                embed=make_embed(
                    "YouTube Channels",
                    (
                        "No YouTube channels are being tracked.\n\n"
                        "Use `,youtube add <channel>` to add one."
                    ),
                    WARNING
                )
            )
            return

        lines = []

        for index, (cid, info) in enumerate(
            channels.items(),
            start=1
        ):
            lines.append(
                f"**{index}. {info['name']}**\n"
                f"🆔 `{cid}`\n"
                f"🔔 <#{info['discord_channel_id']}>"
            )

        embed = make_embed(
            "Tracked YouTube Channels",
            "\n\n".join(lines)
        )

        await ctx.send(embed=embed)

    # =====================================================
    # CONFIG
    # =====================================================

    async def show_config(self, ctx):
        guild_data = self.get_guild(
            ctx.guild.id
        )

        status = (
            "🟢 Enabled"
            if guild_data["enabled"]
            else "🔴 Disabled"
        )

        alert_channel = guild_data.get(
            "default_channel"
        )

        alert_text = (
            f"<#{alert_channel}>"
            if alert_channel
            else "Not configured"
        )

        embed = make_embed(
            "YouTube Alert Configuration",
            (
                f"**Status:** {status}\n"
                f"**Tracked Channels:** "
                f"{len(guild_data['channels'])}\n"
                f"**Default Alert Channel:** "
                f"{alert_text}\n"
                f"**Check Interval:** "
                f"{CHECK_INTERVAL}s\n"
                f"**API:** "
                f"{'🟢 Connected' if YOUTUBE_API_KEY else '🔴 Missing'}"
            )
        )

        await ctx.send(embed=embed)

    # =====================================================
    # ENABLE / DISABLE
    # =====================================================

    async def set_enabled(
        self,
        ctx,
        enabled
    ):
        guild_data = self.get_guild(
            ctx.guild.id
        )

        guild_data["enabled"] = enabled

        save_data(self.data)

        if enabled:
            title = "YouTube Alerts Enabled"
            description = (
                "🟢 New YouTube uploads will be checked."
            )
            color = SUCCESS
        else:
            title = "YouTube Alerts Disabled"
            description = (
                "🔴 YouTube alerts are temporarily disabled."
            )
            color = WARNING

        await ctx.send(
            embed=make_embed(
                title,
                description,
                color
            )
        )

    # =====================================================
    # TEST
    # =====================================================

    async def test_alert(self, ctx):
        guild_data = self.get_guild(
            ctx.guild.id
        )

        target_channel_id = guild_data.get(
            "default_channel"
        )

        if not target_channel_id:
            await ctx.send(
                embed=make_embed(
                    "No Alert Channel",
                    "Run `,youtube setup` first.",
                    WARNING
                )
            )
            return

        channel = self.bot.get_channel(
            target_channel_id
        )

        if not channel:
            await ctx.send(
                embed=make_embed(
                    "Channel Not Found",
                    "The configured Discord channel no longer exists or I cannot access it.",
                    ERROR
                )
            )
            return

        embed = make_embed(
            "NEW VIDEO UPLOAD",
            (
                "**Air Commander YouTube Alert Test**\n\n"
                "This is how a real YouTube upload notification "
                "will look."
            ),
            RED
        )

        embed.add_field(
            name="📺 Channel",
            value="Example YouTube Channel",
            inline=True
        )

        embed.add_field(
            name="🎬 Video",
            value="Example New Video",
            inline=True
        )

        embed.add_field(
            name="▶️ Watch",
            value="[Open YouTube](https://youtube.com/)",
            inline=False
        )

        await channel.send(
            embed=embed
        )

        await ctx.send(
            embed=make_embed(
                "Test Sent",
                f"✅ Test alert sent to {channel.mention}.",
                SUCCESS
            )
        )

    # =====================================================
    # SEND REAL ALERT
    # =====================================================

    async def send_video_alert(
        self,
        guild,
        info,
        video
    ):
        channel_id = info.get(
            "discord_channel_id"
        )

        channel = guild.get_channel(
            channel_id
        )

        if not channel:
            return False

        description = video["description"]

        if len(description) > 500:
            description = (
                description[:497]
                + "..."
            )

        embed = discord.Embed(
            title="🔴 NEW VIDEO UPLOAD",
            description=(
                f"**{video['title']}**\n\n"
                f"{description}"
                if description
                else f"**{video['title']}**"
            ),
            color=RED,
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="📺 Channel",
            value=video["channel_name"],
            inline=True
        )

        embed.add_field(
            name="▶️ Watch",
            value=(
                f"[Watch Video](https://youtu.be/"
                f"{video['id']})"
            ),
            inline=True
        )

        if video.get("thumbnail"):
            embed.set_image(
                url=video["thumbnail"]
            )

        embed.set_footer(
            text="Air Commander • YouTube Alerts"
        )

        view = discord.ui.View()

        button = discord.ui.Button(
            label="▶️ WATCH ON YOUTUBE",
            url=(
                f"https://youtu.be/"
                f"{video['id']}"
            ),
            style=discord.ButtonStyle.link
        )

        view.add_item(button)

        try:
            await channel.send(
                embed=embed,
                view=view
            )

            return True

        except Exception:
            return False

    # =====================================================
    # CHECK LOOP
    # =====================================================

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def check_loop(self):
        if not self.bot.is_ready():
            return

        if not YOUTUBE_API_KEY:
            return

        changed = False

        for guild_id, guild_data in list(
            self.data.get("guilds", {}).items()
        ):

            if not guild_data.get(
                "enabled",
                True
            ):
                continue

            guild = self.bot.get_guild(
                int(guild_id)
            )

            if not guild:
                continue

            channels = guild_data.get(
                "channels",
                {}
            )

            for channel_id, info in list(
                channels.items()
            ):

                try:
                    video = await get_latest_video(
                        info
                    )

                    if not video:
                        continue

                    last_video = info.get(
                        "last_video_id"
                    )

                    # First check only stores current video.
                    # This prevents old videos from being sent.
                    if not last_video:
                        info["last_video_id"] = video["id"]
                        changed = True
                        continue

                    if video["id"] == last_video:
                        continue

                    success = await self.send_video_alert(
                        guild,
                        info,
                        video
                    )

                    if success:
                        info["last_video_id"] = video["id"]
                        changed = True

                except Exception as e:
                    print(
                        f"⚠️ YouTube alert error "
                        f"[{guild_id}/{channel_id}]: {e}"
                    )

                await asyncio.sleep(0.3)

        if changed:
            save_data(self.data)

    @check_loop.before_loop
    async def before_check_loop(self):
        await self.bot.wait_until_ready()

    # =====================================================
    # SLASH COMMAND GROUP
    # =====================================================

    def create_slash_group(self):

        group = app_commands.Group(
            name="youtube",
            description="YouTube alert system"
        )

        @group.command(
            name="setup",
            description="Set this channel as the YouTube alert channel"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def setup(interaction: discord.Interaction):

            if not interaction.guild:
                await interaction.response.send_message(
                    "Server only.",
                    ephemeral=True
                )
                return

            guild_data = self.get_guild(
                interaction.guild.id
            )

            guild_data["default_channel"] = (
                interaction.channel_id
            )

            save_data(self.data)

            await interaction.response.send_message(
                embed=make_embed(
                    "YouTube Alerts Setup",
                    (
                        f"✅ Alerts will be sent to "
                        f"<#{interaction.channel_id}>."
                    ),
                    SUCCESS
                )
            )

        @group.command(
            name="add",
            description="Track a YouTube channel"
        )
        @app_commands.describe(
            channel="YouTube channel URL, @handle or channel ID"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def add(
            interaction: discord.Interaction,
            channel: str
        ):

            if not interaction.guild:
                await interaction.response.send_message(
                    "Server only.",
                    ephemeral=True
                )
                return

            await interaction.response.defer()

            if not YOUTUBE_API_KEY:
                await interaction.followup.send(
                    embed=make_embed(
                        "API Key Missing",
                        "Set `YOUTUBE_API_KEY` first.",
                        ERROR
                    )
                )
                return

            found = await resolve_channel(
                channel
            )

            if not found:
                await interaction.followup.send(
                    embed=make_embed(
                        "Channel Not Found",
                        "I couldn't find that YouTube channel.",
                        ERROR
                    )
                )
                return

            guild_data = self.get_guild(
                interaction.guild.id
            )

            if found["id"] in guild_data["channels"]:
                await interaction.followup.send(
                    embed=make_embed(
                        "Already Added",
                        f"**{found['name']}** is already tracked.",
                        WARNING
                    )
                )
                return

            alert_channel = guild_data.get(
                "default_channel"
            )

            if not alert_channel:
                alert_channel = interaction.channel_id

            latest = await get_latest_video(
                found
            )

            guild_data["channels"][found["id"]] = {
                "name": found["name"],
                "handle": found.get(
                    "handle",
                    ""
                ),
                "channel_id": found["id"],
                "uploads_playlist": found[
                    "uploads_playlist"
                ],
                "discord_channel_id": alert_channel,
                "last_video_id": (
                    latest["id"]
                    if latest
                    else None
                )
            }

            save_data(self.data)

            await interaction.followup.send(
                embed=make_embed(
                    "YouTube Channel Added",
                    (
                        f"📺 **{found['name']}**\n"
                        f"🔔 <#{alert_channel}>\n\n"
                        "✅ New uploads will be announced."
                    ),
                    SUCCESS
                )
            )

        @group.command(
            name="remove",
            description="Remove a YouTube channel"
        )
        @app_commands.describe(
            channel_id="YouTube channel ID"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def remove(
            interaction: discord.Interaction,
            channel_id: str
        ):

            if not interaction.guild:
                await interaction.response.send_message(
                    "Server only.",
                    ephemeral=True
                )
                return

            guild_data = self.get_guild(
                interaction.guild.id
            )

            channels = guild_data["channels"]

            if channel_id not in channels:
                await interaction.response.send_message(
                    embed=make_embed(
                        "Not Found",
                        "That YouTube channel is not tracked.",
                        ERROR
                    ),
                    ephemeral=True
                )
                return

            name = channels[channel_id]["name"]

            del channels[channel_id]

            save_data(self.data)

            await interaction.response.send_message(
                embed=make_embed(
                    "YouTube Channel Removed",
                    f"🗑️ Removed **{name}**.",
                    SUCCESS
                )
            )

        @group.command(
            name="list",
            description="Show tracked YouTube channels"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def list_channels(
            interaction: discord.Interaction
        ):

            if not interaction.guild:
                await interaction.response.send_message(
                    "Server only.",
                    ephemeral=True
                )
                return

            guild_data = self.get_guild(
                interaction.guild.id
            )

            channels = guild_data["channels"]

            if not channels:
                await interaction.response.send_message(
                    embed=make_embed(
                        "YouTube Channels",
                        "No channels are being tracked.",
                        WARNING
                    )
                )
                return

            lines = []

            for index, (cid, info) in enumerate(
                channels.items(),
                start=1
            ):
                lines.append(
                    f"**{index}. {info['name']}**\n"
                    f"🆔 `{cid}`\n"
                    f"🔔 <#{info['discord_channel_id']}>"
                )

            await interaction.response.send_message(
                embed=make_embed(
                    "Tracked YouTube Channels",
                    "\n\n".join(lines)
                )
            )

        @group.command(
            name="config",
            description="Show YouTube alert configuration"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def config(
            interaction: discord.Interaction
        ):

            if not interaction.guild:
                await interaction.response.send_message(
                    "Server only.",
                    ephemeral=True
                )
                return

            guild_data = self.get_guild(
                interaction.guild.id
            )

            status = (
                "🟢 Enabled"
                if guild_data["enabled"]
                else "🔴 Disabled"
            )

            alert_channel = guild_data.get(
                "default_channel"
            )

            await interaction.response.send_message(
                embed=make_embed(
                    "YouTube Configuration",
                    (
                        f"**Status:** {status}\n"
                        f"**Tracked:** "
                        f"{len(guild_data['channels'])}\n"
                        f"**Alert Channel:** "
                        f"{f'<#{alert_channel}>' if alert_channel else 'Not configured'}\n"
                        f"**Check Interval:** "
                        f"{CHECK_INTERVAL}s\n"
                        f"**API:** "
                        f"{'🟢 Connected' if YOUTUBE_API_KEY else '🔴 Missing'}"
                    )
                )
            )

        @group.command(
            name="test",
            description="Send a YouTube alert test"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def test(
            interaction: discord.Interaction
        ):

            if not interaction.guild:
                await interaction.response.send_message(
                    "Server only.",
                    ephemeral=True
                )
                return

            guild_data = self.get_guild(
                interaction.guild.id
            )

            channel_id = guild_data.get(
                "default_channel"
            )

            if not channel_id:
                await interaction.response.send_message(
                    embed=make_embed(
                        "No Alert Channel",
                        "Run `/youtube setup` first.",
                        WARNING
                    ),
                    ephemeral=True
                )
                return

            channel_obj = interaction.guild.get_channel(
                channel_id
            )

            if not channel_obj:
                await interaction.response.send_message(
                    "Alert channel not found.",
                    ephemeral=True
                )
                return

            embed = make_embed(
                "NEW VIDEO UPLOAD",
                (
                    "**Air Commander YouTube Alert Test**\n\n"
                    "This is a preview of your YouTube alert."
                ),
                RED
            )

            embed.add_field(
                name="📺 Channel",
                value="Example Channel",
                inline=True
            )

            embed.add_field(
                name="🎬 Video",
                value="Example Video",
                inline=True
            )

            view = discord.ui.View()

            view.add_item(
                discord.ui.Button(
                    label="▶️ WATCH ON YOUTUBE",
                    url="https://youtube.com/",
                    style=discord.ButtonStyle.link
                )
            )

            await channel_obj.send(
                embed=embed,
                view=view
            )

            await interaction.response.send_message(
                embed=make_embed(
                    "Test Sent",
                    f"✅ Sent to {channel_obj.mention}.",
                    SUCCESS
                ),
                ephemeral=True
            )

        @group.command(
            name="enable",
            description="Enable YouTube alerts"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def enable(
            interaction: discord.Interaction
        ):

            guild_data = self.get_guild(
                interaction.guild.id
            )

            guild_data["enabled"] = True
            save_data(self.data)

            await interaction.response.send_message(
                embed=make_embed(
                    "YouTube Alerts Enabled",
                    "🟢 YouTube alerts are enabled.",
                    SUCCESS
                )
            )

        @group.command(
            name="disable",
            description="Disable YouTube alerts"
        )
        @app_commands.checks.has_permissions(
            manage_guild=True
        )
        async def disable(
            interaction: discord.Interaction
        ):

            guild_data = self.get_guild(
                interaction.guild.id
            )

            guild_data["enabled"] = False
            save_data(self.data)

            await interaction.response.send_message(
                embed=make_embed(
                    "YouTube Alerts Disabled",
                    "🔴 YouTube alerts are disabled.",
                    WARNING
                )
            )

        return group


# =========================================================
# SETUP
# =========================================================

def setup(bot):

    ensure_data_file()

    youtube_system = YouTubeAlerts(bot)

    # -----------------------------------------------------
    # PREFIX COMMAND
    # -----------------------------------------------------

    @bot.command(
        name="youtube"
    )
    async def youtube(
        ctx,
        action=None,
        *,
        argument=None
    ):
        await youtube_system.youtube_prefix(
            ctx,
            action,
            argument=argument
        )

    # -----------------------------------------------------
    # SLASH COMMAND
    # -----------------------------------------------------

    group = youtube_system.create_slash_group()

    # Avoid duplicate registration
    existing = bot.tree.get_command(
        "youtube"
    )

    if existing is None:
        bot.tree.add_command(group)
        print(
            "📺 YouTube Alerts slash command registered."
        )
    else:
        print(
            "⚠️ YouTube slash command already registered; skipped duplicate."
        )

    bot._air_youtube_alerts = youtube_system

    print(
        "📺 YouTube Alerts system initialized."
    )
