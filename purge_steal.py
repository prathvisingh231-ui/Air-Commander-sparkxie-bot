import io
import re
import discord
from discord import app_commands
from discord.ext import commands


def _hex_color(value: str) -> int:
    value = value.strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', value):
        raise ValueError('Invalid hex color')
    return int(value, 16)


class StealView(discord.ui.View):
    def __init__(self, source: discord.Sticker | discord.Emoji, author_id: int):
        super().__init__(timeout=60)
        self.source = source
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message('❌ Only the person who started the steal can use these buttons.', ephemeral=True)
            return False
        return True

    @discord.ui.button(label='Steal as Sticker', style=discord.ButtonStyle.primary, emoji='🎟️')
    async def sticker(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message('❌ This can only be used in a server.', ephemeral=True)
        if not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
            return await interaction.response.send_message('❌ I need **Manage Expressions** permission.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            url = self.source.url
            async with interaction.client.http._HTTPClient__session.get(url) as resp:
                data = await resp.read()
            if isinstance(self.source, discord.Emoji):
                filename = f'{self.source.name}.png'
            else:
                filename = f'{self.source.name}.png'
            sticker = await interaction.guild.create_sticker(
                name=re.sub(r'[^a-zA-Z0-9_\-]', '_', self.source.name)[:30] or 'stolen_sticker',
                description=f'Imported by {interaction.user}',
                emoji='✨',
                file=discord.File(io.BytesIO(data), filename=filename),
                reason=f'Steal requested by {interaction.user} ({interaction.user.id})',
            )
            await interaction.followup.send(f'✅ Added **{sticker.name}** as a server sticker.', ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f'❌ Discord could not add the sticker: `{e}`', ephemeral=True)

    @discord.ui.button(label='Steal as Emoji', style=discord.ButtonStyle.success, emoji='😀')
    async def emoji(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message('❌ This can only be used in a server.', ephemeral=True)
        if not interaction.guild.me.guild_permissions.manage_emojis_and_stickers:
            return await interaction.response.send_message('❌ I need **Manage Expressions** permission.', ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        try:
            async with interaction.client.http._HTTPClient__session.get(self.source.url) as resp:
                data = await resp.read()
            name = re.sub(r'[^a-zA-Z0-9_]', '_', self.source.name)[:32] or 'stolen_emoji'
            emoji = await interaction.guild.create_custom_emoji(
                name=name,
                image=data,
                reason=f'Steal requested by {interaction.user} ({interaction.user.id})',
            )
            await interaction.followup.send(f'✅ Added {emoji} to this server.', ephemeral=True)
        except discord.HTTPException as e:
            await interaction.followup.send(f'❌ Discord could not add the emoji: `{e}`', ephemeral=True)


class PurgeSteal(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name='purge', description='Bulk-delete recent messages.')
    @app_commands.describe(amount='Number of recent messages to delete (1-100).')
    @app_commands.default_permissions(manage_messages=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 100]):
        if not interaction.guild or not interaction.channel:
            return await interaction.response.send_message('❌ This command can only be used in a server.', ephemeral=True)
        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message('❌ Use this in a text channel.', ephemeral=True)
        if not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message('❌ You need **Manage Messages**.', ephemeral=True)
        if not interaction.guild.me.guild_permissions.manage_messages:
            return await interaction.response.send_message('❌ I need **Manage Messages** permission.', ephemeral=True)
        await interaction.response.defer()
        deleted = await channel.purge(limit=int(amount), reason=f'Purge requested by {interaction.user} ({interaction.user.id})')
        embed = discord.Embed(title='🧹 Messages Purged', description=f'✅ Deleted **{len(deleted)}** messages.', color=discord.Color.blurple())
        await interaction.followup.send(embed=embed, ephemeral=True)

    @app_commands.command(name='steal', description='Steal a replied sticker or emoji into this server.')
    @app_commands.default_permissions(manage_emojis_and_stickers=True)
    async def steal(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await interaction.response.send_message('❌ This command can only be used in a server.', ephemeral=True)
        if not interaction.user.guild_permissions.manage_emojis_and_stickers:
            return await interaction.response.send_message('❌ You need **Manage Expressions**.', ephemeral=True)
        ref = interaction.message.reference if interaction.message else None
        message = None
        if ref and ref.resolved:
            message = ref.resolved if isinstance(ref.resolved, discord.Message) else None
        source = None
        if message:
            if message.stickers:
                source = message.stickers[0]
            elif message.content:
                match = re.search(r'<a?:([A-Za-z0-9_]+):(\d+)>', message.content)
                if match:
                    source = discord.PartialEmoji(name=match.group(1), id=int(match.group(2)), animated=message.content[1] == 'a')
        if source is None:
            return await interaction.response.send_message('❌ Reply to a message containing a sticker or custom emoji, then use `/steal`.', ephemeral=True)
        if isinstance(source, discord.PartialEmoji):
            source.url = f'https://cdn.discordapp.com/emojis/{source.id}.{"gif" if source.animated else "png"}'
        embed = discord.Embed(title='✨ Steal Expression', description=f'Choose how to import **{source.name}**.', color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, view=StealView(source, interaction.user.id), ephemeral=True)


def setup(bot):
    bot.add_cog(PurgeSteal(bot))
