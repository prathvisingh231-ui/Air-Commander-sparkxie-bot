# Air Commander — Advanced Tickets
import discord, sqlite3, time
from discord import app_commands
from discord.ext import commands

DB="aircommander.db"
def db():
    c=sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS ticket_cfg(guild_id INTEGER PRIMARY KEY, category_id INTEGER, support_role_id INTEGER, log_channel_id INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tickets(guild_id INTEGER, channel_id INTEGER, opener_id INTEGER, claimed_id INTEGER, status TEXT, created REAL)""")
    c.commit(); return c
def E(t,d,c=0x5865F2): return discord.Embed(title=f"🎫 {t}",description=d,color=c,timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")

class TicketView(discord.ui.View):
    def __init__(self,cog): super().__init__(timeout=None); self.cog=cog
    @discord.ui.button(label="Claim",emoji="🙋",style=discord.ButtonStyle.primary,custom_id="ac:ticket:claim")
    async def claim(self,i,b): await self.cog.claim_channel(i)
    @discord.ui.button(label="Close",emoji="🔒",style=discord.ButtonStyle.secondary,custom_id="ac:ticket:close")
    async def close(self,i,b): await self.cog.close_channel(i)
    @discord.ui.button(label="Delete",emoji="🗑️",style=discord.ButtonStyle.danger,custom_id="ac:ticket:delete")
    async def delete(self,i,b): await self.cog.delete_channel(i)

class Tickets(commands.Cog):
    ticket=app_commands.Group(name="ticket",description="Advanced ticket system")
    def __init__(self,bot): self.bot=bot
    async def cog_load(self): db().close(); self.bot.add_view(TicketView(self))

    async def setup_cfg(self,g):
        c=db(); c.execute("INSERT OR IGNORE INTO ticket_cfg(guild_id) VALUES(?)",(g.id,)); c.commit()
        row=c.execute("SELECT category_id,support_role_id,log_channel_id FROM ticket_cfg WHERE guild_id=?",(g.id,)).fetchone(); c.close(); return row
    @ticket.command(name="setup",description="Configure ticket category/support role.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setup_ticket(self,i,category:discord.CategoryChannel=None,support_role:discord.Role=None,log_channel:discord.TextChannel=None):
        c=db(); c.execute("INSERT OR REPLACE INTO ticket_cfg VALUES(?,?,?,?)",(i.guild.id,category.id if category else None,support_role.id if support_role else None,log_channel.id if log_channel else None)); c.commit(); c.close()
        await i.response.send_message(embed=E("Ticket Setup","✅ Configuration saved."))
    @ticket.command(name="panel",description="Send a ticket panel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def panel(self,i,channel:discord.TextChannel=None,title:str="Air Commander Support",description:str="Choose a ticket category below."):
        ch=channel or i.channel
        await ch.send(embed=E(title,f"🎟️ {description}\n\n🛒 Purchase • 🚨 Report • 🛠️ Support"),view=TicketView(self))
        await i.response.send_message("✅ Ticket panel sent.",ephemeral=True)
    @ticket.command(name="settings",description="View ticket settings.")
    async def settings(self,i):
        r=await self.setup_cfg(i.guild); await i.response.send_message(embed=E("Ticket Settings",f"📁 Category: `{r[0] or 'Not set'}`\n🛡️ Support Role: `{r[1] or 'Not set'}`\n📜 Logs: `{r[2] or 'Not set'}`"))
    @ticket.command(name="add",description="Add a member to the current ticket.")
    async def add(self,i,member:discord.Member):
        if not i.channel.name.startswith("ticket-"): return await i.response.send_message("❌ Use this inside a ticket.",ephemeral=True)
        await i.channel.set_permissions(member,view_channel=True,send_messages=True); await i.response.send_message(f"➕ Added {member.mention}.")
    @ticket.command(name="remove",description="Remove a member from the current ticket.")
    async def remove(self,i,member:discord.Member):
        await i.channel.set_permissions(member,overwrite=None); await i.response.send_message(f"➖ Removed {member.mention}.")
    @ticket.command(name="claim",description="Claim current ticket.")
    async def claim(self,i): await self.claim_channel(i)
    async def claim_channel(self,i):
        r=await self.setup_cfg(i.guild)
        if r[1] and r[1] not in [x.id for x in i.user.roles] and not i.user.guild_permissions.manage_channels: return await i.response.send_message("❌ Support permission required.",ephemeral=True)
        c=db(); c.execute("UPDATE tickets SET claimed_id=? WHERE channel_id=?",(i.user.id,i.channel.id)); c.commit(); c.close()
        await i.response.send_message(embed=E("Ticket Claimed",f"🙋 Claimed by {i.user.mention}",0x57F287))
    @ticket.command(name="unclaim",description="Unclaim current ticket.")
    async def unclaim(self,i):
        c=db(); c.execute("UPDATE tickets SET claimed_id=NULL WHERE channel_id=?",(i.channel.id,)); c.commit(); c.close(); await i.response.send_message("↩️ Ticket unclaimed.")
    @ticket.command(name="close",description="Close current ticket.")
    async def close(self,i): await self.close_channel(i)
    async def close_channel(self,i):
        if not i.channel.name.startswith("ticket-"): return await i.response.send_message("❌ Not a ticket.",ephemeral=True)
        await i.channel.set_permissions(i.guild.default_role,view_channel=False); await i.channel.set_permissions(i.channel.guild.get_member(i.channel.topic and 0 or i.user.id),send_messages=False) if False else None
        c=db(); c.execute("UPDATE tickets SET status='closed' WHERE channel_id=?",(i.channel.id,)); c.commit(); c.close()
        await i.response.send_message(embed=E("Ticket Closed","🔒 This ticket is now closed."))
    @ticket.command(name="reopen",description="Reopen current ticket.")
    async def reopen(self,i):
        await i.channel.set_permissions(i.guild.default_role,view_channel=True,send_messages=False)
        await i.response.send_message("🔓 Ticket reopened.")
    @ticket.command(name="delete",description="Delete current ticket.")
    async def delete(self,i): await self.delete_channel(i)
    async def delete_channel(self,i):
        if not i.user.guild_permissions.manage_channels: return await i.response.send_message("❌ Manage Channels required.",ephemeral=True)
        await i.response.send_message("🗑️ Deleting ticket…"); await i.channel.delete(reason=f"Ticket deleted by {i.user}")
    @ticket.command(name="rename",description="Rename current ticket.")
    async def rename(self,i,name:str):
        await i.channel.edit(name=f"ticket-{name[:80].lower()}"); await i.response.send_message("✏️ Ticket renamed.")
    @ticket.command(name="info",description="Show ticket information.")
    async def info(self,i):
        c=db(); r=c.execute("SELECT opener_id,claimed_id,status,created FROM tickets WHERE channel_id=?",(i.channel.id,)).fetchone(); c.close()
        await i.response.send_message(embed=E("Ticket Info",f"👤 Opener: `{r[0] if r else 'Unknown'}`\n🙋 Claimed: `{r[1] if r else 'Nobody'}`\n📌 Status: `{r[2] if r else 'Unknown'}`"))

    async def _open(self,i):
        cfg=await self.setup_cfg(i.guild); cat=i.guild.get_channel(cfg[0]) if cfg and cfg[0] else None
        overwrites={i.guild.default_role:discord.PermissionOverwrite(view_channel=False),i.user:discord.PermissionOverwrite(view_channel=True,send_messages=True)}
        if cfg and cfg[1] and i.guild.get_role(cfg[1]): overwrites[i.guild.get_role(cfg[1])]=discord.PermissionOverwrite(view_channel=True,send_messages=True)
        ch=await (cat.create_text_channel if cat else i.guild.create_text_channel)(f"ticket-{i.user.name[:20]}",overwrites=overwrites,topic=f"Opened by {i.user.id}")
        c=db(); c.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?)",(i.guild.id,ch.id,i.user.id,None,"open",time.time())); c.commit(); c.close()
        await ch.send(embed=E("Air Commander Ticket",f"👋 Welcome {i.user.mention}!\n📝 Please describe your request.\n\nSupport will be with you shortly."),view=TicketView(self))
        return ch

    async def ticket_create(self,i): ch=await self._open(i); await i.response.send_message(f"🎫 Created {ch.mention}.",ephemeral=True)
    @ticket.command(name="create",description="Create a ticket.")
    async def create(self,i): await self.ticket_create(i)

async def setup(bot): await bot.add_cog(Tickets(bot))
