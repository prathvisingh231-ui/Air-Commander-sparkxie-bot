import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import time


def embed(title, description="", color=discord.Color.blurple()):
    e = discord.Embed(title=f"✈️ {title}", description=description, color=color, timestamp=discord.utils.utcnow())
    e.set_footer(text="Air Commander • Clean control center")
    return e


def setup(bot: commands.Bot):
    @bot.tree.command(name="clear", description="Delete recent messages")
    @app_commands.describe(amount="Number of messages to delete (1-100)")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def clear(i: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        if not isinstance(i.channel, discord.TextChannel):
            return await i.response.send_message("❌ This command works in text channels only.", ephemeral=True)
        await i.response.defer(ephemeral=True)
        deleted = await i.channel.purge(limit=amount)
        e = embed("Messages Cleared", f"Removed **{len(deleted)}** message(s) from {i.channel.mention}.", discord.Color.orange())
        await i.followup.send(embed=e, ephemeral=True)

    @bot.tree.command(name="kick", description="Kick a member")
    @app_commands.describe(member="Member to kick", reason="Reason for the action")
    @app_commands.checks.has_permissions(kick_members=True)
    async def kick(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        if member == i.user or member.top_role >= i.user.top_role or member.top_role >= i.guild.me.top_role:
            return await i.response.send_message("❌ That member cannot be kicked due to role hierarchy.", ephemeral=True)
        await member.kick(reason=f"{reason} | Moderator: {i.user}")
        e = embed("Member Kicked", f"{member.mention} was removed from the server.", discord.Color.red())
        e.add_field(name="Moderator", value=i.user.mention)
        e.add_field(name="Reason", value=reason[:1024])
        await i.response.send_message(embed=e)

    @bot.tree.command(name="ban", description="Ban a member")
    @app_commands.describe(member="Member to ban", reason="Reason for the action", delete_days="Delete message history in days (0-7)")
    @app_commands.checks.has_permissions(ban_members=True)
    async def ban(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided", delete_days: app_commands.Range[int, 0, 7] = 0):
        if member == i.user or member.top_role >= i.user.top_role or member.top_role >= i.guild.me.top_role:
            return await i.response.send_message("❌ That member cannot be banned due to role hierarchy.", ephemeral=True)
        await member.ban(reason=f"{reason} | Moderator: {i.user}", delete_message_days=delete_days)
        e = embed("Member Banned", f"{member.mention} was banned from the server.", discord.Color.red())
        e.add_field(name="Moderator", value=i.user.mention)
        e.add_field(name="Reason", value=reason[:1024])
        await i.response.send_message(embed=e)

    @bot.tree.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="Discord user ID", reason="Reason for the action")
    @app_commands.checks.has_permissions(ban_members=True)
    async def unban(i: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        try:
            uid = int(user_id)
            await i.guild.unban(discord.Object(id=uid), reason=f"{reason} | Moderator: {i.user}")
        except (ValueError, discord.NotFound):
            return await i.response.send_message("❌ No matching banned user was found.", ephemeral=True)
        e = embed("Member Unbanned", f"User ID **{uid}** is no longer banned.", discord.Color.green())
        e.add_field(name="Moderator", value=i.user.mention)
        e.add_field(name="Reason", value=reason[:1024])
        await i.response.send_message(embed=e)

    @bot.tree.command(name="timeout", description="Timeout a member")
    @app_commands.describe(member="Member to timeout", minutes="Timeout duration in minutes", reason="Reason")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def timeout(i: discord.Interaction, member: discord.Member, minutes: app_commands.Range[int, 1, 40320], reason: str = "No reason provided"):
        if member == i.user or member.top_role >= i.user.top_role or member.top_role >= i.guild.me.top_role:
            return await i.response.send_message("❌ That member cannot be timed out due to role hierarchy.", ephemeral=True)
        await member.timeout(timedelta(minutes=minutes), reason=f"{reason} | Moderator: {i.user}")
        e = embed("Member Timed Out", f"{member.mention} is timed out for **{minutes} minute(s)**.", discord.Color.orange())
        e.add_field(name="Moderator", value=i.user.mention)
        e.add_field(name="Reason", value=reason[:1024])
        await i.response.send_message(embed=e)

    @bot.tree.command(name="untimeout", description="Remove a member timeout")
    @app_commands.describe(member="Member to untimeout", reason="Reason")
    @app_commands.checks.has_permissions(moderate_members=True)
    async def untimeout(i: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        await member.timeout(None, reason=f"{reason} | Moderator: {i.user}")
        e = embed("Timeout Removed", f"Timeout removed from {member.mention}.", discord.Color.green())
        e.add_field(name="Moderator", value=i.user.mention)
        e.add_field(name="Reason", value=reason[:1024])
        await i.response.send_message(embed=e)

    @bot.tree.command(name="slowmode", description="Set channel slowmode")
    @app_commands.describe(seconds="Slowmode seconds (0 disables it)")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def slowmode(i: discord.Interaction, seconds: app_commands.Range[int, 0, 21600]):
        if not hasattr(i.channel, "edit"):
            return await i.response.send_message("❌ This channel cannot use slowmode.", ephemeral=True)
        await i.channel.edit(slowmode_delay=seconds, reason=f"Changed by {i.user}")
        e = embed("Slowmode Updated", f"{i.channel.mention} slowmode is now **{seconds}s**.", discord.Color.teal())
        await i.response.send_message(embed=e)

    async def set_lock(i, locked):
        if not isinstance(i.channel, discord.TextChannel):
            return await i.response.send_message("❌ Text channel only.", ephemeral=True)
        overwrite = i.channel.overwrites_for(i.guild.default_role)
        overwrite.send_messages = False if locked else None
        await i.channel.set_permissions(i.guild.default_role, overwrite=overwrite, reason=f"Channel {'locked' if locked else 'unlocked'} by {i.user}")
        e = embed("Channel Locked" if locked else "Channel Unlocked", f"{i.channel.mention} is now **{'locked' if locked else 'open'}** for @everyone.", discord.Color.red() if locked else discord.Color.green())
        await i.response.send_message(embed=e)

    @bot.tree.command(name="lock", description="Lock the current text channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def lock(i: discord.Interaction): await set_lock(i, True)

    @bot.tree.command(name="unlock", description="Unlock the current text channel")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def unlock(i: discord.Interaction): await set_lock(i, False)

    @bot.tree.command(name="nick", description="Change a member nickname")
    @app_commands.describe(member="Member", nickname="New nickname")
    @app_commands.checks.has_permissions(manage_nicknames=True)
    async def nick(i: discord.Interaction, member: discord.Member, nickname: str | None = None):
        await member.edit(nick=nickname, reason=f"Nickname changed by {i.user}")
        e = embed("Nickname Updated", f"Updated nickname for {member.mention}.", discord.Color.blurple())
        e.add_field(name="New Nickname", value=nickname or "Reset to username")
        await i.response.send_message(embed=e)

    @bot.tree.command(name="role", description="Add or remove a role from a member")
    @app_commands.describe(action="Add or remove", member="Member", role="Role")
    @app_commands.choices(action=[app_commands.Choice(name="Add", value="add"), app_commands.Choice(name="Remove", value="remove")])
    @app_commands.checks.has_permissions(manage_roles=True)
    async def role(i: discord.Interaction, action: app_commands.Choice[str], member: discord.Member, role: discord.Role):
        if role.is_default() or role >= i.guild.me.top_role:
            return await i.response.send_message("❌ I cannot manage that role because of role hierarchy.", ephemeral=True)
        if action.value == "add": await member.add_roles(role, reason=f"Role added by {i.user}")
        else: await member.remove_roles(role, reason=f"Role removed by {i.user}")
        e = embed("Role Updated", f"{role.mention} was **{action.name.lower()}** for {member.mention}.", discord.Color.green())
        await i.response.send_message(embed=e)

    @bot.tree.command(name="say", description="Make Air Commander send a message")
    @app_commands.describe(message="Message to send")
    @app_commands.checks.has_permissions(manage_messages=True)
    async def say(i: discord.Interaction, message: str):
        await i.response.send_message(embed=embed("Message Sent", f"{message}", discord.Color.blurple()))

    @bot.tree.command(name="announce", description="Send a styled announcement")
    @app_commands.describe(message="Announcement text")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def announce(i: discord.Interaction, message: str):
        e = embed("Announcement", message, discord.Color.gold())
        e.set_author(name=i.guild.name, icon_url=i.guild.icon.url if i.guild.icon else discord.Embed.Empty)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="poll", description="Create a simple yes/no poll")
    @app_commands.describe(question="Poll question")
    async def poll(i: discord.Interaction, question: str):
        e = embed("Community Poll", question, discord.Color.blurple())
        e.add_field(name="Vote", value="👍 Yes\n👎 No", inline=False)
        await i.response.send_message(embed=e)
        msg = await i.original_response()
        await msg.add_reaction("👍"); await msg.add_reaction("👎")

    @bot.tree.command(name="servericon", description="Show the server icon")
    async def servericon(i: discord.Interaction):
        if not i.guild.icon: return await i.response.send_message("This server has no icon.", ephemeral=True)
        e = embed(f"{i.guild.name} • Server Icon")
        e.set_image(url=i.guild.icon.replace(size=1024).url)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="banner", description="Show the server banner")
    async def banner(i: discord.Interaction):
        if not i.guild.banner: return await i.response.send_message("This server has no banner.", ephemeral=True)
        e = embed(f"{i.guild.name} • Server Banner")
        e.set_image(url=i.guild.banner.replace(size=1024).url)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="membercount", description="Show server member counts")
    async def membercount(i: discord.Interaction):
        g=i.guild; bots=sum(1 for m in g.members if m.bot)
        e=embed("Member Count", f"Live member breakdown for **{g.name}**.")
        e.add_field(name="Total", value=str(g.member_count), inline=True); e.add_field(name="Humans", value=str(g.member_count-bots), inline=True); e.add_field(name="Bots", value=str(bots), inline=True)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="channelinfo", description="Show channel information")
    @app_commands.describe(channel="Channel to inspect")
    async def channelinfo(i: discord.Interaction, channel: discord.abc.GuildChannel | None = None):
        c=channel or i.channel
        e=embed(f"Channel Info • {c.name}")
        e.add_field(name="ID", value=str(c.id), inline=True); e.add_field(name="Type", value=str(c.type), inline=True); e.add_field(name="Category", value=c.category.name if c.category else "None", inline=True)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="roleinfo", description="Show role information")
    @app_commands.describe(role="Role to inspect")
    async def roleinfo(i: discord.Interaction, role: discord.Role):
        e=embed(f"Role Info • {role.name}")
        e.add_field(name="ID", value=str(role.id), inline=True); e.add_field(name="Members", value=str(len(role.members)), inline=True); e.add_field(name="Position", value=str(role.position), inline=True)
        e.add_field(name="Mentionable", value="Yes" if role.mentionable else "No", inline=True); e.add_field(name="Managed", value="Yes" if role.managed else "No", inline=True)
        await i.response.send_message(embed=e)

    @bot.tree.command(name="botinfo", description="Show Air Commander status")
    async def botinfo(i: discord.Interaction):
        uptime=int(time.time()-bot._air_start_time) if hasattr(bot,"_air_start_time") else 0
        e=embed("Air Commander • System Status", "Clean, fast and ready.", discord.Color.blurple())
        e.add_field(name="Servers", value=str(len(bot.guilds)), inline=True); e.add_field(name="Latency", value=f"{round(bot.latency*1000)} ms", inline=True); e.add_field(name="Uptime", value=f"{uptime//3600}h {(uptime%3600)//60}m", inline=True)
        await i.response.send_message(embed=e)

    @bot.tree.error
    async def on_app_command_error(i: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.MissingPermissions):
            msg = "❌ You don't have the required permission for this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            msg = "❌ I don't have the required Discord permission to do that."
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = "⏳ Please wait before using that command again."
        else:
            print(f"Basic command error: {type(error).__name__}: {error}")
            msg = "❌ Something went wrong while running that command."
        if i.response.is_done(): await i.followup.send(msg, ephemeral=True)
        else: await i.response.send_message(msg, ephemeral=True)
