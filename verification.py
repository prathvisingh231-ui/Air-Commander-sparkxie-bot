# ============================================================
# AIR COMMANDER — BUTTON VERIFICATION
# Prefix commands + slash commands, persistent button, JSON config
# ============================================================

import json
import re
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

CONFIG_PATH = Path("data/verification_config.json")
VERIFY_CUSTOM_ID = "aircommander:verification:verify"


def _load_config():
    try:
        if CONFIG_PATH.exists():
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError) as exc:
        print(f"⚠️ Verification config load failed: {type(exc).__name__}: {exc}", flush=True)
    return {}


_CONFIG = _load_config()


def _save_config():
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        temp = CONFIG_PATH.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(_CONFIG, handle, ensure_ascii=False, indent=2)
        temp.replace(CONFIG_PATH)
        return True
    except (OSError, TypeError, ValueError) as exc:
        print(f"⚠️ Verification config save failed: {type(exc).__name__}: {exc}", flush=True)
        return False


def _guild_config(guild_id: int):
    return _CONFIG.get(str(guild_id), {})


def _embed_for(guild: discord.Guild, config: dict):
    color_text = str(config.get("color", "#5865F2")).strip().lstrip("#")
    try:
        color = int(color_text, 16)
        if len(color_text) != 6:
            raise ValueError
    except (TypeError, ValueError):
        color = 0x5865F2

    embed = discord.Embed(
        title=str(config.get("title", "✈️ Verify to access the server"))[:256],
        description=str(config.get(
            "description",
            "Welcome! Click the button below to verify your account and unlock the server."
        ))[:4000],
        color=color,
    )
    footer = str(config.get("footer", "Air Commander • Verification"))[:2048]
    if footer:
        embed.set_footer(text=footer)
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    return embed


class VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(VerificationButton())


class VerificationButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="✅ Verify",
            style=discord.ButtonStyle.success,
            custom_id=VERIFY_CUSTOM_ID,
        )

    async def callback(self, interaction: discord.Interaction):
        guild = interaction.guild
        member = interaction.user
        if guild is None or not isinstance(member, discord.Member):
            return await interaction.response.send_message(
                "❌ Verification only works inside a server.", ephemeral=True
            )

        config = _guild_config(guild.id)
        role_id = config.get("role_id")
        if not config.get("enabled") or not role_id:
            return await interaction.response.send_message(
                "⚠️ Verification is not configured yet. Please contact a server admin.",
                ephemeral=True,
            )

        role = guild.get_role(int(role_id))
        if role is None:
            return await interaction.response.send_message(
                "⚠️ The verification role no longer exists. Please contact a server admin.",
                ephemeral=True,
            )

        if role in member.roles:
            return await interaction.response.send_message(
                "✅ You're already verified!", ephemeral=True
            )

        bot_member = guild.me
        if bot_member is None or not bot_member.guild_permissions.manage_roles:
            return await interaction.response.send_message(
                "❌ I need the **Manage Roles** permission to verify members.",
                ephemeral=True,
            )
        if role.is_default() or role.managed or role >= bot_member.top_role:
            return await interaction.response.send_message(
                "❌ I can't assign that role. Move my bot role above the verification role.",
                ephemeral=True,
            )

        try:
            await member.add_roles(role, reason="Air Commander button verification")
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I don't have permission to assign the verification role. Check role hierarchy.",
                ephemeral=True,
            )
        except discord.HTTPException:
            return await interaction.response.send_message(
                "❌ Discord couldn't assign the role. Please try again later.",
                ephemeral=True,
            )

        await interaction.response.send_message(
            f"🎉 Verification complete! You now have {role.mention}.",
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


def _parse_color(value: str):
    value = value.strip().lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", value):
        return None
    return "#" + value.upper()


def setup(bot: commands.Bot):
    # Register persistent button after each bot startup.
    if not getattr(bot, "_air_verification_view_registered", False):
        bot.add_view(VerificationView())
        bot._air_verification_view_registered = True

    verify_group = app_commands.Group(
        name="verify",
        description="Set up and customize the server verification panel",
    )

    @verify_group.command(name="setup", description="Configure and post the verification panel")
    @app_commands.describe(
        channel="Channel where the verification panel will be posted",
        role="Role members receive after clicking Verify",
        title="Verification embed title",
        description="Verification embed description",
        color="Embed color as a hex value, e.g. #5865F2",
        footer="Embed footer text",
        button_text="Text displayed on the Verify button",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_setup(
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        role: discord.Role,
        title: str = "✈️ Verify to access the server",
        description: str = "Welcome! Click the button below to verify your account and unlock the server.",
        color: str = "#5865F2",
        footer: str = "Air Commander • Verification",
        button_text: str = "✅ Verify",
    ):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("❌ Use this command inside a server.", ephemeral=True)
        bot_member = guild.me
        if role.is_default() or role.managed or (bot_member and role >= bot_member.top_role):
            return await interaction.response.send_message(
                "❌ Choose a normal role below my bot's highest role.", ephemeral=True
            )
        parsed_color = _parse_color(color)
        if parsed_color is None:
            return await interaction.response.send_message("❌ Color must be a hex value such as #5865F2.", ephemeral=True)
        if not button_text.strip() or len(button_text) > 80:
            return await interaction.response.send_message("❌ Button text must be 1–80 characters.", ephemeral=True)
        if not title.strip() or len(title) > 256 or not description.strip() or len(description) > 4000:
            return await interaction.response.send_message("❌ Title/description is empty or too long.", ephemeral=True)

        cfg = {
            "enabled": True,
            "channel_id": channel.id,
            "role_id": role.id,
            "title": title.strip(),
            "description": description.strip(),
            "color": parsed_color,
            "footer": footer[:2048],
            "button_text": button_text.strip(),
        }
        _CONFIG[str(guild.id)] = cfg
        if not _save_config():
            return await interaction.response.send_message(
                "⚠️ Config was changed in memory but couldn't be saved to disk. Check hosting file permissions.",
                ephemeral=True,
            )

        view = VerificationView()
        view.children[0].label = cfg["button_text"]
        try:
            message = await channel.send(embed=_embed_for(guild, cfg), view=view)
            cfg["panel_message_id"] = message.id
            _save_config()
        except discord.Forbidden:
            return await interaction.response.send_message(
                "❌ I need View Channel and Send Messages permissions in the target channel.", ephemeral=True
            )
        except discord.HTTPException:
            return await interaction.response.send_message("❌ Discord couldn't post the verification panel.", ephemeral=True)

        await interaction.response.send_message(
            f"✅ Verification is set up in {channel.mention}. Members receive {role.mention} after clicking the button.",
            ephemeral=True,
        )

    @verify_group.command(name="customize", description="Customize the saved verification embed")
    @app_commands.describe(
        title="New embed title",
        description="New embed description",
        color="New hex color, e.g. #5865F2",
        footer="New footer text",
        button_text="New button label",
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_customize(
        interaction: discord.Interaction,
        title: str | None = None,
        description: str | None = None,
        color: str | None = None,
        footer: str | None = None,
        button_text: str | None = None,
    ):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("❌ Use this command inside a server.", ephemeral=True)
        cfg = _guild_config(guild.id)
        if not cfg.get("enabled") or not cfg.get("channel_id"):
            return await interaction.response.send_message("⚠️ Run /verify setup first.", ephemeral=True)

        if title is not None:
            if not title.strip() or len(title) > 256:
                return await interaction.response.send_message("❌ Title must be 1–256 characters.", ephemeral=True)
            cfg["title"] = title.strip()
        if description is not None:
            if not description.strip() or len(description) > 4000:
                return await interaction.response.send_message("❌ Description must be 1–4000 characters.", ephemeral=True)
            cfg["description"] = description.strip()
        if color is not None:
            parsed = _parse_color(color)
            if parsed is None:
                return await interaction.response.send_message("❌ Color must be a hex value such as #5865F2.", ephemeral=True)
            cfg["color"] = parsed
        if footer is not None:
            cfg["footer"] = footer[:2048]
        if button_text is not None:
            if not button_text.strip() or len(button_text) > 80:
                return await interaction.response.send_message("❌ Button text must be 1–80 characters.", ephemeral=True)
            cfg["button_text"] = button_text.strip()

        _CONFIG[str(guild.id)] = cfg
        if not _save_config():
            return await interaction.response.send_message("❌ Couldn't save verification settings.", ephemeral=True)

        channel = guild.get_channel(int(cfg["channel_id"]))
        if isinstance(channel, discord.TextChannel):
            message_id = cfg.get("panel_message_id")
            try:
                panel = await channel.fetch_message(int(message_id)) if message_id else None
                if panel:
                    view = VerificationView()
                    view.children[0].label = cfg.get("button_text", "✅ Verify")
                    await panel.edit(embed=_embed_for(guild, cfg), view=view)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
                pass

        await interaction.response.send_message("✅ Verification panel settings updated.", ephemeral=True)

    @verify_group.command(name="post", description="Post the configured verification panel again")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_post(interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("❌ Use this command inside a server.", ephemeral=True)
        cfg = _guild_config(guild.id)
        channel = guild.get_channel(int(cfg.get("channel_id", 0)))
        if not cfg.get("enabled") or not isinstance(channel, discord.TextChannel):
            return await interaction.response.send_message("⚠️ Run /verify setup first.", ephemeral=True)
        view = VerificationView()
        view.children[0].label = cfg.get("button_text", "✅ Verify")
        try:
            panel = await channel.send(embed=_embed_for(guild, cfg), view=view)
            cfg["panel_message_id"] = panel.id
            _save_config()
        except discord.HTTPException:
            return await interaction.response.send_message("❌ Couldn't post the panel. Check channel permissions.", ephemeral=True)
        await interaction.response.send_message(f"✅ Verification panel posted in {channel.mention}.", ephemeral=True)

    @verify_group.command(name="config", description="Show current verification settings")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_config(interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("❌ Use this command inside a server.", ephemeral=True)
        cfg = _guild_config(guild.id)
        if not cfg:
            return await interaction.response.send_message("⚠️ Verification is not configured.", ephemeral=True)
        role = guild.get_role(int(cfg.get("role_id", 0)))
        channel = guild.get_channel(int(cfg.get("channel_id", 0)))
        embed = discord.Embed(title="✈️ Verification Settings", color=0x5865F2)
        embed.add_field(name="Status", value="Enabled" if cfg.get("enabled") else "Disabled", inline=True)
        embed.add_field(name="Channel", value=channel.mention if isinstance(channel, discord.TextChannel) else "Not found", inline=True)
        embed.add_field(name="Verified role", value=role.mention if role else "Not found", inline=True)
        embed.add_field(name="Title", value=cfg.get("title", "—")[:256], inline=False)
        embed.add_field(name="Button", value=cfg.get("button_text", "✅ Verify"), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @verify_group.command(name="disable", description="Disable button verification")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verify_disable(interaction: discord.Interaction):
        guild = interaction.guild
        if guild is None:
            return await interaction.response.send_message("❌ Use this command inside a server.", ephemeral=True)
        cfg = _guild_config(guild.id)
        cfg["enabled"] = False
        _CONFIG[str(guild.id)] = cfg
        if not _save_config():
            return await interaction.response.send_message("❌ Couldn't save verification settings.", ephemeral=True)
        await interaction.response.send_message("✅ Verification disabled. Existing panels will no longer grant roles.", ephemeral=True)

    bot.tree.add_command(verify_group)

    @commands.group(name="verify", invoke_without_command=True)
    @commands.guild_only()
    async def verify_prefix(ctx, *, action: str = ""):
        if not action:
            return await ctx.send(
                "✈️ **Verification commands**\n"
                "`,verify setup #channel @role` — create a panel\n"
                "`,verify customize title|description|color|footer|button text` — customize\n"
                "`,verify post` — post the panel again\n"
                "`,verify config` — view settings\n"
                "`,verify disable` — disable verification"
            )
        await ctx.send("Use a subcommand, e.g. `,verify setup #verify @Verified`.")

    @verify_prefix.command(name="setup")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_prefix_setup(ctx, channel: discord.TextChannel, role: discord.Role):
        guild = ctx.guild
        if guild is None:
            return
        bot_member = guild.me
        if role.is_default() or role.managed or (bot_member and role >= bot_member.top_role):
            return await ctx.send("❌ Choose a normal role below my bot's highest role.")
        cfg = _guild_config(guild.id)
        cfg.update({
            "enabled": True,
            "channel_id": channel.id,
            "role_id": role.id,
            "title": cfg.get("title", "✈️ Verify to access the server"),
            "description": cfg.get("description", "Welcome! Click the button below to verify your account and unlock the server."),
            "color": cfg.get("color", "#5865F2"),
            "footer": cfg.get("footer", "Air Commander • Verification"),
            "button_text": cfg.get("button_text", "✅ Verify"),
        })
        _CONFIG[str(guild.id)] = cfg
        if not _save_config():
            return await ctx.send("❌ Couldn't save verification settings.")
        view = VerificationView()
        view.children[0].label = cfg["button_text"]
        try:
            panel = await channel.send(embed=_embed_for(guild, cfg), view=view)
            cfg["panel_message_id"] = panel.id
            _save_config()
        except discord.HTTPException:
            return await ctx.send("❌ Couldn't post the panel. Check my channel permissions.")
        await ctx.send(f"✅ Verification set up in {channel.mention}; button grants {role.mention}.")

    @verify_prefix.command(name="customize")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_prefix_customize(ctx, *, settings: str):
        guild = ctx.guild
        if guild is None:
            return
        parts = settings.split("|", 1)
        if len(parts) != 2:
            return await ctx.send("Use: `,verify customize title|Your new title` (or description|..., color|#5865F2, footer|..., button|...)")
        key, value = parts[0].strip().lower(), parts[1].strip()
        cfg = _guild_config(guild.id)
        aliases = {"button text": "button_text", "button": "button_text"}
        key = aliases.get(key, key)
        limits = {"title": 256, "description": 4000, "color": 7, "footer": 2048, "button_text": 80}
        if key not in limits:
            return await ctx.send("❌ Fields: title, description, color, footer, button.")
        if not value or len(value) > limits[key]:
            return await ctx.send(f"❌ Value must be 1–{limits[key]} characters.")
        if key == "color":
            value = _parse_color(value)
            if value is None:
                return await ctx.send("❌ Use a hex color such as #5865F2.")
        cfg[key] = value
        _CONFIG[str(guild.id)] = cfg
        if not _save_config():
            return await ctx.send("❌ Couldn't save verification settings.")
        channel = guild.get_channel(int(cfg.get("channel_id", 0)))
        try:
            message_id = cfg.get("panel_message_id")
            panel = await channel.fetch_message(int(message_id)) if isinstance(channel, discord.TextChannel) and message_id else None
            if panel:
                view = VerificationView()
                view.children[0].label = cfg.get("button_text", "✅ Verify")
                await panel.edit(embed=_embed_for(guild, cfg), view=view)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, ValueError, TypeError):
            pass
        await ctx.send("✅ Verification panel customization saved.")

    @verify_prefix.command(name="post")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_prefix_post(ctx):
        guild = ctx.guild
        if guild is None:
            return
        cfg = _guild_config(guild.id)
        channel = guild.get_channel(int(cfg.get("channel_id", 0)))
        if not cfg.get("enabled") or not isinstance(channel, discord.TextChannel):
            return await ctx.send("⚠️ Run `,verify setup #channel @role` first.")
        view = VerificationView()
        view.children[0].label = cfg.get("button_text", "✅ Verify")
        try:
            panel = await channel.send(embed=_embed_for(guild, cfg), view=view)
            cfg["panel_message_id"] = panel.id
            _save_config()
        except discord.HTTPException:
            return await ctx.send("❌ Couldn't post the panel.")
        await ctx.send(f"✅ Panel posted in {channel.mention}.")

    @verify_prefix.command(name="config")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_prefix_config(ctx):
        guild = ctx.guild
        if guild is None:
            return
        cfg = _guild_config(guild.id)
        if not cfg:
            return await ctx.send("⚠️ Verification is not configured.")
        role = guild.get_role(int(cfg.get("role_id", 0)))
        channel = guild.get_channel(int(cfg.get("channel_id", 0)))
        await ctx.send(
            f"**Verification config**\n"
            f"Status: {'Enabled' if cfg.get('enabled') else 'Disabled'}\n"
            f"Channel: {channel.mention if isinstance(channel, discord.TextChannel) else 'Not found'}\n"
            f"Role: {role.mention if role else 'Not found'}\n"
            f"Title: {cfg.get('title', '—')}\n"
            f"Button: {cfg.get('button_text', '✅ Verify')}"
        )

    @verify_prefix.command(name="disable")
    @commands.has_guild_permissions(manage_guild=True)
    async def verify_prefix_disable(ctx):
        guild = ctx.guild
        if guild is None:
            return
        cfg = _guild_config(guild.id)
        cfg["enabled"] = False
        _CONFIG[str(guild.id)] = cfg
        if not _save_config():
            return await ctx.send("❌ Couldn't save verification settings.")
        await ctx.send("✅ Verification disabled.")

    bot.add_command(verify_prefix)

    @verify_prefix.error
    async def verify_prefix_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ You need **Manage Server** permission for verification settings.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Missing argument. Use `,verify` to see the command guide.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Couldn't recognize that channel/role. Example: `,verify setup #verify @Verified`.")
        else:
            print(f"Verification prefix command error: {type(error).__name__}: {error}", flush=True)
            await ctx.send("❌ Verification command failed. Check the bot logs.")
