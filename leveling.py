        )

        user = user_data(
            config,
            member.id
        )

        stats = get_message_stats(
            user
        )

        embed = discord.Embed(
            title=(
                f"💬 {member.display_name}'s "
                f"Message Stats"
            ),
            description=(
                f"{member.mention}\n\n"
                f"📅 **Today**\n"
                f"`{stats['today']:,}` messages\n\n"
                f"📆 **Week**\n"
                f"`{stats['week']:,}` messages\n\n"
                f"🗓️ **Month**\n"
                f"`{stats['month']:,}` messages\n\n"
                f"💬 **All Time**\n"
                f"`{stats['all']:,}` messages"
            ),
            color=discord.Color.blurple()
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.set_footer(
            text="Air Commander • Message Statistics"
        )

        await ctx.send(
            embed=embed
        )

    # ========================================================
    # MESSAGE COUNT — SLASH
    #
    # /message
    # ========================================================

    @app_commands.command(
        name="message",
        description="View message statistics"
    )
    @app_commands.describe(
        member="Member whose message statistics you want to see"
    )
    async def slash_message(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None
    ):

        if not interaction.guild:

            await interaction.response.send_message(
                "This command can only be used inside a server.",
                ephemeral=True
            )
            return

        member = (
            member
            or interaction.user
        )

        config = guild_config(
            interaction.guild.id
        )

        user = user_data(
            config,
            member.id
        )

        stats = get_message_stats(
            user
        )

        embed = discord.Embed(
            title=(
                f"💬 {member.display_name}'s "
                f"Message Stats"
            ),
            description=(
                f"{member.mention}\n\n"
                f"📅 **Today** — "
                f"`{stats['today']:,}`\n"
                f"📆 **Week** — "
                f"`{stats['week']:,}`\n"
                f"🗓️ **Month** — "
                f"`{stats['month']:,}`\n"
                f"💬 **All Time** — "
                f"`{stats['all']:,}`"
            ),
            color=discord.Color.blurple()
        )

        embed.set_thumbnail(
            url=member.display_avatar.url
        )

        embed.set_footer(
            text="Air Commander • Message Statistics"
        )

        await interaction.response.send_message(
            embed=embed
        )


# ============================================================
# SETUP
# ============================================================

async def setup(bot):

    await bot.add_cog(
        AirLeveling(bot)
    )
