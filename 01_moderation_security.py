# Air Commander — Moderation & Security
# discord.py 2.x | Drop-in Cog
import discord, sqlite3, time, re
from discord import app_commands
from discord.ext import commands

DB = "aircommander.db"

def db():
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS warns(
        guild_id INTEGER, user_id INTEGER, moderator_id INTEGER,
        reason TEXT, created REAL)""")
    c.execute("""CREATE TABLE IF NOT EXISTS security(
        guild_id INTEGER PRIMARY KEY, antispam INTEGER DEFAULT 0,
        antilink INTEGER DEFAULT 0, antiraid INTEGER DEFAULT 0,
        antimention INTEGER DEFAULT 0, antibot INTEGER DEFAULT 0,
        verification INTEGER DEFAULT 0)""")
    c.commit()
    return c

def emb(title, desc, color=0x5865F2):
    return discord.Embed(title=f"🛰️ {title}", description=desc, color=color,
                         timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")

class ModerationSecurity(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.spam = {}
        self.links = re.compile(r"(https?://|discord\.gg/)", re.I)

    async def cog_load(self):
        db().close()

    @app_commands.command(name="ban", description="Ban a member.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str="No reason provided"):
        await member.ban(reason=reason)
        await interaction.response.send_message(embed=emb("Member Banned", f"🔨 {member.mention} was banned.\n📝 **Reason:** {reason}", 0xED4245))

    @app_commands.command(name="unban", description="Unban a user by ID.")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user_id: str):
        try: uid=int(user_id)
        except: return await interaction.response.send_message("❌ Invalid user ID.", ephemeral=True)
        try:
            user=await self.bot.fetch_user(uid); await interaction.guild.unban(user)
            await interaction.response.send_message(embed=emb("User Unbanned", f"✅ {user} is unbanned.", 0x57F287))
        except discord.NotFound:
            await interaction.response.send_message("❌ User is not banned.", ephemeral=True)

    @app_commands.command(name="kick", description="Kick a member.")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(self, interaction, member: discord.Member, reason: str="No reason provided"):
        await member.kick(reason=reason)
        await interaction.response.send_message(embed=emb("Member Kicked", f"👢 {member.mention} was kicked.\n📝 {reason}", 0xFEE75C))

    @app_commands.command(name="timeout", description="Timeout a member.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(self, interaction, member: discord.Member, minutes: app_commands.Range[int,1,10080], reason: str="No reason provided"):
        await member.timeout(discord.utils.utcnow()+__import__("datetime").timedelta(minutes=minutes), reason=reason)
        await interaction.response.send_message(embed=emb("Timeout Applied", f"💤 {member.mention} for **{minutes}m**.\n📝 {reason}"))

    @app_commands.command(name="untimeout", description="Remove a timeout.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(self, interaction, member: discord.Member):
        await member.timeout(None)
        await interaction.response.send_message(embed=emb("Timeout Removed", f"⚡ {member.mention} can speak again.", 0x57F287))

    @app_commands.command(name="warn", description="Warn a member.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warn(self, interaction, member: discord.Member, reason: str="No reason provided"):
        c=db(); c.execute("INSERT INTO warns VALUES(?,?,?,?,?)",(interaction.guild.id,member.id,interaction.user.id,reason,time.time())); c.commit(); c.close()
        await interaction.response.send_message(embed=emb("Warning Issued", f"⚠️ {member.mention}\n📝 {reason}", 0xFEE75C))

    @app_commands.command(name="warnings", description="View warnings.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def warnings(self, interaction, member: discord.Member):
        c=db(); rows=c.execute("SELECT reason,created FROM warns WHERE guild_id=? AND user_id=? ORDER BY created DESC",(interaction.guild.id,member.id)).fetchall(); c.close()
        text="\n".join(f"**#{i+1}** • {r[0]}" for i,r in enumerate(rows[:15])) or "No warnings."
        await interaction.response.send_message(embed=emb(f"Warnings — {member}", text, 0xFEE75C))

    @app_commands.command(name="clearwarn", description="Clear all warnings for a member.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clearwarn(self, interaction, member: discord.Member):
        c=db(); c.execute("DELETE FROM warns WHERE guild_id=? AND user_id=?",(interaction.guild.id,member.id)); c.commit(); c.close()
        await interaction.response.send_message(embed=emb("Warnings Cleared", f"🧹 Cleared warnings for {member.mention}.", 0x57F287))

    @app_commands.command(name="purge", description="Delete messages.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def purge(self, interaction, amount: app_commands.Range[int,1,100]):
        await interaction.response.defer(ephemeral=True)
        deleted=await interaction.channel.purge(limit=amount)
        await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** messages.", ephemeral=True)

    @app_commands.command(name="clear", description="Alias for purge.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(self, interaction, amount: app_commands.Range[int,1,100]):
        await self.purge.callback(self, interaction, amount)

    @app_commands.command(name="slowmode", description="Set channel slowmode.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(self, interaction, seconds: app_commands.Range[int,0,21600]):
        await interaction.channel.edit(slowmode_delay=seconds)
        await interaction.response.send_message(embed=emb("Slowmode Updated", f"🐢 **{seconds}s** slowmode enabled."))

    async def _lock(self, interaction, locked):
        ow=interaction.channel.overwrites_for(interaction.guild.default_role); ow.send_messages=not locked
        await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=ow)
        await interaction.response.send_message(embed=emb("Channel Locked" if locked else "Channel Unlocked", "🔒" if locked else "🔓"))

    @app_commands.command(name="lock", description="Lock the channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(self, interaction): await self._lock(interaction, True)

    @app_commands.command(name="unlock", description="Unlock the channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(self, interaction): await self._lock(interaction, False)

    @app_commands.command(name="nickname", description="Change a member nickname.")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def nickname(self, interaction, member: discord.Member, nickname: str=None):
        await member.edit(nick=nickname)
        await interaction.response.send_message(embed=emb("Nickname Updated", f"🎨 {member.mention} → **{nickname or 'Reset'}**", 0x57F287))

    @app_commands.command(name="mute", description="Mute using timeout.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def mute(self, interaction, member: discord.Member, minutes: app_commands.Range[int,1,10080]=60):
        await member.timeout(discord.utils.utcnow()+__import__("datetime").timedelta(minutes=minutes))
        await interaction.response.send_message(embed=emb("Muted", f"🔇 {member.mention} for **{minutes}m**."))

    @app_commands.command(name="unmute", description="Remove mute.")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def unmute(self, interaction, member: discord.Member): await self.untimeout.callback(self, interaction, member)

    @app_commands.command(name="automod", description="Configure basic security modules.")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.choices(module=[app_commands.Choice(name=x,value=x) for x in ["antispam","antilink","antiraid","antimention","antibot","verification"]])
    async def automod(self, interaction, module: app_commands.Choice[str], enabled: bool):
        c=db(); c.execute("INSERT OR IGNORE INTO security(guild_id) VALUES(?)",(interaction.guild.id,))
        c.execute(f"UPDATE security SET {module.value}=? WHERE guild_id=?",(int(enabled),interaction.guild.id)); c.commit(); c.close()
        await interaction.response.send_message(embed=emb("Security Center", f"🛡️ **{module.name}** → {'🟢 ON' if enabled else '🔴 OFF'}"))

    @app_commands.command(name="security", description="Show security status.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def security(self, interaction):
        c=db(); r=c.execute("SELECT antispam,antilink,antiraid,antimention,antibot,verification FROM security WHERE guild_id=?",(interaction.guild.id,)).fetchone(); c.close()
        r=r or (0,)*6
        names=["Anti-Spam","Anti-Link","Anti-Raid","Anti-Mention","Anti-Bot","Verification"]
        await interaction.response.send_message(embed=emb("Advanced Security Center","\n".join(f"{'🟢' if x else '🔴'} **{n}**" for n,x in zip(names,r))))

    @app_commands.command(name="antinuke", description="Toggle anti-nuke protection status.")
    @app_commands.checks.has_permissions(administrator=True)
    async def antinuke(self, interaction, enabled: bool=True):
        await interaction.response.send_message(embed=emb("Anti-Nuke", f"🛡️ Protection set to **{'ON' if enabled else 'OFF'}**."))

    @app_commands.command(name="antispam", description="Toggle anti-spam.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antispam(self, interaction, enabled: bool): await self._toggle(interaction,"antispam",enabled)

    @app_commands.command(name="antilink", description="Toggle anti-link.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antilink(self, interaction, enabled: bool): await self._toggle(interaction,"antilink",enabled)

    @app_commands.command(name="antiraid", description="Toggle anti-raid.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antiraid(self, interaction, enabled: bool): await self._toggle(interaction,"antiraid",enabled)

    @app_commands.command(name="antimention", description="Toggle anti-mass-mention.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antimention(self, interaction, enabled: bool): await self._toggle(interaction,"antimention",enabled)

    @app_commands.command(name="antibot", description="Toggle anti-bot join protection.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def antibot(self, interaction, enabled: bool): await self._toggle(interaction,"antibot",enabled)

    async def _toggle(self, i, module, enabled):
        c=db(); c.execute("INSERT OR IGNORE INTO security(guild_id) VALUES(?)",(i.guild.id,)); c.execute(f"UPDATE security SET {module}=? WHERE guild_id=?",(int(enabled),i.guild.id)); c.commit(); c.close()
        await i.response.send_message(embed=emb("Security Updated",f"🛡️ **{module}** → {'🟢 ON' if enabled else '🔴 OFF'}"))

async def setup(bot): await bot.add_cog(ModerationSecurity(bot))
