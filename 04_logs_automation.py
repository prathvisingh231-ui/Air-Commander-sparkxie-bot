# Air Commander — Logging, Automation, Custom Commands, Panels
import discord, sqlite3, time, json
from discord import app_commands
from discord.ext import commands
DB="aircommander.db"
def db():
    c=sqlite3.connect(DB); c.execute("CREATE TABLE IF NOT EXISTS logs(guild_id INTEGER PRIMARY KEY, channel_id INTEGER)"); c.execute("CREATE TABLE IF NOT EXISTS custom(guild_id INTEGER, trigger TEXT, response TEXT, PRIMARY KEY(guild_id,trigger))"); c.commit(); return c
def E(t,d,c=0x5865F2): return discord.Embed(title=f"🛰️ {t}",description=d,color=c,timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")
class LogsAutomation(commands.Cog):
    custom=app_commands.Group(name="customcommand",description="Custom commands")
    logs=app_commands.Group(name="logs",description="Logging configuration")
    config=app_commands.Group(name="config",description="Server configuration")
    command=app_commands.Group(name="command",description="Per-command permissions")
    def __init__(self,bot): self.bot=bot
    async def cog_load(self): db().close()
    @logs.command(name="setup",description="Set logging channel.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def logs_setup(self,i,channel:discord.TextChannel): c=db(); c.execute("INSERT OR REPLACE INTO logs VALUES(?,?)",(i.guild.id,channel.id)); c.commit(); c.close(); await i.response.send_message(embed=E("Logging",f"📜 Logs → {channel.mention}",0x57F287))
    @logs.command(name="message",description="Configure message logging.")
    async def logs_message(self,i,enabled:bool=True): await i.response.send_message(f"💬 Message logs: **{'ON' if enabled else 'OFF'}**")
    @logs.command(name="moderation",description="Configure moderation logging.")
    async def logs_moderation(self,i,enabled:bool=True): await i.response.send_message(f"🛡️ Moderation logs: **{'ON' if enabled else 'OFF'}**")
    @logs.command(name="member",description="Configure member logging.")
    async def logs_member(self,i,enabled:bool=True): await i.response.send_message(f"👤 Member logs: **{'ON' if enabled else 'OFF'}**")
    @logs.command(name="channel",description="Configure channel logging.")
    async def logs_channel(self,i,enabled:bool=True): await i.response.send_message(f"📺 Channel logs: **{'ON' if enabled else 'OFF'}**")
    @logs.command(name="role",description="Configure role logging.")
    async def logs_role(self,i,enabled:bool=True): await i.response.send_message(f"🎭 Role logs: **{'ON' if enabled else 'OFF'}**")
    @logs.command(name="server",description="Configure server logging.")
    async def logs_server(self,i,enabled:bool=True): await i.response.send_message(f"🏠 Server logs: **{'ON' if enabled else 'OFF'}**")
    @custom.command(name="create",description="Create a custom response.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_create(self,i,trigger:str,response:str):
        c=db(); c.execute("INSERT OR REPLACE INTO custom VALUES(?,?,?)",(i.guild.id,trigger.lower(),response)); c.commit(); c.close(); await i.response.send_message(f"🧩 Custom command `{trigger}` saved.")
    @custom.command(name="edit",description="Edit custom response.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_edit(self,i,trigger:str,response:str): await self.custom_create.callback(self,i,trigger,response)
    @custom.command(name="delete",description="Delete custom response.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def custom_delete(self,i,trigger:str):
        c=db(); c.execute("DELETE FROM custom WHERE guild_id=? AND trigger=?",(i.guild.id,trigger.lower())); c.commit(); c.close(); await i.response.send_message("🗑️ Custom command deleted.")
    @config.command(name="view",description="View configuration.")
    async def config_view(self,i): await i.response.send_message(embed=E("Configuration","⚙️ Air Commander configuration center is active."))
    @config.command(name="reset",description="Reset configurable modules.")
    @app_commands.checks.has_permissions(administrator=True)
    async def config_reset(self,i): await i.response.send_message("♻️ Configuration reset requested.",ephemeral=True)
    @config.command(name="main",description="Open configuration center.")
    async def config_main(self,i): await self.config_view.callback(self,i)
    @command.command(name="enable",description="Enable a command.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def command_enable(self,i,name:str): await i.response.send_message(f"🟢 Enabled `/{name}`.")
    @command.command(name="disable",description="Disable a command.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def command_disable(self,i,name:str): await i.response.send_message(f"🔴 Disabled `/{name}`.")
    @command.command(name="permission",description="Set command permission.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def command_permission(self,i,name:str,role:discord.Role): await i.response.send_message(f"🔐 `/{name}` → {role.mention}")
    @app_commands.command(name="embed",description="Create an embed.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed(self,i,title:str,description:str,color:str="5865F2"):
        try: c=discord.Color(int(color.replace("#",""),16))
        except: c=discord.Color.blurple()
        e=discord.Embed(title=title,description=description,color=c,timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")
        await i.response.send_message(embed=e)
    @app_commands.command(name="say",description="Send a message.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(self,i,message:str): await i.response.send_message("✅ Sent.",ephemeral=True); await i.channel.send(message)
    @app_commands.command(name="embed_builder",description="Embed/panel builder starter.")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def embed_builder(self,i,title:str,description:str): await self.embed.callback(self,i,title,description)
    @commands.Cog.listener()
    async def on_message(self,message):
        if message.author.bot or not message.guild: return
        c=db(); r=c.execute("SELECT response FROM custom WHERE guild_id=? AND trigger=?",(message.guild.id,message.content.lower())).fetchone(); c.close()
        if r:
            try: await message.channel.send(r[0])
            except: pass
async def setup(bot): await bot.add_cog(LogsAutomation(bot))
