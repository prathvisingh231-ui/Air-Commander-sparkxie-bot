import re
import discord
from discord import app_commands
from discord.ext import commands


def _embed(title, description, color):
    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    e.set_footer(text="Air Commander • Auto Channel Setup")
    return e


def _parse_layout(layout: str):
    """Parse a simple layout:

    Category Name - category
    text-channel
    voice-channel -vc

    A category header becomes the active category. Normal lines create text
    channels inside that category; lines ending in -vc create voice channels.
    """
    categories = []
    current = None

    for raw in layout.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        match = re.match(r"^(.+?)\s*-\s*category\s*$", line, re.I)
        if match:
            name = match.group(1).strip()
            if name:
                current = {"name": name[:100], "channels": []}
                categories.append(current)
            continue

        voice = bool(re.search(r"\s*-\s*vc\s*$", line, re.I))
        if voice:
            name = re.sub(r"\s*-\s*vc\s*$", "", line, flags=re.I).strip()
        else:
            name = line
        if not name:
            continue

        # A channel before the first category is invalid instead of silently
        # creating it outside the requested layout.
        if current is None:
            raise ValueError(
                f"Channel **{name}** appears before a category. Add a `- category` line first."
            )

        current["channels"].append({"name": name[:100], "voice": voice})

    if not categories:
        raise ValueError("No categories found. Use lines ending with `- category`.")
    return categories


def _find_category(guild: discord.Guild, name: str):
    wanted = name.casefold()
    return discord.utils.find(
        lambda c: c.name.casefold() == wanted,
        guild.categories,
    )


def _find_channel(category: discord.CategoryChannel, name: str, voice: bool):
    wanted = name.casefold()
    for channel in category.channels:
        if channel.name.casefold() == wanted:
            if voice and isinstance(channel, discord.VoiceChannel):
                return channel
            if not voice and isinstance(channel, discord.TextChannel):
                return channel
    return None


async def _apply_layout(guild: discord.Guild, layout: str):
    parsed = _parse_layout(layout)
    created_categories = 0
    existing_categories = 0
    created_channels = 0
    existing_channels = 0

    for spec in parsed:
        category = _find_category(guild, spec["name"])
        if category is None:
            category = await guild.create_category(
                spec["name"],
                reason="Air Commander auto channel setup",
            )
            created_categories += 1
        else:
            existing_categories += 1

        for channel_spec in spec["channels"]:
            name = channel_spec["name"]
            voice = channel_spec["voice"]
            if _find_channel(category, name, voice):
                existing_channels += 1
                continue

            if voice:
                await guild.create_voice_channel(
                    name,
                    category=category,
                    reason="Air Commander auto channel setup",
                )
            else:
                await guild.create_text_channel(
                    name,
                    category=category,
                    reason="Air Commander auto channel setup",
                )
            created_channels += 1

    return created_categories, existing_categories, created_channels, existing_channels


def setup(bot: commands.Bot):
    @bot.tree.command(
        name="autosetup",
        description="Create categories and channels from a simple layout",
    )
    @app_commands.describe(
        layout="Layout using `Name - category`, channel names, and `Name -vc` for voice",
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    async def autosetup(interaction: discord.Interaction, layout: str):
        if interaction.guild is None:
            return await interaction.response.send_message(
                embed=_embed("Server Only", "This command can only be used inside a server.", discord.Color.red()),
                ephemeral=True,
            )

        if not interaction.guild.me.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                embed=_embed(
                    "Missing Permission",
                    "I need **Manage Channels** to create the requested layout.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        if len(layout) > 4000:
            return await interaction.response.send_message(
                embed=_embed("Layout Too Long", "Keep the layout under **4000 characters**.", discord.Color.red()),
                ephemeral=True,
            )

        try:
            await interaction.response.defer(ephemeral=True)
            result = await _apply_layout(interaction.guild, layout)
        except ValueError as exc:
            if interaction.response.is_done():
                return await interaction.followup.send(
                    embed=_embed("Invalid Layout", str(exc), discord.Color.red()),
                    ephemeral=True,
                )
            return await interaction.response.send_message(
                embed=_embed("Invalid Layout", str(exc), discord.Color.red()),
                ephemeral=True,
            )
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=_embed(
                    "Permission Error",
                    "Discord denied channel creation. Make sure my role has **Manage Channels** and is high enough to manage the server configuration.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )
        except Exception as exc:
            print(f"[AutoSetup] Error in {interaction.guild.id}: {type(exc).__name__}: {exc}")
            return await interaction.followup.send(
                embed=_embed(
                    "Auto Setup Failed",
                    "The layout could not be completed. Check the bot permissions and Render logs.",
                    discord.Color.red(),
                ),
                ephemeral=True,
            )

        cc, ec, ch, eh = result
        description = (
            "The requested server layout has been processed.\n\n"
            f"📁 Categories created: **{cc}**\n"
            f"📁 Categories already present: **{ec}**\n"
            f"💬 Channels created: **{ch}**\n"
            f"↪️ Channels already present: **{eh}**"
        )
        await interaction.followup.send(
            embed=_embed("Auto Setup Complete", description, discord.Color.green()),
            ephemeral=True,
        )

    @bot.command(name="autosetup")
    @commands.has_guild_permissions(manage_channels=True)
    async def prefix_autosetup(ctx: commands.Context, *, layout: str):
        if ctx.guild is None:
            return await ctx.send(
                embed=_embed("Server Only", "This command can only be used inside a server.", discord.Color.red())
            )
        if not ctx.guild.me.guild_permissions.manage_channels:
            return await ctx.send(
                embed=_embed("Missing Permission", "I need **Manage Channels** to create channels.", discord.Color.red())
            )
        try:
            result = await _apply_layout(ctx.guild, layout)
        except ValueError as exc:
            return await ctx.send(embed=_embed("Invalid Layout", str(exc), discord.Color.red()))
        except discord.Forbidden:
            return await ctx.send(
                embed=_embed(
                    "Permission Error",
                    "Discord denied channel creation. Give Air Commander **Manage Channels**.",
                    discord.Color.red(),
                )
            )
        except Exception as exc:
            print(f"[AutoSetup] Prefix error in {ctx.guild.id}: {type(exc).__name__}: {exc}")
            return await ctx.send(
                embed=_embed("Auto Setup Failed", "The layout could not be completed.", discord.Color.red())
            )

        cc, ec, ch, eh = result
        await ctx.send(
            embed=_embed(
                "Auto Setup Complete",
                f"📁 Categories created: **{cc}**\n"
                f"📁 Categories already present: **{ec}**\n"
                f"💬 Channels created: **{ch}**\n"
                f"↪️ Channels already present: **{eh}**",
                discord.Color.green(),
            )
        )
