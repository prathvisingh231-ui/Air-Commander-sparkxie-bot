import random
import asyncio
import db
import hashlib
import discord
from discord import app_commands
from discord.ext import commands

def embed(title, desc="", color=None):
    return discord.Embed(title=f"✈️ {title}", description=desc, color=color or discord.Color.blurple(), timestamp=discord.utils.utcnow())

def seed(*parts):
    return int(hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()[:12], 16)

def setup(bot):
    class LobbyView(discord.ui.View):
        def __init__(self, game, session_id):
            super().__init__(timeout=31); self.game=game; self.session_id=session_id; self.message=None; self.remaining=30
        async def on_timeout(self):
            info=await db.session_info(self.session_id)
            if not info or info["status"] != "lobby": return
            await db.close_session(self.session_id, "cancelled")
            if self.message:
                try: await self.message.edit(embed=embed(f"{self.game.title()} • Lobby Closed ⏰","No players joined before the 30-second countdown ended. Game cancelled.",discord.Color.red()),view=None)
                except discord.HTTPException: pass
        @discord.ui.button(label="Join Game",emoji="🎮",style=discord.ButtonStyle.success)
        async def join(self,interaction,button):
            ok=await db.join_session(self.session_id,interaction.user.id)
            if not ok: return await interaction.response.send_message("❌ Lobby is closed.",ephemeral=True)
            await interaction.response.send_message(f"✅ {interaction.user.mention} joined **{self.game.title()}**! Watch the lobby countdown.",ephemeral=True)
        @discord.ui.button(label="How to Play",emoji="📖",style=discord.ButtonStyle.primary)
        async def how(self,interaction,button):
            e=embed(f"How to Play • {self.game.title()}","**1. Join** the lobby before the timer ends.\n**2. Wait** for the 30-second countdown.\n**3. Start:** the bot creates the scenario automatically.\n**4. Play:** use the action buttons/turn commands to make decisions.\n**5. Progress:** earn virtual coins, XP, loot and achievements.\n\n💾 Everything is saved to PostgreSQL.\n\n⚠️ If **0 players** have joined when the timer ends, the lobby is cancelled automatically.",discord.Color.green())
            await interaction.response.send_message(embed=e,ephemeral=True)

    async def lobby_countdown(message,game,sid,view):
        view.message=message
        for remaining in range(30,0,-1):
            view.remaining=remaining
            try:
                rows=await db.session_players(sid)
                e=embed(f"{game.title()} • Lobby 🎮",f"**Session:** #{sid}\n\n📖 **How to play**\nJoin with **🎮 Join Game**. The game starts automatically after 30 seconds. During the game, follow the action buttons and turn prompts. Your rewards and progress are saved.\n\n👥 **Players:** {len(rows)}\n⏱️ **Starting in: {remaining}s**",discord.Color.blurple())
                e.set_footer(text="No players joined by the end = lobby automatically cancelled.")
                await message.edit(embed=e,view=view)
            except discord.HTTPException: return
            await asyncio.sleep(1)
        rows=await db.session_players(sid)
        minimum_players = 2
        if len(rows) < minimum_players:
            await db.close_session(sid,"cancelled")
            try:
                await message.edit(
                    embed=embed(
                        f"{game.title()} • Cancelled ⏰",
                        f"The 30-second lobby ended with **{len(rows)} player(s)**. At least **{minimum_players} players** are required, so the game was cancelled. Nothing was charged or changed.",
                        discord.Color.red(),
                    ),
                    view=None,
                )
            except discord.HTTPException:
                pass
            return
        await db.close_session(sid,"active")
        try: await message.edit(embed=embed(f"{game.title()} • GAME STARTED 🚀",f"**{len(rows)} player(s)** joined! The game is now starting.\n\n🎯 Make decisions when the bot presents each turn.\n💾 XP, coins and progression are saved.",discord.Color.green()),view=None)
        except discord.HTTPException: pass

    @bot.tree.command(name="startgame", description="Start a persistent multiplayer game")
    @app_commands.describe(game="Game name")
    async def startgame(i, game: str):
        allowed={"heist","kingdom","assassin","blackmarket","escape","outbreak","conquest","treasure","arena","casino","detective","zombie","race","pirate","dungeon"}
        game=game.lower().strip()
        if game not in allowed: return await i.response.send_message("❌ Unknown game. Choose a supported game.",ephemeral=True)
        sid=await db.new_session(i.guild_id,game,i.user.id,{"round":1,"seed":random.randint(1,999999)})
        if sid is None: return await i.response.send_message("⚠️ PostgreSQL is not connected. Set DATABASE_URL on Render.",ephemeral=True)
        view=LobbyView(game,sid)
        e=embed(f"{game.title()} • Lobby 🎮",f"**Session:** #{sid}\n\n📖 **How to play**\nYou have **30 seconds** to join. Press **🎮 Join Game**. The game starts automatically only if at least **2 players** are in the lobby when the timer ends; otherwise it is cancelled.\n\n👤 Host: {i.user.mention}\n👥 Players: 1 / 2 minimum\n⏱️ Starting in: **30s**",discord.Color.blurple())
        e.add_field(name="🪙 Economy",value="Virtual coins + XP",inline=True)
        e.add_field(name="💾 Persistence",value="PostgreSQL",inline=True)
        await i.response.send_message(embed=e,view=view)
        await db.join_session(sid,i.user.id)
        msg=await i.original_response()
        asyncio.create_task(lobby_countdown(msg,game,sid,view))
    @bot.tree.command(name="play", description="Take a turn in a game session")
    @app_commands.describe(session_id="Session ID", decision="Your decision")
    async def play(i, session_id:int, decision:str):
        roll=random.randint(1,100); win=roll>=55
        outcome=random.choice(["Success!","Partial success.","A surprise event occurred!","You found a bonus!","The plan backfired — recover and continue."])
        coins=random.randint(10,40) if win else random.randint(2,12); xp=15 if win else 5
        await db.add_coins(i.guild_id,i.user.id,coins); await db.add_xp(i.guild_id,i.user.id,xp)
        e=embed("Game Turn 🎲",f"Session #{session_id}\\nDecision: {decision}",discord.Color.green() if win else discord.Color.orange())
        e.add_field(name="🎲 Roll",value=str(roll),inline=True); e.add_field(name="📜 Outcome",value=outcome,inline=False)
        e.add_field(name="🪙 Reward",value=f"+{coins} coins",inline=True); e.add_field(name="⭐ XP",value=f"+{xp} XP",inline=True)
        e.set_footer(text="Virtual gameplay • Rewards saved to profile"); await i.response.send_message(embed=e)

    @bot.tree.command(name="leaderboard", description="Show the server game leaderboard")
    async def leaderboard(i):
        if not db._pool: return await i.response.send_message(embed=embed("Leaderboard 🏆","Set DATABASE_URL on Render to enable persistent leaderboard data."))
        rows=await db._pool.fetch("SELECT user_id,coins,xp,level FROM players WHERE guild_id=$1 ORDER BY xp DESC,coins DESC LIMIT 10",i.guild_id)
        lines=[]
        for n,row in enumerate(rows,1):
            m=i.guild.get_member(row["user_id"]); name=m.display_name if m else f"User {row["user_id"]}"
            lines.append(f"**{n}.** {name} — ⭐ {row["xp"]} XP • 🪙 {row["coins"]} • Lv {row["level"]}")
        await i.response.send_message(embed=embed("AirCommander Leaderboard 🏆","\\n".join(lines) or "No players yet.",discord.Color.gold()))
    @bot.tree.command(name="profile", description="Show your persistent game profile")
    async def profile(i):
        p=await db.get_player(i.guild_id,i.user.id)
        e=embed("Player Profile 🧑‍✈️",f"{i.user.mention}'s AirCommander game profile")
        e.add_field(name="🪙 Coins",value=str(p["coins"]),inline=True)
        e.add_field(name="⭐ XP",value=str(p["xp"]),inline=True)
        e.add_field(name="🏅 Level",value=str(p["level"]),inline=True)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="gamejoin", description="Join a game session")
    @app_commands.describe(session_id="Session ID")
    async def gamejoin(i,session_id:int):
        await db.join_session(session_id,i.user.id)
        e=embed("Game Lobby 🎮",f"{i.user.mention} joined session **#{session_id}**.",discord.Color.green())
        await i.response.send_message(embed=e)

    async def whatif(i, action: str):
        outcomes=[("🟢 Low risk","Likely smooth; little disruption."),("🟡 Medium risk","Could affect members or channels; review permissions first."),("🔴 High risk","Potentially disruptive; verify target, permissions and rollback before applying.")]
        r=random.Random(seed(i.guild_id,action.lower())).choice(outcomes)
        e=embed("WhatIf • Action Preview",f"**Action:** {action}\n\n**Possible result:** {r[0]}\n{r[1]}\n\n*Preview only — nothing was changed.*")
        e.add_field(name="Safety",value="No Discord state was modified.",inline=False)
        await i.response.send_message(embed=e,ephemeral=True)

    async def impact(i, action: str):
        a=action.lower(); risk="Low"; score=20
        if any(x in a for x in ("ban","delete","remove","reset","lock","everyone")): risk="High"; score=85
        elif any(x in a for x in ("kick","mute","timeout","role","channel")): risk="Medium"; score=55
        e=embed("Impact Analysis",f"**{action}** is estimated at **{score}/100 impact** — **{risk}**.",discord.Color.orange() if risk!="Low" else discord.Color.green())
        e.add_field(name="👥 Members",value="May affect the selected target(s).",inline=True)
        e.add_field(name="📡 Server",value="Review permissions and scope.",inline=True)
        e.add_field(name="↩️ Recovery",value="Use /sandbox to preview before applying.",inline=False)
        await i.response.send_message(embed=e,ephemeral=True)

    async def sandbox(i, change: str):
        e=embed("Sandbox • Dry Run",f"**Requested change:** {change}\n\n🧪 **Simulation complete.**\nNo members, roles, channels, permissions or messages were changed.",discord.Color.teal())
        e.add_field(name="Result",value="Preview generated successfully.",inline=False)
        await i.response.send_message(embed=e,ephemeral=True)

    async def blindspot(i):
        g=i.guild
        admins=[r for r in g.roles if r!=g.default_role and r.permissions.administrator]
        unc=[c for c in g.channels if getattr(c,"category",None) is None]
        e=embed("BlindSpot • Security Review","Potential issues visible from Discord configuration.",discord.Color.red())
        e.add_field(name="🔐 Administrator Roles",value=f"{len(admins)} non-default admin role(s) detected.",inline=True)
        e.add_field(name="📂 Uncategorized Channels",value=str(len(unc)),inline=True)
        e.add_field(name="⚠️ Review",value="Check powerful roles, channel overwrites, logging, bot permissions, and exposed management channels.",inline=False)
        e.set_footer(text="BlindSpot reports observable configuration; it cannot inspect third-party bot internals.")
        await i.response.send_message(embed=e,ephemeral=True)

    async def sequence(i, actions: str):
        steps=[x.strip() for x in actions.split(",") if x.strip()][:10]
        e=embed("Sequence • Workflow Preview","Automated workflow plan — **preview only**.",discord.Color.purple())
        e.add_field(name="Steps",value="\n".join(f"**{n}.** {x}" for n,x in enumerate(steps,1)) or "No actions supplied.",inline=False)
        e.add_field(name="Safety",value="No actions are executed by this command.",inline=False)
        await i.response.send_message(embed=e,ephemeral=True)

    async def roast(i, member: discord.Member):
        lines=["has the confidence of a final boss and the aim of a tutorial bot.","could turn a 2-minute task into a three-season series.","is running on 2% battery and 98% audacity.","would lose a hide-and-seek match in an empty room.","has officially been diagnosed with terminal skill issue™."]
        e=embed("Roast Engine 🔥",f"{member.mention}, {random.choice(lines)}\n\n*Playful fictional roast — just for fun.*",discord.Color.orange())
        await i.response.send_message(embed=e)

    async def ship(i, first: discord.Member, second: discord.Member):
        pct=seed(first.id,second.id)%101
        e=embed("Ship • Compatibility Scan",f"{first.mention} 💞 {second.mention}",discord.Color.magenta())
        e.add_field(name="❤️ Compatibility",value=f"**{pct}%**",inline=True)
        e.add_field(name="🔮 Verdict",value=random.Random(pct).choice(["Chaotic duo","Power couple","Besties energy","Rivals with chemistry","Absolutely unpredictable"]),inline=True)
        await i.response.send_message(embed=e)

    async def chaos(i):
        challenges=["Compliment the next person who speaks.","Use only emojis for your next message.","Change your status to something funny for 10 minutes.","Ask the server a ridiculous but harmless question.","Send a wholesome meme."]
        e=embed("Chaos Challenge 🎲",random.choice(challenges),discord.Color.gold())
        e.set_footer(text="Safe challenge • No real-world or harmful actions")
        await i.response.send_message(embed=e)

    async def bounty(i, member: discord.Member, challenge: str, reward: app_commands.Range[int,1,10000]=100):
        e=embed("Bounty Board 🎯",f"**Target:** {member.mention}\n**Challenge:** {challenge}\n**Reward:** 🪙 {reward} points",discord.Color.gold())
        e.set_footer(text="Virtual fun only • No real money or prizes")
        await i.response.send_message(embed=e)

    async def duel(i, first: discord.Member, second: discord.Member):
        r=random.Random(seed(first.id,second.id)); a=r.randint(40,100); b=r.randint(40,100); winner=first if a>=b else second
        e=embed("Duel Arena ⚔️",f"{first.mention} **{a}**  VS  **{b}** {second.mention}",discord.Color.red())
        e.add_field(name="🏆 Winner",value=winner.mention,inline=False)
        await i.response.send_message(embed=e)

    async def liecheck(i, statement: str):
        pct=seed(statement,i.user.id)%101
        e=embed("LieCheck 🕵️",f"**Statement:** {statement}",discord.Color.dark_teal())
        e.add_field(name="Truth Probability",value=f"**{pct}%**",inline=True)
        e.add_field(name="AI Verdict",value=random.Random(pct).choice(["Suspicious 👀","Seems believable","The bot is unconvinced","Probably true","Maximum cap detected"]),inline=True)
        e.set_footer(text="For entertainment only — not a real lie detector.")
        await i.response.send_message(embed=e)

    async def plot(i):
        ms=[m for m in i.guild.members if not m.bot]
        random.shuffle(ms); ms=ms[:4]
        roles=["hero","mysterious wizard","chaotic sidekick","final boss"]
        story="\n".join(f"**{r.title()}:** {m.mention}" for r,m in zip(roles,ms))
        e=embed("Plot Generator 📖","Tonight's completely fictional server story:",discord.Color.purple())
        e.add_field(name="Cast",value=story or "Not enough members.",inline=False)
        await i.response.send_message(embed=e)

    async def clone(i, member: discord.Member):
        traits=["+99 confidence","+80 snack detection","+100 chaos resistance","+42 tactical wisdom","-7 sleep schedule"]
        e=embed(f"Clone Lab 🧬 • {member.display_name}",f"**Fictional Clone Profile**\n\n"+ "\n".join(f"• {x}" for x in random.sample(traits,3)),discord.Color.teal())
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text="Fictional parody profile — not an impersonation tool.")
        await i.response.send_message(embed=e)

    async def wanted(i, member: discord.Member):
        e=embed("WANTED 🤠",f"**{member.display_name}**\n\nWanted for: **Being suspiciously funny**\nReward: **{seed(member.id)%5000+500} virtual coins**",discord.Color.dark_gold())
        e.set_thumbnail(url=member.display_avatar.url)
        e.set_footer(text="Fictional server game • Not a real accusation")
        await i.response.send_message(embed=e)

    async def fortune(i):
        e=embed("Fortune Oracle 🔮",random.choice(["A legendary ping will arrive soon.","You will find unexpected virtual treasure.","Someone will reply with exactly one emoji.","Your next message will start a chain of chaos.","The server's luck is watching you."]),discord.Color.purple())
        e.set_footer(text="For entertainment only")
        await i.response.send_message(embed=e)

    async def rival(i, first: discord.Member, second: discord.Member):
        e=embed("Rivalry Generator ⚔️",f"{first.mention} 🆚 {second.mention}",discord.Color.red())
        e.add_field(name="Rivalry",value=random.choice(["Who owns the best profile?","Who can win the next challenge?","Who has superior meme energy?","Who will dominate the leaderboard?"]),inline=False)
        e.set_footer(text="Fictional rivalry • Keep it friendly")
        await i.response.send_message(embed=e)

    async def mission(i):
        missions=["Help a new member.","Share a useful tip.","Win a friendly duel.","Earn three reactions.","Complete a community challenge."]
        m=random.choice(missions); pts=random.randint(10,100)
        e=embed("Mission Briefing 🎯",f"**Mission:** {m}\n**Reward:** 🪙 {pts} points",discord.Color.green())
        await i.response.send_message(embed=e)

    async def roulette(i):
        choices=["Tell a clean joke.","Use a random emoji in your next message.","Compliment someone.","Ask a fun question.","Post a harmless meme.","Challenge someone to /duel."]
        e=embed("Roulette 🎰",f"**Selected:** {random.choice(choices)}",discord.Color.gold())
        e.set_footer(text="Safe virtual challenge • No gambling or real-money rewards")
        await i.response.send_message(embed=e)

    async def achievement(i):
        e=embed("Achievement Vault 🏆","Funny server achievements you can unlock.",discord.Color.gold())
        e.add_field(name="Available",value="🏅 First Flight\n🔥 Chaos Agent\n🕵️ Detective\n⚔️ Duelist\n💡 Idea Machine\n👑 Kingdom Builder",inline=False)
        await i.response.send_message(embed=e)

    async def oracle(i):
        e=embed("Oracle 🔮","The server whispers of **a great event approaching...**",discord.Color.purple())
        e.add_field(name="Prediction",value=random.choice(["A legendary member will appear.","A channel will become unexpectedly active.","The next challenge will change the leaderboard.","A forgotten role will return to glory."]),inline=False)
        e.set_footer(text="Dramatic fiction • Not a real prediction")
        await i.response.send_message(embed=e)

    # Keep optional/fun game utilities prefix-only to stay within Discord's
    # global application-command cap. Their logic is shared with the former slash callbacks.
    class _PrefixInteraction:
        def __init__(self, ctx):
            self._ctx = ctx
            self.guild = ctx.guild
            self.guild_id = ctx.guild.id if ctx.guild else None
            self.user = ctx.author
            self.response = self
        async def send_message(self, *args, **kwargs):
            kwargs.pop("ephemeral", None)
            await self._ctx.send(*args, **kwargs)

    @bot.command(name="whatif")
    async def prefix_whatif(ctx, *, action: str):
        await whatif(_PrefixInteraction(ctx), action)

    @bot.command(name="impact")
    async def prefix_impact(ctx, *, action: str):
        await impact(_PrefixInteraction(ctx), action)

    @bot.command(name="sandbox")
    async def prefix_sandbox(ctx, *, change: str):
        await sandbox(_PrefixInteraction(ctx), change)

    @bot.command(name="blindspot")
    async def prefix_blindspot(ctx):
        await blindspot(_PrefixInteraction(ctx))

    @bot.command(name="sequence")
    async def prefix_sequence(ctx, *, actions: str):
        await sequence(_PrefixInteraction(ctx), actions)

    @bot.command(name="roast")
    async def prefix_roast(ctx, member: discord.Member):
        await roast(_PrefixInteraction(ctx), member)

    @bot.command(name="ship")
    async def prefix_ship(ctx, first: discord.Member, second: discord.Member):
        await ship(_PrefixInteraction(ctx), first, second)

    @bot.command(name="chaos")
    async def prefix_chaos(ctx):
        await chaos(_PrefixInteraction(ctx))

    @bot.command(name="bounty")
    async def prefix_bounty(ctx, member: discord.Member, reward: int = 100, *, challenge: str):
        await bounty(_PrefixInteraction(ctx), member, challenge, reward)

    @bot.command(name="duel")
    async def prefix_duel(ctx, first: discord.Member, second: discord.Member):
        await duel(_PrefixInteraction(ctx), first, second)

    @bot.command(name="liecheck")
    async def prefix_liecheck(ctx, *, statement: str):
        await liecheck(_PrefixInteraction(ctx), statement)

    @bot.command(name="plot")
    async def prefix_plot(ctx):
        await plot(_PrefixInteraction(ctx))

    @bot.command(name="clone")
    async def prefix_clone(ctx, member: discord.Member):
        await clone(_PrefixInteraction(ctx), member)

    @bot.command(name="wanted")
    async def prefix_wanted(ctx, member: discord.Member):
        await wanted(_PrefixInteraction(ctx), member)

    @bot.command(name="fortune")
    async def prefix_fortune(ctx):
        await fortune(_PrefixInteraction(ctx))

    @bot.command(name="rival")
    async def prefix_rival(ctx, first: discord.Member, second: discord.Member):
        await rival(_PrefixInteraction(ctx), first, second)

    @bot.command(name="mission")
    async def prefix_mission(ctx):
        await mission(_PrefixInteraction(ctx))

    @bot.command(name="roulette")
    async def prefix_roulette(ctx):
        await roulette(_PrefixInteraction(ctx))

    @bot.command(name="achievement")
    async def prefix_achievement(ctx):
        await achievement(_PrefixInteraction(ctx))

    @bot.command(name="oracle")
    async def prefix_oracle(ctx):
        await oracle(_PrefixInteraction(ctx))

    games={
      "heist":("Heist 🏦","Build a crew, choose roles, and roll for a fictional heist outcome."),
      "kingdom":("Kingdom 👑","Build your virtual kingdom with resources, territory and upgrades."),
      "assassin":("Assassin 🥷","Join a fictional secret-target game and earn points through missions."),
      "blackmarket":("BlackMarket 🏪","Trade fictional items whose prices fluctuate with server activity."),
      "escape":("Escape Room 🔐","Solve fictional clues and puzzles to escape."),
      "outbreak":("Outbreak 🧟","Survive fictional rounds by managing resources."),
      "conquest":("Conquest 🗺️","Teams compete for fictional territories."),
      "treasure":("Treasure Hunt 🗺️","Discover fictional clues across server locations."),
      "arena":("Arena ⚔️","Create stats and fight turn-based fictional battles."),
      "casino":("Casino 🎲","Play fictional coin games with no real-money value."),
      "detective":("Detective 🕵️","Combine fictional clues and suspects to solve a case."),
      "zombie":("Zombie Survival 🧟","Choose a survivor class and face fictional zombie waves."),
      "race":("Virtual Race 🏁","Race with random events and obstacles."),
      "pirate":("Pirate Crew 🏴‍☠️","Build a crew, upgrade a ship and hunt fictional treasure."),
      "dungeon":("Dungeon 🏰","Multiplayer adventure with classes, loot, enemies and bosses.")
    }
    def make_prefix_game(_title, _desc):
        async def prefix_game(ctx):
            e=embed(_title,_desc,discord.Color.blurple())
            e.add_field(name="🎮 Status",value="Game module initialized — ready for the next turn.",inline=False)
            e.add_field(name="🪙 Economy",value="Virtual points only; no real-money value.",inline=False)
            e.set_footer(text="AirCommander Games • Friendly fictional gameplay")
            await ctx.send(embed=e)
        return prefix_game

    # These 15 game launch/info commands are prefix-only to free global
    # application-command slots for essential feature groups.
    for name,(title,desc) in games.items():
        bot.command(name=name)(make_prefix_game(title, desc))


    # ============================================================
    # AIR COMMANDER ARCADE — PREFIX GAME BROWSER + MINI-GAMES
    # Prefix only: ,games / ,game / ,xo / ,rps / ,trivia / ,mafia
    # ============================================================

    ARCADE_GAMES = {
        "xo": ("Tic-Tac-Toe (XO)", "⚔️ Multiplayer", ",xo @user", "Challenge a member to a live 3x3 XO match using buttons."),
        "mafia": ("Mafia", "🎭 Social", ",mafia", "Open a lobby, invite players, and privately deal Mafia/Town roles."),
        "rps": ("Rock Paper Scissors", "⚡ Quick Games", ",rps rock", "Play Rock Paper Scissors against Air Commander."),
        "trivia": ("Trivia Quiz", "🧠 Quiz & Puzzle", ",trivia", "Answer a multiple-choice question with buttons."),
        "guess": ("Guess the Number", "🧠 Quiz & Puzzle", ",guess", "Start a number round, then guess using ,guess 42."),
        "country": ("Guess the Country", "🌍 Multiplayer Quiz", ",country", "Join a 30-second lobby, then identify the country from its flag with other players."),
        "wordle": ("Wordle", "🧠 Quiz & Puzzle", ",wordle", "Start a five-letter puzzle, then submit ,wordle crane."),
        "hangman": ("Hangman", "🧠 Quiz & Puzzle", ",hangman", "Start a word round, then guess letters using ,hangman a."),
        "heist": ("Heist", "🌍 Adventure", ",heist", "Open the existing fictional heist game entry point."),
        "kingdom": ("Kingdom", "🌍 Adventure", ",kingdom", "Open the existing kingdom game entry point."),
        "assassin": ("Assassin", "🌍 Adventure", ",assassin", "Open the existing fictional assassin game entry point."),
        "blackmarket": ("Black Market", "🌍 Adventure", ",blackmarket", "Open the existing fictional trading game entry point."),
        "escape": ("Escape Room", "🧠 Quiz & Puzzle", ",escape", "Open the existing escape-room game entry point."),
        "outbreak": ("Outbreak", "🌍 Adventure", ",outbreak", "Open the existing survival game entry point."),
        "conquest": ("Conquest", "🌍 Adventure", ",conquest", "Open the existing territory game entry point."),
        "treasure": ("Treasure Hunt", "🌍 Adventure", ",treasure", "Open the existing treasure-hunt entry point."),
        "arena": ("Arena", "⚔️ Multiplayer", ",arena", "Open the existing arena game entry point."),
        "detective": ("Detective", "🧠 Quiz & Puzzle", ",detective", "Open the existing detective game entry point."),
        "zombie": ("Zombie Survival", "🌍 Adventure", ",zombie", "Open the existing zombie-survival entry point."),
        "race": ("Virtual Race", "⚡ Quick Games", ",race", "Open the existing virtual race entry point."),
        "pirate": ("Pirate Crew", "🌍 Adventure", ",pirate", "Open the existing pirate-adventure entry point."),
        "dungeon": ("Dungeon", "🌍 Adventure", ",dungeon", "Open the existing dungeon-adventure entry point."),
        "duel": ("Duel", "⚔️ Multiplayer", ",duel @member1 @member2", "Run a friendly fictional duel between two members."),
        "roast": ("Friendly Roast", "🎉 Social & Fun", ",roast @user", "Generate a playful, non-serious roast."),
    }

    def _arcade_embed(title, description="", color=None):
        e = discord.Embed(
            title=f"✈️ Air Commander Arcade • {title}",
            description=description,
            color=color or discord.Color.blurple(),
            timestamp=discord.utils.utcnow(),
        )
        e.set_footer(text="Air Commander • Prefix games • Use ,games to return")
        return e

    def arcade_home_embed():
        e = _arcade_embed(
            "Game Library 🎮",
            "Choose a game from the dropdown to see its exact prefix command and usage.\n\n"
            "⚔️ **Multiplayer:** XO, Duel, Guess the Country\n"
            "🧠 **Quiz & Puzzle:** Trivia, Guess the Number, Guess the Country, Wordle, Hangman, Escape Room, Detective\n"
            "⚡ **Quick Games:** Rock Paper Scissors, Race\n"
            "🎭 **Social & Fun:** Mafia, Friendly Roast\n"
            "🌍 **Adventure:** Heist, Kingdom, Assassin, Black Market, Outbreak, Conquest, Treasure Hunt, Arena, Zombie, Pirate Crew, Dungeon"
        )
        e.add_field(name="Prefix", value="All commands use a comma. Example: ,xo @user", inline=False)
        return e

    class ArcadeGameDetailsView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)

        @discord.ui.button(label="Back to Games", emoji="🎮", style=discord.ButtonStyle.primary)
        async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
            await interaction.response.edit_message(embed=arcade_home_embed(), view=ArcadeGameBrowserView())

    class ArcadeGameSelect(discord.ui.Select):
        def __init__(self):
            options = [
                discord.SelectOption(
                    label=data[0][:100],
                    value=key,
                    description=f"{data[1]} • {data[2]}"[:100],
                    emoji="🎮",
                )
                for key, data in ARCADE_GAMES.items()
            ]
            super().__init__(
                placeholder="🎮 Select a game to see its command...",
                min_values=1,
                max_values=1,
                options=options[:25],
                custom_id="aircommander:arcade:game-select",
            )

        async def callback(self, interaction: discord.Interaction):
            name, category, command_text, description = ARCADE_GAMES[self.values[0]]
            e = _arcade_embed(name, description, discord.Color.green())
            e.add_field(name="Category", value=category, inline=True)
            e.add_field(name="Command", value=command_text, inline=False)
            e.add_field(name="How to use", value=f"Type {command_text} in this server.", inline=False)
            await interaction.response.edit_message(embed=e, view=ArcadeGameDetailsView())

    class ArcadeGameBrowserView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)
            self.add_item(ArcadeGameSelect())

        async def on_timeout(self):
            for item in self.children:
                item.disabled = True

    @bot.command(name="games", aliases=["game"])
    @commands.guild_only()
    async def arcade_games(ctx):
        """Show the interactive prefix-game browser."""
        await ctx.send(embed=arcade_home_embed(), view=ArcadeGameBrowserView())

    # ----------------------------- XO -----------------------------
    def _xo_winner(board):
        lines = ((0,1,2),(3,4,5),(6,7,8),(0,3,6),(1,4,7),(2,5,8),(0,4,8),(2,4,6))
        for a, b, c in lines:
            if board[a] and board[a] == board[b] == board[c]:
                return board[a]
        return None

    def _xo_board_text(board):
        symbols = [v if v else str(i + 1) for i, v in enumerate(board)]
        return "\n".join("  ".join(symbols[start:start + 3]) for start in (0, 3, 6))

    class XOCell(discord.ui.Button):
        def __init__(self, index):
            super().__init__(label=str(index + 1), style=discord.ButtonStyle.secondary, row=index // 3)
            self.index = index

        async def callback(self, interaction: discord.Interaction):
            await self.view.play_move(interaction, self.index)

    class XOView(discord.ui.View):
        def __init__(self, player_x, player_o):
            super().__init__(timeout=180)
            self.players = {"X": player_x, "O": player_o}
            self.board = [""] * 9
            self.turn = "X"
            for idx in range(9):
                self.add_item(XOCell(idx))

        async def play_move(self, interaction, index):
            if interaction.user.id not in self.players.values():
                return await interaction.response.send_message("This match is not yours.", ephemeral=True)
            if interaction.user.id != self.players[self.turn]:
                return await interaction.response.send_message("Wait for your turn.", ephemeral=True)
            if self.board[index]:
                return await interaction.response.send_message("That square is already taken.", ephemeral=True)

            self.board[index] = self.turn
            winner = _xo_winner(self.board)
            draw = not winner and all(self.board)
            for item in self.children:
                if isinstance(item, XOCell):
                    item.label = self.board[item.index] or str(item.index + 1)
                    item.disabled = bool(winner or draw or self.board[item.index])
                    item.style = (
                        discord.ButtonStyle.success if self.board[item.index] == "X"
                        else discord.ButtonStyle.danger if self.board[item.index] == "O"
                        else discord.ButtonStyle.secondary
                    )

            if winner:
                e = _arcade_embed("XO • Match Over 🏆", f"<@{self.players[winner]}> wins!\n\n{_xo_board_text(self.board)}", discord.Color.green())
                self.stop()
            elif draw:
                e = _arcade_embed("XO • Draw 🤝", f"It's a draw!\n\n{_xo_board_text(self.board)}", discord.Color.gold())
                self.stop()
            else:
                self.turn = "O" if self.turn == "X" else "X"
                e = _arcade_embed("Tic-Tac-Toe (XO)", f"X: <@{self.players['X']}>\nO: <@{self.players['O']}>\nTurn: <@{self.players[self.turn]}>\n\n{_xo_board_text(self.board)}")
            await interaction.response.edit_message(embed=e, view=None if winner or draw else self)

    @bot.command(name="xo")
    @commands.guild_only()
    async def arcade_xo(ctx, opponent: discord.Member):
        if opponent.bot or opponent.id == ctx.author.id:
            return await ctx.send("You cannot challenge yourself or a bot to XO.")
        view = XOView(ctx.author.id, opponent.id)
        e = _arcade_embed("Tic-Tac-Toe Challenge ❎", f"{ctx.author.mention} (X) vs {opponent.mention} (O)\nFirst turn: {ctx.author.mention}\n\n{_xo_board_text(view.board)}")
        await ctx.send(embed=e, view=view)

    # ------------------------ Rock Paper Scissors -------------------
    @bot.command(name="rps", aliases=["rockpaperscissors"])
    async def arcade_rps(ctx, choice: str = None):
        choices = {"rock": "🪨", "paper": "📄", "scissors": "✂️"}
        if choice is None:
            return await ctx.send("Choose one: ,rps rock, ,rps paper, or ,rps scissors.")
        choice = choice.lower().strip()
        if choice not in choices:
            return await ctx.send("Choose rock, paper, or scissors.")
        bot_choice = random.choice(list(choices))
        if choice == bot_choice:
            result, color = "It's a draw 🤝", discord.Color.gold()
        elif (choice, bot_choice) in {("rock","scissors"),("paper","rock"),("scissors","paper")}:
            result, color = f"You win, {ctx.author.mention}! 🏆", discord.Color.green()
        else:
            result, color = "Air Commander wins this round 🤖", discord.Color.red()
        await ctx.send(embed=_arcade_embed("Rock Paper Scissors", f"You: {choices[choice]} {choice.title()}\nBot: {choices[bot_choice]} {bot_choice.title()}\n\n{result}", color))

    # ------------------------------ Trivia --------------------------
    TRIVIA_QUESTIONS = [
        ("Which planet is known as the Red Planet?", ["Venus","Mars","Jupiter","Mercury"], 1),
        ("How many sides does a hexagon have?", ["Five","Six","Seven","Eight"], 1),
        ("What is the largest ocean on Earth?", ["Atlantic","Indian","Arctic","Pacific"], 3),
        ("Which gas do plants absorb?", ["Oxygen","Nitrogen","Carbon dioxide","Helium"], 2),
        ("What is the capital of Japan?", ["Seoul","Tokyo","Beijing","Bangkok"], 1),
        ("How many minutes are in two hours?", ["60","90","120","180"], 2),
    ]

    class TriviaView(discord.ui.View):
        def __init__(self, options, answer, author_id):
            super().__init__(timeout=45)
            self.answer = answer
            self.author_id = author_id
            for idx, option in enumerate(options):
                button = discord.ui.Button(label=option, style=discord.ButtonStyle.primary, row=idx // 2)
                button.callback = self.make_callback(idx)
                self.add_item(button)

        def make_callback(self, idx):
            async def callback(interaction):
                if interaction.user.id != self.author_id:
                    return await interaction.response.send_message("This trivia round belongs to another player.", ephemeral=True)
                for item in self.children:
                    item.disabled = True
                    if isinstance(item, discord.ui.Button) and item.label == self.children[self.answer].label:
                        item.style = discord.ButtonStyle.success
                correct = idx == self.answer
                e = _arcade_embed("Trivia Result", ("Correct answer! 🏆" if correct else "Not quite!") + f"\nAnswer: {self.children[self.answer].label}", discord.Color.green() if correct else discord.Color.orange())
                await interaction.response.edit_message(embed=e, view=self)
                self.stop()
            return callback

    @bot.command(name="trivia", aliases=["quiz"])
    @commands.guild_only()
    async def arcade_trivia(ctx):
        question, options, answer = random.choice(TRIVIA_QUESTIONS)
        await ctx.send(embed=_arcade_embed("Trivia Quiz 🧠", question + "\n\nChoose an answer below. You have 45 seconds."), view=TriviaView(options, answer, ctx.author.id))

    # -------------------------- Guess the Country -------------------
    COUNTRY_QUESTIONS = [
        ("🇯🇵", "Japan", ["Japan", "South Korea", "China", "Thailand"]),
        ("🇧🇷", "Brazil", ["Brazil", "Portugal", "Argentina", "Mexico"]),
        ("🇨🇦", "Canada", ["Canada", "United States", "Australia", "United Kingdom"]),
        ("🇮🇳", "India", ["India", "Pakistan", "Bangladesh", "Nepal"]),
        ("🇫🇷", "France", ["France", "Italy", "Belgium", "Spain"]),
        ("🇦🇺", "Australia", ["Australia", "New Zealand", "United Kingdom", "South Africa"]),
        ("🇪🇬", "Egypt", ["Egypt", "Morocco", "Algeria", "Turkey"]),
        ("🇰🇪", "Kenya", ["Kenya", "Nigeria", "Ghana", "Ethiopia"]),
        ("🇳🇴", "Norway", ["Norway", "Sweden", "Finland", "Denmark"]),
        ("🇲🇽", "Mexico", ["Mexico", "Brazil", "Chile", "Peru"]),
        ("🇬🇷", "Greece", ["Greece", "Italy", "Cyprus", "Turkey"]),
        ("🇸🇬", "Singapore", ["Singapore", "Malaysia", "Indonesia", "Philippines"]),
    ]

    class CountryAnswerView(discord.ui.View):
        def __init__(self, players, flag, answer, options):
            super().__init__(timeout=30)
            self.players = set(players)
            self.answer = answer
            self.finished = False
            random.shuffle(options)
            for option in options:
                button = discord.ui.Button(label=option, style=discord.ButtonStyle.primary)
                button.callback = self.make_callback(option)
                self.add_item(button)

        def make_callback(self, option):
            async def callback(interaction):
                if self.finished:
                    return await interaction.response.send_message("This country round has ended.", ephemeral=True)
                if interaction.user.id not in self.players:
                    return await interaction.response.send_message("Join the lobby before answering.", ephemeral=True)
                if option != self.answer:
                    return await interaction.response.send_message("❌ Not quite! Try another option.", ephemeral=True)
                self.finished = True
                for item in self.children:
                    item.disabled = True
                    if item.label == self.answer:
                        item.style = discord.ButtonStyle.success
                e = _arcade_embed(
                    "Guess the Country • Winner 🏆",
                    f"{interaction.user.mention} guessed correctly! The answer was **{self.answer}**.",
                    discord.Color.green(),
                )
                await interaction.response.edit_message(embed=e, view=self)
                self.stop()
            return callback

        async def on_timeout(self):
            if self.finished:
                return
            self.finished = True
            for item in self.children:
                item.disabled = True
            try:
                if self.message:
                    await self.message.edit(
                        embed=_arcade_embed("Guess the Country • Time's Up ⏰", f"The correct answer was **{self.answer}**.", discord.Color.orange()),
                        view=self,
                    )
            except (discord.HTTPException, AttributeError):
                pass

    class CountryLobbyView(discord.ui.View):
        def __init__(self, host):
            super().__init__(timeout=35)
            self.host = host
            self.players = {host.id: host}
            self.message = None
            self.started = False

        def lobby_embed(self, remaining=30):
            return _arcade_embed(
                "Guess the Country • Lobby 🌍",
                f"Host: {self.host.mention}\nPlayers: **{len(self.players)}** (minimum 2)\n\n"
                f"Press **Join Game**. The round starts automatically in **{remaining}s** if at least 2 players joined; otherwise it is cancelled.",
            )

        @discord.ui.button(label="Join Game", emoji="🌍", style=discord.ButtonStyle.success)
        async def join_country(self, interaction, button):
            if self.started:
                return await interaction.response.send_message("This lobby has already started.", ephemeral=True)
            if interaction.user.bot:
                return await interaction.response.send_message("Bots cannot join.", ephemeral=True)
            self.players[interaction.user.id] = interaction.user
            await interaction.response.edit_message(embed=self.lobby_embed(), view=self)

        async def countdown(self):
            for remaining in range(30, 0, -1):
                if self.started:
                    return
                try:
                    await self.message.edit(embed=self.lobby_embed(remaining), view=self)
                except discord.HTTPException:
                    return
                await asyncio.sleep(1)
            if self.started:
                return
            if len(self.players) < 2:
                self.started = True
                for item in self.children:
                    item.disabled = True
                try:
                    await self.message.edit(
                        embed=_arcade_embed("Guess the Country • Cancelled ⏰", "Only one player joined in 30 seconds. At least **2 players** are required, so this game was cancelled.", discord.Color.red()),
                        view=self,
                    )
                except discord.HTTPException:
                    pass
                self.stop()
                return
            self.started = True
            flag, answer, options = random.choice(COUNTRY_QUESTIONS)
            view = CountryAnswerView(self.players.keys(), flag, answer, options)
            e = _arcade_embed(
                "Guess the Country 🌍",
                f"**Which country does this flag belong to?**\n\n# {flag}\n\nPlayers: {len(self.players)}\nChoose the correct answer below. First correct answer wins!",
            )
            try:
                await self.message.edit(embed=e, view=view)
                view.message = self.message
            except discord.HTTPException:
                pass
            self.stop()

    @bot.command(name="country", aliases=["guesscountry", "guess-country"])
    @commands.guild_only()
    async def arcade_country(ctx):
        view = CountryLobbyView(ctx.author)
        msg = await ctx.send(embed=view.lobby_embed(), view=view)
        view.message = msg
        asyncio.create_task(view.countdown())

    # -------------------------- Guess the Number --------------------
    guess_sessions = {}

    @bot.command(name="guess")
    @commands.guild_only()
    async def arcade_guess(ctx, number: int = None):
        key = (ctx.guild.id, ctx.author.id)
        if number is None:
            guess_sessions[key] = {"secret": random.randint(1, 100), "tries": 0}
            return await ctx.send(f"{ctx.author.mention}, I picked a number from 1–100. Guess with ,guess 42.")
        session = guess_sessions.get(key)
        if not session:
            return await ctx.send("No active round. Start one with ,guess.")
        if not 1 <= number <= 100:
            return await ctx.send("Choose a number from 1 to 100.")
        session["tries"] += 1
        if number == session["secret"]:
            guess_sessions.pop(key, None)
            return await ctx.send(f"Correct, {ctx.author.mention}! You found it in {session['tries']} guess(es). Start again with ,guess.")
        await ctx.send(("Too low ⬆️" if number < session["secret"] else "Too high ⬇️") + " — try again with ,guess <number>.")

    # ------------------------------- Wordle -------------------------
    WORDLE_WORDS = ["plane","brave","crane","smile","ghost","light","storm","grape","flame","sword"]
    wordle_sessions = {}

    @bot.command(name="wordle")
    @commands.guild_only()
    async def arcade_wordle(ctx, *, guess: str = None):
        key = (ctx.guild.id, ctx.author.id)
        if guess is None:
            wordle_sessions[key] = {"word": random.choice(WORDLE_WORDS), "tries": 0}
            return await ctx.send("Wordle started! Guess a 5-letter word using ,wordle crane. You have 6 tries.")
        guess = guess.lower().strip()
        session = wordle_sessions.get(key)
        if not session:
            return await ctx.send("Start a round first with ,wordle.")
        if len(guess) != 5 or not guess.isalpha():
            return await ctx.send("Enter exactly 5 letters.")
        session["tries"] += 1
        answer = session["word"]
        marks = []
        for idx, letter in enumerate(guess):
            marks.append("🟩" if letter == answer[idx] else "🟨" if letter in answer else "⬛")
        if guess == answer:
            wordle_sessions.pop(key, None)
            return await ctx.send(f"You solved it!\n{''.join(marks)}\nAnswer: {answer.upper()}")
        if session["tries"] >= 6:
            wordle_sessions.pop(key, None)
            return await ctx.send(f"{''.join(marks)}\nRound over! The word was {answer.upper()}.")
        await ctx.send(f"{''.join(marks)}\nTry {session['tries']}/6. Use ,wordle <word>.")

    # ------------------------------- Hangman ------------------------
    HANGMAN_WORDS = ["discord","airplane","commander","galaxy","puzzle","victory","rainbow","treasure"]
    hangman_sessions = {}

    def _hangman_display(session):
        return " ".join(letter.upper() if letter in session["guessed"] else "＿" for letter in session["word"])

    @bot.command(name="hangman")
    @commands.guild_only()
    async def arcade_hangman(ctx, letter: str = None):
        key = (ctx.guild.id, ctx.author.id)
        session = hangman_sessions.get(key)
        if letter is None:
            hangman_sessions[key] = {"word": random.choice(HANGMAN_WORDS), "guessed": set(), "misses": 0}
            return await ctx.send(f"Hangman started!\n{_hangman_display(hangman_sessions[key])}\nGuess one letter using ,hangman a.")
        if not session:
            return await ctx.send("Start a round first with ,hangman.")
        letter = letter.lower().strip()
        if len(letter) != 1 or not letter.isalpha():
            return await ctx.send("Enter one letter, e.g. ,hangman a.")
        if letter in session["guessed"]:
            return await ctx.send("You already guessed that letter.")
        session["guessed"].add(letter)
        if letter not in session["word"]:
            session["misses"] += 1
        display = _hangman_display(session)
        if "＿" not in display:
            hangman_sessions.pop(key, None)
            return await ctx.send(f"You solved it!\n{display}")
        if session["misses"] >= 7:
            word = session["word"]
            hangman_sessions.pop(key, None)
            return await ctx.send(f"Round over. The word was {word.upper()}.")
        await ctx.send(f"{display}\nMisses: {session['misses']}/7 • Guessed: {', '.join(sorted(session['guessed']))}")

    # ------------------------------- Mafia --------------------------
    class MafiaLobbyView(discord.ui.View):
        def __init__(self, host):
            super().__init__(timeout=35)
            self.host = host
            self.host_id = host.id
            self.players = {host.id: host}
            self.message = None
            self.started = False

        def lobby_embed(self, remaining=30):
            mentions = "\n".join(f"• <@{uid}>" for uid in self.players) or "Nobody has joined yet."
            return _arcade_embed(
                "Mafia • Lobby 🎭",
                f"Host: <@{self.host_id}>\n\nPlayers ({len(self.players)}/12):\n{mentions}\n\n"
                f"Minimum **4 players**. Automatic start in **{remaining}s** if enough players join; otherwise cancelled.",
            )

        @discord.ui.button(label="Join Mafia", emoji="🎭", style=discord.ButtonStyle.success)
        async def join_mafia(self, interaction, button):
            if self.started:
                return await interaction.response.send_message("Lobby already started or cancelled.", ephemeral=True)
            if interaction.user.bot:
                return await interaction.response.send_message("Bots cannot join.", ephemeral=True)
            if len(self.players) >= 12 and interaction.user.id not in self.players:
                return await interaction.response.send_message("Lobby is full (12 players).", ephemeral=True)
            self.players[interaction.user.id] = interaction.user
            await interaction.response.edit_message(embed=self.lobby_embed(), view=self)

        async def deal_roles(self):
            if self.started:
                return
            self.started = True
            players = list(self.players.values())
            random.shuffle(players)
            mafia_ids = {m.id for m in players[:max(1, len(players) // 4)]}
            delivered = 0
            for member in players:
                role = "Mafia" if member.id in mafia_ids else "Town"
                try:
                    await member.send(f"Air Commander Mafia — your secret role: {role}. Keep it secret and follow the host's in-channel instructions.")
                    delivered += 1
                except (discord.Forbidden, discord.HTTPException):
                    pass
            for item in self.children:
                item.disabled = True
            e = _arcade_embed(
                "Mafia • Roles Dealt 🎭",
                f"Roles assigned to {len(players)} players. Secret-role DMs delivered: {delivered}/{len(players)}.\n\n"
                "This starter mode handles lobby and role dealing; it does not automatically run day/night phases or eliminations.",
                discord.Color.green(),
            )
            try:
                await self.message.edit(embed=e, view=self)
            except discord.HTTPException:
                pass
            self.stop()

        async def countdown(self):
            for remaining in range(30, 0, -1):
                if self.started:
                    return
                try:
                    await self.message.edit(embed=self.lobby_embed(remaining), view=self)
                except discord.HTTPException:
                    return
                await asyncio.sleep(1)
            if self.started:
                return
            if len(self.players) < 4:
                self.started = True
                for item in self.children:
                    item.disabled = True
                try:
                    await self.message.edit(
                        embed=_arcade_embed("Mafia • Cancelled ⏰", f"Only **{len(self.players)}** player(s) joined. Mafia needs at least **4 players**, so it was cancelled.", discord.Color.red()),
                        view=self,
                    )
                except discord.HTTPException:
                    pass
                self.stop()
                return
            await self.deal_roles()

    @bot.command(name="mafia")
    @commands.guild_only()
    async def arcade_mafia(ctx):
        view = MafiaLobbyView(ctx.author)
        msg = await ctx.send(embed=view.lobby_embed(), view=view)
        view.message = msg
        asyncio.create_task(view.countdown())

