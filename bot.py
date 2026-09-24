
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
