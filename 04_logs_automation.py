import discord
from discord.ext import commands
from discord import app_commands

class LogsAutomation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ##automod
    @app_commands.command(name="automod", description="🛡️ Configure AutoMod.")
    @app_commands.checks.has_permissions(administrator=True)
    async def automod(self, interaction: discord.Interaction, state: str):
        embed = discord.Embed(title="🛡️ **AUTOMOD**", description=f"> Status: `{state}`", color=discord.Color.from_rgb(88, 101, 242))
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(LogsAutomation(bot))
