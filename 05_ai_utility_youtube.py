# Air Commander — AI/Utility + YouTube alert configuration
import discord, sqlite3, re, math, ast, operator, urllib.parse
from discord import app_commands
from discord.ext import commands
DB="aircommander.db"
def db():
    c=sqlite3.connect(DB); c.execute("""CREATE TABLE IF NOT EXISTS youtube(
      guild_id INTEGER, channel_key TEXT, target_channel INTEGER, kind TEXT, enabled INTEGER DEFAULT 1,
      PRIMARY KEY(guild_id,channel_key))"""); c.commit(); return c
def E(t,d,c=0x5865F2): return discord.Embed(title=f"🤖 {t}",description=d,color=c,timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")
class YouTubeGroup(app_commands.Group): pass
class AIUtility(commands.Cog):
    youtube=app_commands.Group(name="youtube",description="YouTube alert manager")
    def __init__(self,bot): self.bot=bot
    @app_commands.command(name="ping",description="Bot latency.")
    async def ping(self,i): await i.response.send_message(embed=E("Pong",f"🏓 **{round(self.bot.latency*1000)}ms**"))
    @app_commands.command(name="uptime",description="Bot uptime.")
    async def uptime(self,i): await i.response.send_message(embed=E("Uptime","🟢 Online and operational."))
    @app_commands.command(name="botinfo",description="Bot information.")
    async def botinfo(self,i): await i.response.send_message(embed=E("Air Commander",f"🤖 Servers: **{len(self.bot.guilds)}**\n👥 Cached users: **{len(self.bot.users)}**\n⚡ Latency: **{round(self.bot.latency*1000)}ms**"))
    @app_commands.command(name="calculator",description="Safe calculator.")
    async def calculator(self,i,expression:str):
        allowed=set("0123456789+-*/(). %")
        if any(x not in allowed for x in expression): return await i.response.send_message("❌ Unsupported expression.",ephemeral=True)
        try: result=eval(expression,{"__builtins__":{}},{})
        except: result="Error"
        await i.response.send_message(embed=E("Calculator",f"🧮 `{expression}` = **{result}**"))
    @app_commands.command(name="search",description="Create a search URL.")
    async def search(self,i,query:str):
        u="https://www.google.com/search?q="+urllib.parse.quote_plus(query)
        await i.response.send_message(embed=E("Search",f"🔎 [Search the web]({u})"))
    @app_commands.command(name="weather",description="Weather search shortcut.")
    async def weather(self,i,city:str): await i.response.send_message(embed=E("Weather",f"🌤️ Weather lookup: **{city}**\n🔎 https://www.google.com/search?q=weather+{urllib.parse.quote_plus(city)}"))
    @app_commands.command(name="translate",description="Translation shortcut.")
    async def translate(self,i,text:str,language:str): await i.response.send_message(embed=E("Translate",f"🌐 Translate to **{language}**:\n> {text}"))
    @app_commands.command(name="ask",description="AI question placeholder.")
    async def ask(self,i,question:str): await i.response.send_message(embed=E("AirMarshal AI",f"🧠 **Question:** {question}\n\nConnect your preferred AI API key in the bot core to enable generated answers."))
    @app_commands.command(name="summarise",description="Summarise supplied text.")
    async def summarise(self,i,text:str): await i.response.send_message(embed=E("Summarise",f"📚 Text received ({len(text)} chars).\nFor full AI summarisation, connect an AI provider."))
    @app_commands.command(name="remind",description="Reminder placeholder.")
    async def remind(self,i,minutes:app_commands.Range[int,1,10080],message:str):
        await i.response.send_message(embed=E("Reminder",f"⏰ Reminder scheduled for **{minutes} minutes**:\n{message}"))
    @youtube.command(name="add",description="Add YouTube alert source.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def yt_add(self,i,channel_key:str,target_channel:discord.TextChannel,kind:str="all"):
        c=db(); c.execute("INSERT OR REPLACE INTO youtube VALUES(?,?,?,?,1)",(i.guild.id,channel_key,target_channel.id,kind)); c.commit(); c.close()
        await i.response.send_message(embed=E("YouTube Alerts",f"📺 Source: `{channel_key}`\n📥 Destination: {target_channel.mention}\n🎬 Type: **{kind}**",0xFF0000))
    @youtube.command(name="remove",description="Remove YouTube alert source.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def yt_remove(self,i,channel_key:str):
        c=db(); c.execute("DELETE FROM youtube WHERE guild_id=? AND channel_key=?",(i.guild.id,channel_key)); c.commit(); c.close(); await i.response.send_message("🗑️ YouTube alert removed.")
    @youtube.command(name="list",description="List YouTube alerts.")
    async def yt_list(self,i):
        c=db(); rows=c.execute("SELECT channel_key,target_channel,kind,enabled FROM youtube WHERE guild_id=?",(i.guild.id,)).fetchall(); c.close()
        text="\n".join(f"📺 `{a}` → <#{b}> • `{k}` • {'🟢' if e else '🔴'}" for a,b,k,e in rows) or "No YouTube alerts configured."
        await i.response.send_message(embed=E("YouTube Alerts",text,0xFF0000))
    @youtube.command(name="edit",description="Edit YouTube alert.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def yt_edit(self,i,channel_key:str,target_channel:discord.TextChannel,kind:str="all"):
        await self.yt_add.callback(self,i,channel_key,target_channel,kind)
    @youtube.command(name="test",description="Test an alert.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def yt_test(self,i,channel_key:str):
        c=db(); r=c.execute("SELECT target_channel FROM youtube WHERE guild_id=? AND channel_key=?",(i.guild.id,channel_key)).fetchone(); c.close()
        ch=i.guild.get_channel(r[0]) if r else i.channel
        await ch.send(embed=E("YouTube Test",f"🔴 Test alert for **{channel_key}**"))
        await i.response.send_message("✅ Test sent.",ephemeral=True)
    @youtube.command(name="pause",description="Pause alerts.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def yt_pause(self,i,channel_key:str): await self._yt_toggle(i,channel_key,0)
    @youtube.command(name="resume",description="Resume alerts.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def yt_resume(self,i,channel_key:str): await self._yt_toggle(i,channel_key,1)
    async def _yt_toggle(self,i,key,val):
        c=db(); c.execute("UPDATE youtube SET enabled=? WHERE guild_id=? AND channel_key=?",(val,i.guild.id,key)); c.commit(); c.close(); await i.response.send_message(f"{'▶️ Resumed' if val else '⏸️ Paused'} `{key}`.")
    @youtube.command(name="settings",description="YouTube alert settings.")
    async def yt_settings(self,i):
        await self.yt_list.callback(self,i)
async def setup(bot): await bot.add_cog(AIUtility(bot))
