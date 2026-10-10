                    f"Ends: {_timestamp(_row_value(row, 'ends_at'))}"
                ),
                inline=False,
            )
        embed.set_footer(text=BRAND)
        await ctx.send(embed=embed)

    @giveaway.command(name="end", description="End a giveaway and draw winners now")
    @app_commands.describe(giveaway_id="ID shown in the giveaway embed")
    async def giveaway_end(self, ctx: commands.Context, giveaway_id: int):
        if not await self._require_manager(ctx):
            return
        row = await self._fetch_giveaway(giveaway_id)
        if not row or int(_row_value(row, "guild_id", 0)) != ctx.guild.id:
            await ctx.send("❌ I couldn't find that giveaway in this server.")
            return
        if _row_value(row, "status", "active") != "active":
            await ctx.send("That giveaway is not active.")
            return
        success = await self.finish_giveaway(giveaway_id, force=True)
        await ctx.send("🏁 Giveaway ended." if success else "❌ Couldn't end the giveaway. Check the logs.")

    @giveaway.command(name="reroll", description="Reroll winner(s) for an ended giveaway")
    @app_commands.describe(giveaway_id="ID shown in the giveaway embed", winners="Number of replacement winners")
    async def giveaway_reroll(
        self,
        ctx: commands.Context,
        giveaway_id: int,
        winners: app_commands.Range[int, 1, 20] = 1,
    ):
        if not await self._require_manager(ctx):
            return
        row = await self._fetch_giveaway(giveaway_id)
        if not row or int(_row_value(row, "guild_id", 0)) != ctx.guild.id:
            await ctx.send("❌ I couldn't find that giveaway in this server.")
            return
        if _row_value(row, "status", "active") != "ended":
            await ctx.send("You can only reroll an **ended** giveaway.")
            return
        old_winners = [int(uid) for uid in _json_list(_row_value(row, "winners", []))]
        original_count = int(_row_value(row, "winner_count", 1))
        # Respect requested reroll count, while never exceeding the original count.
        row_dict = dict(row)
        row_dict["winner_count"] = min(int(winners), original_count)
        new_winners = await self._pick_winners(row_dict, exclude_ids=old_winners)
        if not new_winners:
            await ctx.send("No additional eligible entrants are available for a reroll.")
            return
        all_winners = old_winners + new_winners
        await db.db_execute(
            "UPDATE giveaways SET winners=$2::jsonb WHERE id=$1",
            int(giveaway_id),
            json.dumps(all_winners),
        )
        updated = await self._fetch_giveaway(giveaway_id) or row
        await self._edit_giveaway_message(updated, status="ended", winners=all_winners)
        mentions = ", ".join(f"<@{uid}>" for uid in new_winners)
        await ctx.send(f"🎲 **Rerolled!** New winner(s): {mentions}")

    @giveaway.command(name="cancel", description="Cancel an active giveaway without drawing")
    @app_commands.describe(giveaway_id="ID shown in the giveaway embed")
    async def giveaway_cancel(self, ctx: commands.Context, giveaway_id: int):
        if not await self._require_manager(ctx):
            return
        row = await self._fetch_giveaway(giveaway_id)
        if not row or int(_row_value(row, "guild_id", 0)) != ctx.guild.id:
            await ctx.send("❌ I couldn't find that giveaway in this server.")
            return
        if _row_value(row, "status", "active") != "active":
            await ctx.send("That giveaway is not active.")
            return
        await db.db_execute(
            "UPDATE giveaways SET status='cancelled' WHERE id=$1 AND status='active'",
            int(giveaway_id),
        )
        updated = await self._fetch_giveaway(giveaway_id) or row
        await self._edit_giveaway_message(updated, status="cancelled")
        await ctx.send(f"🛑 Giveaway `{giveaway_id}` has been cancelled.")

    @giveaway.command(name="entrants", description="Show entrant count and optionally list entrants")
    @app_commands.describe(giveaway_id="ID shown in the giveaway embed")
    async def giveaway_entrants(self, ctx: commands.Context, giveaway_id: int):
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return
        row = await self._fetch_giveaway(giveaway_id)
        if not row or int(_row_value(row, "guild_id", 0)) != ctx.guild.id:
            await ctx.send("❌ I couldn't find that giveaway in this server.")
            return
        entries = await db.get_giveaway_entries(giveaway_id)
        user_ids = [int(_row_value(entry, "user_id", 0)) for entry in (entries or [])]
        embed = discord.Embed(
            title=f"👥 Giveaway {giveaway_id} Entrants",
            description=f"**{len(user_ids)}** unique participant(s)",
            color=PURPLE,
        )
        if user_ids:
            # Keep the response below Discord's embed field limits.
            preview = user_ids[:50]
            embed.add_field(
                name="Participants (first 50)",
                value=", ".join(f"<@{uid}>" for uid in preview),
                inline=False,
            )
        embed.set_footer(text=BRAND)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(GiveawayCog(bot))
