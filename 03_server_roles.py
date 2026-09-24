# Air Commander — Server Setup & Roles
import discord, sqlite3
from discord import app_commands
from discord.ext import commands
DB="aircommander.db"
def E(t,d,c=0x5865F2): return discord.Embed(title=f"⚙️ {t}",description=d,color=c,timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")
class ServerRoles(commands.Cog):
    def __init__(self,bot): self.bot=bot
    @app_commands.command(name="serverconfig",description="Server configuration overview.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def serverconfig(self,i):
        g=i.guild
        await i.response.send_message(embed=E("Server Configuration",f"🏠 **{g.name}**\n👥 Members: **{g.member_count}**\n💬 Channels: **{len(g.channels)}**\n🎭 Roles: **{len(g.roles)}**\n🚀 Boosts: **{g.premium_subscription_count}**"))
    @app_commands.command(name="welcome",description="Set welcome channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def welcome(self,i,channel:discord.TextChannel,enabled:bool=True):
        await i.response.send_message(embed=E("Welcome System",f"👋 Welcome messages: **{'ON' if enabled else 'OFF'}**\n📺 Channel: {channel.mention}"))
    @app_commands.command(name="goodbye",description="Set goodbye channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def goodbye(self,i,channel:discord.TextChannel,enabled:bool=True):
        await i.response.send_message(embed=E("Goodbye System",f"👋 Leave messages: **{'ON' if enabled else 'OFF'}**\n📺 Channel: {channel.mention}"))
    @app_commands.command(name="autorole",description="Configure autorole.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def autorole(self,i,role:discord.Role,enabled:bool=True):
        await i.response.send_message(embed=E("AutoRole",f"🎭 Role: {role.mention}\n{'🟢 Enabled' if enabled else '🔴 Disabled'}"))
    @app_commands.command(name="setprefix",description="Show prefix configuration note.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setprefix(self,i,prefix:str):
        await i.response.send_message(embed=E("Prefix",f"⌨️ Prefix set request: `{prefix}`"))
    @app_commands.command(name="setlogs",description="Set server log channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setlogs(self,i,channel:discord.TextChannel):
        await i.response.send_message(embed=E("Logs",f"📜 Log channel: {channel.mention}",0x57F287))
    role=app_commands.Group(name="role",description="Role management")
    @role.command(name="create",description="Create role.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_create(self,i,name:str,color:str="5865F2"):
        try: col=discord.Color(int(color.replace("#",""),16))
        except: col=discord.Color.blurple()
        r=await i.guild.create_role(name=name,color=col); await i.response.send_message(embed=E("Role Created",f"🎭 {r.mention}"))
    @role.command(name="delete",description="Delete role.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_delete(self,i,role:discord.Role):
        await role.delete(); await i.response.send_message("🗑️ Role deleted.")
    @role.command(name="add",description="Give role.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_add(self,i,member:discord.Member,role:discord.Role):
        await member.add_roles(role); await i.response.send_message(f"🎭 Added {role.mention} to {member.mention}.")
    @role.command(name="remove",description="Remove role.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_remove(self,i,member:discord.Member,role:discord.Role):
        await member.remove_roles(role); await i.response.send_message(f"➖ Removed {role.mention} from {member.mention}.")
    @role.command(name="edit",description="Edit role name.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role_edit(self,i,role:discord.Role,name:str=None,color:str=None):
        kw={}
        if name: kw["name"]=name
        if color:
            try: kw["color"]=discord.Color(int(color.replace("#",""),16))
            except: pass
        await role.edit(**kw); await i.response.send_message("✏️ Role updated.")
    @role.command(name="info",description="Role information.")
    async def role_info(self,i,role:discord.Role):
        await i.response.send_message(embed=E("Role Info",f"🎭 {role.mention}\n🆔 `{role.id}`\n👥 Members: **{len(role.members)}**\n🎨 Color: `{role.color}`"))
    @app_commands.command(name="userinfo",description="Member information.")
    async def userinfo(self,i,member:discord.Member=None):
        m=member or i.user
        await i.response.send_message(embed=E("User Info",f"👤 {m.mention}\n🆔 `{m.id}`\n📅 Joined: <t:{int(m.joined_at.timestamp())}:R>\n🎭 Roles: **{max(0,len(m.roles)-1)}**"))
    @app_commands.command(name="serverinfo",description="Server information.")
    async def serverinfo(self,i):
        g=i.guild; await i.response.send_message(embed=E("Server Info",f"🏠 **{g.name}**\n🆔 `{g.id}`\n👑 Owner: <@{g.owner_id}>\n👥 Members: **{g.member_count}**\n💬 Channels: **{len(g.channels)}**\n🎭 Roles: **{len(g.roles)}**\n📅 Created: <t:{int(g.created_at.timestamp())}:D>"))
    @app_commands.command(name="avatar",description="Show avatar.")
    async def avatar(self,i,member:discord.Member=None):
        m=member or i.user; await i.response.send_message(embed=E("Avatar",f"🖼️ {m.mention}"),file=discord.File(__import__("io").BytesIO(await m.display_avatar.read()),filename="avatar.png"))
    @app_commands.command(name="banner",description="Show user banner if available.")
    async def banner(self,i,member:discord.Member=None):
        u=await self.bot.fetch_user((member or i.user).id)
        await i.response.send_message(embed=E("Banner",f"🎨 {u.banner.url if u.banner else 'No banner set.'}"))
    @app_commands.command(name="roleinfo",description="Role information.")
    async def roleinfo(self,i,role:discord.Role): await self.role_info.callback(self,i,role)
    @app_commands.command(name="channelinfo",description="Channel information.")
    async def channelinfo(self,i,channel:discord.abc.GuildChannel=None):
        c=channel or i.channel; await i.response.send_message(embed=E("Channel Info",f"📺 {c.mention}\n🆔 `{c.id}`\n📁 Type: `{c.type}`"))
    @app_commands.command(name="membercount",description="Member count.")
    async def membercount(self,i): await i.response.send_message(embed=E("Member Count",f"👥 **{i.guild.member_count}** members."))
    @app_commands.command(name="selfrole",description="Add/remove a role from yourself.")
    async def selfrole(self,i,role:discord.Role):
        if role in i.user.roles: await i.user.remove_roles(role); action="removed"
        else: await i.user.add_roles(role); action="added"
        await i.response.send_message(f"🎭 Role {action}: {role.mention}",ephemeral=True)
    @app_commands.command(name="roleall",description="Give role to all members.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def roleall(self,i,role:discord.Role):
        await i.response.defer(ephemeral=True); n=0
        for m in i.guild.members:
            try: await m.add_roles(role); n+=1
            except: pass
        await i.followup.send(f"🎭 Added {role.mention} to **{n}** members.",ephemeral=True)
    @app_commands.command(name="unroleall",description="Remove role from all members.")
    @app_commands.checks.has_permissions(manage_roles=True)
    async def unroleall(self,i,role:discord.Role):
        await i.response.defer(ephemeral=True); n=0
        for m in i.guild.members:
            try: await m.remove_roles(role); n+=1
            except: pass
        await i.followup.send(f"🧹 Removed {role.mention} from **{n}** members.",ephemeral=True)
async def setup(bot): await bot.add_cog(ServerRoles(bot))
