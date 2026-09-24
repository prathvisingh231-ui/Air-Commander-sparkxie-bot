import discord
from discord.ext import commands
from discord import app_commands

class ServerRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    ##role add
    @app_commands.command(name="role_add", description="➕ Assign a role to a member.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        await member.add_roles(role)
        embed = discord.Embed(title="🎭 **ROLE ASSIGNMENT**", description=f"> Assigned {role.mention} to {member.mention}", color=discord.Color.from_rgb(46, 204, 113))
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(ServerRoles(bot))
