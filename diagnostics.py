import discord
from discord import app_commands
from discord.ext import commands
import db

async def _is_owner(bot, user):
    try:
        return await bot.is_owner(user)
    except Exception:
        return False

async def _make_report(bot, detailed=False):
    status = await db.database_status()
    loaded = sorted(getattr(bot, "_air_loaded_feature_modules", set()))
    expected = {"autorolesetup", "automation", "cmdmaker", "command_permissions", "embed_builder", "giveaways", "leveling", "snipe", "welcome_autorole", "youtube_alerts", "config_dashboard", "diagnostics", "backup_system", "modlog"}
    missing = sorted(expected - set(loaded))
    e = discord.Embed(title="Air Commander • Diagnostics", colour=discord.Colour.blurple(), timestamp=discord.utils.utcnow())
    e.add_field(name="PostgreSQL", value="Connected" if status.get("connected") else "DISCONNECTED", inline=True)
    e.add_field(name="Bot ready", value="Yes" if bot.is_ready() else "No", inline=True)
    e.add_field(name="Slash roots (local)", value=str(len(bot.tree.get_commands())), inline=True)
    e.add_field(name="Feature loader", value=f"{len(loaded)} tracked as loaded", inline=True)
    if detailed:
        e.add_field(name="Loaded modules", value=", ".join(loaded)[:1000] or "None reported", inline=False)
        e.add_field(name="Not marked loaded", value=", ".join(missing)[:1000] or "None", inline=False)
        if status.get("error"):
            e.add_field(name="Database error", value=str(status["error"])[:1000], inline=False)
    else:
        e.add_field(name="Next steps", value="If PostgreSQL is disconnected, fix DATABASE_URL first. Then run ,syncslash as the bot owner and check Render logs.", inline=False)
    e.set_footer(text="No secret values are displayed.")
    return e

def setup(bot):
    group = app_commands.Group(name="diagnostics", description="Inspect Air Commander health")
    @group.command(name="status", description="Check bot, database and slash registration health")
    async def diagnostics_status(interaction: discord.Interaction):
        if not await _is_owner(bot, interaction.user):
            return await interaction.response.send_message("Bot owner only.", ephemeral=True)
        await interaction.response.send_message(embed=await _make_report(bot), ephemeral=True)
    @group.command(name="modules", description="List loaded and unverified feature modules")
    async def diagnostics_modules(interaction: discord.Interaction):
        if not await _is_owner(bot, interaction.user):
            return await interaction.response.send_message("Bot owner only.", ephemeral=True)
        await interaction.response.send_message(embed=await _make_report(bot, detailed=True), ephemeral=True)

    @bot.group(name="diagnostics", invoke_without_command=True)
    async def prefix_diagnostics(ctx):
        if not await _is_owner(bot, ctx.author):
            return await ctx.send("Bot owner only.")
        await ctx.send(embed=await _make_report(bot))
    @prefix_diagnostics.command(name="modules")
    async def prefix_diagnostics_modules(ctx):
        if not await _is_owner(bot, ctx.author):
            return await ctx.send("Bot owner only.")
        await ctx.send(embed=await _make_report(bot, detailed=True))

    existing = bot.tree.get_command("diagnostics")
    if existing is None:
        bot.tree.add_command(group)
    elif isinstance(existing, app_commands.Group):
        for child in group.commands:
            if existing.get_command(child.name) is None:
                existing.add_command(child)
    print("Diagnostics registered.", flush=True)
