from pathlib import Path
import json
import discord
from discord import app_commands
from discord.ext import commands
import db

DATA_DIR = Path("data")

async def _status_embed(bot, guild):
    status = await db.database_status()
    e = discord.Embed(title="✈️ Air Commander • Server Setup Dashboard", description=f"Configuration overview for {guild.name}.", colour=discord.Colour.blurple(), timestamp=discord.utils.utcnow())
    e.add_field(name="PostgreSQL", value="🟢 Connected" if status.get("connected") else "🔴 Disconnected", inline=True)
    e.add_field(name="Feature modules", value=f"{len(getattr(bot, '_air_loaded_feature_modules', set()))} loaded", inline=True)
    e.add_field(name="Slash commands", value=f"{len(bot.tree.get_commands())} locally registered roots", inline=True)
    e.add_field(name="Feature checklist", value="• AI channel: /ai-channel-set\n• Welcome: /welcome\n• Self-role: /selfrole\n• YouTube: /youtube setup\n• Tickets: /ticket\n• Giveaways: /giveaway\n• Leveling: /airlevel\n• Autoresponder: /autoresponder\n• Modlog: /modlog setup", inline=False)
    e.add_field(name="Persistence warning", value="Settings backed only by local JSON can be lost on a host redeploy unless PostgreSQL snapshots are working. Use /backup create to download an owner-only backup.", inline=False)
    e.set_footer(text="Air Commander • Config Status")
    return e

def setup(bot):
    group = app_commands.Group(name="config", description="Air Commander server configuration dashboard")
    @group.command(name="status", description="Show setup status for this server")
    async def config_status(interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message("Server only.", ephemeral=True)
        await interaction.response.send_message(embed=await _status_embed(bot, interaction.guild), ephemeral=True)

    @bot.group(name="config", invoke_without_command=True)
    @commands.guild_only()
    async def prefix_config(ctx):
        await ctx.send(embed=await _status_embed(bot, ctx.guild))
    @prefix_config.command(name="status")
    async def prefix_config_status(ctx):
        await ctx.send(embed=await _status_embed(bot, ctx.guild))

    existing = bot.tree.get_command("config")
    if existing is None:
        bot.tree.add_command(group)
    elif isinstance(existing, app_commands.Group):
        for child in group.commands:
            if existing.get_command(child.name) is None:
                existing.add_command(child)
    print("Config dashboard registered.", flush=True)
