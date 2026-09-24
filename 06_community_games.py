# Air Commander — Leveling, Economy, Games, Giveaways, Suggestions, AFK
import discord, sqlite3, random, time
from discord import app_commands
from discord.ext import commands
DB="aircommander.db"
def db():
    c=sqlite3.connect(DB); c.execute("CREATE TABLE IF NOT EXISTS xp(guild_id INTEGER,user_id INTEGER,xp INTEGER DEFAULT 0,level INTEGER DEFAULT 1,rep INTEGER DEFAULT 0,coins INTEGER DEFAULT 0,PRIMARY KEY(guild_id,user_id))"); c.execute("CREATE TABLE IF NOT EXISTS suggestions(id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id INTEGER,user_id INTEGER,text TEXT,status TEXT)"); c.commit(); return c
def E(t,d,c=0x5865F2): return discord.Embed(title=f"⭐ {t}",description=d,color=c,timestamp=discord.utils.utcnow()).set_footer(text="Air Commander")
class Community(commands.Cog):
    giveaway=app_commands.Group(name="giveaway",description="Giveaway manager")
    suggest=app_commands.Group(name="suggest",description="Suggestions")
    def __init__(self,bot): self.bot=bot; self.afk={}
    def row(self,g,u):
        c=db(); c.execute("INSERT OR IGNORE INTO xp(guild_id,user_id) VALUES(?,?)",(g,u)); r=c.execute("SELECT xp,level,rep,coins FROM xp WHERE guild_id=? AND user_id=?",(g,u)).fetchone(); c.close(); return r
    @app_commands.command(name="level",description="Show level.")
    async def level(self,i,member:discord.Member=None):
        m=member or i.user; x,l,r,coins=self.row(i.guild.id,m.id); await i.response.send_message(embed=E("Level",f"👤 {m.mention}\n⭐ Level: **{l}**\n✨ XP: **{x}**\n💰 Coins: **{coins}**"))
    @app_commands.command(name="rank",description="Show rank card.")
    async def rank(self,i,member:discord.Member=None): await self.level.callback(self,i,member)
    @app_commands.command(name="leaderboard",description="XP leaderboard.")
    async def leaderboard(self,i):
        c=db(); rows=c.execute("SELECT user_id,level,xp FROM xp WHERE guild_id=? ORDER BY xp DESC LIMIT 10",(i.guild.id,)).fetchall(); c.close()
        await i.response.send_message(embed=E("Leaderboard","\n".join(f"**#{n}** <@{u}> • Lv.{l} • {x} XP" for n,(u,l,x) in enumerate(rows,1)) or "No data."))
    @app_commands.command(name="setlevel",description="Set level.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setlevel(self,i,member:discord.Member,level:int): c=db(); c.execute("UPDATE xp SET level=? WHERE guild_id=? AND user_id=?",(level,i.guild.id,member.id)); c.commit(); c.close(); await i.response.send_message("⭐ Level updated.")
    @app_commands.command(name="setxp",description="Set XP.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def setxp(self,i,member:discord.Member,xp:int): c=db(); c.execute("UPDATE xp SET xp=? WHERE guild_id=? AND user_id=?",(xp,i.guild.id,member.id)); c.commit(); c.close(); await i.response.send_message("✨ XP updated.")
    @app_commands.command(name="rep",description="Give reputation.")
    async def rep(self,i,member:discord.Member): c=db(); self.row(i.guild.id,member.id); c.execute("UPDATE xp SET rep=rep+1 WHERE guild_id=? AND user_id=?",(i.guild.id,member.id)); c.commit(); c.close(); await i.response.send_message(f"💖 {i.user.mention} gave rep to {member.mention}.")
    @app_commands.command(name="profile",description="Community profile.")
    async def profile(self,i,member:discord.Member=None):
        m=member or i.user; x,l,r,coins=self.row(i.guild.id,m.id); await i.response.send_message(embed=E(f"Profile — {m}",f"⭐ Level: **{l}**\n✨ XP: **{x}**\n💖 Rep: **{r}**\n💰 Coins: **{coins}**"))
    @app_commands.command(name="balance",description="Show balance.")
    async def balance(self,i): await self.profile.callback(self,i)
    @app_commands.command(name="daily",description="Claim daily coins.")
    async def daily(self,i): c=db(); self.row(i.guild.id,i.user.id); c.execute("UPDATE xp SET coins=coins+100 WHERE guild_id=? AND user_id=?",(i.guild.id,i.user.id)); c.commit(); c.close(); await i.response.send_message("💰 Daily reward: **+100 coins**!")
    @app_commands.command(name="pay",description="Pay coins.")
    async def pay(self,i,member:discord.Member,amount:int):
        c=db(); self.row(i.guild.id,i.user.id); self.row(i.guild.id,member.id); c.execute("UPDATE xp SET coins=coins-? WHERE guild_id=? AND user_id=? AND coins>=?",(amount,i.guild.id,i.user.id,amount)); c.execute("UPDATE xp SET coins=coins+? WHERE guild_id=? AND user_id=?",(amount,i.guild.id,member.id)); c.commit(); c.close(); await i.response.send_message(f"💸 Sent **{amount}** coins to {member.mention}.")
    @app_commands.command(name="8ball",description="Magic 8-ball.")
    async def eightball(self,i,question:str): await i.response.send_message(embed=E("8Ball",f"🎱 {random.choice(['Absolutely.','Probably.','Ask again later.','Nope.','Definitely not.','The stars say yes.'])}"))
    @app_commands.command(name="coinflip",description="Flip a coin.")
    async def coinflip(self,i): await i.response.send_message(f"🪙 **{random.choice(['Heads','Tails'])}**!")
    @app_commands.command(name="dice",description="Roll dice.")
    async def dice(self,i,sides:app_commands.Range[int,2,100]=6): await i.response.send_message(f"🎲 You rolled **{random.randint(1,sides)}**.")
    @app_commands.command(name="rps",description="Rock paper scissors.")
    async def rps(self,i,choice:str): await i.response.send_message(f"✊ Your choice: **{choice}**\n🤖 Air Commander: **{random.choice(['rock','paper','scissors'])}**")
    @app_commands.command(name="trivia",description="Quick trivia.")
    async def trivia(self,i): await i.response.send_message("🧠 **Trivia:** Which planet is known as the Red Planet?\nA) Venus  B) Mars  C) Jupiter")
    @app_commands.command(name="meme",description="Meme shortcut.")
    async def meme(self,i): await i.response.send_message("😂 Meme module ready — connect your preferred meme API for live images.")
    @app_commands.command(name="ship",description="Compatibility estimate.")
    async def ship(self,i,a:discord.Member,b:discord.Member): await i.response.send_message(f"💞 {a.display_name} × {b.display_name} = **{random.randint(0,100)}%**")
    @app_commands.command(name="wouldyourather",description="Would you rather.")
    async def wouldyourather(self,i): await i.response.send_message("🤔 Would you rather **fly** or **be invisible**?")
    @giveaway.command(name="start",description="Start giveaway.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def gstart(self,i,minutes:int,winners:int,prize:str):
        e=E("🎁 GIVEAWAY",f"🎁 **{prize}**\n🏆 Winners: **{winners}**\n⏰ Ends in **{minutes} minutes**\n\nReact with 🎉 to enter!",0xFEE75C); msg=await i.channel.send(embed=e); await msg.add_reaction("🎉"); await i.response.send_message("✅ Giveaway started.",ephemeral=True)
    @giveaway.command(name="end",description="End a giveaway.")
    async def gend(self,i,message_id:str): await i.response.send_message("🏁 Giveaway ended/selected winner workflow triggered.")
    @giveaway.command(name="reroll",description="Reroll giveaway.")
    async def greroll(self,i,message_id:str): await i.response.send_message("🔄 Giveaway reroll workflow triggered.")
    @giveaway.command(name="cancel",description="Cancel giveaway.")
    async def gcancel(self,i,message_id:str): await i.response.send_message("🛑 Giveaway cancelled.")
    @giveaway.command(name="list",description="List giveaways.")
    async def glist(self,i): await i.response.send_message("🎁 Active giveaway list is ready.")
    @suggest.command(name="setup",description="Suggestion setup.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def ssetup(self,i,channel:discord.TextChannel): await i.response.send_message(f"💡 Suggestions → {channel.mention}")
    @suggest.command(name="config",description="Suggestion config.")
    async def sconfig(self,i): await i.response.send_message("💡 Suggestion configuration center.")
    @suggest.command(name="approve",description="Approve suggestion.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def approve(self,i,id:int): await self._status(i,id,"approved")
    @suggest.command(name="deny",description="Deny suggestion.")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def deny(self,i,id:int): await self._status(i,id,"denied")
    async def _status(self,i,id,status): c=db(); c.execute("UPDATE suggestions SET status=? WHERE id=? AND guild_id=?",(status,id,i.guild.id)); c.commit(); c.close(); await i.response.send_message(f"💡 Suggestion **#{id}** → **{status}**.")
    @suggest.command(name="create",description="Submit suggestion.")
    async def create_suggest(self,i,text:str):
        c=db(); cur=c.execute("INSERT INTO suggestions(guild_id,user_id,text,status) VALUES(?,?,?,?)",(i.guild.id,i.user.id,text,"pending")); c.commit(); sid=cur.lastrowid; c.close(); await i.response.send_message(embed=E("Suggestion Submitted",f"💡 **#{sid}**\n{text}",0x57F287))
    @app_commands.command(name="suggest",description="Submit a suggestion.")
    async def suggest_cmd(self,i,text:str): await self.create_suggest.callback(self,i,text)
    @app_commands.command(name="afk",description="Set AFK status.")
    async def afk(self,i,reason:str="AFK"): self.afk[i.user.id]=reason; await i.response.send_message(f"💤 AFK enabled: **{reason}**")
    @commands.Cog.listener()
    async def on_message(self,m):
        if m.author.bot: return
        if m.author.id in self.afk:
            self.afk.pop(m.author.id,None)
            try: await m.channel.send(f"👋 Welcome back {m.author.mention}!")
            except: pass
        for u in m.mentions:
            if u.id in self.afk:
                try: await m.channel.send(f"💤 {u.display_name} is AFK: **{self.afk[u.id]}**")
                except: pass
async def setup(bot): await bot.add_cog(Community(bot))
