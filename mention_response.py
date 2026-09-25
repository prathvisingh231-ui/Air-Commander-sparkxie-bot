from __future__ import annotations
import time, math, random, json, re
from datetime import datetime, timezone
import discord
from discord.ext import commands

TITLE='🤖 AirMarshal Mention'
KEY='mention_response'

def _embed(desc, color=0x5865F2):
    e=discord.Embed(title=TITLE, description=desc, color=color)
    e.set_footer(text="AirMarshal Commander • Air Commander")
    return e

def setup(bot):
    # Commands are intentionally unique; existing moderation/utility commands are retained.
    if bot.get_command('mentionreply') is None:
        @bot.command(name='mentionreply')
        async def _prefix(ctx, *, value: str = ""):
            await _run(ctx, value)
    if bot.tree.get_command('mentionreply') is None:
        @bot.tree.command(name='mentionreply', description='AirMarshal Commander branded mention response.')
        async def _slash(interaction: discord.Interaction, value: str = ""):
            await _run(interaction, value)

async def _run(target, value=""):
    send = target.response.send_message if isinstance(target, discord.Interaction) else target.send
    if isinstance(target, discord.Interaction) and target.response.is_done():
        send = target.followup.send
    await send(embed=_embed('**AirMarshal Commander branded mention response.**\\n\\nConfiguration input: `{value}`\\n\\nUse this command as the control point for the module. Existing Air Commander commands are preserved.'.format(value=value)))
