import re
import discord
from discord import app_commands
from discord.ext import commands

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


# ============================================================
# ✈️ AIR COMMANDER — EMBED
# ============================================================

def _embed(title, description, color=None):
    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    e.set_footer(text="Air Commander • Setup Center")
    return e


# ============================================================
# 🎨 AUTO ROLE SETUP
# ============================================================

def _parse_layout(layout: str):
    roles = []
    seen = set()

    for raw in layout.splitlines():
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        if " - " not in line:
            raise ValueError(
                f"Invalid line: **{line}**\n"
                "Use `Role Name - #RRGGBB`."
            )

        name, hexcode = line.rsplit(" - ", 1)
        name = name.strip()
        hexcode = hexcode.strip()

        match = HEX_RE.fullmatch(hexcode)

        if not name:
            raise ValueError("A role name cannot be empty.")

        if not match:
            raise ValueError(
                f"Invalid hex code for **{name}**. "
                "Use a 6-digit code such as `#5865F2`."
            )

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)
        roles.append((name[:100], int(match.group(1), 16)))

    if not roles:
        raise ValueError(
            "No roles found. Add lines like `Admin - #5865F2`."
        )

    return roles


async def _apply_roles(guild: discord.Guild, layout: str):
    specs = _parse_layout(layout)

    me = guild.me

    if me is None:
        raise RuntimeError(
            "I could not determine my member record in this server."
        )

    if not me.guild_permissions.manage_roles:
        raise PermissionError(
            "I need **Manage Roles** to create roles."
        )

    bot_top = me.top_role
    created = 0
    existing = 0
    skipped = []

    for name, colour_value in specs:
        role = discord.utils.find(
            lambda r: r.name.casefold() == name.casefold(),
            guild.roles,
        )

        if role:
            existing += 1

            if role >= bot_top and role != guild.default_role:
                skipped.append(
                    f"{role.name} (higher than my role)"
                )

            continue

        if bot_top <= guild.default_role:
            raise PermissionError(
                "My bot role must be above @everyone "
                "and have **Manage Roles**."
            )

        await guild.create_role(
            name=name,
            colour=discord.Colour(colour_value),
            reason="Air Commander auto role setup",
        )

        created += 1

    return created, existing, skipped


# ============================================================
# 📂 AUTO CHANNEL SETUP — LAYOUT PARSER
# ============================================================

def _clean_channel_name(name: str):
    name = name.strip().strip("`").lower()
    name = re.sub(r"\s+", "-", name)
    name = re.sub(r"[^a-z0-9\-_]", "", name)
    name = re.sub(r"-{2,}", "-", name)

    return name.strip("-_")[:100]


def _parse_channel_layout(layout: str):
    """
    Format:

    INFORMATION
    - announcements
    - rules

    COMMUNITY
    - general
    - media

    Non-indented headings create categories.
    Indented lines or lines starting with - or >
    create text channels inside the current category.
    """

    categories = []
    current = None
    seen_categories = set()

    for raw in layout.splitlines():
        if not raw.strip():
            continue

        stripped = raw.strip()

        if stripped.startswith("#"):
            continue

        is_indented = raw[:1].isspace()
        is_bullet = stripped.startswith(("-", ">"))

        if is_bullet:
            channel_name = _clean_channel_name(stripped[1:])

            if current is None:
                raise ValueError(
                    f"Channel **{channel_name}** has no category above it."
                )

            if not channel_name:
                raise ValueError("A channel name cannot be empty.")

            if channel_name not in current["channels"]:
                current["channels"].append(channel_name)

            continue

        if is_indented:
            channel_name = _clean_channel_name(stripped)

            if current is None:
                raise ValueError(
                    f"Channel **{channel_name}** has no category above it."
                )

            if not channel_name:
                raise ValueError("A channel name cannot be empty.")

            if channel_name not in current["channels"]:
                current["channels"].append(channel_name)

            continue

        # Non-indented line = category heading.
        category_name = stripped[:100]
        key = category_name.casefold()

        if key in seen_categories:
            raise ValueError(
                f"Duplicate category heading: **{category_name}**"
            )

        seen_categories.add(key)

        current = {
            "name": category_name,
            "channels": [],
        }

        categories.append(current)

    if not categories:
        raise ValueError(
            "No categories found. Add a heading like INFORMATION."
        )

    if not any(item["channels"] for item in categories):
        raise ValueError(
            "No channels found. Add channel names beneath categories."
        )

    return categories


# ============================================================
# 📂 AUTO CHANNEL SETUP — CREATE CATEGORIES AND CHANNELS
# ============================================================

async def _apply_channels(guild: discord.Guild, layout: str):
    if guild is None:
        raise ValueError(
            "This command can only be used inside a server."
        )

    me = guild.me

    if me is None:
        raise RuntimeError(
            "Could not determine the bot's server member."
        )

    if not me.guild_permissions.manage_channels:
        raise PermissionError(
            "Air Commander needs **Manage Channels** permission."
        )

    categories = _parse_channel_layout(layout)

    created_categories = 0
    existing_categories = 0
    created_channels = 0
    existing_channels = 0
    errors = []

    for item in categories:
        category_name = item["name"]

        category = discord.utils.find(
            lambda c: c.name.casefold() == category_name.casefold(),
            guild.categories,
        )

        if category is None:
            try:
                category = await guild.create_category(
                    name=category_name,
                    reason="Air Commander auto channel setup",
                )
                created_categories += 1

            except discord.Forbidden:
                raise PermissionError(
                    "Discord denied category creation. "
                    "Check Manage Channels permission."
                )

            except discord.HTTPException as exc:
                errors.append(
                    f"Category **{category_name}**: {exc}"
                )
                continue

        else:
            existing_categories += 1

        for channel_name in item["channels"]:
            existing = discord.utils.find(
                lambda c: (
                    isinstance(c, discord.TextChannel)
                    and c.name.casefold() == channel_name.casefold()
                    and c.category_id == category.id
                ),
                guild.channels,
            )

            if existing is not None:
                existing_channels += 1
                continue

            try:
                await guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    reason="Air Commander auto channel setup",
                )
                created_channels += 1

            except discord.Forbidden:
                errors.append(
                    f"#{channel_name}: Missing permission."
                )

            except discord.HTTPException as exc:
                errors.append(
                    f"#{channel_name}: {exc}"
                )

    return (
        created_categories,
        existing_categories,
        created_channels,
        existing_channels,
        errors,
    )


# ============================================================
# 📊 SETUP RESULT EMBED
# ============================================================

def _channel_result_embed(result):
    (
        new_categories,
        old_categories,
        new_channels,
        old_channels,
        errors,
    ) = result

    description = (
        f"📂 Categories created: **{new_categories}**\n"
        f"↪️ Existing categories: **{old_categories}**\n\n"
        f"📝 Channels created: **{new_channels}**\n"
        f"↪️ Existing channels: **{old_channels}**"
    )

    if errors:
        description += "\n\n⚠️ **Items not completed:**\n"
        description += "\n".join(
            f"• {error}" for error in errors[:10]
        )

        if len(errors) > 10:
            description += (
                f"\n• And {len(errors) - 10} more errors."
            )

    color = (
        discord.Color.orange()
        if errors
        else discord.Color.green()
    )

    return _embed(
        "Auto Channel Setup Complete",
        description,
        color,
    )


# ============================================================
# 🔧 REGISTER COMMANDS
# ============================================================

def setup(bot: commands.Bot):

    # --------------------------------------------------------
    # /autorolesetup
    # --------------------------------------------------------

    @bot.tree.command(
        name="autorolesetup",
        description="Create roles from Role Name - #RRGGBB lines",
    )
    @app_commands.describe(
        layout="Example: Admin - #5865F2\nOwner - #FF0000"
    )
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorolesetup(
        interaction: discord.Interaction,
        layout: str,
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                embed=_embed(
                    "Server Only",
                    "This command can only be used inside a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        try:
            created, existing, skipped = await _apply_roles(
                interaction.guild,
                layout,
            )

        except ValueError as exc:
            return await interaction.followup.send(
                embed=_embed(
                    "Invalid Layout",
                    str(exc),
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        except PermissionError as exc:
            return await interaction.followup.send(
                embed=_embed(
                    "Missing Permission",
                    str(exc),
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        except discord.Forbidden:
            return await interaction.followup.send(
                embed=_embed(
                    "Discord Permission Error",
                    "Give Air Commander **Manage Roles** and move "
                    "its bot role above the roles it needs to manage.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        except Exception as exc:
            print(
                f"[AutoRoleSetup] Error in "
                f"{interaction.guild.id}: "
                f"{type(exc).__name__}: {exc}"
            )

            return await interaction.followup.send(
                embed=_embed(
                    "Setup Failed",
                    "The roles could not be created. "
                    "Check bot permissions and Render logs.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        text = (
            f"🎨 Roles created: **{created}**\n"
            f"↪️ Roles already present: **{existing}**"
        )

        if skipped:
            text += (
                "\n\n⚠️ Not manageable because they are "
                "at/above my role:\n"
                + "\n".join(f"• {x}" for x in skipped)
            )

        await interaction.followup.send(
            embed=_embed(
                "Auto Role Setup Complete",
                text,
                discord.Color.green(),
            ),
            ephemeral=True,
        )

    # --------------------------------------------------------
    # ,autorolesetup
    # --------------------------------------------------------

    @bot.command(name="autorolesetup")
    @commands.has_guild_permissions(manage_roles=True)
    async def prefix_autorolesetup(
        ctx: commands.Context,
        *,
        layout: str,
    ):
        if ctx.guild is None:
            return await ctx.send(
                embed=_embed(
                    "Server Only",
                    "This command can only be used inside a server.",
                    discord.Color.red(),
                )
            )

        try:
            created, existing, skipped = await _apply_roles(
                ctx.guild,
                layout,
            )

        except ValueError as exc:
            return await ctx.send(
                embed=_embed(
                    "Invalid Layout",
                    str(exc),
                    discord.Color.red(),
                )
            )

        except PermissionError as exc:
            return await ctx.send(
                embed=_embed(
                    "Missing Permission",
                    str(exc),
                    discord.Color.red(),
                )
            )

        except discord.Forbidden:
            return await ctx.send(
                embed=_embed(
                    "Discord Permission Error",
                    "Give Air Commander **Manage Roles** and move "
                    "its bot role above the roles it needs to manage.",
                    discord.Color.red(),
                )
            )

        except Exception as exc:
            print(
                f"[AutoRoleSetup] Prefix error in "
                f"{ctx.guild.id}: "
                f"{type(exc).__name__}: {exc}"
            )

            return await ctx.send(
                embed=_embed(
                    "Setup Failed",
                    "The roles could not be created.",
                    discord.Color.red(),
                )
            )

        text = (
            f"🎨 Roles created: **{created}**\n"
            f"↪️ Roles already present: **{existing}**"
        )

        if skipped:
            text += (
                "\n\n⚠️ Not manageable because they are "
                "at/above my role:\n"
                + "\n".join(f"• {x}" for x in skipped)
            )

        await ctx.send(
            embed=_embed(
                "Auto Role Setup Complete",
                text,
                discord.Color.green(),
            )
        )

    # --------------------------------------------------------
    # /autochannel setup
    # --------------------------------------------------------

    autochannel_group = app_commands.Group(
        name="autochannel",
        description="Automatically create categories and channels",
    )

    @autochannel_group.command(
        name="setup",
        description="Create categories and text channels from a layout",
    )
    @app_commands.describe(
        layout=(
            "Category headings on separate lines; prefix channels "
            "with - or indent them"
        )
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slash_autochannel_setup(
        interaction: discord.Interaction,
        layout: str,
    ):
        if interaction.guild is None:
            return await interaction.response.send_message(
                embed=_embed(
                    "Server Only",
                    "This command can only be used inside a server.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        try:
            result = await _apply_channels(
                interaction.guild,
                layout,
            )

        except ValueError as exc:
            return await interaction.followup.send(
                embed=_embed(
                    "Invalid Layout",
                    str(exc),
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        except PermissionError as exc:
            return await interaction.followup.send(
                embed=_embed(
                    "Missing Permission",
                    str(exc),
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        except Exception as exc:
            print(
                f"[AutoChannelSetup] Error in "
                f"{interaction.guild.id}: "
                f"{type(exc).__name__}: {exc}"
            )

            return await interaction.followup.send(
                embed=_embed(
                    "Setup Failed",
                    "Could not complete channel setup. "
                    "Check permissions and Render logs.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        await interaction.followup.send(
            embed=_channel_result_embed(result),
            ephemeral=True,
        )

    # Avoid replacing an existing slash group.
    if bot.tree.get_command("autochannel") is None:
        bot.tree.add_command(autochannel_group)
    else:
        print(
            "[AutoChannelSetup] Slash group 'autochannel' "
            "already exists; skipping duplicate registration."
        )

    # --------------------------------------------------------
    # ,autochannel setup
    # --------------------------------------------------------

    @commands.group(
        name="autochannel",
        invoke_without_command=True,
    )
    @commands.has_guild_permissions(manage_channels=True)
    async def prefix_autochannel(ctx: commands.Context):
        await ctx.send(
            embed=_embed(
                "Auto Channel Setup",
                "Use `,autochannel setup` followed by your layout.",
            )
        )

    @prefix_autochannel.command(
        name="setup",
        aliases=["create"],
    )
    @commands.has_guild_permissions(manage_channels=True)
    async def prefix_autochannel_setup(
        ctx: commands.Context,
        *,
        layout: str,
    ):
        if ctx.guild is None:
            return await ctx.send(
                embed=_embed(
                    "Server Only",
                    "This command can only be used inside a server.",
                    discord.Color.red(),
                )
            )

        try:
            result = await _apply_channels(
                ctx.guild,
                layout,
            )

        except ValueError as exc:
            return await ctx.send(
                embed=_embed(
                    "Invalid Layout",
                    str(exc),
                    discord.Color.red(),
                )
            )

        except PermissionError as exc:
            return await ctx.send(
                embed=_embed(
                    "Missing Permission",
                    str(exc),
                    discord.Color.red(),
                )
            )

        except Exception as exc:
            print(
                f"[AutoChannelSetup] Prefix error in "
                f"{ctx.guild.id}: "
                f"{type(exc).__name__}: {exc}"
            )

            return await ctx.send(
                embed=_embed(
                    "Setup Failed",
                    "Could not complete channel setup. "
                    "Check permissions and Render logs.",
                    discord.Color.red(),
                )
            )

        ```python
# ============================================================
# ✈️ AIR COMMANDER — CLEAR CHANNELS ADD-ON
# Paste at the bottom of autochannel.py
# Existing imports required:
# import discord
# from discord import app_commands
# from discord.ext import commands
# ============================================================

class _ClearChannelsConfirm(discord.ui.View):
    def __init__(self, guild_id, owner_id):
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the command invoker can use these buttons.",
                ephemeral=True,
            )
            return False

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Administrator permission is required.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="Continue",
        style=discord.ButtonStyle.danger,
        emoji="⚠️",
    )
    async def continue_button(self, interaction, button):
        view = _ClearChannelsFinal(
            self.guild_id,
            self.owner_id,
        )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⚠️ FINAL CONFIRMATION",
                description=(
                    "This will delete **all server channels "
                    "and categories**.\n\n"
                    "This action cannot be automatically undone."
                ),
                color=discord.Color.red(),
            ),
            view=view,
        )
        self.stop()

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="✖️",
    )
    async def cancel_button(self, interaction, button):
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="Cancelled. Nothing was deleted.",
            embed=None,
            view=self,
        )
        self.stop()


class _ClearChannelsFinal(discord.ui.View):
    def __init__(self, guild_id, owner_id):
        super().__init__(timeout=30)
        self.guild_id = guild_id
        self.owner_id = owner_id

    async def interaction_check(self, interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "Only the command invoker can use these buttons.",
                ephemeral=True,
            )
            return False

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Administrator permission is required.",
                ephemeral=True,
            )
            return False

        return True

    @discord.ui.button(
        label="DELETE EVERYTHING",
        style=discord.ButtonStyle.danger,
        emoji="🗑️",
    )
    async def delete_button(self, interaction, button):
        guild = interaction.guild

        if guild is None or guild.id != self.guild_id:
            return await interaction.response.send_message(
                "Invalid server.",
                ephemeral=True,
            )

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "Air Commander needs Manage Channels permission.",
                ephemeral=True,
            )

        await interaction.response.defer(ephemeral=True)

        for child in self.children:
            child.disabled = True

        try:
            await interaction.message.edit(view=self)
        except discord.HTTPException:
            pass

        # Delete regular channels first, categories last.
        channels = list(guild.channels)
        channels.sort(
            key=lambda channel: isinstance(
                channel, discord.CategoryChannel
            )
        )

        deleted = 0
        failed = []

        for channel in channels:
            try:
                await channel.delete(
                    reason=(
                        f"Clear channels confirmed by "
                        f"{interaction.user} ({interaction.user.id})"
                    )
                )
                deleted += 1

            except discord.NotFound:
                continue

            except (discord.Forbidden, discord.HTTPException) as exc:
                failed.append(f"{channel.name}: {type(exc).__name__}")

        result = discord.Embed(
            title="✈️ Channel Cleanup Finished",
            description=(
                f"Deleted: **{deleted}**\n"
                f"Failed: **{len(failed)}**\n\n"
                "The server and its roles were not deleted."
            ),
            color=(
                discord.Color.orange()
                if failed
                else discord.Color.green()
            ),
        )

        if failed:
            result.add_field(
                name="Failed items",
                value="\n".join(failed[:10]),
                inline=False,
            )

        await interaction.followup.send(
            embed=result,
            ephemeral=True,
        )

    @discord.ui.button(
        label="Cancel",
        style=discord.ButtonStyle.secondary,
        emoji="✖️",
    )
    async def cancel_button(self, interaction, button):
        for child in self.children:
            child.disabled = True

        await interaction.response.edit_message(
            content="Cancelled. Nothing was deleted.",
            embed=None,
            view=self,
        )
        self.stop()


# Call this from your EXISTING setup(bot) function.
def register_clearchannels(bot: commands.Bot):

    @bot.tree.command(
        name="clearchannels",
        description="Clear all server channels and categories",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def slash_clearchannels(interaction: discord.Interaction):
        guild = interaction.guild

        if guild is None:
            return await interaction.response.send_message(
                "Use this command inside a server.",
                ephemeral=True,
            )

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "Air Commander needs Manage Channels permission.",
                ephemeral=True,
            )

        channels = list(guild.channels)
        categories = sum(
            isinstance(c, discord.CategoryChannel)
            for c in channels
        )

        view = _ClearChannelsConfirm(
            guild.id,
            interaction.user.id,
        )

        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Clear All Channels?",
                description=(
                    f"Server: **{guild.name}**\n"
                    f"Channels and categories: **{len(channels)}**\n"
                    f"Categories: **{categories}**\n\n"
                    "You will need to confirm twice. "
                    "Deletion cannot be automatically undone."
                ),
                color=discord.Color.red(),
            ),
            view=view,
            ephemeral=True,
        )

    @bot.command(name="clearchannels")
    @commands.has_guild_permissions(administrator=True)
    async def prefix_clearchannels(ctx):
        guild = ctx.guild

        if guild is None:
            return await ctx.send(
                "Use this command inside a server."
            )

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return await ctx.send(
                "Air Commander needs Manage Channels permission."
            )

        channels = list(guild.channels)
        categories = sum(
            isinstance(c, discord.CategoryChannel)
            for c in channels
        )

        view = _ClearChannelsConfirm(
            guild.id,
            ctx.author.id,
        )

        await ctx.send(
            embed=discord.Embed(
                title="⚠️ Clear All Channels?",
                description=(
                    f"Server: **{guild.name}**\n"
                    f"Channels and categories: **{len(channels)}**\n"
                    f"Categories: **{categories}**\n\n"
                    "You will need to confirm twice. "
                    "Deletion cannot be automatically undone."
                ),
                color=discord.Color.red(),
            ),
            view=view,
        )
```

        await ctx.send(embed=_channel_result_embed(result))
