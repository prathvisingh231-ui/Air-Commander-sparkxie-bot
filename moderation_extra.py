import discord
from discord import app_commands
from discord.ext import commands
import db
import cmdmaker


def clean_embed(title, description="", color=None):
    e = discord.Embed(
        title=f"✈️ {title}",
        description=description,
        color=color or discord.Color.blurple(),
        timestamp=discord.utils.utcnow(),
    )
    e.set_footer(text="Air Commander • Moderation Control")
    return e


def setup(bot: commands.Bot):
    # Persistent per-server prefix control.
    if not hasattr(bot, "_air_prefixes"):
        bot._air_prefixes = {}

    async def load_prefixes():
        try:
            bot._air_prefixes.update(await db.all_prefixes())
        except Exception as exc:
            print(f"Prefix load error: {exc}")

    async def dynamic_prefix(_bot, message):
        if message.guild:
            return bot._air_prefixes.get(message.guild.id, "!")
        return "!"

    # discord.py accepts a callable prefix. This makes /prefix set actually
    # change the prefix used by normal text commands without restarting.
    bot.command_prefix = dynamic_prefix
    bot._air_load_prefixes = load_prefixes

    @bot.tree.command(name="warn", description="Warn a member and save a persistent moderation record")
    @app_commands.describe(member="Member to warn", reason="Reason for the warning", evidence="Optional evidence or reference")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided", evidence: str = "Not provided"):
        if not i.guild:
            return await i.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        if member == i.user or member.bot:
            return await i.response.send_message("❌ That member cannot be warned.", ephemeral=True)
        if member.top_role >= i.user.top_role:
            return await i.response.send_message("❌ You cannot warn a member with an equal or higher role.", ephemeral=True)
        if i.guild.me and member.top_role >= i.guild.me.top_role:
            return await i.response.send_message("❌ I cannot manage that member because of role hierarchy.", ephemeral=True)

        case_code, warning_count = await db.create_warning(
            i.guild.id, member.id, i.user.id, reason[:1024], evidence[:1024]
        )

        e = clean_embed("Warning Issued", f"{member.mention} has received a moderation warning.", discord.Color.orange())
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Member", value=f"{member.mention}\n`{member.id}`", inline=True)
        e.add_field(name="Total Warnings", value=f"**{warning_count}**", inline=True)
        e.add_field(name="Case", value=f"`{case_code}`", inline=True)
        e.add_field(name="Moderator", value=i.user.mention, inline=True)
        e.add_field(name="Reason", value=reason[:1024], inline=False)
        if evidence != "Not provided":
            e.add_field(name="Evidence", value=evidence[:1024], inline=False)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="warnings", description="View a member's warning history")
    @app_commands.describe(member="Member to inspect")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warnings(i: discord.Interaction, member: discord.Member):
        if not i.guild:
            return await i.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        rows = await db.get_warnings(i.guild.id, member.id)
        e = clean_embed("Warning History", f"Moderation history for {member.mention}.", discord.Color.orange())
        e.set_thumbnail(url=member.display_avatar.url)
        e.add_field(name="Total", value=f"**{len(rows)}** warning(s)", inline=True)
        if not rows:
            e.add_field(name="History", value="No warnings recorded.", inline=False)
        else:
            lines = []
            for row in rows[:10]:
                created = discord.utils.format_dt(row["created_at"], "R")
                lines.append(f"`{row['case_code']}` • {created}\n**Reason:** {row['reason'][:300]}\n**Moderator:** <@{row['moderator_id']}>")
            e.add_field(name="Recent Warnings", value="\n\n".join(lines)[:1024], inline=False)
        await i.response.send_message(embed=e, ephemeral=True)

    prefix_group = app_commands.Group(name="prefix", description="Configure the server's text command prefix")

    @prefix_group.command(name="set", description="Set the server prefix")
    @app_commands.describe(prefix="New prefix, 1-5 characters")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def prefix_set(i: discord.Interaction, prefix: str):
        if not i.guild:
            return await i.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        prefix = prefix.strip()
        if not 1 <= len(prefix) <= 5:
            return await i.response.send_message("❌ Prefix must be between 1 and 5 characters.", ephemeral=True)
        if prefix.isspace() or "@everyone" in prefix or "@here" in prefix:
            return await i.response.send_message("❌ That prefix cannot be used.", ephemeral=True)

        await db.set_prefix(i.guild.id, prefix)
        bot._air_prefixes[i.guild.id] = prefix

        e = clean_embed("Prefix Updated", f"Text commands in **{i.guild.name}** now use **`{prefix}`**.", discord.Color.green())
        e.add_field(name="New Prefix", value=f"`{prefix}`", inline=True)
        e.add_field(name="Example", value=f"`{prefix}help`", inline=True)
        e.add_field(name="Changed By", value=i.user.mention, inline=True)
        await i.response.send_message(embed=e)

    @prefix_group.command(name="view", description="Show the current server prefix")
    async def prefix_view(i: discord.Interaction):
        if not i.guild:
            return await i.response.send_message("❌ This command can only be used in a server.", ephemeral=True)
        prefix = bot._air_prefixes.get(i.guild.id, "!")
        e = clean_embed("Server Prefix", f"The current text command prefix is **`{prefix}`**.")
        e.add_field(name="Example", value=f"`{prefix}help`", inline=False)
        await i.response.send_message(embed=e)

    bot.tree.add_command(prefix_group)

    # Custom command builder: /cmdmaker is registered through the same startup
    # hook used by moderation, so bot.py does not need another architectural hook.
    cmdmaker.setup(bot)
