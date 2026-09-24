import discord
from discord.ext import commands
from discord import app_commands

class TicketsAndModeration(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ##ban
    @app_commands.command(name="ban", description="🛡️ Ban a disruptive member from the server.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.ban(reason=reason)
        embed = discord.Embed(
            title="🛡️ **MODCASE // USER BANNED**",
            description=f"> *Security protocol executed.* Target: {member.mention}",
            color=discord.Color.from_rgb(231, 76, 60)
        )
        await interaction.response.send_message(embed=embed)

    ##purge
    @app_commands.command(name="purge", description="🧹 Bulk delete messages.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: int):
        await interaction.channel.purge(limit=amount)
        embed = discord.Embed(title="🧹 **PURGE // CLEANUP COMPLETE**", description=f"> Cleared `{amount}` messages.", color=discord.Color.from_rgb(46, 204, 113))
        await interaction.response.send_message(embed=embed, delete_after=5)

async def setup(bot):
    await bot.add_cog(TicketsAndModeration(bot))
