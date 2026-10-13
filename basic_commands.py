import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import time


# =========================================================
# AIR COMMANDER — COMMON EMBED
# =========================================================

def embed(title, description="", color=discord.Color.blurple()):
    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color,
        timestamp=discord.utils.utcnow()
    )
    e.set_footer(text="Air Commander • Clean control center")
    return e


def format_count(number: int) -> str:
    if number >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B".rstrip("0").rstrip(".")

    if number >= 1_000_000:
        return f"{number / 1_000_000:.1f}M".rstrip("0").rstrip(".")

    if number >= 1_000:
        return f"{number / 1_000:.1f}k".rstrip("0").rstrip(".")

    return str(number)


# =========================================================
# AIR COMMANDER — PREMIUM MASTER HELP MENU
# =========================================================

HELP_PAGE_SIZE = 7
HELP_CATEGORIES = [
    ("⚡", "Hosting & Bot Utilities"),
    ("🛡️", "Moderation & Security"),
    ("🎉", "Giveaways"),
    ("📈", "Leveling & XP"),
    ("📺", "YouTube Alerts"),
    ("🤖", "AI Assistant"),
    ("⚙️", "Server Setup & Automation"),
    ("🎫", "Ticket System"),
    ("🎮", "Games & Economy"),
    ("🎨", "Embeds & Custom Commands"),
    ("👑", "Owner Master Suite"),
    ("✨", "Other Commands"),
]


def _help_category(command_name: str) -> str:
    name = command_name.lower().strip()
    compact = name.replace("_", "").replace("-", "")
    if any(x in compact for x in ("giveaway", "gstart", "gend", "greroll")):
        return "Giveaways"
    if any(x in compact for x in ("level", "rank", "xp", "leaderboard", "quest", "airlevel")):
        return "Leveling & XP"
    if any(x in compact for x in ("youtube", "ytalert", "youtubealert")):
        return "YouTube Alerts"
    if any(x in compact for x in ("ticket", "transcript", "supportpanel")):
        return "Ticket System"
    if any(x in compact for x in ("ai", "chat", "askai", "mentionresponse")):
        return "AI Assistant"
    if any(x in compact for x in ("antinuke", "automode", "security", "airscan", "snipe", "warn", "ban", "kick", "purge", "clear", "timeout", "mute", "unmute", "lock", "unlock", "unwarn", "modcase")):
        return "Moderation & Security"
    if any(x in compact for x in ("welcome", "autorole", "automati", "config", "setup", "serverconfig", "log", "backup", "restore", "voice", "jtc")):
        return "Server Setup & Automation"
    if any(x in compact for x in ("embed", "customcommand", "cmdmaker", "autoresponder")):
        return "Embeds & Custom Commands"
    if any(x in compact for x in ("game", "coinflip", "dice", "rps", "blox", "fruit", "inventory", "balance", "daily", "work", "shop", "pay")):
        return "Games & Economy"
    if any(x in compact for x in ("owner", "syncslash", "prefixless", "shutdown", "restart", "global")):
        return "Owner Master Suite"
    if any(x in compact for x in ("ping", "uptime", "botinfo", "dbstatus", "diagnostic", "status", "help", "serverinfo", "userinfo", "avatar", "membercount")):
        return "Hosting & Bot Utilities"
    return "Other Commands"


def _command_description(command, mode: str) -> str:
    description = getattr(command, "description", None) if mode == "slash" else (getattr(command, "help", None) or getattr(command, "brief", None))
    return str(description or "No description added yet.").replace("\n", " ").strip()[:100]


def _collect_commands(bot, mode="prefix"):
    entries, seen = [], set()
    if mode == "slash":
        def add_slash(command, parent=""):
            full_name = f"{parent} {command.name}".strip()
            children = getattr(command, "commands", None)
            if children:
                for child in children:
                    add_slash(child, full_name)
                return
            key = full_name.lower()
            if key not in seen:
                seen.add(key)
                entries.append((_help_category(full_name), "/" + full_name, _command_description(command, "slash"), command))
        try:
            for command in bot.tree.get_commands():
                add_slash(command)
        except Exception as exc:
            print(f"Help slash command collection error: {type(exc).__name__}: {exc}", flush=True)
    else:
        def add_prefix(command, parent=""):
            if getattr(command, "hidden", False):
                return
            full_name = f"{parent} {command.name}".strip()
            children = getattr(command, "commands", None)
            key = full_name.lower()
            if key in seen:
                return
            seen.add(key)
            entries.append((_help_category(full_name), "," + full_name, _command_description(command, "prefix"), command))
            if children:
                for child in children:
                    add_prefix(child, full_name)
        try:
            for command in bot.commands:
                add_prefix(command)
        except Exception as exc:
            print(f"Help prefix command collection error: {type(exc).__name__}: {exc}", flush=True)
    entries.sort(key=lambda item: (item[0].lower(), item[1].lower()))
    return entries


def _help_embed(bot, mode="prefix", category=None, page=0, search_query=None):
    all_entries = _collect_commands(bot, mode)
    if search_query:
        query = search_query.casefold().strip()
        entries = [item for item in all_entries if query in item[1].casefold() or query in item[2].casefold() or query in item[0].casefold()]
        title = "🔎 Air Commander • Search Results"
        intro = f"Search: **{discord.utils.escape_markdown(search_query)}** • **{len(entries)} result(s)**"
    elif category:
        entries = [item for item in all_entries if item[0] == category]
        emoji = next((e for e, name in HELP_CATEGORIES if name == category), "📚")
        title = f"{emoji} Air Commander • {category}"
        intro = f"**{len(entries)} command(s)** in this category."
    else:
        entries = []
        title = "✦ A I R   C O M M A N D E R ✦"
        intro = ("💎 **Premium Discord Bot Infrastructure**\n"
                 "Moderation, security, giveaways, leveling, YouTube alerts, AI, tickets and automation — all in one command center.\n\n"
                 f"**Command entries:** {len(all_entries)} • **Mode:** {('comma prefix' if mode == 'prefix' else 'slash commands')}\n\n"
                 "✨ **Select a category from the dropdown below:**")

    pages = max(1, (len(entries) + HELP_PAGE_SIZE - 1) // HELP_PAGE_SIZE)
    page = max(0, min(page, pages - 1))
    current = entries[page * HELP_PAGE_SIZE:(page + 1) * HELP_PAGE_SIZE]
    result = discord.Embed(title=title, description=intro, color=discord.Color.from_rgb(64, 137, 255), timestamp=discord.utils.utcnow())

    if category is None and not search_query:
        counts = {name: 0 for _, name in HELP_CATEGORIES}
        for item in all_entries:
            counts[item[0]] = counts.get(item[0], 0) + 1
        lines = [f"{emoji} **{name}** — {counts.get(name, 0)} commands" for emoji, name in HELP_CATEGORIES if counts.get(name, 0)]
        result.add_field(name="📚 Command Categories", value="\n".join(lines)[:1024] or "Commands are being indexed.", inline=False)
        result.add_field(name="⌨️ Quick Guide", value=",help — open this menu\n,help <command> — command details\nUse the dropdown, page buttons, or Search.", inline=False)
    elif current:
        lines = [f"**{name}**\n> {description}" for _, name, description, _ in current]
        result.add_field(name=f"📖 Commands • Page {page + 1}/{pages}", value="\n".join(lines)[:1024], inline=False)
    else:
        result.add_field(name="No matching commands", value="Try a shorter search or select another category.", inline=False)
    result.set_footer(text=f"✈️ Air Commander • Master Menu • {len(all_entries)} commands")
    return result, pages


class HelpSearchModal(discord.ui.Modal, title="Search Air Commander Commands"):
    query = discord.ui.TextInput(label="Command name or keyword", placeholder="Try: leveling, youtube, warn, giveaway...", min_length=1, max_length=80, required=True)

    def __init__(self, bot, mode="prefix"):
        super().__init__()
        self.bot, self.mode = bot, mode

    async def on_submit(self, interaction: discord.Interaction):
        query = str(self.query.value).strip()
        result, _ = _help_embed(self.bot, self.mode, search_query=query)
        await interaction.response.send_message(embed=result, view=HelpView(self.bot, self.mode, search_query=query), ephemeral=True)


class HelpCategorySelect(discord.ui.Select):
    def __init__(self, bot, mode="prefix", category=None, page=0, search_query=None):
        self.bot, self.mode = bot, mode
        options = [discord.SelectOption(label="Master Menu", value="__home__", emoji="✈️", description="Return to the main menu", default=category is None and search_query is None)]
        counts = {}
        for cat, _, _, _ in _collect_commands(bot, mode):
            counts[cat] = counts.get(cat, 0) + 1
        for emoji, name in HELP_CATEGORIES:
            count = counts.get(name, 0)
            if count:
                options.append(discord.SelectOption(label=name[:100], value=name, emoji=emoji, description=f"{count} command(s)", default=category == name))
        super().__init__(placeholder="✨ Select a command category...", min_values=1, max_values=1, options=options[:25], custom_id=f"aircommander:masterhelp:{mode}")

    async def callback(self, interaction: discord.Interaction):
        category = None if self.values[0] == "__home__" else self.values[0]
        result, _ = _help_embed(self.bot, self.mode, category=category)
        await interaction.response.edit_message(embed=result, view=HelpView(self.bot, self.mode, category=category))


class HelpView(discord.ui.View):
    def __init__(self, bot, mode="prefix", category=None, page=0, search_query=None):
        super().__init__(timeout=300)
        self.bot, self.mode, self.category, self.page, self.search_query = bot, mode, category, page, search_query
        self.add_item(HelpCategorySelect(bot, mode, category, page, search_query))
        _, pages = _help_embed(bot, mode, category=category, page=page, search_query=search_query)
        self.previous_page.disabled = page <= 0
        self.next_page.disabled = page >= pages - 1

    @discord.ui.button(label="Previous", emoji="◀️", style=discord.ButtonStyle.secondary, custom_id="aircommander:help:previous")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        new_page = max(0, self.page - 1)
        result, _ = _help_embed(self.bot, self.mode, category=self.category, page=new_page, search_query=self.search_query)
        await interaction.response.edit_message(embed=result, view=HelpView(self.bot, self.mode, self.category, new_page, self.search_query))

    @discord.ui.button(label="Next", emoji="▶️", style=discord.ButtonStyle.primary, custom_id="aircommander:help:next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        _, pages = _help_embed(self.bot, self.mode, category=self.category, page=self.page, search_query=self.search_query)
        new_page = min(pages - 1, self.page + 1)
        result, _ = _help_embed(self.bot, self.mode, category=self.category, page=new_page, search_query=self.search_query)
        await interaction.response.edit_message(embed=result, view=HelpView(self.bot, self.mode, self.category, new_page, self.search_query))

    @discord.ui.button(label="Search", emoji="🔎", style=discord.ButtonStyle.success, custom_id="aircommander:help:search")
    async def search_commands(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(HelpSearchModal(self.bot, self.mode))

    @discord.ui.button(label="Home", emoji="🏠", style=discord.ButtonStyle.secondary, custom_id="aircommander:help:home")
    async def home(self, interaction: discord.Interaction, button: discord.ui.Button):
        result, _ = _help_embed(self.bot, self.mode)
        await interaction.response.edit_message(embed=result, view=HelpView(self.bot, self.mode))


# =========================================================
# SETUP
# =========================================================

def setup(bot: commands.Bot):

    # =====================================================
    # SLASH COMMANDS
    # =====================================================

    @bot.tree.command(
        name="clear",
        description="Delete recent messages"
    )
    @app_commands.describe(
        amount="Number of messages to delete (1-100)"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def clear(
        i: discord.Interaction,
        amount: app_commands.Range[int, 1, 100]
    ):

        if not isinstance(
            i.channel,
            discord.TextChannel
        ):
            return await i.response.send_message(
                "❌ This command works in text channels only.",
                ephemeral=True
            )

        await i.response.defer(
            ephemeral=True
        )

        deleted = await i.channel.purge(
            limit=amount
        )

        await i.followup.send(
            embed=embed(
                "Messages Cleared",
                f"Removed **{len(deleted)}** message(s) from {i.channel.mention}.",
                discord.Color.orange()
            ),
            ephemeral=True
        )

    # =====================================================
    # KICK
    # =====================================================

    @bot.tree.command(
        name="kick",
        description="Kick a member"
    )
    @app_commands.describe(
        member="Member to kick",
        reason="Reason for the action"
    )
    @app_commands.checks.has_permissions(
        kick_members=True
    )
    async def kick(
        i: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided"
    ):

        if (
            member == i.user
            or member.top_role >= i.user.top_role
            or member.top_role >= i.guild.me.top_role
        ):
            return await i.response.send_message(
                "❌ That member cannot be kicked due to role hierarchy.",
                ephemeral=True
            )

        await member.kick(
            reason=f"{reason} | Moderator: {i.user}"
        )

        e = embed(
            "Member Kicked",
            f"{member.mention} was removed from the server.",
            discord.Color.red()
        )

        e.add_field(
            name="Moderator",
            value=i.user.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # BAN
    # =====================================================

    @bot.tree.command(
        name="ban",
        description="Ban a member"
    )
    @app_commands.describe(
        member="Member to ban",
        reason="Reason for the action",
        delete_days="Delete message history in days (0-7)"
    )
    @app_commands.checks.has_permissions(
        ban_members=True
    )
    async def ban(
        i: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
        delete_days: app_commands.Range[int, 0, 7] = 0
    ):

        if (
            member == i.user
            or member.top_role >= i.user.top_role
            or member.top_role >= i.guild.me.top_role
        ):
            return await i.response.send_message(
                "❌ That member cannot be banned due to role hierarchy.",
                ephemeral=True
            )

        await member.ban(
            reason=f"{reason} | Moderator: {i.user}",
            delete_message_days=delete_days
        )

        e = embed(
            "Member Banned",
            f"{member.mention} was banned from the server.",
            discord.Color.red()
        )

        e.add_field(
            name="Moderator",
            value=i.user.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # UNBAN
    # =====================================================

    @bot.tree.command(
        name="unban",
        description="Unban a user by ID"
    )
    @app_commands.describe(
        user_id="Discord user ID",
        reason="Reason for the action"
    )
    @app_commands.checks.has_permissions(
        ban_members=True
    )
    async def unban(
        i: discord.Interaction,
        user_id: str,
        reason: str = "No reason provided"
    ):

        try:
            uid = int(user_id)

            await i.guild.unban(
                discord.Object(id=uid),
                reason=f"{reason} | Moderator: {i.user}"
            )

        except (
            ValueError,
            discord.NotFound
        ):
            return await i.response.send_message(
                "❌ No matching banned user was found.",
                ephemeral=True
            )

        e = embed(
            "Member Unbanned",
            f"User ID **{uid}** is no longer banned.",
            discord.Color.green()
        )

        e.add_field(
            name="Moderator",
            value=i.user.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # TIMEOUT
    # =====================================================

    @bot.tree.command(
        name="timeout",
        description="Timeout a member"
    )
    @app_commands.describe(
        member="Member to timeout",
        minutes="Timeout duration in minutes",
        reason="Reason"
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def timeout(
        i: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str = "No reason provided"
    ):

        if (
            member == i.user
            or member.top_role >= i.user.top_role
            or member.top_role >= i.guild.me.top_role
        ):
            return await i.response.send_message(
                "❌ That member cannot be timed out due to role hierarchy.",
                ephemeral=True
            )

        await member.timeout(
            timedelta(minutes=minutes),
            reason=f"{reason} | Moderator: {i.user}"
        )

        e = embed(
            "Member Timed Out",
            f"{member.mention} is timed out for **{minutes} minute(s)**.",
            discord.Color.orange()
        )

        e.add_field(
            name="Moderator",
            value=i.user.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # UNTIMEOUT
    # =====================================================

    @bot.tree.command(
        name="untimeout",
        description="Remove a member timeout"
    )
    @app_commands.describe(
        member="Member to untimeout",
        reason="Reason"
    )
    @app_commands.checks.has_permissions(
        moderate_members=True
    )
    async def untimeout(
        i: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided"
    ):

        await member.timeout(
            None,
            reason=f"{reason} | Moderator: {i.user}"
        )

        e = embed(
            "Timeout Removed",
            f"Timeout removed from {member.mention}.",
            discord.Color.green()
        )

        e.add_field(
            name="Moderator",
            value=i.user.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # SLOWMODE
    # =====================================================

    @bot.tree.command(
        name="slowmode",
        description="Set channel slowmode"
    )
    @app_commands.describe(
        seconds="Slowmode seconds (0 disables it)"
    )
    @app_commands.checks.has_permissions(
        manage_channels=True
    )
    async def slowmode(
        i: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600]
    ):

        if not hasattr(i.channel, "edit"):
            return await i.response.send_message(
                "❌ This channel cannot use slowmode.",
                ephemeral=True
            )

        await i.channel.edit(
            slowmode_delay=seconds,
            reason=f"Changed by {i.user}"
        )

        e = embed(
            "Slowmode Updated",
            f"{i.channel.mention} slowmode is now **{seconds}s**.",
            discord.Color.teal()
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # LOCK / UNLOCK
    # =====================================================

    async def set_lock(i, locked):

        if not isinstance(
            i.channel,
            discord.TextChannel
        ):
            return await i.response.send_message(
                "❌ Text channel only.",
                ephemeral=True
            )

        overwrite = i.channel.overwrites_for(
            i.guild.default_role
        )

        overwrite.send_messages = (
            False if locked else None
        )

        await i.channel.set_permissions(
            i.guild.default_role,
            overwrite=overwrite,
            reason=(
                f"Channel "
                f"{'locked' if locked else 'unlocked'} "
                f"by {i.user}"
            )
        )

        e = embed(
            "Channel Locked" if locked else "Channel Unlocked",
            (
                f"{i.channel.mention} is now "
                f"**{'locked' if locked else 'open'}** "
                "for @everyone."
            ),
            discord.Color.red()
            if locked
            else discord.Color.green()
        )

        await i.response.send_message(
            embed=e
        )

    @bot.tree.command(
        name="lock",
        description="Lock the current text channel"
    )
    @app_commands.checks.has_permissions(
        manage_channels=True
    )
    async def lock(i: discord.Interaction):
        await set_lock(i, True)

    @bot.tree.command(
        name="unlock",
        description="Unlock the current text channel"
    )
    @app_commands.checks.has_permissions(
        manage_channels=True
    )
    async def unlock(i: discord.Interaction):
        await set_lock(i, False)

    # =====================================================
    # NICK
    # =====================================================

    @bot.tree.command(
        name="nick",
        description="Change a member nickname"
    )
    @app_commands.describe(
        member="Member",
        nickname="New nickname"
    )
    @app_commands.checks.has_permissions(
        manage_nicknames=True
    )
    async def nick(
        i: discord.Interaction,
        member: discord.Member,
        nickname: str | None = None
    ):

        await member.edit(
            nick=nickname,
            reason=f"Nickname changed by {i.user}"
        )

        e = embed(
            "Nickname Updated",
            f"Updated nickname for {member.mention}."
        )

        e.add_field(
            name="New Nickname",
            value=nickname or "Reset to username"
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # ROLE
    # =====================================================

    @bot.tree.command(
        name="role",
        description="Add or remove a role from a member"
    )
    @app_commands.describe(
        action="Add or remove",
        member="Member",
        role="Role"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(
                name="Add",
                value="add"
            ),
            app_commands.Choice(
                name="Remove",
                value="remove"
            )
        ]
    )
    @app_commands.checks.has_permissions(
        manage_roles=True
    )
    async def role(
        i: discord.Interaction,
        action: app_commands.Choice[str],
        member: discord.Member,
        role: discord.Role
    ):

        if (
            role.is_default()
            or role >= i.guild.me.top_role
        ):
            return await i.response.send_message(
                "❌ I cannot manage that role because of role hierarchy.",
                ephemeral=True
            )

        if action.value == "add":

            await member.add_roles(
                role,
                reason=f"Role added by {i.user}"
            )

        else:

            await member.remove_roles(
                role,
                reason=f"Role removed by {i.user}"
            )

        e = embed(
            "Role Updated",
            (
                f"{role.mention} was "
                f"**{action.name.lower()}** "
                f"for {member.mention}."
            ),
            discord.Color.green()
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # SAY
    # =====================================================

    @bot.tree.command(
        name="say",
        description="Make Air Commander send a message"
    )
    @app_commands.describe(
        message="Message to send"
    )
    @app_commands.checks.has_permissions(
        manage_messages=True
    )
    async def say(
        i: discord.Interaction,
        message: str
    ):

        await i.response.send_message(
            embed=embed(
                "Message Sent",
                message,
                discord.Color.blurple()
            )
        )

    # =====================================================
    # ANNOUNCE
    # =====================================================

    @bot.tree.command(
        name="announce",
        description="Send a styled announcement"
    )
    @app_commands.describe(
        message="Announcement text"
    )
    @app_commands.checks.has_permissions(
        manage_guild=True
    )
    async def announce(
        i: discord.Interaction,
        message: str
    ):

        e = embed(
            "Announcement",
            message,
            discord.Color.gold()
        )

        if i.guild.icon:
            e.set_author(
                name=i.guild.name,
                icon_url=i.guild.icon.url
            )
        else:
            e.set_author(
                name=i.guild.name
            )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # POLL
    # =====================================================

    @bot.tree.command(
        name="poll",
        description="Create a simple yes/no poll"
    )
    @app_commands.describe(
        question="Poll question"
    )
    async def poll(
        i: discord.Interaction,
        question: str
    ):

        e = embed(
            "Community Poll",
            question,
            discord.Color.blurple()
        )

        e.add_field(
            name="Vote",
            value="👍 Yes\n👎 No",
            inline=False
        )

        await i.response.send_message(
            embed=e
        )

        msg = await i.original_response()

        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    # =====================================================
    # SERVER ICON
    # =====================================================

    @bot.tree.command(
        name="servericon",
        description="Show the server icon"
    )
    async def servericon(
        i: discord.Interaction
    ):

        if not i.guild.icon:
            return await i.response.send_message(
                "This server has no icon.",
                ephemeral=True
            )

        e = embed(
            f"{i.guild.name} • Server Icon"
        )

        e.set_image(
            url=i.guild.icon.replace(
                size=1024
            ).url
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # BANNER
    # =====================================================

    @bot.tree.command(
        name="banner",
        description="Show the server banner"
    )
    async def banner(
        i: discord.Interaction
    ):

        if not i.guild.banner:
            return await i.response.send_message(
                "This server has no banner.",
                ephemeral=True
            )

        e = embed(
            f"{i.guild.name} • Server Banner"
        )

        e.set_image(
            url=i.guild.banner.replace(
                size=1024
            ).url
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # MEMBER COUNT
    # =====================================================

    @bot.tree.command(
        name="membercount",
        description="Show server member counts"
    )
    async def membercount(
        i: discord.Interaction
    ):

        g = i.guild

        bots = sum(
            1
            for m in g.members
            if m.bot
        )

        total = g.member_count or len(g.members)

        e = embed(
            "Member Count",
            f"Live member breakdown for **{g.name}**."
        )

        e.add_field(
            name="Total",
            value=str(total),
            inline=True
        )

        e.add_field(
            name="Humans",
            value=str(max(total - bots, 0)),
            inline=True
        )

        e.add_field(
            name="Bots",
            value=str(bots),
            inline=True
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # CHANNEL INFO
    # =====================================================

    @bot.tree.command(
        name="channelinfo",
        description="Show channel information"
    )
    @app_commands.describe(
        channel="Channel to inspect"
    )
    async def channelinfo(
        i: discord.Interaction,
        channel: discord.TextChannel | None = None
    ):

        c = channel or i.channel

        e = embed(
            f"Channel Info • {c.name}"
        )

        e.add_field(
            name="ID",
            value=str(c.id),
            inline=True
        )

        e.add_field(
            name="Type",
            value=str(c.type),
            inline=True
        )

        e.add_field(
            name="Category",
            value=(
                c.category.name
                if c.category
                else "None"
            ),
            inline=True
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # ROLE INFO
    # =====================================================

    @bot.tree.command(
        name="roleinfo",
        description="Show role information"
    )
    @app_commands.describe(
        role="Role to inspect"
    )
    async def roleinfo(
        i: discord.Interaction,
        role: discord.Role
    ):

        e = embed(
            f"Role Info • {role.name}"
        )

        e.add_field(
            name="ID",
            value=str(role.id),
            inline=True
        )

        e.add_field(
            name="Members",
            value=str(len(role.members)),
            inline=True
        )

        e.add_field(
            name="Position",
            value=str(role.position),
            inline=True
        )

        e.add_field(
            name="Mentionable",
            value="Yes" if role.mentionable else "No",
            inline=True
        )

        e.add_field(
            name="Managed",
            value="Yes" if role.managed else "No",
            inline=True
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # BOT INFO
    # =====================================================

    @bot.tree.command(
        name="botinfo",
        description="Show Air Commander status"
    )
    async def botinfo(
        i: discord.Interaction
    ):

        uptime = int(
            time.time()
            - getattr(
                bot,
                "_air_start_time",
                time.time()
            )
        )

        total_members = sum(
            g.member_count or len(g.members)
            for g in bot.guilds
        )

        e = embed(
            "✈️ Air Commander • System Status",
            "🟢 **Online & Operational** • Clean, fast and ready.",
            discord.Color.blurple()
        )

        e.add_field(
            name="🌐 Servers",
            value=f"**{len(bot.guilds):,}**",
            inline=True
        )

        e.add_field(
            name="👥 Members",
            value=(
                f"**{total_members:,}** "
                f"({format_count(total_members)})"
            ),
            inline=True
        )

        e.add_field(
            name="📡 Latency",
            value=f"**{round(bot.latency * 1000)} ms**",
            inline=True
        )

        e.add_field(
            name="⏱️ Uptime",
            value=(
                f"**{uptime // 3600}h "
                f"{(uptime % 3600) // 60}m**"
            ),
            inline=True
        )

        e.add_field(
            name="🛠️ Framework",
            value="**discord.py**",
            inline=True
        )

        e.add_field(
            name="🟢 Status",
            value="**Operational**",
            inline=True
        )

        e.add_field(
            name="💬 Support Server",
            value="[🚀 Join Air Commander Support Server](https://discord.gg/hVpaK2gbhh)",
            inline=False
        )

        if bot.user:
            e.set_thumbnail(
                url=bot.user.display_avatar.url
            )

        e.set_footer(
            text="✈️ Air Commander • Systems Operational"
        )

        await i.response.send_message(
            embed=e
        )

    # =====================================================
    # PREFIX COMMANDS
    # Prefix: ,
    # =====================================================

    @bot.command(name="ping")
    async def prefix_ping(ctx):

        await ctx.send(
            embed=embed(
                "Pong!",
                f"Latency: **{round(bot.latency * 1000)} ms**",
                discord.Color.green()
            )
        )

    @bot.command(name="clear")
    @commands.has_permissions(
        manage_messages=True
    )
    async def prefix_clear(
        ctx,
        amount: int
    ):

        if amount < 1 or amount > 100:
            return await ctx.send(
                "❌ Amount must be between **1 and 100**."
            )

        if not isinstance(
            ctx.channel,
            discord.TextChannel
        ):
            return await ctx.send(
                "❌ This command works in text channels only."
            )

        deleted = await ctx.channel.purge(
            limit=amount
        )

        await ctx.send(
            embed=embed(
                "Messages Cleared",
                f"Removed **{len(deleted)}** message(s) from {ctx.channel.mention}.",
                discord.Color.orange()
            ),
            delete_after=5
        )

    @bot.command(name="kick")
    @commands.has_permissions(
        kick_members=True
    )
    async def prefix_kick(
        ctx,
        member: discord.Member,
        *,
        reason="No reason provided"
    ):

        if (
            member == ctx.author
            or member.top_role >= ctx.author.top_role
            or member.top_role >= ctx.guild.me.top_role
        ):
            return await ctx.send(
                "❌ That member cannot be kicked due to role hierarchy."
            )

        await member.kick(
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        e = embed(
            "Member Kicked",
            f"{member.mention} was removed from the server.",
            discord.Color.red()
        )

        e.add_field(
            name="Moderator",
            value=ctx.author.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="ban")
    @commands.has_permissions(
        ban_members=True
    )
    async def prefix_ban(
        ctx,
        member: discord.Member,
        *,
        reason="No reason provided"
    ):

        if (
            member == ctx.author
            or member.top_role >= ctx.author.top_role
            or member.top_role >= ctx.guild.me.top_role
        ):
            return await ctx.send(
                "❌ That member cannot be banned due to role hierarchy."
            )

        await member.ban(
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        e = embed(
            "Member Banned",
            f"{member.mention} was banned from the server.",
            discord.Color.red()
        )

        e.add_field(
            name="Moderator",
            value=ctx.author.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="unban")
    @commands.has_permissions(
        ban_members=True
    )
    async def prefix_unban(
        ctx,
        user_id: int,
        *,
        reason="No reason provided"
    ):

        try:

            await ctx.guild.unban(
                discord.Object(id=user_id),
                reason=f"{reason} | Moderator: {ctx.author}"
            )

        except discord.NotFound:

            return await ctx.send(
                "❌ No matching banned user was found."
            )

        e = embed(
            "Member Unbanned",
            f"User ID **{user_id}** is no longer banned.",
            discord.Color.green()
        )

        e.add_field(
            name="Moderator",
            value=ctx.author.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="timeout")
    @commands.has_permissions(
        moderate_members=True
    )
    async def prefix_timeout(
        ctx,
        member: discord.Member,
        minutes: int,
        *,
        reason="No reason provided"
    ):

        if minutes < 1 or minutes > 40320:
            return await ctx.send(
                "❌ Timeout must be between **1 and 40320 minutes**."
            )

        if (
            member == ctx.author
            or member.top_role >= ctx.author.top_role
            or member.top_role >= ctx.guild.me.top_role
        ):
            return await ctx.send(
                "❌ That member cannot be timed out due to role hierarchy."
            )

        await member.timeout(
            timedelta(minutes=minutes),
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        e = embed(
            "Member Timed Out",
            f"{member.mention} is timed out for **{minutes} minute(s)**.",
            discord.Color.orange()
        )

        e.add_field(
            name="Moderator",
            value=ctx.author.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="untimeout")
    @commands.has_permissions(
        moderate_members=True
    )
    async def prefix_untimeout(
        ctx,
        member: discord.Member,
        *,
        reason="No reason provided"
    ):

        await member.timeout(
            None,
            reason=f"{reason} | Moderator: {ctx.author}"
        )

        e = embed(
            "Timeout Removed",
            f"Timeout removed from {member.mention}.",
            discord.Color.green()
        )

        e.add_field(
            name="Moderator",
            value=ctx.author.mention
        )

        e.add_field(
            name="Reason",
            value=reason[:1024]
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="slowmode")
    @commands.has_permissions(
        manage_channels=True
    )
    async def prefix_slowmode(
        ctx,
        seconds: int
    ):

        if seconds < 0 or seconds > 21600:
            return await ctx.send(
                "❌ Slowmode must be between **0 and 21600 seconds**."
            )

        if not isinstance(
            ctx.channel,
            discord.TextChannel
        ):
            return await ctx.send(
                "❌ Text channel only."
            )

        await ctx.channel.edit(
            slowmode_delay=seconds,
            reason=f"Changed by {ctx.author}"
        )

        await ctx.send(
            embed=embed(
                "Slowmode Updated",
                f"{ctx.channel.mention} slowmode is now **{seconds}s**.",
                discord.Color.teal()
            )
        )

    @bot.command(name="lock")
    @commands.has_permissions(
        manage_channels=True
    )
    async def prefix_lock(ctx):

        if not isinstance(
            ctx.channel,
            discord.TextChannel
        ):
            return await ctx.send(
                "❌ Text channel only."
            )

        overwrite = ctx.channel.overwrites_for(
            ctx.guild.default_role
        )

        overwrite.send_messages = False

        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel locked by {ctx.author}"
        )

        await ctx.send(
            embed=embed(
                "Channel Locked",
                f"{ctx.channel.mention} is now **locked** for @everyone.",
                discord.Color.red()
            )
        )

    @bot.command(name="unlock")
    @commands.has_permissions(
        manage_channels=True
    )
    async def prefix_unlock(ctx):

        if not isinstance(
            ctx.channel,
            discord.TextChannel
        ):
            return await ctx.send(
                "❌ Text channel only."
            )

        overwrite = ctx.channel.overwrites_for(
            ctx.guild.default_role
        )

        overwrite.send_messages = None

        await ctx.channel.set_permissions(
            ctx.guild.default_role,
            overwrite=overwrite,
            reason=f"Channel unlocked by {ctx.author}"
        )

        await ctx.send(
            embed=embed(
                "Channel Unlocked",
                f"{ctx.channel.mention} is now **open** for @everyone.",
                discord.Color.green()
            )
        )

    @bot.command(name="nick")
    @commands.has_permissions(
        manage_nicknames=True
    )
    async def prefix_nick(
        ctx,
        member: discord.Member,
        *,
        nickname=None
    ):

        await member.edit(
            nick=nickname,
            reason=f"Nickname changed by {ctx.author}"
        )

        e = embed(
            "Nickname Updated",
            f"Updated nickname for {member.mention}."
        )

        e.add_field(
            name="New Nickname",
            value=nickname or "Reset to username"
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="role")
    @commands.has_permissions(
        manage_roles=True
    )
    async def prefix_role(
        ctx,
        action: str,
        member: discord.Member,
        role: discord.Role
    ):

        action = action.lower()

        if action not in (
            "add",
            "remove"
        ):
            return await ctx.send(
                "❌ Use `,role add @user @role` or `,role remove @user @role`."
            )

        if (
            role.is_default()
            or role >= ctx.guild.me.top_role
        ):
            return await ctx.send(
                "❌ I cannot manage that role because of role hierarchy."
            )

        if action == "add":

            await member.add_roles(
                role,
                reason=f"Role added by {ctx.author}"
            )

        else:

            await member.remove_roles(
                role,
                reason=f"Role removed by {ctx.author}"
            )

        await ctx.send(
            embed=embed(
                "Role Updated",
                f"{role.mention} was **{action}** for {member.mention}.",
                discord.Color.green()
            )
        )

    @bot.command(name="say")
    @commands.has_permissions(
        manage_messages=True
    )
    async def prefix_say(
        ctx,
        *,
        message: str
    ):

        await ctx.send(
            embed=embed(
                "Message Sent",
                message
            )
        )

    @bot.command(name="announce")
    @commands.has_permissions(
        manage_guild=True
    )
    async def prefix_announce(
        ctx,
        *,
        message: str
    ):

        e = embed(
            "Announcement",
            message,
            discord.Color.gold()
        )

        if ctx.guild.icon:

            e.set_author(
                name=ctx.guild.name,
                icon_url=ctx.guild.icon.url
            )

        else:

            e.set_author(
                name=ctx.guild.name
            )

        await ctx.send(
            embed=e
        )

    @bot.command(name="poll")
    async def prefix_poll(
        ctx,
        *,
        question: str
    ):

        e = embed(
            "Community Poll",
            question
        )

        e.add_field(
            name="Vote",
            value="👍 Yes\n👎 No",
            inline=False
        )

        msg = await ctx.send(
            embed=e
        )

        await msg.add_reaction("👍")
        await msg.add_reaction("👎")

    @bot.command(name="servericon")
    async def prefix_servericon(ctx):

        if not ctx.guild.icon:
            return await ctx.send(
                "This server has no icon."
            )

        e = embed(
            f"{ctx.guild.name} • Server Icon"
        )

        e.set_image(
            url=ctx.guild.icon.replace(
                size=1024
            ).url
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="banner")
    async def prefix_banner(ctx):

        if not ctx.guild.banner:
            return await ctx.send(
                "This server has no banner."
            )

        e = embed(
            f"{ctx.guild.name} • Server Banner"
        )

        e.set_image(
            url=ctx.guild.banner.replace(
                size=1024
            ).url
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="membercount")
    async def prefix_membercount(ctx):

        g = ctx.guild

        bots = sum(
            1
            for m in g.members
            if m.bot
        )

        total = g.member_count or len(g.members)

        e = embed(
            "Member Count",
            f"Live member breakdown for **{g.name}**."
        )

        e.add_field(
            name="Total",
            value=str(total),
            inline=True
        )

        e.add_field(
            name="Humans",
            value=str(max(total - bots, 0)),
            inline=True
        )

        e.add_field(
            name="Bots",
            value=str(bots),
            inline=True
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="channelinfo")
    async def prefix_channelinfo(
        ctx,
        channel: discord.TextChannel | None = None
    ):

        c = channel or ctx.channel

        e = embed(
            f"Channel Info • {c.name}"
        )

        e.add_field(
            name="ID",
            value=str(c.id),
            inline=True
        )

        e.add_field(
            name="Type",
            value=str(c.type),
            inline=True
        )

        e.add_field(
            name="Category",
            value=(
                c.category.name
                if c.category
                else "None"
            ),
            inline=True
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="roleinfo")
    async def prefix_roleinfo(
        ctx,
        role: discord.Role
    ):

        e = embed(
            f"Role Info • {role.name}"
        )

        e.add_field(
            name="ID",
            value=str(role.id),
            inline=True
        )

        e.add_field(
            name="Members",
            value=str(len(role.members)),
            inline=True
        )

        e.add_field(
            name="Position",
            value=str(role.position),
            inline=True
        )

        e.add_field(
            name="Mentionable",
            value="Yes" if role.mentionable else "No",
            inline=True
        )

        e.add_field(
            name="Managed",
            value="Yes" if role.managed else "No",
            inline=True
        )

        await ctx.send(
            embed=e
        )

    @bot.command(name="botinfo")
    async def prefix_botinfo(ctx):

        uptime = int(
            time.time()
            - getattr(
                bot,
                "_air_start_time",
                time.time()
            )
        )

        total_members = sum(
            g.member_count or len(g.members)
            for g in bot.guilds
        )

        e = embed(
            "✈️ Air Commander • System Status",
            "🟢 **Online & Operational** • Clean, fast and ready.",
            discord.Color.blurple()
        )

        e.add_field(
            name="🌐 Servers",
            value=f"**{len(bot.guilds):,}**",
            inline=True
        )

        e.add_field(
            name="👥 Members",
            value=(
                f"**{total_members:,}** "
                f"({format_count(total_members)})"
            ),
            inline=True
        )

        e.add_field(
            name="📡 Latency",
            value=f"**{round(bot.latency * 1000)} ms**",
            inline=True
        )

        e.add_field(
            name="⏱️ Uptime",
            value=(
                f"**{uptime // 3600}h "
                f"{(uptime % 3600) // 60}m**"
            ),
            inline=True
        )

        e.add_field(
            name="🛠️ Framework",
            value="**discord.py**",
            inline=True
        )

        e.add_field(
            name="🟢 Status",
            value="**Operational**",
            inline=True
        )

        e.add_field(
            name="💬 Support Server",
            value="[🚀 Join Air Commander Support Server](https://discord.gg/hVpaK2gbhh)",
            inline=False
        )

        if bot.user:
            e.set_thumbnail(
                url=bot.user.display_avatar.url
            )

        e.set_footer(
            text="✈️ Air Commander • Systems Operational"
        )

        await ctx.send(
            embed=e
        )

    # =====================================================
    # PREFIX COMMAND ERROR HANDLER
    # =====================================================

    @bot.event
    async def on_command_error(
        ctx,
        error
    ):

        if isinstance(
            error,
            commands.CommandNotFound
        ):
            return

        if isinstance(
            error,
            commands.MissingPermissions
        ):
            return await ctx.send(
                "❌ You don't have the required permission."
            )

        if isinstance(
            error,
            commands.BotMissingPermissions
        ):
            return await ctx.send(
                "❌ I don't have the required Discord permission."
            )

        if isinstance(
            error,
            commands.MissingRequiredArgument
        ):
            return await ctx.send(
                f"❌ Missing argument: `{error.param.name}`."
            )

        if isinstance(
            error,
            commands.BadArgument
        ):
            return await ctx.send(
                "❌ Invalid argument. Please check the command format."
            )

        print(
            f"Prefix command error: "
            f"{type(error).__name__}: {error}"
        )

    # =====================================================
    # PREFIX ,HELP
    # =====================================================

    @bot.command(
        name="help"
    )
    async def prefix_help(
        ctx,
        command_name: str | None = None
    ):

        # Detailed command help
        if command_name:

            command = bot.get_command(
                command_name.lower()
            )

            if not command:

                return await ctx.send(
                    embed=embed(
                        "Command Not Found",
                        (
                            f"❌ Command "
                            f"`,{command_name}` not found."
                        ),
                        discord.Color.red()
                    )
                )

            description = (
                getattr(
                    command,
                    "help",
                    None
                )
                or
                getattr(
                    command,
                    "brief",
                    None
                )
                or
                "No description available."
            )

            e = embed(
                f"Help • ,{command.name}",
                description,
                discord.Color.blurple()
            )

            usage = (
                f"`,{command.qualified_name}"
                f" {command.signature}`"
            ).strip()

            e.add_field(
                name="Usage",
                value=usage,
                inline=False
            )

            if command.aliases:

                e.add_field(
                    name="Aliases",
                    value=" ".join(
                        f"`,{alias}`"
                        for alias in command.aliases
                    ),
                    inline=False
                )

            return await ctx.send(
                embed=e
            )

        await ctx.send(
            embed=_help_embed(bot, "prefix")[0],
            view=HelpView(
                bot,
                "prefix"
            )
        )

    # =====================================================
    # SLASH /HELP
    # =====================================================

    # Remove an older help command if another basic
    # help registration was left behind.
    existing_help = bot.tree.get_command(
        "help"
    )

    if existing_help is not None:
        bot.tree.remove_command(
            "help"
        )

    @bot.tree.command(
        name="help",
        description="Open the Air Commander Help Center"
    )
    async def slash_help(
        i: discord.Interaction
    ):

        await i.response.send_message(
            embed=_help_embed(bot, "slash")[0],
            view=HelpView(
                bot,
                "slash"
            ),
            ephemeral=False
        )

    # =====================================================
    # SLASH COMMAND ERROR HANDLER
    # =====================================================

    @bot.tree.error
    async def on_app_command_error(
        i: discord.Interaction,
        error: app_commands.AppCommandError
    ):

        if isinstance(
            error,
            app_commands.MissingPermissions
        ):

            msg = (
                "❌ You don't have the required "
                "permission for this command."
            )

        elif isinstance(
            error,
            app_commands.BotMissingPermissions
        ):

            msg = (
                "❌ I don't have the required Discord "
                "permission to do that."
            )

        elif isinstance(
            error,
            app_commands.CommandOnCooldown
        ):

            msg = (
                "⏳ Please wait before using "
                "that command again."
            )

        elif isinstance(
            error,
            app_commands.CheckFailure
        ):

            msg = (
                "❌ You cannot use this command "
                "here or right now."
            )

        else:

            print(
                f"Basic slash command error: "
                f"{type(error).__name__}: {error}"
            )

            msg = (
                "❌ Something went wrong while "
                "running that command."
            )

        try:

            if i.response.is_done():

                await i.followup.send(
                    msg,
                    ephemeral=True
                )

            else:

                await i.response.send_message(
                    msg,
                    ephemeral=True
                )

        except discord.HTTPException as exc:

            print(
                f"⚠️ Could not send slash error response: {exc}"
            )


# =========================================================
# END OF BASIC COMMANDS
# =========================================================
