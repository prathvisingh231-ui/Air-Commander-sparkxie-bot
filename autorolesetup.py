import re
import discord
from discord import app_commands
from discord.ext import commands

HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def _embed(title, description, color):
    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color,
        timestamp=discord.utils.utcnow(),
    )
    e.set_footer(text="Air Commander • Auto Role Setup")
    return e


def _parse_layout(layout: str):
    roles = []
    seen = set()
    for raw in layout.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if " - " not in line:
            raise ValueError(f"Invalid line: **{line}**\nUse `Role Name - #RRGGBB`.")
        name, hexcode = line.rsplit(" - ", 1)
        name = name.strip()
        hexcode = hexcode.strip()
        match = HEX_RE.fullmatch(hexcode)
        if not name:
            raise ValueError("A role name cannot be empty.")
        if not match:
            raise ValueError(f"Invalid hex code for **{name}**. Use a 6-digit code such as `#5865F2`.")
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        roles.append((name[:100], int(match.group(1), 16)))
    if not roles:
        raise ValueError("No roles found. Add lines like `Admin - #5865F2`.")
    return roles


async def _apply_roles(guild: discord.Guild, layout: str):
    specs = _parse_layout(layout)
    me = guild.me
    if me is None:
        raise RuntimeError("I could not determine my member record in this server.")
    if not me.guild_permissions.manage_roles:
        raise PermissionError("I need **Manage Roles** to create roles.")
    bot_top = me.top_role
    created = 0
    existing = 0
    skipped = []

    for name, colour_value in specs:
        role = discord.utils.find(lambda r: r.name.casefold() == name.casefold(), guild.roles)
        if role:
            existing += 1
            if role >= bot_top and role != guild.default_role:
                skipped.append(f"{role.name} (higher than my role)")
            continue
        if bot_top <= guild.default_role:
            raise PermissionError("My bot role must be above @everyone and have **Manage Roles**.")
        role = await guild.create_role(
            name=name,
            colour=discord.Colour(colour_value),
            reason="Air Commander auto role setup",
        )
        created += 1

    return created, existing, skipped


def setup(bot: commands.Bot):
    @bot.tree.command(name="autorolesetup", description="Create roles from Role Name - #RRGGBB lines")
    @app_commands.describe(layout="Example: Admin - #5865F2\nOwner - #FF0000")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def autorolesetup(interaction: discord.Interaction, layout: str):
        if not interaction.guild:
            return await interaction.response.send_message(
                embed=_embed("Server Only", "This command can only be used inside a server.", discord.Color.red()),
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        try:
            created, existing, skipped = await _apply_roles(interaction.guild, layout)
        except ValueError as exc:
            return await interaction.followup.send(embed=_embed("Invalid Layout", str(exc), discord.Color.red()), ephemeral=True)
        except PermissionError as exc:
            return await interaction.followup.send(embed=_embed("Missing Permission", str(exc), discord.Color.red()), ephemeral=True)
        except discord.Forbidden:
            return await interaction.followup.send(
                embed=_embed("Discord Permission Error", "Discord denied role creation. Give Air Commander **Manage Roles** and move its bot role above the roles it needs to manage.", discord.Color.red()),
                ephemeral=True,
            )
        except Exception as exc:
            print(f"[AutoRoleSetup] Error in {interaction.guild.id}: {type(exc).__name__}: {exc}")
            return await interaction.followup.send(embed=_embed("Setup Failed", "The roles could not be created. Check the bot permissions and Render logs.", discord.Color.red()), ephemeral=True)

        text = f"🎨 Roles created: **{created}**\n↪️ Roles already present: **{existing}**"
        if skipped:
            text += "\n\n⚠️ Not manageable because they are at/above my role:\n" + "\n".join(f"• {x}" for x in skipped)
        await interaction.followup.send(embed=_embed("Auto Role Setup Complete", text, discord.Color.green()), ephemeral=True)

    @bot.command(name="autorolesetup")
    @commands.has_guild_permissions(manage_roles=True)
    async def prefix_autorolesetup(ctx: commands.Context, *, layout: str):
        if not ctx.guild:
            return await ctx.send(embed=_embed("Server Only", "This command can only be used inside a server.", discord.Color.red()))
        try:
            created, existing, skipped = await _apply_roles(ctx.guild, layout)
        except ValueError as exc:
            return await ctx.send(embed=_embed("Invalid Layout", str(exc), discord.Color.red()))
        except PermissionError as exc:
            return await ctx.send(embed=_embed("Missing Permission", str(exc), discord.Color.red()))
        except discord.Forbidden:
            return await ctx.send(embed=_embed("Discord Permission Error", "Give Air Commander **Manage Roles** and move its bot role above the roles it needs to manage.", discord.Color.red()))
        except Exception as exc:
            print(f"[AutoRoleSetup] Prefix error in {ctx.guild.id}: {type(exc).__name__}: {exc}")
            return await ctx.send(embed=_embed("Setup Failed", "The roles could not be created.", discord.Color.red()))
        text = f"🎨 Roles created: **{created}**\n↪️ Roles already present: **{existing}**"
        if skipped:
            text += "\n\n⚠️ Not manageable because they are at/above my role:\n" + "\n".join(f"• {x}" for x in skipped)
        await ctx.send(embed=_embed("Auto Role Setup Complete", text, discord.Color.green()))
