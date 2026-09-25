from __future__ import annotations
import discord
from discord.ext import commands

_snipes={}

def setup(bot):
    @bot.event
    async def on_message_delete(message):
        if message.guild and not message.author.bot:
            _snipes[message.channel.id]={"author":message.author,"content":message.content,"created":message.created_at}

    if bot.get_command("snipe") is None:
        @bot.command(name="snipe")
        async def snipe_prefix(ctx):
            await send_snipe(ctx)
    if bot.tree.get_command("snipe") is None:
        @bot.tree.command(name="snipe", description="Show the most recently deleted message in this channel")
        async def snipe_slash(interaction: discord.Interaction):
            await send_snipe(interaction)

async def send_snipe(target):
    cid=target.channel.id
    data=_snipes.get(cid)
    if not data:
        msg="❌ No recently deleted message found in this channel."
    else:
        content=data["content"] or "[attachment/embed/no text]"
        e=discord.Embed(title="🕵️ Snipe", description=content[:4000], color=0x5865F2)
        e.set_author(name=data["author"].display_name, icon_url=data["author"].display_avatar.url)
        e.set_footer(text="AirMarshal Commander • Snipe")
        if isinstance(target, discord.Interaction): return await target.response.send_message(embed=e)
        return await target.send(embed=e)
    if isinstance(target, discord.Interaction): return await target.response.send_message(msg, ephemeral=True)
    return await target.send(msg)
